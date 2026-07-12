from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from aioquic.asyncio import serve
from aioquic.quic.configuration import QuicConfiguration

from .certs import ensure_self_signed_cert
from .constants import ALPN_PROTOCOLS, DEFAULT_CERT_PATH, DEFAULT_HOST, DEFAULT_KEY_PATH, DEFAULT_PORT
from .protocol import ProtocolError, read_command, send_bytes


async def handle_stream(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    stream_id = writer.get_extra_info("stream_id")
    try:
        _, byte_count = await read_command(reader)
        print(f"stream={stream_id} sending bytes={byte_count}")
        await send_bytes(writer, byte_count)
        print(f"stream={stream_id} complete")
    except ProtocolError as exc:
        print(f"stream={stream_id} protocol error: {exc}")
        writer.close()


async def run_server(args: argparse.Namespace) -> None:
    cert_path = Path(args.cert)
    key_path = Path(args.key)
    if args.generate_cert:
        ensure_self_signed_cert(cert_path, key_path, args.host)

    configuration = QuicConfiguration(
        is_client=False,
        alpn_protocols=ALPN_PROTOCOLS,
        congestion_control_algorithm=args.cc,
    )
    configuration.load_cert_chain(cert_path, key_path)

    server = await serve(
        args.host,
        args.port,
        configuration=configuration,
        stream_handler=lambda reader, writer: asyncio.create_task(
            handle_stream(reader, writer)
        ),
    )
    print(f"qcl4s server listening on {args.host}:{args.port} cc={args.cc}")
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
    parser.add_argument("--cc", choices=["reno", "cubic"], default="reno")
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
