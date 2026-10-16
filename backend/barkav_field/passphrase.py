"""FD-11: the passphrase kept on this computer, in the Windows Credential Manager.

The passphrase is typed once with `pull set-passphrase`. It is never written to a file,
to Git or to a log. Tests replace the keyring module with an in-memory stand-in.
"""

from __future__ import annotations

import keyring

SERVICE = "BARKAV Field"
ACCOUNT = "passphrase"


class PassphraseError(ValueError):
    """The passphrase cannot be stored, for example because it is empty."""


def save_passphrase(value: str) -> None:
    if not value:
        raise PassphraseError("passphrase is empty")
    keyring.set_password(SERVICE, ACCOUNT, value)


def load_passphrase() -> str | None:
    return keyring.get_password(SERVICE, ACCOUNT) or None
