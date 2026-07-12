from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import transfer
from .constants import (
    DEFAULT_CERT_PATH,
    DEFAULT_HOST,
    DEFAULT_KEY_PATH,
    DEFAULT_RUNS_DIR,
    DEFAULT_TRANSFER_BYTES,
)
from .server import create_server


async def run_benchmark(args: argparse.Namespace) -> None:
    run_id = args.name or default_run_id(args.cc)
    run_dir = Path(args.runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    server_metrics = run_dir / "server-metrics.csv"
    client_metrics = run_dir / "client-metrics.csv"
    summary_path = run_dir / "summary.json"

    cert_path = Path(args.cert)
    key_path = Path(args.key)
    server = await create_server(
        host=args.host,
        port=args.port,
        cert_path=cert_path,
        key_path=key_path,
        cc=args.cc,
        metrics_path=server_metrics,
        generate_cert=True,
    )
    actual_port = bound_port(server, args.port)

    started_at = datetime.now(UTC)
    try:
        result = await transfer(
            host=args.host,
            port=actual_port,
            byte_count=args.bytes,
            cc=args.cc,
            metrics_path=client_metrics,
            insecure=True,
        )
    finally:
        server.close()

    summary: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "host": args.host,
        "port": actual_port,
        "requested_bytes": args.bytes,
        "received_bytes": result.received_bytes,
        "elapsed_s": result.elapsed_s,
        "throughput_mbps": result.throughput_mbps,
        "ping_ms": result.ping_ms,
        "congestion_control": args.cc,
        "server_metrics": str(server_metrics),
        "client_metrics": str(client_metrics),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print(f"run={run_id}")
    print(f"summary={summary_path}")
    print(f"server_metrics={server_metrics}")
    print(f"client_metrics={client_metrics}")
    print(
        "received={received} bytes elapsed={elapsed:.3f}s throughput={throughput:.2f}Mbps ping={ping:.2f}ms cc={cc}".format(
            received=result.received_bytes,
            elapsed=result.elapsed_s,
            throughput=result.throughput_mbps,
            ping=result.ping_ms,
            cc=args.cc,
        )
    )


def default_run_id(cc: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{cc}"


def bound_port(server: Any, fallback: int) -> int:
    transport = getattr(server, "_transport", None)
    if transport is None:
        return fallback

    socket_name = transport.get_extra_info("sockname")
    if isinstance(socket_name, tuple) and len(socket_name) >= 2:
        return int(socket_name[1])
    return fallback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an automated QCL4S benchmark.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="server port to bind; 0 picks an available local port",
    )
    parser.add_argument("--bytes", type=int, default=DEFAULT_TRANSFER_BYTES)
    parser.add_argument("--cc", choices=["reno", "cubic"], default="reno")
    parser.add_argument("--runs-dir", default=DEFAULT_RUNS_DIR)
    parser.add_argument("--name", help="run directory name; defaults to timestamp-cc")
    parser.add_argument("--cert", default=DEFAULT_CERT_PATH)
    parser.add_argument("--key", default=DEFAULT_KEY_PATH)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run_benchmark(args))
