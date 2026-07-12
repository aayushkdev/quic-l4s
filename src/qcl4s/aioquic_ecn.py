from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from aioquic.quic import connection as aioquic_connection
from aioquic.quic import packet as aioquic_packet
from aioquic.quic.packet import QuicFrameType

from .ecn import ECNCodepoint

_current_ecn: ContextVar[Optional[ECNCodepoint]] = ContextVar(
    "qcl4s_current_ecn",
    default=None,
)
_installed = False


def set_current_ecn(codepoint: Optional[ECNCodepoint]):
    return _current_ecn.set(codepoint)


def reset_current_ecn(token) -> None:
    _current_ecn.reset(token)


def install_ack_ecn_patch() -> None:
    global _installed
    if _installed:
        return

    original_handle_ack_frame = aioquic_connection.QuicConnection._handle_ack_frame
    original_payload_received = aioquic_connection.QuicConnection._payload_received
    original_write_ack_frame = aioquic_connection.QuicConnection._write_ack_frame

    def handle_ack_frame(self, context, frame_type, buf):
        ecn_counts = None
        if frame_type == QuicFrameType.ACK_ECN:
            start = buf.tell()
            aioquic_packet.pull_ack_frame(buf)
            ecn_counts = {
                ECNCodepoint.ECT0: buf.pull_uint_var(),
                ECNCodepoint.ECT1: buf.pull_uint_var(),
                ECNCodepoint.CE: buf.pull_uint_var(),
            }
            buf.seek(start)

        result = original_handle_ack_frame(self, context, frame_type, buf)
        if ecn_counts is not None:
            cc = getattr(getattr(self, "_loss", None), "_cc", None)
            on_ecn_feedback = getattr(cc, "on_ecn_feedback", None)
            if on_ecn_feedback is not None:
                on_ecn_feedback(
                    ect1=ecn_counts[ECNCodepoint.ECT1],
                    ce=ecn_counts[ECNCodepoint.CE],
                )
        return result

    def payload_received(self, context, plain, crypto_frame_required=False):
        result = original_payload_received(
            self,
            context,
            plain,
            crypto_frame_required=crypto_frame_required,
        )
        codepoint = _current_ecn.get()
        if codepoint is not None:
            counts = _ecn_counts(self)
            counts[codepoint] += 1
        return result

    def write_ack_frame(self, builder, space, now):
        counts = getattr(self, "_qcl4s_ecn_counts", None)
        if not counts:
            return original_write_ack_frame(self, builder, space, now)

        ack_delay = now - space.largest_received_time
        ack_delay_encoded = int(ack_delay * 1000000) >> self._local_ack_delay_exponent

        buf = builder.start_frame(
            QuicFrameType.ACK_ECN,
            capacity=aioquic_connection.ACK_FRAME_CAPACITY,
            handler=self._on_ack_delivery,
            handler_args=(space, space.largest_received_packet),
        )
        ranges = aioquic_packet.push_ack_frame(buf, space.ack_queue, ack_delay_encoded)
        buf.push_uint_var(counts[ECNCodepoint.ECT0])
        buf.push_uint_var(counts[ECNCodepoint.ECT1])
        buf.push_uint_var(counts[ECNCodepoint.CE])
        space.ack_at = None

        if self._quic_logger is not None:
            builder.quic_logger_frames.append(
                self._quic_logger.encode_ack_frame(
                    ranges=space.ack_queue,
                    delay=ack_delay,
                )
            )

        if ranges > 1 and builder.packet_number % 8 == 0:
            self._write_ping_frame(builder, comment="ACK-of-ACK trigger")

    aioquic_connection.QuicConnection._handle_ack_frame = handle_ack_frame
    aioquic_connection.QuicConnection._payload_received = payload_received
    aioquic_connection.QuicConnection._write_ack_frame = write_ack_frame
    _installed = True


def _ecn_counts(connection) -> dict[ECNCodepoint, int]:
    counts = getattr(connection, "_qcl4s_ecn_counts", None)
    if counts is None:
        counts = {
            ECNCodepoint.NOT_ECT: 0,
            ECNCodepoint.ECT0: 0,
            ECNCodepoint.ECT1: 0,
            ECNCodepoint.CE: 0,
        }
        connection._qcl4s_ecn_counts = counts
    return counts
