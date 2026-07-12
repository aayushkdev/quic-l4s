from __future__ import annotations

import argparse
import socket
import sys

from .ecn import ECNCodepoint, validate_udp_loopback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check local UDP ECN socket support.")
    parser.add_argument(
        "--codepoint",
        choices=["ect1", "ect0"],
        default="ect1",
        help="ECN-capable codepoint to test",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="receive timeout in seconds",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    codepoint = {
        "ect1": ECNCodepoint.ECT1,
        "ect0": ECNCodepoint.ECT0,
    }[args.codepoint]

    results = [
        validate_udp_loopback(
            family=socket.AF_INET,
            codepoint=codepoint,
            timeout=args.timeout,
        ),
        validate_udp_loopback(
            family=socket.AF_INET6,
            codepoint=codepoint,
            timeout=args.timeout,
        ),
    ]

    for result in results:
        observed = result.observed.label if result.observed is not None else "none"
        status = "supported" if result.supported else "unsupported"
        line = (
            f"{result.family}: {status} "
            f"requested={result.requested.label} observed={observed}"
        )
        if result.error:
            line += f" error={result.error}"
        print(line)

    if not all(result.supported for result in results):
        sys.exit(1)
