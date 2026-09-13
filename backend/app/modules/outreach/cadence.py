"""Pure send-window scheduling math — no I/O, no DB, no network. Encodes the cadence rule from
the meeting: outreach only goes out Monday-Wednesday (Thursday too, but only if urgent), never
Friday or the weekend, landing around 11:00 in the recipient's local time. Kept separate from
`service.py` so this, the piece of logic precision matters most for, is independently and
exhaustively unit-testable without a database or event loop."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)

# Mon-Wed are always a valid send day; Thursday only counts as eligible for an urgent follow-up.
_ALWAYS_ELIGIBLE_WEEKDAYS = frozenset({MONDAY, TUESDAY, WEDNESDAY})
_URGENT_ONLY_WEEKDAY = THURSDAY

_SEND_HOUR = 11


def _add_business_days(start: date, business_days: int) -> date:
    """Advances `start` by `business_days` calendar weekdays (Mon-Fri counted, weekends
    skipped) — this is a distinct step from send-window eligibility below: a company might
    reasonably follow up "3 business days later" and land on a Thursday or a weekend, which
    then gets rolled forward to the next day the send window actually allows."""
    current = start
    advanced = 0
    while advanced < business_days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            advanced += 1
    return current


def _roll_to_eligible_weekday(d: date, urgent: bool) -> date:
    eligible = _ALWAYS_ELIGIBLE_WEEKDAYS | ({_URGENT_ONLY_WEEKDAY} if urgent else set())
    while d.weekday() not in eligible:
        d += timedelta(days=1)
    return d


def next_send_window_slot(
    after: datetime,
    timezone_name: str | None = None,
    urgent: bool = False,
    gap_business_days: int | None = None,
) -> datetime:
    """The next valid send-window slot at least `gap_business_days` business days after `after`:
    Mon-Wed always eligible, Thu only if `urgent`, Fri/Sat/Sun never — landing at 11:00 in the
    resolved timezone (the contact's own `timezone_name` when set, else the app-wide
    `settings.default_timezone`), returned as a UTC-aware datetime for storage."""
    settings = get_settings()
    if gap_business_days is None:
        gap_business_days = settings.default_follow_up_gap_business_days
    tz = ZoneInfo(timezone_name or settings.default_timezone)

    local_after = after.astimezone(tz)
    candidate_date = _add_business_days(local_after.date(), gap_business_days)
    candidate_date = _roll_to_eligible_weekday(candidate_date, urgent)

    candidate = datetime.combine(candidate_date, time(hour=_SEND_HOUR), tzinfo=tz)
    return candidate.astimezone(UTC)
