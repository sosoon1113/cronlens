from datetime import date, datetime, timedelta, timezone

import pytest

from cronlens import parse
from cronlens.schedule import (
    cron_weekday,
    day_matches,
    iter_runs,
    matches,
    next_run,
    next_runs,
    runs_between,
)

UTC = timezone.utc


def at(*args, tz=UTC):
    return datetime(*args, tzinfo=tz)


def fmt(runs):
    return [run.strftime("%Y-%m-%d %H:%M") for run in runs]


def test_cron_weekday_uses_sunday_zero():
    assert cron_weekday(date(2026, 11, 8)) == 0  # Sunday
    assert cron_weekday(date(2026, 11, 9)) == 1  # Monday
    assert cron_weekday(date(2026, 11, 14)) == 6  # Saturday


class TestNextRuns:
    def test_every_five_minutes(self):
        runs = next_runs(parse("*/5 * * * *"), at(2026, 11, 9, 10, 2), count=3)
        assert fmt(runs) == ["2026-11-09 10:05", "2026-11-09 10:10", "2026-11-09 10:15"]

    def test_start_is_exclusive(self):
        runs = next_runs(parse("0 * * * *"), at(2026, 11, 9, 10, 0), count=2)
        assert fmt(runs) == ["2026-11-09 11:00", "2026-11-09 12:00"]

    def test_seconds_are_ignored_when_rounding(self):
        runs = next_runs(parse("* * * * *"), at(2026, 11, 9, 10, 0, 59), count=1)
        assert fmt(runs) == ["2026-11-09 10:01"]

    def test_rolls_over_day_month_and_year(self):
        runs = next_runs(parse("30 23 31 12 *"), at(2026, 11, 9), count=2)
        assert fmt(runs) == ["2026-12-31 23:30", "2027-12-31 23:30"]

    def test_weekdays_only(self):
        # 2026-11-13 is a Friday.
        runs = next_runs(parse("0 9 * * mon-fri"), at(2026, 11, 13, 12, 0), count=2)
        assert fmt(runs) == ["2026-11-16 09:00", "2026-11-17 09:00"]

    def test_skips_months_that_do_not_match(self):
        runs = next_runs(parse("0 0 1 jun,dec *"), at(2026, 6, 15), count=3)
        assert fmt(runs) == ["2026-12-01 00:00", "2027-06-01 00:00", "2027-12-01 00:00"]

    def test_day_31_skips_short_months(self):
        runs = next_runs(parse("0 0 31 * *"), at(2027, 1, 31, 1, 0), count=3)
        assert fmt(runs) == ["2027-03-31 00:00", "2027-05-31 00:00", "2027-07-31 00:00"]

    def test_leap_day(self):
        assert fmt(next_runs(parse("0 0 29 2 *"), at(2026, 11, 9), count=2)) == [
            "2028-02-29 00:00",
            "2032-02-29 00:00",
        ]

    def test_impossible_expression_yields_nothing(self):
        assert next_runs(parse("0 0 30 2 *"), at(2026, 11, 9), count=3) == []
        assert next_run(parse("0 0 31 4 *"), at(2026, 11, 9)) is None

    def test_count_zero(self):
        assert next_runs(parse("* * * * *"), at(2026, 11, 9), count=0) == []

    def test_negative_count_is_rejected(self):
        with pytest.raises(ValueError):
            next_runs(parse("* * * * *"), at(2026, 11, 9), count=-1)

    def test_naive_start_is_treated_as_utc(self):
        run = next_run(parse("0 12 * * *"), datetime(2026, 11, 9, 8, 0))
        assert run == at(2026, 11, 9, 12, 0)


class TestTimezones:
    def test_runs_follow_target_wall_clock(self, berlin):
        start = at(2026, 11, 9, 7, 0)  # 08:00 in Berlin
        run = next_run(parse("30 9 * * *"), start, tz=berlin)
        assert run.tzinfo is berlin
        assert run.strftime("%H:%M") == "09:30"
        assert run.astimezone(UTC) == at(2026, 11, 9, 8, 30)

    def test_spring_forward_gap_is_skipped(self, new_york):
        # 2026-03-08 02:30 does not exist in New York.
        start = at(2026, 3, 7, 12, 0, tz=new_york)
        runs = next_runs(parse("30 2 * * *"), start, count=2, tz=new_york)
        assert fmt(runs) == ["2026-03-09 02:30", "2026-03-10 02:30"]

    def test_fall_back_runs_once(self, new_york):
        start = at(2026, 10, 31, 12, 0, tz=new_york)
        runs = next_runs(parse("30 1 * * *"), start, count=2, tz=new_york)
        assert fmt(runs) == ["2026-11-01 01:30", "2026-11-02 01:30"]
        assert [run.utcoffset() for run in runs] == [timedelta(hours=-4), timedelta(hours=-5)]

    def test_runs_are_strictly_increasing_across_fall_back(self, new_york):
        start = at(2026, 11, 1, 0, 0, tz=new_york)
        runs = next_runs(parse("*/20 * * * *"), start, count=12, tz=new_york)
        instants = [run.astimezone(UTC) for run in runs]
        assert instants == sorted(set(instants))

    def test_start_during_repeated_hour(self, new_york):
        # 01:15 EST happens after the first 01:30 (EDT), so the next run is the next day.
        start = datetime(2026, 11, 1, 1, 15, tzinfo=new_york, fold=1)
        run = next_run(parse("30 1 * * *"), start, tz=new_york)
        assert run.strftime("%Y-%m-%d %H:%M") == "2026-11-02 01:30"


class TestMatching:
    def test_matches(self):
        expr = parse("15 10 * * 1")
        assert matches(expr, at(2026, 11, 9, 10, 15))
        assert not matches(expr, at(2026, 11, 9, 10, 16))
        assert not matches(expr, at(2026, 11, 10, 10, 15))

    def test_day_matches_checks_month(self):
        expr = parse("0 0 * 1 *")
        assert day_matches(expr, date(2027, 1, 5))
        assert not day_matches(expr, date(2026, 12, 5))


class TestRunsBetween:
    def test_interval_is_half_open(self):
        runs = runs_between(parse("0 * * * *"), at(2026, 11, 9, 0, 0), at(2026, 11, 9, 3, 0))
        assert fmt(runs) == ["2026-11-09 00:00", "2026-11-09 01:00", "2026-11-09 02:00"]

    def test_inclusive_iteration(self):
        runs = iter_runs(parse("0 * * * *"), at(2026, 11, 9, 5, 0), inclusive=True)
        assert fmt([next(runs)]) == ["2026-11-09 05:00"]

    def test_counts_a_full_day(self):
        start = at(2026, 11, 9)
        runs = list(runs_between(parse("*/15 * * * *"), start, start + timedelta(days=1)))
        assert len(runs) == 96
