from datetime import date

from app.analytics import daily_active_users, top_event_types


def test_dau():
    dau = daily_active_users()
    assert dau[date(2026, 1, 1)] == 2
    assert dau[date(2026, 1, 2)] == 2


def test_top_events():
    top = top_event_types(2)
    assert top[0] == ("login", 3)
    assert len(top) == 2
