"""Command-line interface for cronlens."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone, tzinfo
from typing import TextIO

import click
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cronlens import __version__
from cronlens.analyze import Severity, busiest_hours, check_crontab, week_start, weekly_load
from cronlens.crontab import CronJob, Crontab, parse_crontab
from cronlens.describe import compact_values, describe
from cronlens.errors import CronLensError
from cronlens.expression import CronExpression
from cronlens.heatmap import DAY_LABELS, render_heatmap, render_legend
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
        cronlens check /etc/crontab --system
        cronlens heatmap my.crontab --tz UTC
    """


json_option = click.option("--json", "as_json", is_flag=True, help="Print JSON instead of text.")


@main.command()
@click.argument("expression", nargs=-1, required=True)
@click.option(
    "--fields", "show_fields", is_flag=True, help="Also show how each field was interpreted."
)
@json_option
def explain(expression: tuple[str, ...], show_fields: bool, as_json: bool) -> None:
    """Describe EXPRESSION in plain English."""
    expr = _parse_expression(expression)
    if as_json:
        _emit_json(
            {
                "expression": expr.source,
                "normalized": expr.normalized,
                "description": describe(expr),
                "fields": {
                    field.spec.name: {"raw": field.raw, "values": field.sorted_values()}
                    for field in expr.fields
                },
            }
        )
        return

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
@json_option
def next_command(
    expression: tuple[str, ...],
    count: int,
    tz_name: str | None,
    start_text: str | None,
    as_json: bool,
) -> None:
    """List the next run times of EXPRESSION."""
    expr = _parse_expression(expression)
    zone = _resolve_zone(tz_name)
    start = _resolve_start(start_text, zone)

    runs = next_runs(expr, start, count, zone)
    if not runs:
        raise click.ClickException(f"{expr.source!r} never fires")
    if as_json:
        _emit_json(
            {
                "expression": expr.source,
                "description": describe(expr),
                "timezone": _zone_name(zone, start),
                "from": start.isoformat(),
                "runs": [run.isoformat() for run in runs],
            }
        )
        return
    for run in runs:
        console.print(f"{format_run(run)}  [dim]{humanize_delta(_elapsed(start, run))}[/dim]")


@main.command()
@click.argument("crontab_file", metavar="CRONTAB", type=click.File("r", encoding="utf-8"))
@click.option("--system", is_flag=True, help="Parse as a system crontab (with a user column).")
@click.option("--tz", "tz_name", metavar="ZONE", help="IANA timezone (default: local time).")
@click.option("--from", "start_text", metavar="DATETIME", help="ISO 8601 start (default: now).")
@json_option
def jobs(
    crontab_file: TextIO,
    system: bool,
    tz_name: str | None,
    start_text: str | None,
    as_json: bool,
) -> None:
    """List the jobs in CRONTAB with a description and their next run.

    Use - as CRONTAB to read from standard input.
    """
    crontab = _read_crontab(crontab_file, system)
    zone = _resolve_zone(tz_name)
    start = _resolve_start(start_text, zone)
    summaries = [(job, *_summarize_job(job, start, zone)) for job in crontab.jobs]

    if as_json:
        _emit_json(
            {
                "source": crontab.source,
                "jobs": [
                    {
                        "line": job.line,
                        "schedule": job.schedule,
                        "command": job.command,
                        "user": job.user,
                        "label": job.label,
                        "timezone": job.timezone,
                        "description": description,
                        "next_run": run.isoformat() if run else None,
                        "note": note,
                    }
                    for job, description, run, note in summaries
                ],
                "issues": [
                    {"line": issue.line, "text": issue.text, "message": issue.message}
                    for issue in crontab.issues
                ],
            }
        )
        return

    table = Table(box=box.SIMPLE_HEAD, pad_edge=False)
    table.add_column("Line", justify="right", style="dim")
    table.add_column("Schedule", no_wrap=True)
    table.add_column("When")
    table.add_column("Next run")
    table.add_column("Job")
    for job, description, run, note in summaries:
        upcoming = format_run(run) if run else (note or "-")
        table.add_row(
            str(job.line), escape(job.schedule), description, escape(upcoming), escape(job.label)
        )

    console.print(table)
    _report_issues(crontab)


