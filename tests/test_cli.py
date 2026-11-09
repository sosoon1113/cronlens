from datetime import timedelta

import pytest
from click.testing import CliRunner

from cronlens import __version__, cli
from cronlens.cli import humanize_delta, main


def run(*args):
    return CliRunner().invoke(main, list(args))


@pytest.fixture
def wide_console(monkeypatch):
    """Stop rich from wrapping table rows at the default 80 columns."""
    monkeypatch.setattr(cli.console, "width", 200)


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


CRONTAB = """\
# Nightly backup
30 2 * * * /opt/backup.sh
@reboot /opt/start.sh
CRON_TZ=Mars/Base
0 9 * * * /opt/report.sh
0 0 30 2 * /opt/never.sh
0 99 * * * /opt/broken.sh
"""


class TestJobs:
    @pytest.fixture
    def crontab_path(self, tmp_path):
        path = tmp_path / "crontab"
        path.write_text(CRONTAB, encoding="utf-8")
        return path

    def test_lists_jobs(self, crontab_path, wide_console):
        result = run("jobs", str(crontab_path), "--tz", "UTC", "--from", "2026-11-09T00:00")
        assert result.exit_code == 0
        lines = result.stdout.splitlines()
        backup = next(line for line in lines if "Nightly backup" in line)
        assert "At 02:30" in backup
        assert "Mon 2026-11-09 02:30 UTC" in backup
        assert "At system startup" in result.stdout
        assert "unknown CRON_TZ 'Mars/Base'" in result.stdout
        assert "never" in next(line for line in lines if "/opt/never.sh" in line)

    def test_reports_unparseable_lines(self, crontab_path):
        result = run("jobs", str(crontab_path))
        assert "warning:" in result.stderr
        assert ":7: hour value 99 is out of range" in result.stderr

    def test_reads_stdin(self):
        result = CliRunner().invoke(main, ["jobs", "-"], input="@hourly /opt/tick.sh\n")
        assert result.exit_code == 0
        assert "/opt/tick.sh" in result.stdout


class TestCheck:
    def write(self, tmp_path, text):
        path = tmp_path / "crontab"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_clean_crontab_passes(self, tmp_path):
        path = self.write(tmp_path, "0 1 * * * a\n0 2 * * * b\n")
        result = run("check", path, "--tz", "UTC")
        assert result.exit_code == 0
        assert "2 jobs checked. No problems found." in result.output

    def test_errors_fail(self, tmp_path, wide_console):
        path = self.write(tmp_path, "0 0 30 2 * never\n0 1 * * * ok\n")
        result = run("check", path, "--tz", "UTC")
        assert result.exit_code == 1
        assert "never fires: day 30 never occurs in February" in result.output
        assert "2 jobs checked: 1 error, 0 warnings, 0 notes" in result.output

    def test_warnings_pass_unless_strict(self, tmp_path):
        path = self.write(tmp_path, "0 0 * * * a\n0 0 * * * b\n")
        assert run("check", path, "--tz", "UTC").exit_code == 0
        assert run("check", path, "--tz", "UTC", "--strict").exit_code == 1

    def test_days_option(self, tmp_path, wide_console):
        path = self.write(tmp_path, "0 0 * * * a\n0 0 * * * b\n")
        result = run("check", path, "--tz", "UTC", "--from", "2026-11-09T00:00", "--days", "3")
        assert "3 times in the next 3 days" in result.output


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
