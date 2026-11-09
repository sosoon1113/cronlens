import pytest

from cronlens.crontab import CronJob, load_crontab, parse_crontab

USER_CRONTAB = """\
SHELL=/bin/bash
MAILTO=""

# Nightly backup
30 2 * * * /opt/backup.sh --full > /var/log/backup.log 2>&1
*/5 * * * *   curl -fsS https://example.com/ping

# 0 * * * * disabled-job
15 * * * * echo "after disabled"
@daily /usr/bin/cleanup
@reboot /usr/bin/start-agent
CRON_TZ=Europe/Berlin
0 8 * * mon-fri /usr/bin/standup-reminder
0 25 * * * broken
0 0 * *
"""

SYSTEM_CRONTAB = """\
17 * * * * root cd / && run-parts --report /etc/cron.hourly
@daily www-data /usr/bin/php /var/www/cron.php
0 4 * * * root
@weekly root
"""


@pytest.fixture
def user_crontab():
    return parse_crontab(USER_CRONTAB, source="user.crontab")


def job_at(crontab, line):
    return next(job for job in crontab.jobs if job.line == line)


class TestUserCrontab:
    def test_finds_every_job(self, user_crontab):
        assert [job.line for job in user_crontab.jobs] == [5, 6, 9, 10, 11, 13]

    def test_environment_is_recorded(self, user_crontab):
        assert user_crontab.env == {
            "SHELL": "/bin/bash",
            "MAILTO": "",
            "CRON_TZ": "Europe/Berlin",
        }

    def test_job_fields(self, user_crontab):
        job = job_at(user_crontab, 5)
        assert job.schedule == "30 2 * * *"
        assert job.command == "/opt/backup.sh --full > /var/log/backup.log 2>&1"
        assert job.comment == "Nightly backup"
        assert job.user is None
        assert job.expression.hour.values == {2}

    def test_extra_spaces_before_command(self, user_crontab):
        assert job_at(user_crontab, 6).command == "curl -fsS https://example.com/ping"

    def test_comment_only_labels_the_next_line(self, user_crontab):
        assert job_at(user_crontab, 6).comment is None

    def test_commented_out_job_is_not_a_label(self, user_crontab):
        assert job_at(user_crontab, 9).comment is None

    def test_macro_job(self, user_crontab):
        job = job_at(user_crontab, 10)
        assert job.schedule == "@daily"
        assert job.expression.normalized == "0 0 * * *"

    def test_reboot_job(self, user_crontab):
        job = job_at(user_crontab, 11)
        assert job.is_reboot
        assert job.expression is None
        assert job.command == "/usr/bin/start-agent"
        assert job not in user_crontab.scheduled_jobs
        assert len(user_crontab.scheduled_jobs) == 5

    def test_cron_tz_applies_to_following_jobs(self, user_crontab):
        assert job_at(user_crontab, 10).timezone is None
        assert job_at(user_crontab, 13).timezone == "Europe/Berlin"

    def test_invalid_lines_become_issues(self, user_crontab):
        issues = {issue.line: issue for issue in user_crontab.issues}
        assert sorted(issues) == [14, 15]
        assert "out of range" in issues[14].message
        assert issues[15].message == "expected 5 time fields and a command"
        assert issues[15].text == "0 0 * *"


class TestSystemCrontab:
    def test_user_column(self):
        crontab = parse_crontab(SYSTEM_CRONTAB, system=True)
        first, second = crontab.jobs
        assert (first.user, first.command) == (
            "root",
            "cd / && run-parts --report /etc/cron.hourly",
        )
        assert (second.user, second.command) == ("www-data", "/usr/bin/php /var/www/cron.php")

    def test_missing_command(self):
        crontab = parse_crontab(SYSTEM_CRONTAB, system=True)
        messages = {issue.line: issue.message for issue in crontab.issues}
        assert messages == {
            3: "expected 5 time fields, a user and a command",
            4: "expected a user and a command after the schedule",
        }


def test_label_prefers_comment():
    job = CronJob(line=1, schedule="@daily", command="run", expression=None, comment="Backups")
    assert job.label == "Backups"


def test_label_truncates_long_commands():
    job = CronJob(line=1, schedule="@daily", command="x" * 80, expression=None)
    assert len(job.label) == 48
    assert job.label.endswith("...")


def test_quoted_environment_values():
    crontab = parse_crontab("PATH='/usr/bin:/bin'\nGREETING = \"hello world\"\n")
    assert crontab.env == {"PATH": "/usr/bin:/bin", "GREETING": "hello world"}


def test_load_crontab_from_file(tmp_path):
    path = tmp_path / "crontab"
    path.write_text("# Ping\n* * * * * ping\n", encoding="utf-8")
    crontab = load_crontab(path)
    assert crontab.source == str(path)
    assert crontab.jobs[0].label == "Ping"


def test_empty_crontab():
    crontab = parse_crontab("")
    assert crontab.jobs == []
    assert crontab.issues == []
