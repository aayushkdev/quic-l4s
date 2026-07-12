from __future__ import annotations

import argparse
import asyncio
import ssl

from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

from .constants import ALPN_PROTOCOLS, DEFAULT_HOST, DEFAULT_PORT, DEFAULT_TRANSFER_BYTES
from .protocol import mbps, receive_all


async def run_client(args: argparse.Namespace) -> None:
    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=ALPN_PROTOCOLS,
        congestion_control_algorithm=args.cc,
    )
    if args.insecure:
        configuration.verify_mode = ssl.CERT_NONE

    async with connect(
        args.host,
        args.port,
        configuration=configuration,
    ) as protocol:
        await protocol.ping()
        reader, writer = await protocol.create_stream()
        writer.write(f"GET {args.bytes}\n".encode("ascii"))
        await writer.drain()

        received, elapsed = await receive_all(reader)
        writer.close()

    print(
        "received={received} bytes elapsed={elapsed:.3f}s throughput={throughput:.2f}Mbps cc={cc}".format(
            received=received,
            elapsed=elapsed,
            throughput=mbps(received, elapsed),
            cc=args.cc,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the QCL4S baseline QUIC client.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--bytes", type=int, default=DEFAULT_TRANSFER_BYTES)
    parser.add_argument("--cc", choices=["reno", "cubic"], default="reno")
    parser.add_argument(
        "--insecure",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="skip certificate verification for the local self-signed test certificate",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run_client(args))
