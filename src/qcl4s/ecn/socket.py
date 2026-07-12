from __future__ import annotations

import socket as std_socket
import struct
from dataclasses import dataclass
from typing import Any, Optional

from .codepoint import ECNCodepoint, apply_ecn, parse_ecn


class ECNSocketError(RuntimeError):
    pass


@dataclass
class ReceivedDatagram:
    data: bytes
    address: Any
    ecn: Optional[ECNCodepoint]
    flags: int


def set_outgoing_ecn(sock: std_socket.socket, codepoint: ECNCodepoint) -> None:
    level, option = _traffic_class_option(sock.family)
    current = _get_socket_traffic_class(sock, level, option)
    sock.setsockopt(level, option, apply_ecn(current, codepoint))


def enable_ecn_receiving(sock: std_socket.socket) -> None:
    level, option = _receive_traffic_class_option(sock.family)
    sock.setsockopt(level, option, 1)


def recvmsg_with_ecn(
    sock: std_socket.socket,
    bufsize: int = 65_535,
) -> ReceivedDatagram:
    if not hasattr(sock, "recvmsg"):
        raise ECNSocketError("recvmsg is not available on this platform")

    data, ancillary, flags, address = sock.recvmsg(bufsize, _ancillary_buffer_size())
    return ReceivedDatagram(
        data=data,
        address=address,
        ecn=extract_ecn_from_ancillary(ancillary),
        flags=flags,
    )


def extract_ecn_from_ancillary(
    ancillary: list[tuple[int, int, bytes]],
) -> Optional[ECNCodepoint]:
    for level, option, value in ancillary:
        if level == std_socket.IPPROTO_IP and option == getattr(
            std_socket, "IP_TOS", None
        ):
            return parse_ecn(_decode_cmsg_int(value))
        if level == std_socket.IPPROTO_IPV6 and option == getattr(
            std_socket, "IPV6_TCLASS", None
        ):
            return parse_ecn(_decode_cmsg_int(value))
    return None


def _traffic_class_option(family: std_socket.AddressFamily) -> tuple[int, int]:
    if family == std_socket.AF_INET:
        option = getattr(std_socket, "IP_TOS", None)
        if option is not None:
            return std_socket.IPPROTO_IP, option
    if family == std_socket.AF_INET6:
        option = getattr(std_socket, "IPV6_TCLASS", None)
        if option is not None:
            return std_socket.IPPROTO_IPV6, option
    raise ECNSocketError(f"unsupported socket family for outgoing ECN: {family!r}")


def _receive_traffic_class_option(family: std_socket.AddressFamily) -> tuple[int, int]:
    if family == std_socket.AF_INET:
        option = getattr(std_socket, "IP_RECVTOS", None)
        if option is not None:
            return std_socket.IPPROTO_IP, option
    if family == std_socket.AF_INET6:
        option = getattr(std_socket, "IPV6_RECVTCLASS", None)
        if option is not None:
            return std_socket.IPPROTO_IPV6, option
    raise ECNSocketError(f"unsupported socket family for receiving ECN: {family!r}")


def _get_socket_traffic_class(
    sock: std_socket.socket,
    level: int,
    option: int,
) -> int:
    try:
        return int(sock.getsockopt(level, option))
    except OSError:
        return 0


def _ancillary_buffer_size() -> int:
    if hasattr(std_socket, "CMSG_SPACE"):
        return std_socket.CMSG_SPACE(struct.calcsize("i")) * 4
    return 1024


def _decode_cmsg_int(value: bytes) -> int:
    int_size = struct.calcsize("i")
    if len(value) >= int_size:
        return struct.unpack("i", value[:int_size])[0]
    if value:
        return value[0]
    return 0
