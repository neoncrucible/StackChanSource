import pytest

from kcore.protocol import Envelope, MessageKind


def test_envelope_round_trip():
    original = Envelope(MessageKind.EVENT, "touch.tap", {"x": 12, "y": 34})
    restored = Envelope.from_json(original.to_json())
    assert restored.to_dict() == original.to_dict()


def test_rejects_wrong_protocol_version():
    data = Envelope(MessageKind.HELLO, "device").to_dict()
    data["v"] = 999
    with pytest.raises(ValueError, match="unsupported protocol version"):
        Envelope.from_dict(data)
