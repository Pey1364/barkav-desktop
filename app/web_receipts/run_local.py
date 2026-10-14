"""WR-04: run the receipt page on the home network: `python -m web_receipts.run_local`.

Prints the address to open on the phone and a new pairing code. The code changes
each time the server starts. Stop the server with Ctrl+C.

The inbox and the certificate live in app/data/web_receipts, which Git ignores.
"""

from __future__ import annotations

import socket
from pathlib import Path

from .cert import ensure_certificate
from .inbox import new_pairing_token
from .server import make_server

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data" / "web_receipts"
PORT = 8443


def lan_address() -> str:
    """The address other devices on this network use to reach this computer."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))  # no packet is sent; it only picks the route
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def main() -> None:
    address = lan_address()
    cert, key = ensure_certificate(DATA_DIR / "cert", hosts=[address, "127.0.0.1", "localhost"])
    token = new_pairing_token()
    server = make_server(
        inbox_dir=DATA_DIR / "inbox",
        token=token,
        host="0.0.0.0",
        port=PORT,
        certfile=cert,
        keyfile=key,
    )
    print("صفحه‌ی ثبت رسید روی شبکه‌ی خانگی آماده است.")
    print(f"  آدرس روی گوشی: https://{address}:{PORT}/")
    print(f"  کد جفت‌سازی:   {token}")
    print("  اولین بار گواهی را روی گوشی یک‌بار تأیید کن. Ctrl+C برای توقف.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
