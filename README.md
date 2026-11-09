# cronlens

[![CI](https://github.com/sosoon1113/cronlens/actions/workflows/ci.yml/badge.svg)](https://github.com/sosoon1113/cronlens/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://github.com/sosoon1113/cronlens)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Explain, preview and audit cron schedules from your terminal.**

Cron syntax is compact and easy to get subtly wrong. `cronlens` tells you what an
expression actually means, when it will run next (in any timezone, DST included),
and what is wrong with a crontab before it bites you in production.

```console
$ cronlens explain "*/15 9-17 * * 1-5"
Every 15 minutes, between 09:00 and 17:59, on weekdays

$ cronlens next "0 9 * * mon-fri" --tz Europe/Berlin -n 2
Mon 2026-11-16 09:00 CET  in 2d 23h
Tue 2026-11-17 09:00 CET  in 3d 23h
```

## Features

- **Plain-English descriptions** of any five-field expression, names and `@macros` included.
- **Next run times** in any IANA timezone, with correct handling of DST gaps and repeats.
- **Crontab auditing**: invalid lines, schedules that can never fire, unknown `CRON_TZ`
  values and jobs that start in the same minute.
- **Weekly heatmap** of job starts per hour to spot load spikes.
- **User and system crontabs** (`/etc/crontab`, `/etc/cron.d/*` with a user column).
- **JSON output** on every command for scripts and CI, with meaningful exit codes.
- A small, typed **Python API** if you want to embed it.

## Installation

cronlens needs Python 3.10 or newer.

```bash
# with pipx (recommended for CLI tools)
pipx install git+https://github.com/sosoon1113/cronlens.git

# or with pip
pip install git+https://github.com/sosoon1113/cronlens.git
```

From a clone:

```bash
git clone https://github.com/sosoon1113/cronlens.git
cd cronlens
pip install -e .
```

`python -m cronlens` works as well as the `cronlens` command.

## Usage

> Quote expressions (`"*/5 * * * *"`) so your shell doesn't expand the asterisks.

### `explain` — what does this expression mean?

```console
$ cronlens explain "0 0 13 * 5"
At 00:00, on the 13th of the month or on Friday

$ cronlens explain --fields "*/20 8-18 * * mon-fri"
Every 20 minutes, between 08:00 and 18:59, on weekdays
Field          Raw       Values
────────────────────────────────
minute         */20      0,20,40
hour           8-18      8-18
day-of-month   *         1-31
month          *         1-12
day-of-week    mon-fri   1-5
```

### `next` — when will it run?

```console
$ cronlens next "30 2 * * *" --tz America/New_York --from 2026-03-06T12:00 -n 3
Sat 2026-03-07 02:30 EST  in 14h 30m
Mon 2026-03-09 02:30 EDT  in 2d 13h
Tue 2026-03-10 02:30 EDT  in 3d 13h
```

02:30 on 8 March doesn't exist in New York (clocks jump from 02:00 to 03:00), so
that run is skipped. Without `--tz`, your local timezone is used; without `--from`,
the current time.

### `jobs` — what's in this crontab?

```console
$ cronlens jobs examples/sample.crontab --tz Europe/Berlin
 Line   Schedule       When                         Next run                   Job
 ───────────────────────────────────────────────────────────────────────────────────────────────────────────
    7   0 0 * * *      At 00:00                     Tue 2026-11-10 00:00 CET   Rotate application logs
   10   30 2 * * *     At 02:30                     Tue 2026-11-10 02:30 CET   Nightly database backup
   13   */15 * * * *   Every 15 minutes             Mon 2026-11-09 08:15 CET   Refresh the search index
   16   0 9 * * mon    At 09:00, on Monday          Mon 2026-11-09 09:00 CET   Weekly report for the team
   19   0 0 * * *      At 00:00                     Tue 2026-11-10 00:00 CET   Purge temp files older than a week
   22   * * * * *      Every minute                 Mon 2026-11-09 08:01 CET   Health check ping
   25   0 6 30 2 *     At 06:00, on February 30th   never fires                February month-end invoices
   27   @reboot        At system startup            -                          /opt/app/bin/start-workers
   31   30 9 * * 1-5   At 09:30, on weekdays        Mon 2026-11-09 09:30 EST   Snapshot prices at the US market open

warning: examples/sample.crontab:34: hour value 25 is out of range (0-23)
```

A comment directly above a job is used as its label, and jobs under `CRON_TZ` are shown in
their own timezone. Pipe your live crontab in with `crontab -l | cronlens jobs -`.

### `check` — is anything wrong?

```console
$ cronlens check examples/sample.crontab --tz Europe/Berlin
 Severity     Line   Finding
 ───────────────────────────────────────────────────────────────────────────────────────────────────────────
 error          25   '0 6 30 2 *' never fires: day 30 never occurs in February
 error          34   hour value 25 is out of range (0-23): '0 25 * * * /opt/app/bin/warm-cache'
 warning     7, 13   'Rotate application logs' and 'Refresh the search index' start at the same minute 7 times in
                     the next 7 days (first at Mon 2026-11-09 00:00)
 warning     7, 19   'Rotate application logs' and 'Purge temp files older than a week' start at the same minute 7
                     times in the next 7 days (first at Mon 2026-11-09 00:00)
 warning    10, 13   'Nightly database backup' and 'Refresh the search index' start at the same minute 7 times in
                     the next 7 days (first at Mon 2026-11-09 02:30)
 warning    13, 16   'Refresh the search index' and 'Weekly report for the team' start at the same minute once in
                     the next 7 days (first at Mon 2026-11-09 09:00)
 warning    13, 19   'Refresh the search index' and 'Purge temp files older than a week' start at the same minute 7
                     times in the next 7 days (first at Mon 2026-11-09 00:00)
 warning    13, 31   'Refresh the search index' and 'Snapshot prices at the US market open' start at the same minute
                     5 times in the next 7 days (first at Mon 2026-11-09 15:30)
 info           22   '* * * * *' runs every minute; skipped in collision checks
 info           27   runs only at system startup; not schedule-checked

9 jobs checked: 2 errors, 6 warnings, 2 notes
```

| Exit code | Meaning                                                   |
|-----------|-----------------------------------------------------------|
| `0`       | No errors (warnings allowed unless `--strict` is passed)  |
| `1`       | At least one error, or a warning with `--strict`           |
| `2`       | Bad input: invalid expression, unknown timezone, bad date |

That makes it easy to run as a CI step:

```yaml
- run: pipx run --spec git+https://github.com/sosoon1113/cronlens.git cronlens check deploy/crontab --strict
```

Use `--days N` to change the collision window (default 7) and `--system` for crontabs with a
user column.

### `heatmap` — when is the box busiest?

```console
$ cronlens heatmap examples/sample.crontab --tz Europe/Berlin
Job starts per hour, week of 2026-11-09 (CET)

     00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Mon  ██ ░░ ▓▓ ░░ ░░ ░░ ░░ ░░ ░░ ▓▓ ░░ ░░ ░░ ░░ ░░ ▓▓ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░
Tue  ██ ░░ ▓▓ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ▓▓ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░
...
Sun  ██ ░░ ▓▓ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░ ░░

·· none   ░░ ▒▒ ▓▓ ██  64 to 66 starts per hour
Busiest hours: Mon 00:00 (66), Tue 00:00 (66), Wed 00:00 (66)
```

Shades are spread between the quietest and busiest hour, so hot spots stand out even
when an every-minute job is in the mix. Pass `--week-of 2026-12-21` for another week,
or `--ascii` for terminals without block characters.

### JSON output

`explain`, `next`, `jobs` and `check` all accept `--json`:

```console
$ cronlens next "0 9 * * mon-fri" --tz Europe/Berlin -n 2 --json
{
  "expression": "0 9 * * mon-fri",
  "description": "At 09:00, on weekdays",
  "timezone": "Europe/Berlin",
  "from": "2026-11-09T08:00:00+01:00",
  "runs": [
    "2026-11-09T09:00:00+01:00",
    "2026-11-10T09:00:00+01:00"
  ]
}
```

## Supported syntax

| Syntax            | Example            | Meaning                                  |
|-------------------|--------------------|------------------------------------------|
| `*`               | `* * * * *`        | every value                              |
| value             | `30 2 * * *`       | a single value                           |
| range             | `0 9-17 * * *`     | inclusive range                          |
| step              | `*/15 * * * *`     | every 15th value                         |
| range with step   | `0 8-18/2 * * *`   | every 2nd hour from 08 to 18             |
| start with step   | `5/20 * * * *`     | every 20th minute starting at 5          |
| list              | `0 9,13,17 * * *`  | any combination of the above             |
| names             | `0 9 * jan-mar mon-fri` | three-letter month and weekday names |
| macros            | `@daily`           | `@yearly`, `@annually`, `@monthly`, `@weekly`, `@daily`, `@midnight`, `@hourly`, `@reboot` |

Day-of-week runs from `0` (Sunday) to `6`; `7` is also accepted for Sunday.

In crontab files, blank lines and `#` comments are skipped, `NAME=value` lines are read as
environment variables, and `CRON_TZ=Zone/Name` applies to every job below it.

### How cronlens interprets edge cases

- **Day-of-month and day-of-week.** Like Vixie cron, if *both* fields are restricted,
  a day matches when **either** one does: `0 0 13 * 5` runs on the 13th *and* on every
  Friday. If either field starts with `*` (including `*/2`), both must match.
- **Daylight saving time.** Times that don't exist on the local clock (spring forward)
  are skipped. Times that happen twice (fall back) run once, at the first occurrence.
- **Impossible schedules** such as `0 0 30 2 *` are detected by searching up to 40
  years ahead, enough for leap-day schedules pinned to a weekday.

## Python API

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from cronlens import describe, next_runs, parse

expr = parse("0 9 * * mon-fri")
print(describe(expr))  # At 09:00, on weekdays

start = datetime(2026, 11, 13, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))
for run in next_runs(expr, start, count=3):
    print(run.isoformat())
# 2026-11-16T09:00:00+01:00
# 2026-11-17T09:00:00+01:00
# 2026-11-18T09:00:00+01:00
```

Auditing a crontab:

```python
from cronlens.analyze import check_crontab
from cronlens.crontab import load_crontab

crontab = load_crontab("examples/sample.crontab")
for finding in check_crontab(crontab, start=start, tz=ZoneInfo("Europe/Berlin")):
    print(finding.severity.value, finding.lines, finding.message)
```

## Project layout

```
src/cronlens/
├── fields.py      # field definitions (ranges, names)
├── parser.py      # expression parser and @macros
├── expression.py  # CronExpression / CronField models
├── schedule.py    # next-run calculation, timezone and DST handling
├── describe.py    # plain-English descriptions
├── crontab.py     # crontab file loader
├── analyze.py     # audits: impossible schedules, collisions, weekly load
├── heatmap.py     # terminal heatmap rendering
├── timezones.py   # timezone lookup
└── cli.py         # click-based command-line interface
```

## Development

```bash
git clone https://github.com/sosoon1113/cronlens.git
cd cronlens
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest --cov                     # run the test suite with coverage
ruff check . && ruff format .    # lint and format
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details. Release notes are in
[CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE) © 2026 sosoon1113
