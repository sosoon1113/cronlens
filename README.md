# cronlens

Explain, preview and audit cron schedules from your terminal.

> Work in progress — crontab auditing is coming next.

## Installation

```bash
git clone https://github.com/sosoon1113/cronlens.git
cd cronlens
pip install -e .
```

Requires Python 3.10+.

## Usage

Describe an expression in plain English:

```console
$ cronlens explain "*/15 9-17 * * 1-5"
Every 15 minutes, between 09:00 and 17:59, on weekdays
```

Show the next run times, in any timezone:

```console
$ cronlens next "0 9 * * mon-fri" --tz Europe/Berlin -n 3
Mon 2026-11-16 09:00 CET  in 2d 23h
Tue 2026-11-17 09:00 CET  in 3d 23h
Wed 2026-11-18 09:00 CET  in 4d 23h
```

## License

MIT — see [LICENSE](LICENSE).
