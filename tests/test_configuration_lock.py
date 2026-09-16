from types import SimpleNamespace

import pytest
from test_auth import auth_module as auth_module


class Callbacks:
    def __init__(self):
        self.callbacks = []

    def add(self, callback):
        self.callbacks.append(callback)

    def run(self):
        callbacks, self.callbacks = self.callbacks, []
        for callback in callbacks:
            callback()


class Mutex:
    def __init__(self, events, available=True):
        self.events = events
        self.available = available

    def acquire(self, blocking=False):
        self.events.append("acquire")
        assert not blocking
        return self.available

    def release(self):
        self.events.append("release")


@pytest.fixture
def locks(auth_module):
    module = auth_module[0]
    events = []
    mutexes = []

    def lock(name, **kwargs):
        events.append(name)
        mutex = Mutex(events)
        mutexes.append(mutex)
        return mutex

    module.frappe.cache = SimpleNamespace(lock=lock)
    module.frappe.local = SimpleNamespace(site="test.local")
    module.frappe.db.after_commit = Callbacks()
    module.frappe.db.after_rollback = Callbacks()
    return module, events, mutexes


@pytest.mark.parametrize("boundary", ["after_commit", "after_rollback"])
def test_configuration_lock_outlives_validation_until_transaction_end(locks, boundary):
    module, events, _ = locks
    module.lock_configuration("connection")
    events.append("document_saved")
    assert events == ["revolut-feed:test.local:connection", "acquire", "document_saved"]
    getattr(module.frappe.db, boundary).run()
    assert events[-1] == "release"


def test_nested_mapping_validation_reuses_lock(locks):
    module, events, mutexes = locks
    module.lock_configuration("connection")
    module.lock_configuration("connection")
    assert len(mutexes) == 1
    module.frappe.db.after_commit.run()
    module.frappe.db.after_rollback.run()
    assert events.count("release") == 1
    module.lock_configuration("connection")
    assert len(mutexes) == 2


def test_busy_worker_prevents_configuration_mutation(locks):
    module, events, _ = locks
    module.frappe.cache.lock = lambda *a, **kw: Mutex(events, available=False)
    with pytest.raises(module.FeedError, match="connection_busy"):
        module.lock_configuration("connection")
    assert not module.frappe.db.after_commit.callbacks
    assert not module.frappe.db.after_rollback.callbacks
    assert "release" not in events


def test_token_refresh_commit_does_not_release_worker_lock(locks):
    module, events, _ = locks
    with module.connection_lock("connection"):
        module.frappe.db.after_commit.run()
        assert "release" not in events
    assert events[-1] == "release"
