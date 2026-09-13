import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def deployment(monkeypatch):
    apps = ["frappe", "erpnext"]
    calls = []
    fake = ModuleType("frappe")
    fake.local = SimpleNamespace(site="erp.test")
    fake.session = SimpleNamespace(user="Administrator")
    fake.get_installed_apps = lambda: list(apps)
    fake.get_all_apps = lambda: ["frappe", "erpnext", "revolut_bank_feed"]

    def throw(message):
        raise ValueError(message)

    fake.throw = throw
    installer = ModuleType("frappe.installer")

    def install_app(name, **kw):
        calls.append(name)
        apps.append(name)

    installer.install_app = install_app
    install = ModuleType("revolut_bank_feed.install")
    install.check_versions = lambda: None
    for key, mod in [
        ("frappe", fake),
        ("frappe.installer", installer),
        ("revolut_bank_feed.install", install),
    ]:
        monkeypatch.setitem(sys.modules, key, mod)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.deployment", raising=False)
    mod = importlib.import_module("revolut_bank_feed.deployment")
    yield mod, apps, calls, fake
    sys.modules.pop("revolut_bank_feed.deployment", None)


def test_site_install_is_idempotent(deployment):
    mod, apps, calls, _ = deployment
    assert mod.ensure_installed()["status"] == "installed"
    assert mod.ensure_installed()["status"] == "already_installed"
    assert calls == ["revolut_bank_feed"]


def test_requires_erpnext_already_installed(deployment):
    mod, apps, calls, _ = deployment
    apps.remove("erpnext")
    with pytest.raises(ValueError):
        mod.ensure_installed()
    assert not calls


def test_missing_image_code_list_is_actionable(deployment):
    mod, _, calls, fake = deployment
    fake.get_all_apps = lambda: ["frappe", "erpnext"]
    with pytest.raises(ValueError, match="apps.txt"):
        mod.ensure_installed()
    assert not calls


def test_deployment_helper_is_not_http_endpoint(deployment):
    mod, _, _, _ = deployment
    from pathlib import Path

    assert "@frappe.whitelist" not in Path(mod.__file__).read_text()


def test_fresh_install_uses_explicit_import_for_bench_fallback(deployment):
    # Frappe v16 get_attr rejects apps not installed on the site. Its CLI-only
    # execute fallback evaluates the expression and calls it if callable.
    import shlex
    from pathlib import Path

    _, apps, calls, _ = deployment
    assert "revolut_bank_feed" not in apps
    script = Path(__file__).parents[1] / "docker/deploy-site.sh"
    line = next(
        line for line in script.read_text().splitlines() if line.startswith("bench ") and " execute " in line
    )
    expression = shlex.split(line)[-1]
    result = eval(compile(expression, "<bench execute>", "eval"), {}, {})
    if callable(result):
        result = result()
    assert result["status"] == "installed"
    assert calls == ["revolut_bank_feed"]
