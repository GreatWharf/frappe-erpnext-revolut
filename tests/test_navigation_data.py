import importlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from revolut_bank_feed.navigation_data import merge_home_icon


@pytest.fixture
def navigation_module(monkeypatch):
    fake = ModuleType("frappe")
    fake.__version__ = "15.99.0"
    documents = {}
    inserted = []
    cache_keys = []
    queried = []

    def exists(doctype, name):
        queried.append(doctype)
        assert doctype == "Workspace", "v15 must not query v16 navigation tables"
        return (doctype, name) in documents

    def get_doc(value):
        assert isinstance(value, dict)

        def insert(**kwargs):
            inserted.append(value)
            documents[value["doctype"], value["name"]] = value

        return SimpleNamespace(insert=insert)

    fake.db = SimpleNamespace(exists=exists)
    fake.get_doc = get_doc
    fake.cache = SimpleNamespace(delete_key=cache_keys.append)
    fake.get_roles = lambda: ["System Manager"]
    monkeypatch.setitem(sys.modules, "frappe", fake)
    monkeypatch.delitem(sys.modules, "revolut_bank_feed.navigation", raising=False)
    module = importlib.import_module("revolut_bank_feed.navigation")
    yield module, fake, documents, inserted, cache_keys, queried
    sys.modules.pop("revolut_bank_feed.navigation", None)


def test_v15_creates_role_restricted_workspace_without_v16_tables(navigation_module):
    module, _, _, inserted, cache_keys, queried = navigation_module
    module.ensure_navigation()
    assert queried == ["Workspace"]
    assert len(inserted) == 1
    workspace = inserted[0]
    assert workspace["doctype"] == "Workspace"
    assert workspace["name"] == workspace["title"] == workspace["label"] == "Revolut Bank Feed"
    assert workspace["public"] == 1
    assert workspace["roles"] == [{"role": "System Manager"}]
    assert any(row["type"] == "Page" and row["link_to"] == "revolut-setup" for row in workspace["shortcuts"])
    assert any(row["link_to"] == "Bank Transaction" for row in workspace["shortcuts"])
    blocks = json.loads(workspace["content"])
    assert {block["data"]["shortcut_name"] for block in blocks} == {
        row["label"] for row in workspace["shortcuts"]
    }
    assert "bootinfo" in cache_keys


def test_v15_navigation_is_idempotent_and_preserves_workspace_customizations(navigation_module):
    module, _, documents, inserted, _, _ = navigation_module
    existing = {"title": "Customized", "content": "[]", "roles": [{"role": "System Manager"}]}
    documents["Workspace", "Revolut Bank Feed"] = existing
    module.ensure_navigation()
    module.ensure_navigation()
    assert inserted == []
    assert documents["Workspace", "Revolut Bank Feed"] is existing


def test_v16_keeps_sidebar_icon_and_existing_desktop_layout_path(navigation_module):
    module, fake, _, inserted, cache_keys, _ = navigation_module
    fake.__version__ = "16.0.0"
    existing_queries = []

    def exists(doctype, name):
        existing_queries.append((doctype, name))
        return False

    fake.db.exists = exists
    root = Path(__file__).parents[1] / "revolut_bank_feed"
    fake.get_app_path = lambda app, kind, filename: str(root / kind / filename)
    create_doc = fake.get_doc
    fake.get_doc = lambda *args: (
        SimpleNamespace(as_dict=lambda: {"label": "Revolut Bank Feed"})
        if len(args) == 2
        else create_doc(*args)
    )
    tables = []
    fake.get_all = lambda doctype, **kwargs: tables.append(doctype) or []
    module.ensure_navigation()
    assert [row["doctype"] for row in inserted] == ["Workspace Sidebar", "Desktop Icon"]
    assert tables == ["Desktop Layout"]
    assert ("Workspace", "Revolut Bank Feed") not in existing_queries
    assert "desktop_icons" in cache_keys


def test_apps_screen_permissions_are_explicit_booleans(navigation_module):
    module, fake, *_ = navigation_module
    assert module.has_app_permission() is True
    fake.get_roles = lambda: ["Accounts User"]
    assert module.has_app_permission() is False


def test_adds_missing_icon_without_changing_saved_layout():
    layout = [{"label": "Accounting", "idx": 4, "hidden": 0}]
    icon = {"label": "Revolut Bank Feed", "logo_url": "/new.svg", "idx": 0}
    result = merge_home_icon(layout, icon)
    assert result[0] == layout[0]
    assert len(layout) == 1
    assert result[1]["idx"] == 5
    assert result[1]["label"] == "Revolut Bank Feed"


def test_refreshes_branding_but_preserves_user_placement_and_visibility():
    layout = [
        {
            "label": "Revolut Bank Feed",
            "idx": 7,
            "hidden": 1,
            "parent_icon": "Accounting",
            "logo_url": "/old.svg",
        }
    ]
    icon = {"label": "Revolut Bank Feed", "logo_url": "/new.svg", "idx": 0, "hidden": 0, "parent_icon": None}
    result = merge_home_icon(layout, icon)
    assert len(result) == 1
    assert result[0]["logo_url"] == "/new.svg"
    assert result[0]["hidden"] == 1
    assert result[0]["idx"] == 7
    assert result[0]["parent_icon"] == "Accounting"
    assert merge_home_icon(result, icon) == result
