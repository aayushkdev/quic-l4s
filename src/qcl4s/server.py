from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Optional

from aioquic.asyncio.server import QuicServer
from aioquic.quic.configuration import QuicConfiguration

from .certs import ensure_self_signed_cert
from .congestion import CONGESTION_CONTROL_CHOICES, profile_for_cc
from .constants import ALPN_PROTOCOLS, DEFAULT_CERT_PATH, DEFAULT_HOST, DEFAULT_KEY_PATH, DEFAULT_PORT
from .metrics import MetricsRecorder, TransferClock, snapshot_transport, stream_protocol
from .protocol import ProtocolError, mbps, read_command, send_bytes
from .quic import serve_quic


async def handle_stream(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    metrics_path: Optional[Path],
) -> None:
    stream_id = writer.get_extra_info("stream_id")
    try:
        _, byte_count = await read_command(reader)
        print(f"stream={stream_id} sending bytes={byte_count}")
        protocol = stream_protocol(writer)
        clock = TransferClock()

        if metrics_path is None:
            await send_bytes(writer, byte_count)
        else:
            with MetricsRecorder(metrics_path) as recorder:

                def record(sent: int) -> None:
                    recorder.write(
                        snapshot_transport(
                            protocol,
                            clock=clock,
                            role="server",
                            direction="send",
                            stream_id=stream_id,
                            bytes_transferred=sent,
                        )
                    )

                record(0)
                await send_bytes(writer, byte_count, on_progress=record)

        elapsed = clock.elapsed_ms() / 1000
        print(
            "stream={stream_id} complete bytes={bytes} elapsed={elapsed:.3f}s throughput={throughput:.2f}Mbps".format(
                stream_id=stream_id,
                bytes=byte_count,
                elapsed=elapsed,
                throughput=mbps(byte_count, elapsed),
            )
        )
    except ProtocolError as exc:
        print(f"stream={stream_id} protocol error: {exc}")
        writer.close()


async def create_server(
    *,
    host: str,
    port: int,
    cert_path: Path,
    key_path: Path,
    cc: str,
    metrics_path: Optional[Path],
    generate_cert: bool,
) -> QuicServer:
    if generate_cert:
        ensure_self_signed_cert(cert_path, key_path, host)

    profile = profile_for_cc(cc)
    configuration = QuicConfiguration(
        is_client=False,
        alpn_protocols=ALPN_PROTOCOLS,
        congestion_control_algorithm=profile.congestion_control,
    )
    configuration.load_cert_chain(cert_path, key_path)

    return await serve_quic(
        host,
        port,
        configuration=configuration,
        ecn=profile.ecn,
        stream_handler=lambda reader, writer: asyncio.create_task(
            handle_stream(reader, writer, metrics_path)
        ),
    )


async def run_server(args: argparse.Namespace) -> None:
    cert_path = Path(args.cert)
    key_path = Path(args.key)
    server = await create_server(
        host=args.host,
        port=args.port,
        cert_path=cert_path,
        key_path=key_path,
        cc=args.cc,
        metrics_path=Path(args.metrics_file) if args.metrics_file else None,
        generate_cert=args.generate_cert,
    )
    profile = profile_for_cc(args.cc)
    print(
        f"qcl4s server listening on {args.host}:{args.port} "
        f"cc={args.cc} ecn={profile.ecn_label}"
    )
    print(f"certificate={cert_path} key={key_path}")

    try:
        await asyncio.Event().wait()
    finally:
        server.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the QCL4S baseline QUIC server.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--cert", default=DEFAULT_CERT_PATH)
    parser.add_argument("--key", default=DEFAULT_KEY_PATH)
    parser.add_argument("--cc", choices=CONGESTION_CONTROL_CHOICES, default="reno")
    parser.add_argument(
        "--metrics-file",
        help="write sender-side transfer metrics to a CSV file",
    )
    parser.add_argument(
        "--generate-cert",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="generate a self-signed local certificate when cert/key are missing",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(run_server(args))
    except KeyboardInterrupt:
        pass
