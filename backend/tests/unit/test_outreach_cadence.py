from datetime import UTC, datetime

from app.modules.outreach.cadence import next_send_window_slot

# All fixed points below use 2024-01-01, a known Monday, as the anchor so every case is
# unambiguous about which weekday it lands on.
_MON = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)  # Monday
_TUE = datetime(2024, 1, 2, 9, 0, tzinfo=UTC)  # Tuesday
_WED = datetime(2024, 1, 3, 9, 0, tzinfo=UTC)  # Wednesday


def test_default_gap_from_monday_lands_on_thursday_then_rolls_to_next_monday() -> None:
    # Mon + 3 business days = Thu, which is not eligible for a non-urgent send -> rolls forward
    # through Fri/Sat/Sun to the following Monday.
    result = next_send_window_slot(_MON, "UTC", urgent=False, gap_business_days=3)
    assert result == datetime(2024, 1, 8, 11, 0, tzinfo=UTC)
    assert result.weekday() == 0  # Monday


def test_urgent_allows_landing_on_thursday() -> None:
    result = next_send_window_slot(_MON, "UTC", urgent=True, gap_business_days=3)
    assert result == datetime(2024, 1, 4, 11, 0, tzinfo=UTC)
    assert result.weekday() == 3  # Thursday


def test_landing_on_wednesday_is_already_eligible_no_roll() -> None:
    # Wed + 3 business days = Mon (Sat/Sun skipped by the business-day advance itself) -> already
    # eligible, no further rolling needed.
    result = next_send_window_slot(_WED, "UTC", urgent=False, gap_business_days=3)
    assert result == datetime(2024, 1, 8, 11, 0, tzinfo=UTC)
    assert result.weekday() == 0


def test_landing_on_friday_rolls_to_monday_even_when_urgent() -> None:
    # Tue + 3 business days = Fri. Friday is never eligible -- urgent only adds Thursday, not
    # Friday -- so both urgent and non-urgent roll the same way, through the weekend to Monday.
    non_urgent = next_send_window_slot(_TUE, "UTC", urgent=False, gap_business_days=3)
    urgent = next_send_window_slot(_TUE, "UTC", urgent=True, gap_business_days=3)
    assert non_urgent == datetime(2024, 1, 8, 11, 0, tzinfo=UTC)
    assert urgent == datetime(2024, 1, 8, 11, 0, tzinfo=UTC)


def test_custom_gap_business_days_overrides_default() -> None:
    result = next_send_window_slot(_MON, "UTC", urgent=False, gap_business_days=1)
    assert result == datetime(2024, 1, 2, 11, 0, tzinfo=UTC)
    assert result.weekday() == 1  # Tuesday


def test_default_timezone_used_when_contact_has_none_set() -> None:
    result = next_send_window_slot(_MON, None, urgent=False, gap_business_days=1)
    # settings.default_timezone defaults to "UTC", so this matches the explicit-UTC case exactly.
    assert result == datetime(2024, 1, 2, 11, 0, tzinfo=UTC)


def test_non_utc_timezone_converts_to_utc_for_storage() -> None:
    # 11:00 IST (UTC+5:30) on Jan 2 is 05:30 UTC.
    result = next_send_window_slot(_MON, "Asia/Kolkata", urgent=False, gap_business_days=1)
    assert result == datetime(2024, 1, 2, 5, 30, tzinfo=UTC)


def test_timezone_conversion_can_shift_the_local_date_before_scheduling() -> None:
    # 23:00 UTC on Monday is already 04:30 IST on Tuesday -- the business-day advance must start
    # from the contact's local Tuesday, not the UTC-side Monday.
    late_monday_utc = datetime(2024, 1, 1, 23, 0, tzinfo=UTC)
    result = next_send_window_slot(
        late_monday_utc, "Asia/Kolkata", urgent=False, gap_business_days=1
    )
    # Local Tue + 1 business day = local Wed, 11:00 IST = 05:30 UTC on Jan 3.
    assert result == datetime(2024, 1, 3, 5, 30, tzinfo=UTC)
