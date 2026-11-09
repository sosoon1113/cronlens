from datetime import timezone
from zoneinfo import ZoneInfo

import pytest
from rich.console import Console

from cronlens import cli

UTC = timezone.utc


@pytest.fixture(autouse=True)
def plain_console(monkeypatch):
    """Render CLI output without ANSI codes at a fixed width.

    Keeps assertions stable regardless of the environment, e.g. FORCE_COLOR
    or COLUMNS being set on CI runners.
    """
    monkeypatch.setattr(cli, "console", Console(highlight=False, color_system=None, width=80))
    monkeypatch.setattr(
        cli, "err_console", Console(stderr=True, highlight=False, color_system=None, width=80)
    )


@pytest.fixture
def new_york():
    return ZoneInfo("America/New_York")


@pytest.fixture
def berlin():
    return ZoneInfo("Europe/Berlin")
