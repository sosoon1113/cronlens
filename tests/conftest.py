from datetime import timezone
from zoneinfo import ZoneInfo

import pytest

UTC = timezone.utc


@pytest.fixture
def new_york():
    return ZoneInfo("America/New_York")


@pytest.fixture
def berlin():
    return ZoneInfo("Europe/Berlin")
