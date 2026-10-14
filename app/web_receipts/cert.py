"""Self-signed HTTPS certificate for the local receipt page.

A phone browser only grants camera access and allows installing a web app on a
secure origin. A self-signed certificate is enough for a home network if the
certificate is trusted once on the phone. The private key stays on this computer.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_FILE = "receipts-cert.pem"
KEY_FILE = "receipts-key.pem"


def ensure_certificate(directory: Path, hosts: list[str], days: int = 365) -> tuple[Path, Path]:
    """Create the certificate once and reuse it. `hosts` are IP addresses or DNS names."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cert_path = directory / CERT_FILE
    key_path = directory / KEY_FILE
    if cert_path.is_file() and key_path.is_file():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "BARKAV receipt inbox")])
    now = dt.datetime.now(dt.timezone.utc)

    alt_names: list[x509.GeneralName] = []
    for host in hosts:
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            alt_names.append(x509.DNSName(host))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path
