import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def install_module(monkeypatch):
    fake = ModuleType("frappe")
    fake.__version__ = "16.0.0"
    fake.db = SimpleNamespace(db_type="mariadb")

    def throw(message):
        raise ValueError(message)

    fake.throw = throw
    erp = ModuleType("erpnext")
    erp.__version__ = "16.0.0"
    custom = ModuleType("frappe.custom.doctype.custom_field.custom_field")
    custom.create_custom_fields = lambda *a, **kw: None
    for key, value in [
        ("frappe", fake),
        ("erpnext", erp),
        ("frappe.custom.doctype.custom_field.custom_field", custom),
    ]:
        monkeypatch.setitem(sys.modules, key, value)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.install", raising=False)
    module = importlib.import_module("revolut_bank_feed.install")
    yield module, fake, erp
    sys.modules.pop("revolut_bank_feed.install", None)


def test_version_16_is_accepted(install_module):
    module, _, _ = install_module
    module.check_versions()


@pytest.mark.parametrize(
    "frappe_version,erp_version", [("15.99.0", "16.0.0"), ("16.0.0", "15.99.0"), ("17.0.0", "17.0.0")]
)
def test_other_major_versions_rejected(install_module, frappe_version, erp_version):
    module, fake, erp = install_module
    fake.__version__ = frappe_version
    erp.__version__ = erp_version
    with pytest.raises(ValueError, match="v16"):
        module.check_versions()


def test_runtime_and_desk_route_target_v16():
    root = Path(__file__).parents[1]
    assert 'requires-python = ">=3.14,<3.15"' in (root / "pyproject.toml").read_text()
    assert "/desk/revolut-setup" in (root / "README.md").read_text()


def test_import_fields_exist_in_official_v16_bank_schema():
    import json

    from test_core import mapping, transaction

    from revolut_bank_feed.core import normalize

    snapshot = json.loads((Path(__file__).parent / "fixtures/v16_fields.json").read_text())
    row = normalize(transaction(), mapping())[0]
    ignored = {
        "leg_id",
        "account_id",
        "fee",
        "account_map",
        "bill_amount",
        "bill_currency",
        "effective_bill_rate",
    }
    assert set(row) - ignored <= set(snapshot["Bank Transaction"]["fields"])
    assert snapshot["Bank Transaction"]["is_submittable"] == 1
    assert snapshot["Bank Account"]["fields"]["company"] == "Link"
    assert "company" not in snapshot["Currency Exchange"]["fields"]
