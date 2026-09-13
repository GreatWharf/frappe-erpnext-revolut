# ruff: noqa: F811
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from test_sync import sync_module  # noqa: F401


def test_routine_poll_does_not_refetch_seven_days(sync_module, monkeypatch):
    mod, state, _, _ = sync_module
    cursor = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    connection = SimpleNamespace(
        name="conn",
        historical_from="2025-01-01",
        poll_cursor=cursor,
        lookback_days=7,
        poll_overlap_minutes=60,
        window_days=7,
    )
    calls = []

    def window(*args):
        calls.append(args)
        return args[5]

    monkeypatch.setattr(mod, "_window", window)
    mod._poll(connection, None, {}, {}, cursor + timedelta(minutes=15))
    assert calls[0][4] == cursor - timedelta(hours=1)
    assert calls[0][5] == cursor + timedelta(minutes=15)


def test_recent_correction_scan_runs_at_most_daily(sync_module, monkeypatch):
    mod, _, _, _ = sync_module
    connection = SimpleNamespace(last_recent_at=datetime.now(), historical_from="2025-01-01", lookback_days=7)
    monkeypatch.setattr(
        mod, "_window", lambda *args: (_ for _ in ()).throw(AssertionError("unexpected scan"))
    )
    mod._recent(connection, None, {}, {}, datetime.now(timezone.utc))
