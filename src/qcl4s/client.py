from __future__ import annotations

import argparse
import asyncio
import ssl
import time
from pathlib import Path
from typing import Optional

from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

from .constants import ALPN_PROTOCOLS, DEFAULT_HOST, DEFAULT_PORT, DEFAULT_TRANSFER_BYTES
from .metrics import MetricsRecorder, TransferClock, snapshot_transport
from .protocol import mbps, receive_all


async def measure_ping(protocol) -> float:
    started_at = time.perf_counter()
    await protocol.ping()
    return (time.perf_counter() - started_at) * 1000


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
        ping_ms = await measure_ping(protocol)
        reader, writer = await protocol.create_stream()
        stream_id = writer.get_extra_info("stream_id")
        metrics_path: Optional[Path] = Path(args.metrics_file) if args.metrics_file else None
        clock = TransferClock()
        writer.write(f"GET {args.bytes}\n".encode("ascii"))
        await writer.drain()

        if metrics_path is None:
            received, elapsed = await receive_all(reader)
        else:
            with MetricsRecorder(metrics_path) as recorder:

                def record(received_bytes: int) -> None:
                    recorder.write(
                        snapshot_transport(
                            protocol,
                            clock=clock,
                            role="client",
                            direction="receive",
                            stream_id=stream_id,
                            bytes_transferred=received_bytes,
                        )
                    )

                record(0)
                received, elapsed = await receive_all(reader, on_progress=record)

        writer.close()

    print(
        "received={received} bytes elapsed={elapsed:.3f}s throughput={throughput:.2f}Mbps ping={ping:.2f}ms cc={cc}".format(
            received=received,
            elapsed=elapsed,
            throughput=mbps(received, elapsed),
            ping=ping_ms,
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
        "--metrics-file",
        help="write receiver-side transfer metrics to a CSV file",
    )
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
