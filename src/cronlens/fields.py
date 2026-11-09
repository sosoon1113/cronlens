"""Definitions of the five standard cron fields."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldSpec:
    """Static description of one cron field and the values it accepts."""

    name: str
    min: int
    max: int
    #: Largest canonical value. Day-of-week accepts 7 as an alias for Sunday (0),
    #: so its ``max`` is 7 but its canonical maximum is 6.
    canonical_max: int | None = None
    #: Case-insensitive names accepted in place of numbers (``jan``, ``mon``...).
    names: Mapping[str, int] = field(default_factory=dict, compare=False, hash=False)

    @property
    def domain(self) -> range:
        """Every canonical value this field can take."""
        top = self.max if self.canonical_max is None else self.canonical_max
        return range(self.min, top + 1)

    def contains(self, value: int) -> bool:
        """Return True if *value* is accepted by this field (before normalization)."""
        return self.min <= value <= self.max

    def normalize(self, value: int) -> int:
        """Fold alternate spellings onto their canonical value (e.g. Sunday 7 -> 0)."""
        if self.canonical_max is not None and value > self.canonical_max:
            return value - (self.canonical_max + 1)
        return value


MONTH_NAMES = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}

WEEKDAY_NAMES = {
    name: number for number, name in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"))
}

MINUTE = FieldSpec("minute", 0, 59)
HOUR = FieldSpec("hour", 0, 23)
DAY_OF_MONTH = FieldSpec("day-of-month", 1, 31)
MONTH = FieldSpec("month", 1, 12, names=MONTH_NAMES)
DAY_OF_WEEK = FieldSpec("day-of-week", 0, 7, canonical_max=6, names=WEEKDAY_NAMES)

#: Fields in the order they appear in a cron expression.
FIELDS: tuple[FieldSpec, ...] = (MINUTE, HOUR, DAY_OF_MONTH, MONTH, DAY_OF_WEEK)
