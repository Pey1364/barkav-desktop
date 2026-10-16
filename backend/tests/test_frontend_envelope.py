"""Cross-check: an envelope sealed by the phone's browser code opens here, with the same format."""

import json
from pathlib import Path

from barkav_field import envelope

FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "js-envelope.json"


def test_envelope_sealed_in_the_browser_opens_in_python():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data = json.dumps(fixture["envelope"]).encode("utf-8")
    assert envelope.open_(data, fixture["passphrase"]) == fixture["payload"]
