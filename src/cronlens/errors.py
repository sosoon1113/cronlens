"""Exception types raised by cronlens."""

from __future__ import annotations


class CronLensError(Exception):
    """Base class for every error raised by cronlens."""


class CronParseError(CronLensError, ValueError):
    """Raised when a cron expression cannot be parsed.

    ``field`` names the cron field that failed (``"minute"``, ``"hour"``...)
    when the problem is local to one field, and ``expression`` holds the full
    expression text when it is known.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        expression: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.expression = expression
