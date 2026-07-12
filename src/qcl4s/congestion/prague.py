from __future__ import annotations

from typing import Any

from aioquic.quic.congestion.base import register_congestion_control
from aioquic.quic.congestion.reno import RenoCongestionControl

from ..ecn import ECNFeedbackState


class PragueCongestionControl(RenoCongestionControl):
    """
    Experimental Prague profile placeholder.

    This currently uses Reno's loss response while the ECN/CE feedback path is
    being wired into aioquic. It exists so `--cc prague` can select the L4S
    transport profile and automatically mark packets as ECT(1).
    """

    def __init__(self, *, max_datagram_size: int) -> None:
        super().__init__(max_datagram_size=max_datagram_size)
        self.ecn_state = ECNFeedbackState()
        self.prague_alpha = 0.0
        self.prague_ce_fraction = 0.0

    def on_ecn_feedback(self, *, ect1: int, ce: int) -> None:
        sample = self.ecn_state.update(ect1=ect1, ce=ce)
        self.prague_ce_fraction = sample.ce_fraction
        self.prague_alpha = (7 / 8 * self.prague_alpha) + (
            1 / 8 * sample.ce_fraction
        )

    def get_log_data(self) -> dict[str, Any]:
        data = super().get_log_data()
        data.update(
            {
                "prague_alpha": self.prague_alpha,
                "prague_ce_fraction": self.prague_ce_fraction,
                "prague_total_ect1": self.ecn_state.total_ect1,
                "prague_total_ce": self.ecn_state.total_ce,
            }
        )
        return data


register_congestion_control("prague", PragueCongestionControl)
