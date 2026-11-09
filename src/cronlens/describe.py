"""Turn cron expressions into plain-English sentences.

>>> from cronlens import parse
>>> describe(parse("*/15 9-17 * * 1-5"))
'Every 15 minutes, between 09:00 and 17:59, on weekdays'
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import pairwise

from cronlens.expression import CronExpression, CronField

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

#: Indexed by cron day-of-week number (Sunday=0).
WEEKDAY_NAMES = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

#: List every time explicitly ("At 09:00 and 17:30") up to this many combinations.
_MAX_LISTED_TIMES = 4


def describe(expr: CronExpression) -> str:
    """Return a one-sentence description of when *expr* fires."""
    text = _time_phrase(expr.minute, expr.hour)
    dom, month, dow = expr.day_of_month, expr.month, expr.day_of_week

    if len(dom.values) == 1 and len(month.values) == 1 and dow.is_full:
        (day,), (number,) = dom.values, month.values
        return f"{text}, on {MONTH_NAMES[number - 1]} {ordinal(day)}"

    return text + _day_clause(dom, dow) + _month_clause(month)


def ordinal(number: int) -> str:
    """Return ``1st``, ``2nd``, ``3rd``, ``4th``, ``11th``, ``21st``..."""
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def join_words(items: Sequence[str]) -> str:
    """Join items as English: ``a``, ``a and b``, ``a, b and c``."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def compact_values(values: Sequence[int]) -> str:
    """Render sorted values in cron-like shorthand, e.g. ``1-5,10`` or ``0-55/5``."""
    step = _step(values)
    if step and len(values) >= 5:
        return f"{values[0]}-{values[-1]}/{step}"
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in _runs(values))


# --------------------------------------------------------------------------- time


def _time_phrase(minute: CronField, hour: CronField) -> str:
    if minute.is_full and hour.is_full:
        return "Every minute"

    minutes, hours = minute.sorted_values(), hour.sorted_values()
    if len(minutes) * len(hours) <= _MAX_LISTED_TIMES:
        return "At " + join_words([f"{h:02d}:{m:02d}" for h in hours for m in minutes])

    text, repeats = _minute_phrase(minute)
    return text + _hour_clause(hour, minute_repeats=repeats)


def _minute_phrase(minute: CronField) -> tuple[str, bool]:
    """Describe the minute field; the flag says whether it repeats within an hour."""
    minutes = minute.sorted_values()
    if minute.is_full:
        return "Every minute", True

    step = _step(minutes)
    if step and _spans_field(minutes, step, minute):
        if 60 % step == 0:
            return f"Every {step} minutes", True
        return f"At every {ordinal(step)} minute", True
    if step and len(minutes) >= 3:
        return f"Every {step} minutes from minute {minutes[0]} through {minutes[-1]}", True

    runs = _runs(minutes)
    if len(runs) == 1 and runs[0][1] - runs[0][0] >= 2:
        return f"Every minute from minute {runs[0][0]} through {runs[0][1]}", True

    noun = "minute" if len(minutes) == 1 else "minutes"
    return f"At {noun} {_list_phrase(minutes)}", False


def _hour_clause(hour: CronField, *, minute_repeats: bool) -> str:
    hours = hour.sorted_values()
    if hour.is_full:
        return "" if minute_repeats else " past every hour"

    step = _step(hours)
    if step and (_spans_field(hours, step, hour) or len(hours) >= 3):
        every = f"every {ordinal(step)} hour"
        if not _spans_field(hours, step, hour):
            every += f" from {hours[0]} through {hours[-1]}"
        return f", during {every}" if minute_repeats else f" past {every}"

    runs = _runs(hours)
    if len(runs) == 1:
        first, last = runs[0]
        if minute_repeats:
            return f", between {first:02d}:00 and {last:02d}:59"
        if last - first >= 2:
            return f" past every hour from {first} through {last}"

    noun = "hour" if len(hours) == 1 else "hours"
    lead = ", during" if minute_repeats else " past"
    return f"{lead} {noun} {_list_phrase(hours)}"


# --------------------------------------------------------------------------- days


def _day_clause(dom: CronField, dow: CronField) -> str:
    either_matches = not (dom.is_wildcard or dow.is_wildcard)  # see schedule.day_matches
    if either_matches and (dom.is_full or dow.is_full):
        return ""  # e.g. "1-31" OR "mon" matches every day

    dom_text = None if dom.is_full else _dom_phrase(dom)
    dow_text = None if dow.is_full else _dow_phrase(dow)
    if dom_text and dow_text:
        if either_matches:
            return f", {dom_text} or {dow_text}"
        return f", {dom_text}, but only {dow_text}"
    text = dom_text or dow_text
    return f", {text}" if text else ""


def _dom_phrase(dom: CronField) -> str:
    days = dom.sorted_values()
    step = _step(days)
    if step and _spans_field(days, step, dom):
        return f"on every {ordinal(step)} day of the month"
    if step and len(days) >= 3:
        return (
            f"on every {ordinal(step)} day of the month "
            f"from the {ordinal(days[0])} through the {ordinal(days[-1])}"
        )
    return f"on the {_list_phrase(days, ordinal)} of the month"


def _dow_phrase(dow: CronField) -> str:
    days = dow.sorted_values()
    if days == [1, 2, 3, 4, 5]:
        return "on weekdays"
    if days == [0, 6]:
        return "on weekends"
    return f"on {_list_phrase(days, WEEKDAY_NAMES.__getitem__)}"


def _month_clause(month: CronField) -> str:
    if month.is_full:
        return ""
    months = month.sorted_values()
    step = _step(months)
    if step and len(months) >= 3 and _spans_field(months, step, month):
        return f", every {ordinal(step)} month"
    return f", in {_list_phrase(months, lambda number: MONTH_NAMES[number - 1])}"


# ------------------------------------------------------------------------ helpers


def _runs(values: Sequence[int]) -> list[tuple[int, int]]:
    """Group sorted values into inclusive ``(first, last)`` runs of consecutive numbers."""
    runs: list[tuple[int, int]] = []
    for value in values:
        if runs and value == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], value)
        else:
            runs.append((value, value))
    return runs


def _step(values: Sequence[int]) -> int | None:
    """Return the common gap if *values* are evenly spaced by 2 or more."""
    if len(values) < 2:
        return None
    gap = values[1] - values[0]
    if gap < 2 or any(b - a != gap for a, b in pairwise(values)):
        return None
    return gap


def _spans_field(values: Sequence[int], step: int, field: CronField) -> bool:
    """True if *values* look like ``*/step``: start at the minimum and run to the end."""
    domain = field.spec.domain
    return values[0] == domain.start and values[-1] + step > domain.stop - 1


def _list_phrase(values: Sequence[int], fmt: Callable[[int], str] = str) -> str:
    """Describe values as English, e.g. ``1, 3 and 5 through 9``."""
    parts: list[str] = []
    for first, last in _runs(values):
        if first == last:
            parts.append(fmt(first))
        elif last == first + 1:
            parts.extend([fmt(first), fmt(last)])
        else:
            parts.append(f"{fmt(first)} through {fmt(last)}")
    return join_words(parts)
