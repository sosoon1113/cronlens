"""Parse five-field cron expressions into :class:`CronExpression` objects.

Supported syntax per field::

    *          every value
    5          a single value
    1-5        an inclusive range
    */15       every 15th value across the whole field
    10-40/10   every 10th value inside a range
    5/20       every 20th value starting at 5
    1,15,30    any comma-separated combination of the above

Months and weekdays may also be written as three-letter names (``jan``,
``mon-fri``), and the usual ``@daily``-style macros are expanded.
"""

from __future__ import annotations

from dataclasses import replace

from cronlens.errors import CronParseError
from cronlens.expression import CronExpression, CronField
from cronlens.fields import FIELDS, FieldSpec

#: Shorthand schedules understood by Vixie cron and its descendants.
MACROS: dict[str, str] = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}


def parse(expression: str) -> CronExpression:
    """Parse *expression*, e.g. ``"*/15 9-17 * * 1-5"`` or ``"@daily"``.

    Raises :class:`~cronlens.errors.CronParseError` if the expression is invalid.
    """
    source = expression.strip()
    if not source:
        raise CronParseError("expression is empty", expression=expression)
    if source.startswith("@"):
        return _parse_macro(source)

    parts = source.split()
    if len(parts) != len(FIELDS):
        raise CronParseError(
            f"expected {len(FIELDS)} fields, got {len(parts)}",
            expression=source,
        )

    try:
        minute, hour, dom, month, dow = (
            parse_field(raw, spec) for raw, spec in zip(parts, FIELDS, strict=True)
        )
    except CronParseError as exc:
        exc.expression = source
        raise

    return CronExpression(source, minute, hour, dom, month, dow)


def parse_field(raw: str, spec: FieldSpec) -> CronField:
    """Parse the text of a single field according to *spec*."""
    values: set[int] = set()
    for item in raw.split(","):
        if not item:
            raise CronParseError(f"empty list item in {spec.name} field {raw!r}", field=spec.name)
        values.update(_parse_item(item, spec))
    return CronField(spec=spec, raw=raw, values=frozenset(values))


def _parse_macro(source: str) -> CronExpression:
    key = source.lower()
    if key == "@reboot":
        raise CronParseError(
            "@reboot runs once at startup and has no time-based schedule",
            expression=source,
        )
    try:
        expanded = MACROS[key]
    except KeyError:
        raise CronParseError(f"unknown macro {source!r}", expression=source) from None
    return replace(parse(expanded), source=source)


def _parse_item(item: str, spec: FieldSpec) -> set[int]:
    base, has_step, step_text = item.partition("/")
    step = _parse_step(step_text, spec) if has_step else 1

    if base == "*":
        start, end = spec.min, spec.max
    elif "-" in base:
        low, _, high = base.partition("-")
        start, end = _parse_value(low, spec), _parse_value(high, spec)
        if start > end:
            raise CronParseError(
                f"range {base!r} in {spec.name} field ends before it starts",
                field=spec.name,
            )
    else:
        start = _parse_value(base, spec)
        # "5/20" means "every 20th value starting at 5".
        end = spec.max if has_step else start

    return {spec.normalize(value) for value in range(start, end + 1, step)}


def _parse_value(text: str, spec: FieldSpec) -> int:
    named = spec.names.get(text.lower())
    if named is not None:
        return named
    if not text.isdigit():
        raise CronParseError(f"invalid value {text!r} in {spec.name} field", field=spec.name)
    value = int(text)
    if not spec.contains(value):
        raise CronParseError(
            f"{spec.name} value {value} is out of range ({spec.min}-{spec.max})",
            field=spec.name,
        )
    return value


def _parse_step(text: str, spec: FieldSpec) -> int:
    if not text.isdigit() or int(text) == 0:
        raise CronParseError(
            f"step {text!r} in {spec.name} field must be a positive integer",
            field=spec.name,
        )
    return int(text)
