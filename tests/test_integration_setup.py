"""Offline contract checks for the real-site test fixture initializer."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def setup_environment(monkeypatch):
    events = []
    state = {"company": False, "accounts": False}
    fake = ModuleType("frappe")
    fake.flags = SimpleNamespace(in_test=True)
    fake._dict = dict
    fake.db = SimpleNamespace(
        exists=lambda doctype, filters: state["company" if doctype == "Company" else "accounts"],
        commit=lambda: events.append("commit"),
    )
    wizard = ModuleType("erpnext.setup.setup_wizard.setup_wizard")

    def setup_complete(args):
        events.append(args)
        state.update(company=True, accounts=True)

    wizard.setup_complete = setup_complete
    monkeypatch.setitem(sys.modules, "frappe", fake)
    monkeypatch.setitem(sys.modules, "erpnext.setup.setup_wizard.setup_wizard", wizard)
    helper = importlib.import_module("revolut_bank_feed.tests")
    return helper, fake, wizard, state, events


def test_real_site_setup_uses_official_wizard_and_commits_only_baseline(setup_environment):
    helper, _, _, _, events = setup_environment
    helper.setup_test_company("_Test Feed", "TFD")
    args, commit = events
    assert args["company_name"] == "_Test Feed"
    assert args["company_abbr"] == "TFD"
    assert args["currency"] == "USD"
    assert args["country"] == "United States"
    assert args["chart_of_accounts"] == "Standard"
    assert args["fy_start_date"].endswith("-01-01")
    assert args["fy_end_date"].endswith("-12-31")
    assert commit == "commit"


def test_existing_test_company_is_not_reconfigured(setup_environment):
    helper, _, _, state, events = setup_environment
    state.update(company=True, accounts=True)
    helper.setup_test_company("_Test Feed", "TFD")
    assert events == []


def test_fixture_initializer_refuses_non_test_context(setup_environment):
    helper, fake, _, _, events = setup_environment
    fake.flags.in_test = False
    with pytest.raises(RuntimeError, match="test"):
        helper.setup_test_company("_Test Feed", "TFD")
    assert events == []


def test_fixture_initializer_refuses_real_company_names(setup_environment):
    helper, _, _, _, events = setup_environment
    with pytest.raises(RuntimeError, match="test"):
        helper.setup_test_company("Real Customer Company", "RCC")
    assert events == []


def test_setup_failure_cannot_be_hidden_by_wizard_fixture_error_handling(setup_environment):
    helper, _, wizard, state, events = setup_environment
    wizard.setup_complete = lambda args: state.update(company=True, accounts=False)
    with pytest.raises(RuntimeError, match="chart of accounts"):
        helper.setup_test_company("_Test Feed", "TFD")
    assert "commit" not in events
