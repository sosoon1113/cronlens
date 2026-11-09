# Contributing to cronlens

Thanks for taking the time to contribute! Bug reports, feature ideas and pull
requests are all welcome.

## Reporting bugs

Please open an issue with:

- the exact command you ran (including the cron expression or a minimal crontab),
- what you expected to happen and what happened instead,
- your Python version and operating system, and the output of `cronlens --version`.

For scheduling bugs, mentioning the timezone and the `--from` time you used makes
the problem much easier to reproduce.

## Development setup

```bash
git clone https://github.com/sosoon1113/cronlens.git
cd cronlens
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Before opening a pull request

```bash
ruff format .
ruff check .
pytest --cov
```

- Add tests for any behaviour change. Tests that involve time should pass a fixed
  `start` (or `--from`) rather than relying on the current clock.
- Keep the public API in `cronlens/__init__.py` backwards compatible where possible.
- Add a line to the `Unreleased` section of `CHANGELOG.md`.

CI runs the same checks on Linux, Windows and macOS.
