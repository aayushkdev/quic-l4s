from __future__ import annotations

from enum import IntEnum

ECN_MASK = 0b0000_0011
DSCP_MASK = 0b1111_1100


class ECNCodepoint(IntEnum):
    NOT_ECT = 0b00
    ECT1 = 0b01
    ECT0 = 0b10
    CE = 0b11

    @property
    def label(self) -> str:
        return {
            ECNCodepoint.NOT_ECT: "Not-ECT",
            ECNCodepoint.ECT0: "ECT(0)",
            ECNCodepoint.ECT1: "ECT(1)",
            ECNCodepoint.CE: "CE",
        }[self]


def parse_ecn(traffic_class: int) -> ECNCodepoint:
    return ECNCodepoint(traffic_class & ECN_MASK)


def apply_ecn(traffic_class: int, codepoint: ECNCodepoint) -> int:
    return (traffic_class & DSCP_MASK) | int(codepoint)
