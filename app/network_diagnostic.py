from __future__ import annotations
import socket
import sys
import urllib.request
from datetime import datetime

HOSTS = ("api.telegram.org", "google.com")

print("Peymaan Telegram Network Diagnostic")
print("Python:", sys.version.replace("\n", " "))
print("Time:", datetime.now().isoformat(timespec="seconds"))
for host in HOSTS:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = sorted({x[4][0] for x in infos})
        print(f"DNS {host}: OK -> {', '.join(ips[:4])}")
    except Exception as exc:
        print(f"DNS {host}: FAIL -> {type(exc).__name__}: {exc}")
try:
    req = urllib.request.Request("https://api.telegram.org", method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        print("HTTPS api.telegram.org: OK ->", r.status)
except Exception as exc:
    # Telegram root may return a non-200 HTTP response; reaching it still proves transport.
    import urllib.error
    if isinstance(exc, urllib.error.HTTPError):
        print("HTTPS api.telegram.org: REACHED -> HTTP", exc.code)
    else:
        print("HTTPS api.telegram.org: FAIL ->", type(exc).__name__, exc)
