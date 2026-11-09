"""Command-line interface for cronlens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import TextIO

import click
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cronlens import __version__
from cronlens.crontab import CronJob, Crontab, parse_crontab
from cronlens.describe import compact_values, describe
from cronlens.errors import CronLensError
from cronlens.expression import CronExpression
from cronlens.parser import parse
from cronlens.schedule import next_run, next_runs
from cronlens.timezones import get_zone

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)


class InputError(click.ClickException):
    """Bad user input such as an invalid expression or unknown timezone."""

    exit_code = 2


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="cronlens")
def main() -> None:
    """Explain, preview and audit cron schedules.

    Quote expressions so your shell does not expand the asterisks:

    \b
        cronlens explain "*/15 9-17 * * 1-5"
        cronlens next "0 3 * * sun" --tz Europe/Berlin
        crontab -l | cronlens jobs -
    """


@main.command()
@click.argument("expression", nargs=-1, required=True)
@click.option(
    "--fields", "show_fields", is_flag=True, help="Also show how each field was interpreted."
)
def explain(expression: tuple[str, ...], show_fields: bool) -> None:
    """Describe EXPRESSION in plain English."""
    expr = _parse_expression(expression)
    console.print(describe(expr))
    if show_fields:
        console.print(_fields_table(expr))


@main.command(name="next")
@click.argument("expression", nargs=-1, required=True)
@click.option(
    "-n",
    "--count",
    default=5,
    show_default=True,
    type=click.IntRange(1, 1000),
    help="How many run times to show.",
)
@click.option("--tz", "tz_name", metavar="ZONE", help="IANA timezone (default: local time).")
@click.option("--from", "start_text", metavar="DATETIME", help="ISO 8601 start (default: now).")
def next_command(
    expression: tuple[str, ...], count: int, tz_name: str | None, start_text: str | None
) -> None:
    """List the next run times of EXPRESSION."""
    expr = _parse_expression(expression)
    zone = _resolve_zone(tz_name)
    start = _resolve_start(start_text, zone)

    runs = next_runs(expr, start, count, zone)
    if not runs:
        raise click.ClickException(f"{expr.source!r} never fires")
    for run in runs:
        console.print(f"{format_run(run)}  [dim]{humanize_delta(_elapsed(start, run))}[/dim]")


@main.command()
@click.argument("crontab_file", metavar="CRONTAB", type=click.File("r", encoding="utf-8"))
@click.option("--system", is_flag=True, help="Parse as a system crontab (with a user column).")
@click.option("--tz", "tz_name", metavar="ZONE", help="IANA timezone (default: local time).")
@click.option("--from", "start_text", metavar="DATETIME", help="ISO 8601 start (default: now).")
def jobs(crontab_file: TextIO, system: bool, tz_name: str | None, start_text: str | None) -> None:
    """List the jobs in CRONTAB with a description and their next run.

    Use - as CRONTAB to read from standard input.
    """
    crontab = _read_crontab(crontab_file, system)
    zone = _resolve_zone(tz_name)
    start = _resolve_start(start_text, zone)

    table = Table(box=box.SIMPLE_HEAD, pad_edge=False)
    table.add_column("Line", justify="right", style="dim")
    table.add_column("Schedule", no_wrap=True)
    table.add_column("When")
    table.add_column("Next run")
    table.add_column("Job")
    for job in crontab.jobs:
        if job.expression is None:
            when, upcoming = "At system startup", "-"
        else:
            when = describe(job.expression)
            job_zone = _job_zone(job, zone)
            if job_zone is None:
                upcoming = f"unknown CRON_TZ {job.timezone!r}"
            else:
                run = next_run(job.expression, start, job_zone)
                upcoming = format_run(run) if run else "never"
        table.add_row(
            str(job.line), escape(job.schedule), when, escape(upcoming), escape(job.label)
        )

    console.print(table)
    _report_issues(crontab)


# ------------------------------------------------------------------- formatting


def format_run(run: datetime) -> str:
    """Format a run time as ``Mon 2026-11-09 09:00 CET``."""
    return f"{run:%a %Y-%m-%d %H:%M} {run.tzname()}"


def humanize_delta(delta: timedelta) -> str:
    """Render a positive delta compactly: ``in 5m``, ``in 2h 30m``, ``in 3d 4h``."""
    minutes = max(0, -(-int(delta.total_seconds()) // 60))  # round up to whole minutes
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"in {days}d {hours}h" if hours else f"in {days}d"
    if hours:
        return f"in {hours}h {minutes}m" if minutes else f"in {hours}h"
    return f"in {minutes}m"


def _fields_table(expr: CronExpression) -> Table:
    table = Table(box=box.SIMPLE, show_edge=False, pad_edge=False)
    table.add_column("Field")
    table.add_column("Raw")
    table.add_column("Values")
    for field in expr.fields:
        table.add_row(field.spec.name, escape(field.raw), compact_values(field.sorted_values()))
    return table


# ------------------------------------------------------------------ input helpers


def _parse_expression(parts: tuple[str, ...]) -> CronExpression:
    text = " ".join(parts)
    try:
        return parse(text)
    except CronLensError as exc:
        raise InputError(f"invalid expression {text!r}: {exc}") from None


def _resolve_zone(name: str | None) -> tzinfo:
    try:
        return get_zone(name)
    except CronLensError as exc:
        raise InputError(str(exc)) from None


def _resolve_start(text: str | None, zone: tzinfo) -> datetime:
    if text is None:
        return datetime.now(zone)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise InputError(
            f"invalid --from value {text!r}; expected ISO 8601 such as 2026-11-09T08:00"
        ) from None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=zone)


def _read_crontab(handle: TextIO, system: bool) -> Crontab:
    return parse_crontab(handle.read(), system=system, source=handle.name)


def _job_zone(job: CronJob, default: tzinfo) -> tzinfo | None:
    """The timezone a job runs in, or None if its CRON_TZ is invalid."""
    if not job.timezone:
        return default
    try:
        return get_zone(job.timezone)
    except CronLensError:
        return None


def _report_issues(crontab: Crontab) -> None:
    for issue in crontab.issues:
        err_console.print(
            f"[yellow]warning:[/yellow] {escape(crontab.source)}:{issue.line}: "
            f"{escape(issue.message)}"
        )


def _elapsed(start: datetime, end: datetime) -> timedelta:
    # Subtract in UTC: aware datetimes sharing a tzinfo subtract by wall clock.
    return end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
