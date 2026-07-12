from __future__ import annotations

import socket as std_socket
from dataclasses import dataclass
from typing import Optional

from .codepoint import ECNCodepoint
from .socket import (
    ECNSocketError,
    enable_ecn_receiving,
    recvmsg_with_ecn,
    set_outgoing_ecn,
)


@dataclass
class ECNValidationResult:
    family: str
    requested: ECNCodepoint
    observed: Optional[ECNCodepoint]
    supported: bool
    error: Optional[str] = None


def validate_udp_loopback(
    *,
    family: std_socket.AddressFamily = std_socket.AF_INET,
    codepoint: ECNCodepoint = ECNCodepoint.ECT1,
    timeout: float = 1.0,
) -> ECNValidationResult:
    family_name = _family_name(family)

    try:
        receive_sock = std_socket.socket(family, std_socket.SOCK_DGRAM)
        send_sock = std_socket.socket(family, std_socket.SOCK_DGRAM)
    except OSError as exc:
        return ECNValidationResult(
            family=family_name,
            requested=codepoint,
            observed=None,
            supported=False,
            error=str(exc),
        )

    try:
        receive_sock.settimeout(timeout)
        enable_ecn_receiving(receive_sock)
        set_outgoing_ecn(send_sock, codepoint)

        receive_sock.bind(_loopback_bind_address(family))
        send_sock.sendto(b"qcl4s-ecn-check", receive_sock.getsockname())

        datagram = recvmsg_with_ecn(receive_sock)
        return ECNValidationResult(
            family=family_name,
            requested=codepoint,
            observed=datagram.ecn,
            supported=datagram.ecn == codepoint,
        )
    except (ECNSocketError, OSError) as exc:
        return ECNValidationResult(
            family=family_name,
            requested=codepoint,
            observed=None,
            supported=False,
            error=str(exc),
        )
    finally:
        receive_sock.close()
        send_sock.close()


def _loopback_bind_address(family: std_socket.AddressFamily):
    if family == std_socket.AF_INET:
        return ("127.0.0.1", 0)
    if family == std_socket.AF_INET6:
        return ("::1", 0)
    raise ECNSocketError(f"unsupported loopback family: {family!r}")


def _family_name(family: std_socket.AddressFamily) -> str:
    if family == std_socket.AF_INET:
        return "ipv4"
    if family == std_socket.AF_INET6:
        return "ipv6"
    return str(family)
