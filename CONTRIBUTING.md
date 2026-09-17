# Contributing

Thanks for helping improve the task factory. Keep changes small, reproducible,
and safe to publish.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

The Windows activation command is `.venv\\Scripts\\Activate.ps1`.

## Pull requests

- Explain the behavior change and include focused tests.
- Do not commit `.env`, API keys, model caches, Harbor jobs, generated zip
  archives, or private infrastructure details.
- Keep generated task packages deterministic and run the static checks before
  submitting changes.
- A task is not `verified` merely because it was generated or passed a local
  smoke test. Record real Harbor evidence before exporting it for training.

## Validation commands

```bash
python -m pytest
python scripts/static_check.py
python scripts/scan_artifacts.py
```
