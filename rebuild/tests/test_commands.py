from __future__ import annotations

import pytest

from kcore.body_contract import CONTRACT
from kcore.commands import CommandRejected, PoseCommand, decode_body_command
from kcore.protocol import Envelope, MessageKind


def test_pose_command_accepts_in_range_values() -> None:
    envelope = Envelope(MessageKind.COMMAND, "body.pose", {"yaw": 120, "pitch": 420})
    assert decode_body_command(envelope) == PoseCommand(yaw=120, pitch=420)


def test_pose_command_clamps_to_body_contract() -> None:
    envelope = Envelope(MessageKind.COMMAND, "body.pose", {"yaw": 9999, "pitch": -9999})
    command = decode_body_command(envelope)
    assert command.yaw == CONTRACT.safe_yaw_max_tenths
    assert command.pitch == CONTRACT.safe_pitch_min_tenths


@pytest.mark.parametrize(
    "envelope",
    [
        Envelope(MessageKind.EVENT, "body.pose", {"yaw": 0, "pitch": 400}),
        Envelope(MessageKind.COMMAND, "body.unknown", {"yaw": 0, "pitch": 400}),
        Envelope(MessageKind.COMMAND, "body.pose", {"yaw": True, "pitch": 400}),
        Envelope(MessageKind.COMMAND, "body.pose", {"yaw": 0}),
    ],
)
def test_pose_command_rejects_invalid_envelopes(envelope: Envelope) -> None:
    with pytest.raises(CommandRejected):
        decode_body_command(envelope)
