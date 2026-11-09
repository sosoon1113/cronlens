from datetime import datetime, timezone

import pytest

from cronlens.errors import UnknownTimezoneError
from cronlens.timezones import get_zone, local_zone


def test_utc_aliases():
    assert get_zone("UTC") is timezone.utc
    assert get_zone("utc") is timezone.utc


def test_iana_name():
    assert str(get_zone("Europe/Berlin")) == "Europe/Berlin"


@pytest.mark.parametrize("name", ["Mars/Olympus_Mons", "../etc/passwd", "Europe/"])
def test_unknown_zone(name):
    with pytest.raises(UnknownTimezoneError) as info:
        get_zone(name)
    assert info.value.name == name


@pytest.mark.parametrize("name", [None, "", "local", "LOCAL"])
def test_local_zone_is_default(name):
    zone = get_zone(name)
    assert datetime.now(zone).utcoffset() is not None


def test_tz_environment_variable_wins(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    assert str(local_zone()) == "Asia/Tokyo"


def test_invalid_tz_environment_variable_is_ignored(monkeypatch):
    monkeypatch.setenv("TZ", "Not/AZone")
    assert datetime.now(local_zone()).utcoffset() is not None
