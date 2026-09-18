# Terminal-Bench Science Task Factory

This repository generates, validates, materializes, and exports independent
scientific tasks in the Harbor/Terminal-Bench format. The factory uses an
OpenAI-compatible JSON endpoint, while generated tasks remain deterministic
and free of credentials.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

Set `API_BASE` and `API_KEY` in your shell or a local `.env` file. Generate
draft candidates with:

```bash
python -m tb_science_factory.task_factory generate \
  --reference references/pattern_cards.json \
  --out work/candidates.jsonl \
  --cache-dir work/llm-cache \
  --model <provider-model> --count 3
```

Materialize validated candidates into Harbor task directories:

```bash
python -m tb_science_factory.task_factory materialize \
  --candidates work/candidates.jsonl --out-root generated
```

Only export candidates after real Harbor verifier evidence reports reward `1`:

```bash
python -m tb_science_factory.task_factory export-opd \
  --candidates generated/candidates/pilot.jsonl \
  --verification generated/VERIFICATION.json \
  --out generated/opd/pilot_verified.jsonl
```

`--allow-unverified` is intended for local format checks only. It must not be
used to create a production training set.

Export the same verified task set for NeMo Gym with its OpenAI Responses API
dataset contract:

```bash
python -m tb_science_factory.task_factory export-gym \
  --candidates generated/candidates/pilot.jsonl \
  --verification generated/VERIFICATION.json \
  --out generated/gym/pilot_verified.jsonl
```

Each JSONL row contains `responses_create_params.input`, a `question` and
`id`, and Harbor routing data in `verifier_metadata`. The `agent_ref` field is
left for `gym dataset collate` to add from the selected agent configuration.
NeMo Gym creates the agent trajectory during rollout; this export is the task
dataset consumed by that rollout. Use `--allow-unverified` only for local
format checks.

## Repository layout

- `tb_science_factory/`: library, CLI, LLM client, prompts, and unit tests.
- `references/`: public workflow pattern cards used as generation input.
- `generated/` is a local output directory for materialized tasks and
  verification records; it is intentionally excluded from this source repo.
- `scripts/`: batch helpers and release checks.
- `CONTRIBUTING.md` and `SECURITY.md`: contribution and security guidance.

Runtime state belongs in ignored `generated/`, `work/`, `jobs/`, and `.venv/`
directories. Publish generated task packages separately when a release needs
them.
Never commit API keys, model caches, private datasets, registry credentials,
or infrastructure-specific runbooks.

## Checks

```bash
python -m pytest
python scripts/static_check.py
python scripts/scan_artifacts.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and review guidance.
