from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from test_setup_api import setup_api as setup_api


@pytest.mark.parametrize("action", ["save_client_id", "pause"])
def test_setup_changes_commit_before_unlock(setup_api, monkeypatch, action):
    module, doc, _ = setup_api
    events = []

    @contextmanager
    def lock(name):
        events.append("lock")
        try:
            yield
        finally:
            events.append("unlock")

    monkeypatch.setattr(module, "connection_lock", lock)
    module.frappe.flags = SimpleNamespace()
    module.frappe.db.commit = lambda: events.append("commit")
    module.frappe.db.set_value = lambda *a, **kw: events.append("write")
    doc.save = lambda: events.append("write")
    if action == "save_client_id":
        module.save_client_id("test", "client-id")
    else:
        module.pause("test")
    assert events == ["lock", "write", "commit", "unlock"]
