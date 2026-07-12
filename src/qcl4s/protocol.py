from __future__ import annotations

import asyncio
import time

from .constants import STREAM_CHUNK_SIZE


class ProtocolError(Exception):
    pass


def payload_chunk(size: int) -> bytes:
    pattern = b"qcl4s-baseline-payload-"
    if size <= len(pattern):
        return pattern[:size]
    repeats, remainder = divmod(size, len(pattern))
    return pattern * repeats + pattern[:remainder]


async def read_command(reader: asyncio.StreamReader) -> tuple[str, int]:
    line = await reader.readline()
    if not line:
        raise ProtocolError("empty request")

    parts = line.decode("ascii").strip().split()
    if len(parts) != 2 or parts[0] != "GET":
        raise ProtocolError("expected request: GET <bytes>")

    try:
        byte_count = int(parts[1])
    except ValueError as exc:
        raise ProtocolError("byte count must be an integer") from exc

    if byte_count < 0:
        raise ProtocolError("byte count must be non-negative")
    return parts[0], byte_count


async def send_bytes(writer: asyncio.StreamWriter, byte_count: int) -> None:
    remaining = byte_count
    chunk = payload_chunk(STREAM_CHUNK_SIZE)

    while remaining > 0:
        write_size = min(remaining, STREAM_CHUNK_SIZE)
        writer.write(chunk[:write_size])
        await writer.drain()
        remaining -= write_size

    writer.write_eof()
    await writer.drain()


async def receive_all(reader: asyncio.StreamReader) -> tuple[int, float]:
    received = 0
    started_at = time.perf_counter()

    while True:
        chunk = await reader.read(STREAM_CHUNK_SIZE)
        if not chunk:
            break
        received += len(chunk)

    return received, time.perf_counter() - started_at


def mbps(byte_count: int, seconds: float) -> float:
    if seconds <= 0:
        return 0.0
    return byte_count * 8 / seconds / 1_000_000
