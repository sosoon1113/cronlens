"""Render a week-by-hour grid of job starts in the terminal."""

from __future__ import annotations

import math
from collections.abc import Sequence

from rich.text import Text

DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

UNICODE_SHADES = ("··", "░░", "▒▒", "▓▓", "██")
#: Fallback for consoles that cannot encode block characters.
ASCII_SHADES = ("..", "::", "++", "##", "@@")
STYLES = ("dim", "green", "yellow", "dark_orange", "bold red")

#: Highest intensity level; level 0 means "no runs".
MAX_LEVEL = len(UNICODE_SHADES) - 1


def intensity(count: int, low: int, high: int) -> int:
    """Map *count* to a level from 0 to :data:`MAX_LEVEL`.

    *low* and *high* are the smallest and largest non-zero counts in the grid.
    Levels are spread between them on a log scale, so hot spots stay visible
    even when an every-minute job adds 60 starts to every hour.
    """
    if count <= 0 or high <= 0:
        return 0
    low = max(1, min(low, high))
    if high == low:
        return MAX_LEVEL
    count = min(max(count, low), high)
    scaled = (math.log(count) - math.log(low)) / (math.log(high) - math.log(low))
    return 1 + round((MAX_LEVEL - 1) * scaled)


def count_range(grid: Sequence[Sequence[int]]) -> tuple[int, int]:
    """Return the smallest and largest non-zero counts, or ``(0, 0)``."""
    counts = [count for row in grid for count in row if count]
    return (min(counts), max(counts)) if counts else (0, 0)


def render_heatmap(grid: Sequence[Sequence[int]], *, unicode: bool = True) -> Text:
    """Render a 7x24 ``grid[weekday][hour]`` with an hour header row."""
    shades = UNICODE_SHADES if unicode else ASCII_SHADES
    low, high = count_range(grid)

    text = Text()
    text.append("     " + " ".join(f"{hour:02d}" for hour in range(24)), style="dim")
    for label, row in zip(DAY_LABELS, grid, strict=True):
        text.append("\n")
        text.append(f"{label}  ", style="bold")
        for hour, count in enumerate(row):
            level = intensity(count, low, high)
            text.append(shades[level], style=STYLES[level])
            if hour < len(row) - 1:
                text.append(" ")
    return text


def render_legend(grid: Sequence[Sequence[int]], *, unicode: bool = True) -> Text:
    """Render a one-line key explaining the shades."""
    shades = UNICODE_SHADES if unicode else ASCII_SHADES
    low, high = count_range(grid)

    text = Text()
    text.append(shades[0], style=STYLES[0])
    text.append(" none   ")
    for level in range(1, MAX_LEVEL + 1):
        text.append(shades[level], style=STYLES[level])
        text.append(" ")
    if high == low:
        text.append(f" {high} starts per hour")
    else:
        text.append(f" {low} to {high} starts per hour")
    return text
