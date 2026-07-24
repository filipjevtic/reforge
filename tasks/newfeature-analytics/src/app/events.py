"""Internal events data the analytics feature should aggregate."""

from datetime import date

EVENTS = [
    {"user_id": 1, "event_type": "login", "day": date(2026, 1, 1)},
    {"user_id": 2, "event_type": "login", "day": date(2026, 1, 1)},
    {"user_id": 1, "event_type": "purchase", "day": date(2026, 1, 1)},
    {"user_id": 3, "event_type": "login", "day": date(2026, 1, 2)},
    {"user_id": 1, "event_type": "view", "day": date(2026, 1, 2)},
]
