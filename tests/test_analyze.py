from datetime import datetime, timedelta, timezone

import pytest

from cronlens import parse
from cronlens.analyze import (
    Severity,
    check_crontab,
    find_collisions,
    impossible_reason,
    never_fires,
)
from cronlens.crontab import parse_crontab

UTC = timezone.utc
MONDAY = datetime(2026, 11, 9, tzinfo=UTC)
WEEK_LATER = MONDAY + timedelta(days=7)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("0 0 30 2 *", True),
        ("0 0 31 4,6,9,11 *", True),
        ("0 0 29 2 *", False),
        ("0 0 31 * *", False),
        ("*/5 * * * *", False),
    ],
)
def test_never_fires(expression, expected):
    assert never_fires(parse(expression), MONDAY) is expected


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        ("0 0 30 2 *", "day 30 never occurs in February"),
        ("0 0 31 4,6 *", "day 31 never occurs in April and June"),
    ],
)
def test_impossible_reason(expression, reason):
    assert impossible_reason(parse(expression)) == reason


def jobs(text):
    return parse_crontab(text).jobs


class TestCollisions:
    def test_same_daily_time(self):
        collisions = find_collisions(jobs("0 0 * * * a\n0 0 * * * b\n"), MONDAY, WEEK_LATER, UTC)
        assert len(collisions) == 1
        collision = collisions[0]
        assert (collision.first.command, collision.second.command) == ("a", "b")
        assert collision.count == 7
        assert collision.first_at == MONDAY

    def test_overlapping_steps(self):
        collisions = find_collisions(jobs("*/15 * * * * a\n0 * * * * b\n"), MONDAY, WEEK_LATER, UTC)
        assert collisions[0].count == 7 * 24

    def test_no_collision_when_minutes_differ(self):
        assert find_collisions(jobs("0 * * * * a\n30 * * * * b\n"), MONDAY, WEEK_LATER, UTC) == []

    def test_every_minute_jobs_are_ignored(self):
        assert find_collisions(jobs("* * * * * a\n0 0 * * * b\n"), MONDAY, WEEK_LATER, UTC) == []

    def test_sorted_by_frequency(self):
        text = "0 0 * * * a\n0 0 * * 1 b\n0 * * * * c\n"
        counts = [c.count for c in find_collisions(jobs(text), MONDAY, WEEK_LATER, UTC)]
        assert counts == sorted(counts, reverse=True)
        assert counts == [7, 1, 1]

    def test_respects_cron_tz(self):
        # 09:00 in New York is 14:00 UTC in November.
        text = "0 14 * * * utc-job\nCRON_TZ=America/New_York\n0 9 * * * ny-job\n"
        collisions = find_collisions(jobs(text), MONDAY, WEEK_LATER, UTC)
        assert collisions[0].count == 7
        assert collisions[0].first_at == datetime(2026, 11, 9, 14, 0, tzinfo=UTC)


SAMPLE = """\
# Backups
0 2 * * * backup
# Reports
0 2 * * * report
* * * * * healthcheck
0 0 30 2 * never
@reboot start
CRON_TZ=Nowhere/Land
0 5 * * * lost
0 77 * * * broken
"""


class TestCheckCrontab:
    @pytest.fixture
    def findings(self):
        return check_crontab(parse_crontab(SAMPLE), start=MONDAY, tz=UTC)

    def test_codes(self, findings):
        assert [(f.severity, f.code, f.lines) for f in findings] == [
            (Severity.ERROR, "never-fires", (6,)),
            (Severity.ERROR, "unknown-timezone", (9,)),
            (Severity.ERROR, "invalid-line", (10,)),
            (Severity.WARNING, "collision", (2, 4)),
            (Severity.INFO, "every-minute", (5,)),
            (Severity.INFO, "reboot", (7,)),
        ]

    def test_messages(self, findings):
        messages = {f.code: f.message for f in findings}
        assert messages["never-fires"] == (
            "'0 0 30 2 *' never fires: day 30 never occurs in February"
        )
        assert messages["collision"] == (
            "'Backups' and 'Reports' start at the same minute 7 times in the next 7 days "
            "(first at Mon 2026-11-09 02:00)"
        )
        assert messages["invalid-line"].startswith("hour value 77 is out of range")

    def test_window_size(self):
        findings = check_crontab(parse_crontab(SAMPLE), start=MONDAY, tz=UTC, days=1)
        collision = next(f for f in findings if f.code == "collision")
        assert "once in the next day" in collision.message

    def test_clean_crontab(self):
        crontab = parse_crontab("0 1 * * * a\n0 2 * * * b\n")
        assert check_crontab(crontab, start=MONDAY, tz=UTC) == []
