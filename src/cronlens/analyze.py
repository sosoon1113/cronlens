"""Audit crontabs for mistakes and scheduling hot spots."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from enum import Enum
from itertools import combinations

from cronlens.crontab import CronJob, Crontab
from cronlens.describe import MONTH_NAMES, join_words
from cronlens.errors import CronLensError
from cronlens.expression import CronExpression
from cronlens.schedule import SEARCH_HORIZON_YEARS, next_run, runs_between
from cronlens.timezones import get_zone

#: The longest each month can be (February counts leap years).
_MONTH_LENGTHS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


@dataclass(frozen=True)
class Finding:
    """One problem or observation reported by :func:`check_crontab`."""

    severity: Severity
    code: str
    message: str
    lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class Collision:
    """Two jobs that start in the same minute."""

    first: CronJob
    second: CronJob
    count: int
    first_at: datetime


def never_fires(expr: CronExpression, start: datetime | None = None) -> bool:
    """Return True if *expr* has no run within the search horizon."""
    start = start or datetime.now(timezone.utc)
    return next_run(expr, start, timezone.utc) is None


def impossible_reason(expr: CronExpression) -> str:
    """Best-effort explanation of why *expr* never fires."""
    if expr.day_of_week.is_full:
        months = expr.month.sorted_values()
        first_day = min(expr.day_of_month.values)
        if all(first_day > _MONTH_LENGTHS[month - 1] for month in months):
            names = join_words([MONTH_NAMES[month - 1] for month in months])
            return f"day {first_day} never occurs in {names}"
    return f"no matching date in the next {SEARCH_HORIZON_YEARS} years"


def find_collisions(
    jobs: Iterable[CronJob], start: datetime, end: datetime, tz: tzinfo
) -> list[Collision]:
    """Find pairs of jobs that start in the same minute in ``[start, end)``.

    Jobs whose minute field is ``*`` are ignored because they collide with
    everything. Each job runs in its own ``CRON_TZ`` if it has one; reported
    times are converted to *tz*. Results are sorted by how often they collide.
    """
    by_minute: dict[datetime, list[CronJob]] = defaultdict(list)
    for job in jobs:
        if job.expression is None or job.expression.minute.is_full:
            continue
        zone = get_zone(job.timezone) if job.timezone else tz
        for run in runs_between(job.expression, start, end, zone):
            by_minute[run.astimezone(timezone.utc)].append(job)

    counts: dict[tuple[int, int], int] = defaultdict(int)
    firsts: dict[tuple[int, int], tuple[CronJob, CronJob, datetime]] = {}
    for minute in sorted(by_minute):
        for first, second in combinations(by_minute[minute], 2):
            key = (first.line, second.line)
            counts[key] += 1
            firsts.setdefault(key, (first, second, minute.astimezone(tz)))

    collisions = [
        Collision(first, second, counts[key], first_at)
        for key, (first, second, first_at) in firsts.items()
    ]
    collisions.sort(key=lambda c: (-c.count, c.first.line, c.second.line))
    return collisions


def week_start(moment: datetime) -> datetime:
    """Return Monday 00:00 of the week containing *moment*, in the same timezone."""
    monday = moment.date() - timedelta(days=moment.weekday())
    return datetime.combine(monday, time(0), tzinfo=moment.tzinfo)


def weekly_load(jobs: Iterable[CronJob], start: datetime, tz: tzinfo) -> list[list[int]]:
    """Count job starts per hour for the week beginning at *start*.

    Returns a 7x24 grid indexed as ``grid[weekday][hour]`` with Monday as
    weekday 0, in the wall-clock time of *tz*. Jobs with an invalid
    ``CRON_TZ`` are left out.
    """
    grid = [[0] * 24 for _ in range(7)]
    end = start + timedelta(days=7)
    for job in jobs:
        if job.expression is None:
            continue
        try:
            zone = get_zone(job.timezone) if job.timezone else tz
        except CronLensError:
            continue
        for run in runs_between(job.expression, start, end, zone):
            local = run.astimezone(tz)
            grid[local.weekday()][local.hour] += 1
    return grid


def busiest_hours(grid: list[list[int]], limit: int = 3) -> list[tuple[int, int, int]]:
    """Return up to *limit* ``(weekday, hour, count)`` cells with the most starts."""
    cells = [
        (weekday, hour, count)
        for weekday, row in enumerate(grid)
        for hour, count in enumerate(row)
        if count
    ]
    cells.sort(key=lambda cell: (-cell[2], cell[0], cell[1]))
    return cells[:limit]


def check_crontab(
    crontab: Crontab,
    *,
    start: datetime,
    tz: tzinfo,
    days: int = 7,
) -> list[Finding]:
    """Audit *crontab* and return findings sorted by severity, then line."""
    findings = [
        Finding(Severity.ERROR, "invalid-line", f"{issue.message}: {issue.text!r}", (issue.line,))
        for issue in crontab.issues
    ]

    candidates: list[CronJob] = []
    for job in crontab.jobs:
        finding = _check_job(job, start)
        if finding is not None:
            findings.append(finding)
        if finding is None or finding.code == "every-minute":
            candidates.append(job)

    end = start + timedelta(days=days)
    window = "day" if days == 1 else f"{days} days"
    for collision in find_collisions(candidates, start, end, tz):
        times = "once" if collision.count == 1 else f"{collision.count} times"
        findings.append(
            Finding(
                Severity.WARNING,
                "collision",
                f"{collision.first.label!r} and {collision.second.label!r} start at the "
                f"same minute {times} in the next {window} "
                f"(first at {collision.first_at:%a %Y-%m-%d %H:%M})",
                (collision.first.line, collision.second.line),
            )
        )

    findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], f.lines))
    return findings


def _check_job(job: CronJob, start: datetime) -> Finding | None:
    lines = (job.line,)
    if job.expression is None:
        return Finding(
            Severity.INFO, "reboot", "runs only at system startup; not schedule-checked", lines
        )
    if job.timezone:
        try:
            get_zone(job.timezone)
        except CronLensError:
            return Finding(
                Severity.ERROR,
                "unknown-timezone",
                f"CRON_TZ {job.timezone!r} is not a known timezone",
                lines,
            )
    if never_fires(job.expression, start):
        reason = impossible_reason(job.expression)
        return Finding(
            Severity.ERROR, "never-fires", f"{job.schedule!r} never fires: {reason}", lines
        )
    if job.expression.minute.is_full:
        return Finding(
            Severity.INFO,
            "every-minute",
            f"{job.schedule!r} runs every minute; skipped in collision checks",
            lines,
        )
    return None
