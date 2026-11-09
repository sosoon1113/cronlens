from datetime import datetime, timezone

import pytest

from cronlens.analyze import busiest_hours, week_start, weekly_load
from cronlens.crontab import parse_crontab
from cronlens.heatmap import MAX_LEVEL, count_range, intensity, render_heatmap, render_legend

UTC = timezone.utc
MONDAY = datetime(2026, 11, 9, tzinfo=UTC)


def grid_for(text, tz=UTC):
    return weekly_load(parse_crontab(text).jobs, MONDAY, tz)


def test_week_start():
    assert week_start(datetime(2026, 11, 12, 15, 30, tzinfo=UTC)) == MONDAY
    assert week_start(MONDAY) == MONDAY
    assert week_start(datetime(2026, 11, 15, 23, 59, tzinfo=UTC)) == MONDAY


class TestWeeklyLoad:
    def test_weekday_job(self):
        grid = grid_for("0 9 * * 1-5 standup\n")
        assert [row[9] for row in grid] == [1, 1, 1, 1, 1, 0, 0]
        assert sum(map(sum, grid)) == 5

    def test_counts_every_start(self):
        grid = grid_for("*/30 * * * * a\n0 12 * * * b\n")
        assert grid[0][11] == 2
        assert grid[0][12] == 3
        assert sum(map(sum, grid)) == 7 * 48 + 7

    def test_reboot_and_bad_timezones_are_skipped(self):
        grid = grid_for("@reboot a\nCRON_TZ=Bad/Zone\n0 0 * * * b\n")
        assert sum(map(sum, grid)) == 0

    def test_cron_tz_is_converted(self):
        grid = grid_for("CRON_TZ=America/New_York\n0 9 * * * report\n")
        assert all(row[14] == 1 for row in grid)


def test_busiest_hours():
    grid = grid_for("0 9 * * * a\n30 9 * * 1 b\n0 3 * * 2 c\n")
    assert busiest_hours(grid) == [(0, 9, 2), (1, 3, 1), (1, 9, 1)]
    assert busiest_hours([[0] * 24 for _ in range(7)]) == []


@pytest.mark.parametrize(
    ("count", "low", "high", "level"),
    [
        (0, 1, 10, 0),
        (5, 0, 0, 0),
        (1, 1, 1, MAX_LEVEL),
        (60, 1, 60, MAX_LEVEL),
        (1, 1, 60, 1),
        (8, 1, 60, 3),
        (64, 64, 66, 1),
        (66, 64, 66, MAX_LEVEL),
    ],
)
def test_intensity(count, low, high, level):
    assert intensity(count, low, high) == level


def test_count_range():
    assert count_range([[0, 3, 9], [0, 0, 1]]) == (1, 9)
    assert count_range([[0, 0]]) == (0, 0)


class TestRender:
    def test_layout(self):
        grid = [[0] * 24 for _ in range(7)]
        grid[2][13] = 4
        lines = render_heatmap(grid).plain.splitlines()
        assert len(lines) == 8
        assert lines[0].startswith("     00 01 02")
        assert lines[0].endswith("23")
        assert lines[3].startswith("Wed  ")
        cells = lines[3][5:].split(" ")
        assert len(cells) == 24
        assert cells[13] == "██"
        assert set(cells[:13] + cells[14:]) == {"··"}

    def test_ascii_mode(self):
        grid = [[1] * 24 for _ in range(7)]
        plain = render_heatmap(grid, unicode=False).plain
        assert "@@" in plain
        assert plain.isascii()

    def test_layout_is_shaded_between_quietest_and_busiest_hour(self):
        grid = [[60] * 24 for _ in range(7)]
        grid[0][0] = 66
        lines = render_heatmap(grid).plain.splitlines()
        assert lines[1].split()[1] == "██"
        assert lines[1].split()[2] == "░░"

    def test_legend(self):
        grid = [[0] * 24 for _ in range(7)]
        grid[0][0], grid[1][1] = 2, 12
        assert render_legend(grid).plain.endswith(" 2 to 12 starts per hour")
        grid[0][0] = 12
        assert render_legend(grid, unicode=False).plain.endswith(" 12 starts per hour")
