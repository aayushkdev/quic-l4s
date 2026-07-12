from __future__ import annotations

from aioquic.quic.congestion.base import register_congestion_control
from aioquic.quic.congestion.reno import RenoCongestionControl


class PragueCongestionControl(RenoCongestionControl):
    """
    Experimental Prague profile placeholder.

    This currently uses Reno's loss response while the ECN/CE feedback path is
    being wired into aioquic. It exists so `--cc prague` can select the L4S
    transport profile and automatically mark packets as ECT(1).
    """


register_congestion_control("prague", PragueCongestionControl)
