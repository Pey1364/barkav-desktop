"""FD-11: the passphrase kept on this computer, tested with an in-memory credential store."""

import pytest

from barkav_field import passphrase, pull
from barkav_field.passphrase import PassphraseError, load_passphrase, save_passphrase


class FakeKeyring:
    def __init__(self):
        self.items = {}

    def set_password(self, service, account, value):
        self.items[(service, account)] = value

    def get_password(self, service, account):
        return self.items.get((service, account))


@pytest.fixture
def store(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(passphrase, "keyring", fake)
    return fake


def test_save_then_load_returns_the_same_value(store):
    save_passphrase("long-test-passphrase-1")
    assert load_passphrase() == "long-test-passphrase-1"


def test_nothing_saved_loads_as_none(store):
    assert load_passphrase() is None


def test_empty_passphrase_is_refused(store):
    with pytest.raises(PassphraseError):
        save_passphrase("")
    assert store.items == {}


def test_pull_uses_the_environment_first(store, monkeypatch):
    save_passphrase("saved-value")
    monkeypatch.setenv("BARKAV_FIELD_PASSPHRASE", "env-value")
    monkeypatch.setattr(pull.getpass, "getpass", lambda prompt="": pytest.fail("should not prompt"))
    assert pull._passphrase("BARKAV_FIELD_PASSPHRASE") == "env-value"


def test_pull_uses_the_saved_passphrase_when_the_environment_is_empty(store, monkeypatch):
    save_passphrase("saved-value")
    monkeypatch.delenv("BARKAV_FIELD_PASSPHRASE", raising=False)
    monkeypatch.setattr(pull.getpass, "getpass", lambda prompt="": pytest.fail("should not prompt"))
    assert pull._passphrase("BARKAV_FIELD_PASSPHRASE") == "saved-value"


def test_pull_asks_only_when_nothing_is_available(store, monkeypatch):
    monkeypatch.delenv("BARKAV_FIELD_PASSPHRASE", raising=False)
    monkeypatch.setattr(pull.getpass, "getpass", lambda prompt="": "typed-value")
    assert pull._passphrase("BARKAV_FIELD_PASSPHRASE") == "typed-value"
