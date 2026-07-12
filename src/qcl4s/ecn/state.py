from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ECNFeedbackSample:
    ect1_delta: int
    ce_delta: int
    marked_delta: int
    ce_fraction: float


class ECNFeedbackState:
    def __init__(self) -> None:
        self.total_ect1 = 0
        self.total_ce = 0
        self.last_ect1 = 0
        self.last_ce = 0
        self.last_fraction = 0.0

    def update(self, *, ect1: int, ce: int) -> ECNFeedbackSample:
        ect1_delta = max(0, ect1 - self.last_ect1)
        ce_delta = max(0, ce - self.last_ce)
        marked_total = ect1_delta + ce_delta
        ce_fraction = ce_delta / marked_total if marked_total else 0.0

        self.total_ect1 = ect1
        self.total_ce = ce
        self.last_ect1 = ect1
        self.last_ce = ce
        self.last_fraction = ce_fraction

        return ECNFeedbackSample(
            ect1_delta=ect1_delta,
            ce_delta=ce_delta,
            marked_delta=marked_total,
            ce_fraction=ce_fraction,
        )