@main.command()
@click.argument("crontab_file", metavar="CRONTAB", type=click.File("r", encoding="utf-8"))
@click.option("--system", is_flag=True, help="Parse as a system crontab (with a user column).")
@click.option("--tz", "tz_name", metavar="ZONE", help="IANA timezone (default: local time).")
@click.option("--from", "start_text", metavar="DATETIME", help="ISO 8601 start (default: now).")
@click.option(
    "--days",
    default=7,
    show_default=True,
    type=click.IntRange(1, 366),
    help="How many days ahead to look for collisions.",
)
@click.option("--strict", is_flag=True, help="Treat warnings as failures.")
@json_option
@click.pass_context
def check(
    ctx: click.Context,
    crontab_file: TextIO,
    system: bool,
    tz_name: str | None,
    start_text: str | None,
    days: int,
    strict: bool,
    as_json: bool,
) -> None:
    """Audit CRONTAB for invalid lines, impossible schedules and collisions.

    Exits with status 1 when errors are found (or warnings, with --strict).
    """
    crontab = _read_crontab(crontab_file, system)
    zone = _resolve_zone(tz_name)
    start = _resolve_start(start_text, zone)
    findings = check_crontab(crontab, start=start, tz=zone, days=days)
    counts = Counter(finding.severity for finding in findings)
    errors, warnings = counts[Severity.ERROR], counts[Severity.WARNING]
    failed = bool(errors or (strict and warnings))

    if as_json:
        _emit_json(
            {
                "source": crontab.source,
                "jobs": len(crontab.jobs),
                "passed": not failed,
                "summary": {severity.value: counts[severity] for severity in Severity},
                "findings": [finding.to_dict() for finding in findings],
            }
        )
        if failed:
            ctx.exit(1)
        return

    if findings:
        table = Table(box=box.SIMPLE_HEAD, pad_edge=False)
        table.add_column("Severity", no_wrap=True)
        table.add_column("Line", justify="right", no_wrap=True)
        table.add_column("Finding")
        for finding in findings:
            style = _SEVERITY_STYLES[finding.severity]
            lines = ", ".join(str(line) for line in finding.lines)
            table.add_row(
                f"[{style}]{finding.severity.value}[/{style}]", lines, escape(finding.message)
            )
        console.print(table)

    checked = _plural(len(crontab.jobs), "job")
    if findings:
        console.print(
            f"{checked} checked: {_plural(errors, 'error')}, "
            f"{_plural(warnings, 'warning')}, {_plural(counts[Severity.INFO], 'note')}"
        )
    else:
        console.print(f"{checked} checked. No problems found.")

    if failed:
        ctx.exit(1)


_SEVERITY_STYLES = {
    Severity.ERROR: "bold red",
    Severity.WARNING: "yellow",
    Severity.INFO: "cyan",
}


@main.command()
@click.argument("crontab_file", metavar="CRONTAB", type=click.File("r", encoding="utf-8"))
@click.option("--system", is_flag=True, help="Parse as a system crontab (with a user column).")
@click.option("--tz", "tz_name", metavar="ZONE", help="IANA timezone (default: local time).")
@click.option(
    "--week-of", "week_text", metavar="DATE", help="Show the week containing DATE (default: now)."
)
@click.option("--ascii", "force_ascii", is_flag=True, help="Draw with plain ASCII characters.")
def heatmap(
    crontab_file: TextIO,
    system: bool,
    tz_name: str | None,
    week_text: str | None,
    force_ascii: bool,
) -> None:
    """Show how many jobs start in each hour of the week."""
    crontab = _read_crontab(crontab_file, system)
    zone = _resolve_zone(tz_name)
    start = week_start(_resolve_start(week_text, zone, option="--week-of"))
    grid = weekly_load(crontab.scheduled_jobs, start, zone)
    unicode = not force_ascii and console.encoding.lower().startswith("utf")

    console.print(f"Job starts per hour, week of {start:%Y-%m-%d} ({start.tzname()})\n")
    console.print(render_heatmap(grid, unicode=unicode))
    console.print()
    console.print(render_legend(grid, unicode=unicode))

    busiest = busiest_hours(grid)
    if busiest:
        cells = ", ".join(
            f"{DAY_LABELS[day]} {hour:02d}:00 ({count})" for day, hour, count in busiest
        )
        console.print(f"Busiest hours: {cells}")
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


def _emit_json(data: object) -> None:
    click.echo(json.dumps(data, indent=2))


def _zone_name(zone: tzinfo, moment: datetime) -> str:
    """IANA key when available (``Europe/Berlin``), otherwise the abbreviation."""
    return getattr(zone, "key", None) or moment.tzname() or str(zone)


def _summarize_job(
    job: CronJob, start: datetime, zone: tzinfo
) -> tuple[str, datetime | None, str | None]:
    """Return ``(description, next run, note)`` for a crontab job."""
    if job.expression is None:
        return "At system startup", None, None
    description = describe(job.expression)
    job_zone = _job_zone(job, zone)
    if job_zone is None:
        return description, None, f"unknown CRON_TZ {job.timezone!r}"
    run = next_run(job.expression, start, job_zone)
    return description, run, None if run else "never fires"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


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


def _resolve_start(text: str | None, zone: tzinfo, *, option: str = "--from") -> datetime:
    if text is None:
        return datetime.now(zone)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise InputError(
            f"invalid {option} value {text!r}; expected ISO 8601 such as 2026-11-09T08:00"
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
        # soft_wrap keeps "file:line: message" on one line, whatever the terminal width.
        err_console.print(
            f"[yellow]warning:[/yellow] {escape(crontab.source)}:{issue.line}: "
            f"{escape(issue.message)}",
            soft_wrap=True,
        )


def _elapsed(start: datetime, end: datetime) -> timedelta:
    # Subtract in UTC: aware datetimes sharing a tzinfo subtract by wall clock.
    return end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
