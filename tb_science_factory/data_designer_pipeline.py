"""NeMo Data Designer integration for task-package generation.

The adapter keeps Data Designer optional: the core factory and its tests do
not import NVIDIA dependencies. When installed, Data Designer owns batching,
parallel requests, retries, checkpointing, and dataset persistence. This
module converts its tabular result into the factory's versioned JSONL envelope.
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "tb-science-factory.dataset.v1"
DEFAULT_COLUMN = "candidate"


@dataclass(frozen=True)
class DataDesignerPipelineConfig:
    seed_path: Path
    output_path: Path
    dataset_name: str = "terminal-bench-science-tasks"
    model: str = "nvidia/nemotron-3-nano-30b-a3b"
    provider: str = "nvidia"
    num_records: int = 1
    buffer_size: int = 100
    max_parallel_requests: int = 8
    max_concurrent_row_groups: int = 3
    timeout: int = 600

    def validate(self) -> None:
        if not self.seed_path.is_file():
            raise FileNotFoundError(self.seed_path)
        if self.num_records <= 0:
            raise ValueError("num_records must be positive")
        if self.buffer_size <= 0:
            raise ValueError("buffer_size must be positive")
        if self.max_parallel_requests <= 0:
            raise ValueError("max_parallel_requests must be positive")
        if self.max_concurrent_row_groups <= 0:
            raise ValueError("max_concurrent_row_groups must be positive")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")


def _candidate_schema() -> type[Any]:
    try:
        from pydantic import BaseModel, Field
    except ImportError as exc:  # pragma: no cover - exercised by CLI users
        raise RuntimeError(
            "NeMo Data Designer support requires the 'nemo' extra: "
            "pip install -e '.[nemo]'"
        ) from exc

    class CandidateRecord(BaseModel):
        slug: str = Field(description="short kebab-case task slug")
        title: str
        domain: str
        field: str
        subfield: str
        description: str
        difficulty: str
        instruction_md: str
        task_toml: str
        files: dict[str, str]
        opd: dict[str, str]

    return CandidateRecord


def build_config_builder(config: DataDesignerPipelineConfig) -> Any:
    """Build a Data Designer config from a seed dataset.

    The seed dataset must expose a ``pattern_json`` column containing one
    workflow-pattern card per row. The generated ``candidate`` column is a
    structured Pydantic record, so downstream consumers receive typed fields
    instead of parsing model prose.
    """
    config.validate()
    try:
        import data_designer.config as dd
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "NeMo Data Designer support requires the 'nemo' extra: "
            "pip install -e '.[nemo]'"
        ) from exc

    model_config = dd.ModelConfig(
        alias="task-generator",
        model=config.model,
        provider=config.provider,
        inference_parameters=dd.ChatCompletionInferenceParams(
            max_parallel_requests=config.max_parallel_requests,
            timeout=config.timeout,
            temperature=0.2,
            max_tokens=32000,
        ),
    )
    builder = dd.DataDesignerConfigBuilder(model_configs=[model_config])
    builder.with_seed_dataset(dd.LocalFileSeedSource(path=str(config.seed_path)))
    builder.add_column(
        dd.LLMStructuredColumnConfig(
            name=DEFAULT_COLUMN,
            model_alias="task-generator",
            output_format=_candidate_schema(),
            prompt=(
                "Create one independent Harbor scientific task package from "
                "this workflow pattern card. Return a fresh task and never "
                "copy source wording, answers, fixtures, or solution code. "
                "The pattern card is: {{ pattern_json }}"
            ),
        )
    )
    return builder


def _records_from_dataset(dataset: Any) -> list[dict[str, Any]]:
    if hasattr(dataset, "to_dict"):
        rows = dataset.to_dict(orient="records")
    elif isinstance(dataset, list):
        rows = dataset
    else:
        raise TypeError("Data Designer result must expose a tabular dataset")
    records: list[dict[str, Any]] = []
    for row in rows:
        value = row.get(DEFAULT_COLUMN, row) if isinstance(row, dict) else row
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        if not isinstance(value, dict):
            raise ValueError("generated candidate column must contain objects")
        records.append(value)
    return records


def write_dataset_jsonl(
    records: list[dict[str, Any]], output_path: Path, *, dataset_name: str, run_id: str | None = None
) -> int:
    """Write the stable interchange format consumed by factory tooling."""
    run_id = run_id or str(uuid.uuid4())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for index, record in enumerate(records):
            envelope = {
                "schema_version": SCHEMA_VERSION,
                "dataset_name": dataset_name,
                "run_id": run_id,
                "row_id": index,
                "record": record,
            }
            stream.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
    return len(records)


def read_dataset_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read and validate the interchange format without importing Data Designer."""
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {line_number}") from exc
        if envelope.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version on line {line_number}")
        record = envelope.get("record")
        if not isinstance(record, dict):
            raise ValueError(f"record must be an object on line {line_number}")
        records.append(record)
    return records


def run_pipeline(config: DataDesignerPipelineConfig) -> int:
    """Run Data Designer and persist its records in the factory envelope."""
    try:
        from data_designer.interface import DataDesigner, ResumeMode
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "NeMo Data Designer support requires the 'nemo' extra: "
            "pip install -e '.[nemo]'"
        ) from exc
    designer = DataDesigner()
    designer.set_run_config(
        __import__("data_designer.config", fromlist=["RunConfig"]).RunConfig(
            buffer_size=config.buffer_size,
            max_concurrent_row_groups=config.max_concurrent_row_groups,
        )
    )
    result = designer.create(
        build_config_builder(config),
        num_records=config.num_records,
        dataset_name=config.dataset_name,
        resume=ResumeMode.IF_POSSIBLE,
    )
    return write_dataset_jsonl(
        _records_from_dataset(result.load_dataset()), config.output_path, dataset_name=config.dataset_name
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", dest="seed_path", type=Path, required=True)
    parser.add_argument("--out", dest="output_path", type=Path, required=True)
    parser.add_argument("--dataset-name", default="terminal-bench-science-tasks")
    parser.add_argument("--model", default="nvidia/nemotron-3-nano-30b-a3b")
    parser.add_argument("--provider", default="nvidia")
    parser.add_argument("--num-records", type=int, default=1)
    parser.add_argument("--buffer-size", type=int, default=100)
    parser.add_argument("--max-parallel-requests", type=int, default=8)
    parser.add_argument("--max-concurrent-row-groups", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    count = run_pipeline(DataDesignerPipelineConfig(**vars(args)))
    print(json.dumps({"records": count, "output": str(args.output_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
