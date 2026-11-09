"""Load jobs from crontab files.

Both formats are supported:

* user crontabs (``crontab -e``): five time fields followed by the command;
* system crontabs (``/etc/crontab``, ``/etc/cron.d/*``): an extra user column
  between the schedule and the command.

Blank lines and comments are skipped, ``NAME=value`` lines are recorded as
environment variables, and ``CRON_TZ=Zone`` applies to every job below it. A
comment line directly above a job is kept as that job's label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from cronlens.errors import CronParseError
from cronlens.expression import CronExpression
from cronlens.parser import parse

_ENV_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_LABEL_WIDTH = 48


@dataclass(frozen=True)
class CronJob:
    """One scheduled entry of a crontab."""

    line: int
    schedule: str
    command: str
    #: ``None`` for ``@reboot`` jobs, which have no time-based schedule.
    expression: CronExpression | None
    user: str | None = None
    comment: str | None = None
    #: Value of ``CRON_TZ`` in effect for this job, if any.
    timezone: str | None = None

    @property
    def is_reboot(self) -> bool:
        return self.expression is None

    @property
    def label(self) -> str:
        """A short human-friendly name: the comment above the job, or its command."""
        if self.comment:
            return self.comment
        if len(self.command) <= _LABEL_WIDTH:
            return self.command
        return self.command[: _LABEL_WIDTH - 3] + "..."


@dataclass(frozen=True)
class CrontabIssue:
    """A line that could not be parsed."""

    line: int
    text: str
    message: str


@dataclass
class Crontab:
    """The parsed contents of a crontab file."""

    source: str
    jobs: list[CronJob] = field(default_factory=list)
    issues: list[CrontabIssue] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    @property
    def scheduled_jobs(self) -> list[CronJob]:
        """Jobs with a time-based schedule (everything except ``@reboot``)."""
        return [job for job in self.jobs if not job.is_reboot]


def load_crontab(path: str | Path, *, system: bool = False) -> Crontab:
    """Read and parse the crontab at *path*."""
    path = Path(path)
    return parse_crontab(path.read_text(encoding="utf-8"), system=system, source=str(path))


def parse_crontab(text: str, *, system: bool = False, source: str = "<string>") -> Crontab:
    """Parse crontab *text*. Invalid lines are collected in ``Crontab.issues``."""
    crontab = Crontab(source=source)
    comment: str | None = None
    zone: str | None = None

    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            comment = None
            continue

        if line.startswith("#"):
            text_after_hash = line.lstrip("#").strip()
            # Commented-out jobs are not labels for the line below them.
            comment = None if _looks_like_entry(text_after_hash) else text_after_hash or None
            continue

        assignment = _ENV_ASSIGNMENT.match(line)
        if assignment:
            name, value = assignment.group(1), _unquote(assignment.group(2).strip())
            crontab.env[name] = value
            if name == "CRON_TZ":
                zone = value or None
            comment = None
            continue

        try:
            job = _parse_job(line, number, system=system, comment=comment, zone=zone)
        except CronParseError as exc:
            crontab.issues.append(CrontabIssue(number, line, str(exc)))
        else:
            crontab.jobs.append(job)
        comment = None

    return crontab


def _parse_job(
    line: str, number: int, *, system: bool, comment: str | None, zone: str | None
) -> CronJob:
    extra = 1 if system else 0
    if line.startswith("@"):
        parts = line.split(None, 1 + extra)
        schedule, rest = parts[0], parts[1:]
        expression = None if schedule.lower() == "@reboot" else parse(schedule)
    else:
        parts = line.split(None, 5 + extra)
        if len(parts) < 6 + extra:
            what = (
                "5 time fields, a user and a command" if system else "5 time fields and a command"
            )
            raise CronParseError(f"expected {what}")
        schedule, rest = " ".join(parts[:5]), parts[5:]
        expression = parse(schedule)

    if len(rest) < 1 + extra:
        raise CronParseError(
            "expected a user and a command after the schedule" if system else "missing command"
        )

    user = rest[0] if system else None
    return CronJob(
        line=number,
        schedule=schedule,
        command=rest[-1],
        expression=expression,
        user=user,
        comment=comment,
        timezone=zone,
    )


def _looks_like_entry(text: str) -> bool:
    if text.startswith("@"):
        return True
    try:
        parse(" ".join(text.split()[:5]))
    except CronParseError:
        return False
    return True


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value
