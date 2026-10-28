from datetime import date

import pytest

from app.services.rent import due_dates

pytestmark = pytest.mark.jira("REN-4")


def test_ac6_no_due_dates_after_end_date():
    assert due_dates(date(2026, 1, 15), date(2026, 3, 15), 1, through=date(2026, 12, 31)) == [
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]


def test_ac6_end_date_on_due_day_is_included():
    assert due_dates(date(2026, 1, 1), date(2026, 3, 1), 1, through=date(2026, 12, 31)) == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]


@pytest.mark.parametrize(
    ("start", "due_day", "first"),
    [
        (date(2026, 1, 15), 1, date(2026, 2, 1)),
        (date(2026, 1, 1), 1, date(2026, 1, 1)),
        (date(2026, 1, 10), 20, date(2026, 1, 20)),
        (date(2026, 12, 20), 5, date(2027, 1, 5)),
    ],
)
def test_due_dates_first_due_on_or_after_start(start, due_day, first):
    assert due_dates(start, None, due_day, through=date(2027, 12, 31))[0] == first


def test_due_dates_due_day_28_across_february_and_year_end():
    assert due_dates(date(2026, 11, 28), None, 28, through=date(2027, 3, 1)) == [
        date(2026, 11, 28),
        date(2026, 12, 28),
        date(2027, 1, 28),
        date(2027, 2, 28),
    ]


def test_due_dates_through_before_first_due_is_empty():
    assert due_dates(date(2026, 1, 15), None, 1, through=date(2026, 1, 31)) == []


def test_due_dates_open_ended_stops_at_through():
    assert due_dates(date(2026, 1, 1), None, 1, through=date(2026, 3, 31))[-1] == date(2026, 3, 1)
