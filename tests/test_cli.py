from datetime import timedelta

import pytest
from click.testing import CliRunner

from cronlens import __version__
from cronlens.cli import humanize_delta, main


def run(*args):
    return CliRunner().invoke(main, list(args))


def test_version():
    result = run("--version")
    assert result.exit_code == 0
    assert __version__ in result.output


class TestExplain:
    def test_describes_expression(self):
        result = run("explain", "*/15 9-17 * * 1-5")
        assert result.exit_code == 0
        assert result.output.strip() == "Every 15 minutes, between 09:00 and 17:59, on weekdays"

    def test_accepts_unquoted_fields(self):
        result = run("explain", "0", "9", "*", "*", "1-5")
        assert result.output.strip() == "At 09:00, on weekdays"

    def test_fields_table(self):
        result = run("explain", "--fields", "*/20 9 * * mon-fri")
        assert result.exit_code == 0
        assert "day-of-week" in result.output
        assert "mon-fri" in result.output
        assert "0,20,40" in result.output

    def test_invalid_expression(self):
        result = run("explain", "0 25 * * *")
        assert result.exit_code == 2
        assert "hour value 25 is out of range" in result.output


class TestNext:
    def test_lists_runs_from_fixed_start(self):
        result = run(
            "next", "0 9 * * 1-5", "--from", "2026-11-13T10:00", "--tz", "Europe/Berlin", "-n", "2"
        )
        assert result.exit_code == 0
        assert result.output.splitlines() == [
            "Mon 2026-11-16 09:00 CET  in 2d 23h",
            "Tue 2026-11-17 09:00 CET  in 3d 23h",
        ]

    def test_default_count_is_five(self):
        result = run("next", "@hourly", "--from", "2026-11-09T00:30", "--tz", "UTC")
        assert len(result.output.splitlines()) == 5
        assert result.output.splitlines()[0] == "Mon 2026-11-09 01:00 UTC  in 30m"

    def test_offset_in_start_is_respected(self):
        result = run(
            "next",
            "0 12 * * *",
            "--from",
            "2026-11-09T10:30+00:00",
            "--tz",
            "Europe/Berlin",
            "-n",
            "1",
        )
        assert result.output.strip() == "Mon 2026-11-09 12:00 CET  in 30m"

    def test_never_fires(self):
        result = run("next", "0 0 30 2 *", "--tz", "UTC")
        assert result.exit_code == 1
        assert "never fires" in result.output

    def test_unknown_timezone(self):
        result = run("next", "* * * * *", "--tz", "Nowhere/Special")
        assert result.exit_code == 2
        assert "unknown timezone" in result.output

    def test_invalid_start(self):
        result = run("next", "* * * * *", "--from", "yesterday")
        assert result.exit_code == 2
        assert "ISO 8601" in result.output


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=20), "in 1m"),
        (timedelta(minutes=5), "in 5m"),
        (timedelta(hours=2), "in 2h"),
        (timedelta(hours=2, minutes=30), "in 2h 30m"),
        (timedelta(days=3), "in 3d"),
        (timedelta(days=3, hours=4, minutes=59), "in 3d 4h"),
    ],
)
def test_humanize_delta(delta, expected):
    assert humanize_delta(delta) == expected
