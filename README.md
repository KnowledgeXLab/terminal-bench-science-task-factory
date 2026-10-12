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

## Data Designer 并行任务合成（可选）

安装 `python -m pip install -e '.[designer]'`，然后运行：

```bash
tb-science-designer --requests requests.jsonl --out runs/designer-batch --concurrency 2 --env-file .env
```

`requests.jsonl` 每行一个独立 reference 输入；路径相对 JSONL 所在目录解析：

```json
{"request_id":"method-a","reference":"references/a.json","model":"gpt-6-luna","count":1}
{"request_id":"method-b","reference":"references/b.json","model":"gpt-6-luna","count":2}
```

Data Designer 自定义列并行执行原生 `generate_candidates()` 和 `materialize_candidate()`，保留模型 API 重试、缓存和候选检查。每项独立输出到 `OUT/items/<request_id>/`，避免同名 task 在不同输入间冲突。`count` 是该输入请求的任务数，`--concurrency` 是并行输入数。

汇总为 `OUT/results.json`，单项结果为 `OUT/items/<request_id>/result.json`，候选为 `candidates.jsonl`，任务为 `tasks/<domain>/<field>/<slug>/`，Data Designer 数据集位于 `OUT/designer/`。所有任务物化才记为 `completed`；无效候选跳过并记录为 `partial`，单项异常记为 `failed`，不阻止其他输入执行。存在未完成项时命令返回非零退出码。

输出目录必须是新目录，不自动重跑或覆盖旧批次。此入口只生产 task，不运行 Oracle 或 Solver，不自动提交 DataAgent 归档；物化成功不代表科学运行验收通过。
