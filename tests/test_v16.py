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


@pytest.mark.parametrize("version", ["15.0.0", "15.99.0", "16.0.0", "16.1.0"])
def test_matching_supported_versions_are_accepted(install_module, version):
    module, fake, erp = install_module
    fake.__version__ = erp.__version__ = version
    module.check_versions()


def test_postgres_is_rejected(install_module):
    module, fake, _ = install_module
    fake.db.db_type = "postgres"
    with pytest.raises(ValueError, match="MariaDB"):
        module.check_versions()


@pytest.mark.parametrize(
    "frappe_version,erp_version",
    [("15.99.0", "16.0.0"), ("16.0.0", "15.99.0"), ("14.99.0", "14.99.0"), ("17.0.0", "17.0.0")],
)
def test_other_major_versions_rejected(install_module, frappe_version, erp_version):
    module, fake, erp = install_module
    fake.__version__ = frappe_version
    erp.__version__ = erp_version
    with pytest.raises(ValueError, match="v16"):
        module.check_versions()


def test_package_allows_supported_python_and_frappe_versions():
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib

    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert project["project"]["requires-python"] == ">=3.10,<3.15"
    assert project["tool"]["ruff"]["target-version"] == "py310"
    assert project["tool"]["bench"]["frappe-dependencies"]["frappe"] == ">=15.0.0-dev,<17.0.0-dev"


def test_application_and_tests_parse_on_python_310():
    import ast

    root = Path(__file__).parents[1]
    for folder in (root / "revolut_bank_feed", root / "tests"):
        for source in folder.rglob("*.py"):
            ast.parse(source.read_text(), filename=str(source), feature_version=(3, 10))


@pytest.mark.parametrize("major", [15, 16])
def test_bench_tests_use_the_available_frappe_test_base(monkeypatch, major):
    fake = ModuleType("frappe")
    fake.__version__ = f"{major}.0.0"
    test_module = ModuleType("frappe.tests")
    utils = ModuleType("frappe.tests.utils")
    base = type("IntegrationTestCase" if major == 16 else "FrappeTestCase", (), {})
    if major == 16:
        test_module.IntegrationTestCase = base
    else:
        utils.FrappeTestCase = base
    importer = ModuleType("revolut_bank_feed.importer")
    importer.get_maps = importer.ingest = lambda *a, **kw: None
    for name, module in (
        ("frappe", fake),
        ("frappe.tests", test_module),
        ("frappe.tests.utils", utils),
        ("revolut_bank_feed.importer", importer),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    name = "revolut_bank_feed.tests.test_integration"
    monkeypatch.delitem(sys.modules, name, raising=False)
    try:
        suite = importlib.import_module(name)
        assert issubclass(suite.TestBankFeedIntegration, base)
        dependencies = suite.test_dependencies if major == 15 else suite.EXTRA_TEST_RECORD_DEPENDENCIES
        assert dependencies == ["Company"]
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize("major", [15, 16])
def test_import_fields_exist_in_official_bank_schema(major):
    import json

    from test_core import mapping, transaction

    from revolut_bank_feed.core import normalize

    snapshot = json.loads((Path(__file__).parent / f"fixtures/v{major}_fields.json").read_text())
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
