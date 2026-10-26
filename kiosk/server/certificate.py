"""The phone mode's HTTPS certificate: made on the first start, reused afterwards.

Chrome lets a page use the microphone only over HTTPS (or on localhost), so the phone opens the
kiosk at https://<this laptop's address>. Nobody signs this certificate: the phone warns once
("Your connection is not private"), and after "Advanced > Proceed" it remembers. The laptop's
addresses are written into it; when the hotspot gives the laptop a new one, it is made again
(and the phone warns once more). Both files are git-ignored (`*.local.pem`).
"""

from __future__ import annotations

import contextlib
import datetime
import ipaddress
import logging
import socket
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

log = logging.getLogger(__name__)

VALID_DAYS = 397  # the longest validity browsers accept
RENEW_BEFORE = datetime.timedelta(days=7)
NAME = "voice-kiosk"


@dataclass(frozen=True)
class Certificate:
    cert: Path
    key: Path


def laptop_addresses() -> list[str]:
    """This computer's IPv4 addresses on its networks (the hotspot's first), no loopback."""
    found: list[str] = []
    # The address used to reach the internet (a UDP "connect" sends nothing), then the others.
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        found.append(s.getsockname()[0])
    with contextlib.suppress(OSError):
        found += socket.gethostbyname_ex(socket.gethostname())[2]
    addresses = []
    for address in found:
        ip = ipaddress.ip_address(address)
        if not (ip.is_loopback or ip.is_link_local) and address not in addresses:
            addresses.append(address)
    return addresses


def ensure_certificate(folder: Path, addresses: list[str]) -> Certificate:
    """The certificate for `addresses` (and localhost): the saved one if it still fits."""
    files = Certificate(folder / "phone-cert.local.pem", folder / "phone-key.local.pem")
    if _fits(files, addresses):
        return files
    folder.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.UTC)
    names: list[x509.GeneralName] = [x509.DNSName("localhost")]
    names += [x509.IPAddress(ipaddress.ip_address(a)) for a in ["127.0.0.1", *addresses]]
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, NAME)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    files.key.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    files.cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    log.info("made the phone certificate for %s", ", ".join(addresses) or "localhost")
    return files


def _fits(files: Certificate, addresses: list[str]) -> bool:
    if not (files.cert.exists() and files.key.exists()):
        return False
    try:
        cert = x509.load_pem_x509_certificate(files.cert.read_bytes())
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (ValueError, x509.ExtensionNotFound):
        return False
    known = {str(ip) for ip in names.get_values_for_type(x509.IPAddress)}
    fresh = cert.not_valid_after_utc - datetime.datetime.now(datetime.UTC) > RENEW_BEFORE
    return fresh and set(addresses) <= known
