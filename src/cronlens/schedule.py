"""Work out when a cron expression fires.

Run times are computed on the wall clock of a timezone, the same way cron
itself does it. Around daylight-saving transitions:

* wall-clock times that do not exist (the "spring forward" gap) are skipped;
* wall-clock times that happen twice ("fall back") fire once, at the first
  occurrence.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from itertools import islice, takewhile

from cronlens.expression import CronExpression

#: How far ahead to search before concluding that an expression never fires.
#: Leap-day schedules restricted to a weekday can take up to 28 years to recur.
SEARCH_HORIZON_YEARS = 40


def cron_weekday(day: date) -> int:
    """Return the cron day-of-week number for *day* (Sunday=0 ... Saturday=6)."""
    return (day.weekday() + 1) % 7


def day_matches(expr: CronExpression, day: date) -> bool:
    """Return True if *expr* can fire at some time on *day*."""
    if day.month not in expr.month:
        return False
    return day.day in expr.day_of_month and cron_weekday(day) in expr.day_of_week


def matches(expr: CronExpression, moment: datetime) -> bool:
    """Return True if *expr* fires at the wall-clock minute of *moment*."""
    return (
        moment.minute in expr.minute
        and moment.hour in expr.hour
        and day_matches(expr, moment.date())
    )


def iter_runs(
    expr: CronExpression,
    start: datetime,
    tz: tzinfo | None = None,
    *,
    inclusive: bool = False,
) -> Iterator[datetime]:
    """Yield run times after *start* in chronological order.

    *tz* is the timezone whose wall clock the schedule follows. It defaults to
    ``start``'s timezone; naive datetimes are treated as UTC unless *tz* is
    given. With ``inclusive=True`` a run exactly at *start* is included.

    The iterator stops once :data:`SEARCH_HORIZON_YEARS` have been searched,
    so expressions that can never fire (``0 0 30 2 *``) simply yield nothing.
    """
    zone = tz or start.tzinfo or timezone.utc
    if start.tzinfo is None:
        start = start.replace(tzinfo=zone)
    start_utc = start.astimezone(timezone.utc)

    local = start.astimezone(zone).replace(tzinfo=None)
    cursor = local.replace(second=0, microsecond=0)
    if not inclusive or cursor != local:
        cursor += timedelta(minutes=1)

    minutes = expr.minute.sorted_values()
    hours = expr.hour.sorted_values()
    limit = date(min(cursor.year + SEARCH_HORIZON_YEARS, 9999), 1, 1)

    day = cursor.date()
    while day < limit:
        if day.month not in expr.month:
            day = _first_of_next_month(day)
            continue
        if day_matches(expr, day):
            on_first_day = day == cursor.date()
            for hour in hours:
                if on_first_day and hour < cursor.hour:
                    continue
                for minute in minutes:
                    if on_first_day and hour == cursor.hour and minute < cursor.minute:
                        continue
                    run = _localize(datetime.combine(day, time(hour, minute)), zone)
                    if run is None:
                        continue
                    run_utc = run.astimezone(timezone.utc)
                    if run_utc > start_utc or (inclusive and run_utc == start_utc):
                        yield run
        day += timedelta(days=1)


def next_runs(
    expr: CronExpression,
    start: datetime,
    count: int = 5,
    tz: tzinfo | None = None,
) -> list[datetime]:
    """Return up to *count* run times strictly after *start*."""
    if count < 0:
        raise ValueError("count must not be negative")
    return list(islice(iter_runs(expr, start, tz), count))


def next_run(expr: CronExpression, start: datetime, tz: tzinfo | None = None) -> datetime | None:
    """Return the first run strictly after *start*, or None if it never fires."""
    return next(iter_runs(expr, start, tz), None)


def runs_between(
    expr: CronExpression,
    start: datetime,
    end: datetime,
    tz: tzinfo | None = None,
) -> Iterator[datetime]:
    """Yield runs in the half-open interval ``[start, end)``."""
    if end.tzinfo is None:
        end = end.replace(tzinfo=tz or start.tzinfo or timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    runs = iter_runs(expr, start, tz, inclusive=True)
    return takewhile(lambda run: run.astimezone(timezone.utc) < end_utc, runs)


def _first_of_next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _localize(wall: datetime, zone: tzinfo) -> datetime | None:
    """Attach *zone* to a naive wall-clock time, or return None if it doesn't exist."""
    aware = wall.replace(tzinfo=zone, fold=0)
    round_trip = aware.astimezone(timezone.utc).astimezone(zone)
    if round_trip.replace(tzinfo=None, fold=0) != wall:
        return None
    return aware
