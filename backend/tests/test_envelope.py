"""FD-01: encrypted envelope. Uses no real data; passphrases are test values."""

import base64
import json

import pytest

from barkav_field import envelope


def test_round_trip_returns_the_same_payload():
    payload = {"kind": "receipt", "id": "R-1", "caption": "بابت آجر", "received_at": "2026-10-14T10:00:00Z"}
    data = envelope.seal(payload, "test-passphrase-1")
    assert envelope.open_(data, "test-passphrase-1") == payload


def test_envelope_does_not_contain_the_plaintext():
    data = envelope.seal({"kind": "daily_report", "body": "متن محرمانه"}, "test-passphrase-1")
    assert "متن محرمانه".encode("utf-8") not in data
    assert b"daily_report" not in data


def test_each_seal_is_different_even_for_the_same_payload():
    payload = {"kind": "daily_report", "id": "D-1", "body": "x"}
    assert envelope.seal(payload, "test-passphrase-1") != envelope.seal(payload, "test-passphrase-1")


def test_wrong_passphrase_is_refused():
    data = envelope.seal({"kind": "daily_report", "id": "D-1", "body": "x"}, "test-passphrase-1")
    with pytest.raises(envelope.EnvelopeError):
        envelope.open_(data, "test-passphrase-2")


def test_changed_ciphertext_is_refused():
    data = json.loads(envelope.seal({"kind": "daily_report", "id": "D-1", "body": "x"}, "test-passphrase-1"))
    raw = bytearray(base64.b64decode(data["ct"]))
    raw[0] ^= 0x01
    data["ct"] = base64.b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(envelope.EnvelopeError):
        envelope.open_(json.dumps(data).encode("utf-8"), "test-passphrase-1")


def test_empty_passphrase_is_refused():
    with pytest.raises(envelope.EnvelopeError):
        envelope.seal({"kind": "daily_report"}, "")


@pytest.mark.parametrize("garbage", [b"", b"not json", b"[1,2]", b'{"v":2}', b'{"v":1,"kdf":"md5"}'])
def test_malformed_envelopes_are_refused(garbage):
    with pytest.raises(envelope.EnvelopeError):
        envelope.open_(garbage, "test-passphrase-1")


def test_scrypt_parameters_out_of_range_are_refused():
    data = json.loads(envelope.seal({"kind": "daily_report"}, "test-passphrase-1"))
    data["n"] = 2**30
    with pytest.raises(envelope.EnvelopeError):
        envelope.open_(json.dumps(data).encode("utf-8"), "test-passphrase-1")
