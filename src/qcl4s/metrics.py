from __future__ import annotations

import csv
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Optional


@dataclass
class TransportSnapshot:
    elapsed_ms: float
    role: str
    direction: str
    stream_id: int
    bytes_transferred: int
    congestion_window: Optional[int]
    bytes_in_flight: Optional[int]
    latest_rtt_ms: Optional[float]
    smoothed_rtt_ms: Optional[float]
    min_rtt_ms: Optional[float]
    ecn_profile: str
    ecn_sent_datagrams: Optional[int]
    ecn_received_datagrams: Optional[int]
    ecn_received_not_ect: Optional[int]
    ecn_received_ect0: Optional[int]
    ecn_received_ect1: Optional[int]
    ecn_received_ce: Optional[int]
    prague_alpha: Optional[float]
    prague_ce_fraction: Optional[float]
    prague_total_ect1: Optional[int]
    prague_total_ce: Optional[int]


class MetricsRecorder:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._file = None
        self._writer: Optional[csv.DictWriter] = None

    def __enter__(self) -> MetricsRecorder:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self._path.open("w", newline="")
        self._writer = csv.DictWriter(
            self._file,
            fieldnames=[field.name for field in fields(TransportSnapshot)],
        )
        self._writer.writeheader()
        return self

    def __exit__(self, *args: object) -> None:
        if self._file is not None:
            self._file.close()

    def write(self, snapshot: TransportSnapshot) -> None:
        if self._writer is None:
            raise RuntimeError("metrics recorder is not open")
        self._writer.writerow(asdict(snapshot))


class TransferClock:
    def __init__(self) -> None:
        self._started_at = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._started_at) * 1000


def snapshot_transport(
    protocol: Any,
    *,
    clock: TransferClock,
    role: str,
    direction: str,
    stream_id: int,
    bytes_transferred: int,
) -> TransportSnapshot:
    recovery = getattr(getattr(protocol, "_quic", None), "_loss", None)

    latest_rtt = getattr(recovery, "_rtt_latest", None)
    smoothed_rtt = getattr(recovery, "_rtt_smoothed", None)
    min_rtt = getattr(recovery, "_rtt_min", None)
    if min_rtt == float("inf"):
        min_rtt = None
    ecn = _ecn_snapshot(protocol)
    cc = getattr(recovery, "_cc", None)

    return TransportSnapshot(
        elapsed_ms=clock.elapsed_ms(),
        role=role,
        direction=direction,
        stream_id=stream_id,
        bytes_transferred=bytes_transferred,
        congestion_window=getattr(recovery, "congestion_window", None),
        bytes_in_flight=getattr(recovery, "bytes_in_flight", None),
        latest_rtt_ms=_seconds_to_ms(latest_rtt),
        smoothed_rtt_ms=_seconds_to_ms(smoothed_rtt),
        min_rtt_ms=_seconds_to_ms(min_rtt),
        ecn_profile=getattr(ecn, "profile", "unknown"),
        ecn_sent_datagrams=getattr(ecn, "sent_datagrams", None),
        ecn_received_datagrams=getattr(ecn, "received_datagrams", None),
        ecn_received_not_ect=getattr(ecn, "received_not_ect", None),
        ecn_received_ect0=getattr(ecn, "received_ect0", None),
        ecn_received_ect1=getattr(ecn, "received_ect1", None),
        ecn_received_ce=getattr(ecn, "received_ce", None),
        prague_alpha=getattr(cc, "prague_alpha", None),
        prague_ce_fraction=getattr(cc, "prague_ce_fraction", None),
        prague_total_ect1=getattr(getattr(cc, "ecn_state", None), "total_ect1", None),
        prague_total_ce=getattr(getattr(cc, "ecn_state", None), "total_ce", None),
    )


def stream_protocol(writer: Any) -> Any:
    transport = getattr(writer, "_transport", None)
    return getattr(transport, "protocol", None)


def _seconds_to_ms(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 1000


def _ecn_snapshot(protocol: Any) -> Any:
    transport = getattr(protocol, "_transport", None)
    if transport is None:
        return None
    get_extra_info = getattr(transport, "get_extra_info", None)
    if get_extra_info is None:
        return None
    return get_extra_info("ecn_snapshot")
