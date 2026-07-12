from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Optional, cast

from aioquic.asyncio.protocol import QuicConnectionProtocol, QuicStreamHandler
from aioquic.asyncio.server import QuicServer
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection, QuicTokenHandler
from aioquic.tls import SessionTicketHandler

from .ecn import ECNCodepoint, enable_ecn_receiving, set_outgoing_ecn


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

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: create_protocol(connection, stream_handler=stream_handler),
        sock=sock,
    )
    protocol = cast(QuicConnectionProtocol, protocol)
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

    _, protocol = await loop.create_datagram_endpoint(
        lambda: QuicServer(
            configuration=configuration,
            create_protocol=create_protocol,
            retry=retry,
            stream_handler=stream_handler,
        ),
        sock=sock,
    )
    return cast(QuicServer, protocol)


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
