from datetime import datetime, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from revolut_bank_feed.core import FeedError
from revolut_bank_feed.setup_core import authorization_code, make_certificate


def test_generated_certificate_matches_private_key_and_hostname():
    private_pem, public_pem = make_certificate("erp.example.test")
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    cert = x509.load_pem_x509_certificate(public_pem)
    assert private_key.key_size >= 2048
    assert private_key.public_key().public_numbers() == cert.public_key().public_numbers()
    assert cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value == "erp.example.test"
    assert cert.not_valid_after_utc > datetime.now(timezone.utc)


@pytest.mark.parametrize(
    "value", ["oa_test_code", "https://erp.example.test/revolut-authorized?code=oa_test_code"]
)
def test_accepts_pasted_code_or_matching_redirect_url(value):
    assert authorization_code(value, "https://erp.example.test/revolut-authorized") == "oa_test_code"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://evil.test/?code=secret",
        "https://erp.example.test/wrong?code=secret",
        "https://erp.example.test/revolut-authorized?error=access_denied",
    ],
)
def test_rejects_wrong_or_empty_authorization_redirect(value):
    with pytest.raises(FeedError):
        authorization_code(value, "https://erp.example.test/revolut-authorized")
