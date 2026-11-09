"""Parsed representation of a cron expression."""

from __future__ import annotations

from dataclasses import dataclass

from cronlens.fields import FieldSpec


@dataclass(frozen=True)
class CronField:
    """A single parsed field: the text as written plus the values it matches."""

    spec: FieldSpec
    raw: str
    values: frozenset[int]

    @property
    def is_wildcard(self) -> bool:
        """True when the field starts with ``*``.

        Cron uses this (not the set of values) to decide how day-of-month and
        day-of-week combine, so ``*/2`` counts as a wildcard here.
        """
        return self.raw.startswith("*")

    @property
    def is_full(self) -> bool:
        """True when the field matches every value in its domain."""
        return self.values == frozenset(self.spec.domain)

    def sorted_values(self) -> list[int]:
        return sorted(self.values)

    def __contains__(self, value: object) -> bool:
        return value in self.values


@dataclass(frozen=True)
class CronExpression:
    """A fully parsed five-field cron expression."""

    source: str
    minute: CronField
    hour: CronField
    day_of_month: CronField
    month: CronField
    day_of_week: CronField

    @property
    def fields(self) -> tuple[CronField, CronField, CronField, CronField, CronField]:
        return (self.minute, self.hour, self.day_of_month, self.month, self.day_of_week)

    @property
    def normalized(self) -> str:
        """The five raw fields joined by single spaces."""
        return " ".join(field.raw for field in self.fields)

    def __str__(self) -> str:
        return self.source
