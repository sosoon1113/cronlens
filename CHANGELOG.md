# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Crontab warnings (`file:line: message`) are no longer wrapped onto several lines
  when the file path is long or the terminal is narrow.

## [0.1.0] - 2026-11-09

First public release.

### Added

- Parser for five-field cron expressions with ranges, steps, lists, month/weekday
  names and `@yearly`/`@monthly`/`@weekly`/`@daily`/`@hourly` macros.
- Next-run calculation in any IANA timezone, skipping DST gaps and running repeated
  wall-clock times once.
- Plain-English descriptions of expressions.
- Crontab loader for user and system formats, including `@reboot`, environment
  lines and `CRON_TZ`.
- `cronlens explain`, `next`, `jobs`, `check` and `heatmap` commands.
- `check` finds unparseable lines, schedules that never fire, unknown `CRON_TZ`
  values and jobs that start in the same minute; exits non-zero on errors.
- `--json` output for `explain`, `next`, `jobs` and `check`.

### Fixed

- Day-of-month and day-of-week now combine with cron's OR rule when both are
  restricted (e.g. `0 0 13 * 5` runs on the 13th and on every Friday).

[Unreleased]: https://github.com/sosoon1113/cronlens/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sosoon1113/cronlens/releases/tag/v0.1.0
