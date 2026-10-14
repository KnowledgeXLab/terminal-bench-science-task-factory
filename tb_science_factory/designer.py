"""Use Data Designer to schedule independent reference-to-Harbor synthesis requests.

Each row runs the native generate/validate/materialize flow in an isolated directory.
This module writes durable per-request results and does not run Oracle or Solver.
Existing output directories are rejected to prevent implicit replay of side effects.
Concurrency limits input rows; each row uses one native model request for its candidates.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import data_designer.config as dd
from data_designer.config.run_config import RunConfig
from data_designer.interface import DataDesigner
from pydantic import BaseModel

from .llm_client import OpenAICompatibleJSONClient, load_env_file
from .task_factory import generate_candidates, materialize_candidate

INPUT_FILES = ("reference",)


class GeneratorParams(BaseModel):
    output: str
    # Per-request HTTP timeout and retry budget for the native model client. The defaults
    # match the historical 180s x 3; a thinking model drafting a full task spec needs more.
    timeout: int = 180
    max_retries: int = 3


def validate_request(row: dict) -> None:
    if not isinstance(row.get("model"), str) or not row["model"].strip():
        raise ValueError("each request requires a model")
    count = row.get("count", 1)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("count must be a positive integer")
    row["count"] = count
    json.loads(Path(row["reference"]).read_text(encoding="utf-8"))


@dd.custom_column_generator(required_columns=["request_id", "reference", "model", "count"])
def generate_task(row: dict, generator_params: GeneratorParams) -> dict:
    directory = Path(generator_params.output) / "items" / row["request_id"]
    directory.mkdir(parents=True, exist_ok=False)
    result = {"request_id": row["request_id"], "status": "failed", "task_paths": []}
    try:
        reference = json.loads(Path(row["reference"]).read_text(encoding="utf-8"))
        client = OpenAICompatibleJSONClient(model=row["model"], cache_dir=directory / "cache",
                                            timeout=generator_params.timeout,
                                            max_retries=generator_params.max_retries)
        candidates = generate_candidates(
            reference,
            output_path=directory / "candidates.jsonl",
            cache_dir=directory / "cache",
            model=row["model"],
            count=int(row["count"]),
            client=client,
        )
        result["validation_errors"] = []
        for candidate in candidates:
            errors = candidate.get("validation_errors") or []
            if errors:
                result["validation_errors"].append(
                    {"candidate_id": candidate["candidate_id"], "errors": errors}
                )
                continue
            path = materialize_candidate(candidate, directory)
            result["task_paths"].append(str(path))
        result["status"] = "completed" if len(result["task_paths"]) == row["count"] else "partial"
    except Exception as exc:  # noqa: BLE001 -- persist native failures per input row
        result["error"] = f"{type(exc).__name__}: {exc}"
    _write_result(directory / "result.json", result)
    return {**row, "task_result": json.dumps(result, ensure_ascii=False)}


def _write_result(path: Path, result: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_batch(requests: Path, output: Path, *, concurrency: int = 2,
              timeout: int = 180, max_retries: int = 3) -> list[dict]:
    """Run a new batch; never overwrite or implicitly replay an existing batch."""
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    if timeout < 1 or max_retries < 1:
        raise ValueError("timeout and max_retries must be positive")
    rows = [json.loads(line) for line in requests.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("requests must contain at least one row")
    identifiers = set()
    for row in rows:
        identifier = row.get("request_id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", identifier):
            raise ValueError("request_id must be a safe identifier of at most 64 characters")
        if identifier in identifiers:
            raise ValueError("duplicate request_id")
        identifiers.add(identifier)
        for field in INPUT_FILES:
            path = Path(row[field]).expanduser()
            if not path.is_absolute():
                path = requests.resolve().parent / path
            path = path.resolve()
            if not path.exists():
                raise FileNotFoundError(path)
            row[field] = str(path)
        validate_request(row)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    seeds = output / "requests.jsonl"
    seeds.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    builder = dd.DataDesignerConfigBuilder()
    builder.with_seed_dataset(dd.LocalFileSeedSource(path=str(seeds)))
    builder.add_column(
        dd.CustomColumnConfig(
            name="task_result",
            generator_function=generate_task,
            generator_params=GeneratorParams(output=str(output), timeout=timeout,
                                             max_retries=max_retries),
        )
    )
    designer = DataDesigner()
    designer.set_run_config(
        RunConfig(
            buffer_size=1,
            max_concurrent_row_groups=concurrency,
            max_in_flight_tasks=concurrency,
            non_inference_max_parallel_workers=concurrency,
            display_tui=False,
            otel_metrics_port=None,
        )
    )
    generated = designer.create(builder, num_records=len(rows), artifact_path=output / "designer")
    records = generated.load_dataset().to_dict(orient="records")
    if len(records) != len(rows) or {r["request_id"] for r in records} != identifiers:
        raise RuntimeError("Data Designer did not return exactly one result per request")
    results = sorted((json.loads(r["task_result"]) for r in records), key=lambda r: r["request_id"])
    _write_result(output / "results.json", {"results": results})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=180,
                        help="per-request HTTP timeout in seconds for the native model client")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="attempts per native model request")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.env_file:
        load_env_file(args.env_file)
    results = run_batch(args.requests, args.out, concurrency=args.concurrency,
                        timeout=args.timeout, max_retries=args.max_retries)
    print(
        json.dumps(
            {
                "results": str(args.out.resolve() / "results.json"),
                "requests": len(results),
                "failed": sum(r["status"] != "completed" for r in results),
            }
        )
    )
    return int(any(r["status"] != "completed" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
