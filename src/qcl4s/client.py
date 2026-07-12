from __future__ import annotations

import argparse
import asyncio
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

from .constants import ALPN_PROTOCOLS, DEFAULT_HOST, DEFAULT_PORT, DEFAULT_TRANSFER_BYTES
from .metrics import MetricsRecorder, TransferClock, snapshot_transport
from .protocol import mbps, receive_all


@dataclass
class TransferResult:
    received_bytes: int
    elapsed_s: float
    throughput_mbps: float
    ping_ms: float
    congestion_control: str


async def measure_ping(protocol) -> float:
    started_at = time.perf_counter()
    await protocol.ping()
    return (time.perf_counter() - started_at) * 1000


async def transfer(
    *,
    host: str,
    port: int,
    byte_count: int,
    cc: str,
    metrics_path: Optional[Path],
    insecure: bool,
) -> TransferResult:
    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=ALPN_PROTOCOLS,
        congestion_control_algorithm=cc,
    )
    if insecure:
        configuration.verify_mode = ssl.CERT_NONE

    async with connect(
        host,
        port,
        configuration=configuration,
    ) as protocol:
        ping_ms = await measure_ping(protocol)
        reader, writer = await protocol.create_stream()
        stream_id = writer.get_extra_info("stream_id")
        clock = TransferClock()
        writer.write(f"GET {byte_count}\n".encode("ascii"))
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

    return TransferResult(
        received_bytes=received,
        elapsed_s=elapsed,
        throughput_mbps=mbps(received, elapsed),
        ping_ms=ping_ms,
        congestion_control=cc,
    )


async def run_client(args: argparse.Namespace) -> None:
    result = await transfer(
        host=args.host,
        port=args.port,
        byte_count=args.bytes,
        cc=args.cc,
        metrics_path=Path(args.metrics_file)
        if args.metrics_file
        else None,
        insecure=args.insecure,
    )

    print(
        "received={received} bytes elapsed={elapsed:.3f}s throughput={throughput:.2f}Mbps ping={ping:.2f}ms cc={cc}".format(
            received=result.received_bytes,
            elapsed=result.elapsed_s,
            throughput=result.throughput_mbps,
            ping=result.ping_ms,
            cc=result.congestion_control,
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
