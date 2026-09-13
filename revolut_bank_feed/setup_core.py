"""Certificate generation and paste parsing without Frappe dependencies."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from .core import FeedError


def make_certificate(hostname):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return (
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
        cert.public_bytes(serialization.Encoding.PEM),
    )


def authorization_code(value, redirect_uri):
    value = (value or "").strip()
    if not value or len(value) > 8192:
        raise FeedError("paste_authorization_code_or_redirect_url")
    if "://" in value:
        supplied, expected = urlparse(value), urlparse(redirect_uri)
        if (supplied.scheme, supplied.netloc, supplied.path) != (
            expected.scheme,
            expected.netloc,
            expected.path,
        ):
            raise FeedError("redirect_url_does_not_match_connection")
        codes = parse_qs(supplied.query).get("code", [])
        if len(codes) != 1:
            raise FeedError("authorization_code_not_found")
        value = codes[0]
    if not value or len(value) > 2048 or any(char.isspace() for char in value):
        raise FeedError("invalid_authorization_code")
    return value
