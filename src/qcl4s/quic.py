from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator, Callable, Optional, cast

from aioquic.asyncio.protocol import QuicConnectionProtocol, QuicStreamHandler
from aioquic.asyncio.server import QuicServer
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection, QuicTokenHandler
from aioquic.tls import SessionTicketHandler

from .ecn import (
    ECNCodepoint,
    enable_ecn_receiving,
    recvmsg_with_ecn,
    set_outgoing_ecn,
)


@dataclass
class ECNTransportSnapshot:
    profile: str
    sent_datagrams: int
    received_datagrams: int
    received_not_ect: int
    received_ect0: int
    received_ect1: int
    received_ce: int


@asynccontextmanager
async def connect_quic(
    host: str,
    port: int,
    *,
    configuration: QuicConfiguration,
    ecn: Optional[ECNCodepoint],
    create_protocol: Callable = QuicConnectionProtocol,
    session_ticket_handler: Optional[SessionTicketHandler] = None,
    stream_handler: Optional[QuicStreamHandler] = None,
    token_handler: Optional[QuicTokenHandler] = None,
    wait_connected: bool = True,
    local_port: int = 0,
) -> AsyncGenerator[QuicConnectionProtocol, None]:
    loop = asyncio.get_running_loop()

    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    family, socktype, proto, _, addr = infos[0]

    if configuration.server_name is None:
        configuration.server_name = host
    connection = QuicConnection(
        configuration=configuration,
        session_ticket_handler=session_ticket_handler,
        token_handler=token_handler,
    )

    sock = socket.socket(family, socktype, proto)
    completed = False
    try:
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        configure_ecn(sock, ecn)
        sock.bind(_local_bind_address(family, local_port))
        completed = True
    finally:
        if not completed:
            sock.close()

    protocol = create_protocol(connection, stream_handler=stream_handler)
    transport = ECNDatagramTransport(loop=loop, sock=sock, protocol=protocol, ecn=ecn)
    try:
        protocol.connect(addr, transmit=wait_connected)
        if wait_connected:
            await protocol.wait_connected()
        yield protocol
    finally:
        protocol.close()
        await protocol.wait_closed()
        transport.close()


async def serve_quic(
    host: str,
    port: int,
    *,
    configuration: QuicConfiguration,
    ecn: Optional[ECNCodepoint],
    create_protocol: Callable = QuicConnectionProtocol,
    retry: bool = False,
    stream_handler: QuicStreamHandler = None,
) -> QuicServer:
    loop = asyncio.get_running_loop()
    sock = await create_bound_udp_socket(host=host, port=port, ecn=ecn)
    protocol = QuicServer(
        configuration=configuration,
        create_protocol=create_protocol,
        retry=retry,
        stream_handler=stream_handler,
    )
    ECNDatagramTransport(loop=loop, sock=sock, protocol=protocol, ecn=ecn)
    return protocol


class ECNDatagramTransport(asyncio.DatagramTransport):
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        sock: socket.socket,
        protocol: asyncio.DatagramProtocol,
        ecn: Optional[ECNCodepoint],
    ) -> None:
        self._loop = loop
        self._sock = sock
        self._protocol = protocol
        self._ecn = ecn
        self._closing = False
        self._received_counts = {
            ECNCodepoint.NOT_ECT: 0,
            ECNCodepoint.ECT0: 0,
            ECNCodepoint.ECT1: 0,
            ECNCodepoint.CE: 0,
        }
        self._received_datagrams = 0
        self._sent_datagrams = 0

        self._sock.setblocking(False)
        self._protocol.connection_made(self)
        self._loop.add_reader(self._sock.fileno(), self._read_ready)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._loop.remove_reader(self._sock.fileno())
        self._sock.close()
        self._protocol.connection_lost(None)

    def get_extra_info(self, name: str, default=None):
        if name == "socket":
            return self._sock
        if name == "sockname":
            try:
                return self._sock.getsockname()
            except OSError:
                return default
        if name == "ecn_snapshot":
            return self.ecn_snapshot()
        return default

    def is_closing(self) -> bool:
        return self._closing

    def sendto(self, data, addr=None) -> None:
        if self._closing:
            return
        try:
            if addr is None:
                self._sock.send(data)
            else:
                self._sock.sendto(data, addr)
            self._sent_datagrams += 1
        except OSError as exc:
            self._protocol.error_received(exc)

    def ecn_snapshot(self) -> ECNTransportSnapshot:
        return ECNTransportSnapshot(
            profile=self._ecn.label if self._ecn is not None else "default",
            sent_datagrams=self._sent_datagrams,
            received_datagrams=self._received_datagrams,
            received_not_ect=self._received_counts[ECNCodepoint.NOT_ECT],
            received_ect0=self._received_counts[ECNCodepoint.ECT0],
            received_ect1=self._received_counts[ECNCodepoint.ECT1],
            received_ce=self._received_counts[ECNCodepoint.CE],
        )

    def _read_ready(self) -> None:
        while not self._closing:
            try:
                if self._ecn is None:
                    data, addr = self._sock.recvfrom(65_535)
                    observed_ecn = None
                else:
                    datagram = recvmsg_with_ecn(self._sock)
                    data = datagram.data
                    addr = datagram.address
                    observed_ecn = datagram.ecn
            except (BlockingIOError, InterruptedError):
                break
            except OSError as exc:
                self._protocol.error_received(exc)
                break

            self._received_datagrams += 1
            if observed_ecn is not None:
                self._received_counts[observed_ecn] += 1
            self._protocol.datagram_received(data, addr)


async def create_bound_udp_socket(
    *,
    host: str,
    port: int,
    ecn: Optional[ECNCodepoint],
) -> socket.socket:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(
        host,
        port,
        type=socket.SOCK_DGRAM,
        flags=socket.AI_PASSIVE,
    )
    family, socktype, proto, _, address = infos[0]
    sock = socket.socket(family, socktype, proto)
    completed = False
    try:
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        configure_ecn(sock, ecn)
        sock.bind(address)
        completed = True
        return sock
    finally:
        if not completed:
            sock.close()


def configure_ecn(sock: socket.socket, ecn: Optional[ECNCodepoint]) -> None:
    if ecn is None:
        return
    enable_ecn_receiving(sock)
    set_outgoing_ecn(sock, ecn)


def _local_bind_address(family: socket.AddressFamily, local_port: int):
    if family == socket.AF_INET:
        return ("0.0.0.0", local_port)
    if family == socket.AF_INET6:
        return ("::", local_port, 0, 0)
    raise ValueError(f"unsupported socket family: {family!r}")
