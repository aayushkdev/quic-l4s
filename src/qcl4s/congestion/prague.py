from __future__ import annotations

from typing import Any

from aioquic.quic.congestion.base import K_MINIMUM_WINDOW, register_congestion_control
from aioquic.quic.congestion.reno import RenoCongestionControl

from ..ecn import ECNFeedbackState

PRAGUE_GAIN = 1 / 8
PRAGUE_MIN_REDUCTION = 1 / 16


class PragueCongestionControl(RenoCongestionControl):
    """
    Experimental Prague-style congestion control.

    This is intentionally conservative: Reno still handles normal ACK growth and
    packet loss, while ACK_ECN feedback applies a DCTCP-like CE response.
    """

    def __init__(self, *, max_datagram_size: int) -> None:
        super().__init__(max_datagram_size=max_datagram_size)
        self.ecn_state = ECNFeedbackState()
        self.prague_cwnd_reductions = 0
        self.prague_alpha = 0.0
        self.prague_ce_fraction = 0.0

    def on_ecn_feedback(self, *, ect1: int, ce: int) -> None:
        sample = self.ecn_state.update(ect1=ect1, ce=ce)
        if sample.marked_delta == 0:
            return

        self.prague_ce_fraction = sample.ce_fraction
        self.prague_alpha = (1 - PRAGUE_GAIN) * self.prague_alpha + (
            PRAGUE_GAIN * sample.ce_fraction
        )

        if sample.ce_delta > 0:
            self._reduce_window_for_ce()

    def _reduce_window_for_ce(self) -> None:
        reduction_factor = max(self.prague_alpha / 2, PRAGUE_MIN_REDUCTION)
        minimum_window = K_MINIMUM_WINDOW * self._max_datagram_size
        self.congestion_window = max(
            int(self.congestion_window * (1 - reduction_factor)),
            minimum_window,
        )
        self.ssthresh = self.congestion_window
        self.prague_cwnd_reductions += 1

    def get_log_data(self) -> dict[str, Any]:
        data = super().get_log_data()
        data.update(
            {
                "prague_alpha": self.prague_alpha,
                "prague_ce_fraction": self.prague_ce_fraction,
                "prague_cwnd_reductions": self.prague_cwnd_reductions,
                "prague_total_ect1": self.ecn_state.total_ect1,
                "prague_total_ce": self.ecn_state.total_ce,
            }
        )
        return data


register_congestion_control("prague", PragueCongestionControl)
