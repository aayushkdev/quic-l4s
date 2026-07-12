from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..ecn import ECNCodepoint

CONGESTION_CONTROL_CHOICES = ("reno", "cubic", "prague")


@dataclass(frozen=True)
class TransportProfile:
    congestion_control: str
    ecn: Optional[ECNCodepoint]

    @property
    def ecn_label(self) -> str:
        return self.ecn.label if self.ecn is not None else "default"


def profile_for_cc(cc: str) -> TransportProfile:
    if cc == "prague":
        return TransportProfile(congestion_control=cc, ecn=ECNCodepoint.ECT1)
    if cc in {"reno", "cubic"}:
        return TransportProfile(congestion_control=cc, ecn=None)
    raise ValueError(f"unsupported congestion control: {cc}")
