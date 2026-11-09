"""Timezone lookup helpers."""

from __future__ import annotations

import os
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cronlens.errors import UnknownTimezoneError

_LOCALTIME = Path("/etc/localtime")


def get_zone(name: str | None = None) -> tzinfo:
    """Return the timezone called *name*.

    Accepts IANA names such as ``Europe/Berlin``, ``UTC``, and ``local``.
    An empty name also means the local timezone.
    """
    if not name or name.lower() == "local":
        return local_zone()
    if name.upper() in ("UTC", "Z"):
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise UnknownTimezoneError(name) from None


def local_zone() -> tzinfo:
    """Best-effort lookup of the machine's timezone.

    Prefers a DST-aware zone (``$TZ`` or ``/etc/localtime``) and falls back to
    the current fixed UTC offset, which is correct until the next DST change.
    """
    env_name = os.environ.get("TZ")
    if env_name:
        try:
            return ZoneInfo(env_name.lstrip(":"))
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass

    if _LOCALTIME.exists():
        try:
            with _LOCALTIME.open("rb") as handle:
                return ZoneInfo.from_file(handle, key="localtime")
        except (OSError, ValueError):
            pass

    fallback = datetime.now().astimezone().tzinfo
    return fallback if fallback is not None else timezone.utc
