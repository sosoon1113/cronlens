"""Command-line interface for cronlens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo

import click
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from cronlens import __version__
from cronlens.describe import compact_values, describe
from cronlens.errors import CronLensError
from cronlens.expression import CronExpression
from cronlens.parser import parse
from cronlens.schedule import next_runs
from cronlens.timezones import get_zone

console = Console(highlight=False)


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


def _elapsed(start: datetime, end: datetime) -> timedelta:
    # Subtract in UTC: aware datetimes sharing a tzinfo subtract by wall clock.
    return end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
