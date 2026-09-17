import json
from pathlib import Path

import pytest

from tb_science_factory.data_designer_pipeline import (
    SCHEMA_VERSION,
    DataDesignerPipelineConfig,
    read_dataset_jsonl,
    write_dataset_jsonl,
)


def test_dataset_envelope_round_trip(tmp_path: Path):
    output = tmp_path / "dataset.jsonl"
    records = [{"slug": "demo-task", "files": {"instruction.md": "text"}}]
    assert write_dataset_jsonl(records, output, dataset_name="demo", run_id="run-1") == 1
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == SCHEMA_VERSION
    assert envelope["dataset_name"] == "demo"
    assert read_dataset_jsonl(output) == records


def test_dataset_reader_rejects_unknown_schema(tmp_path: Path):
    output = tmp_path / "dataset.jsonl"
    output.write_text('{"schema_version":"old","record":{}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported schema_version"):
        read_dataset_jsonl(output)


def test_pipeline_config_validates_limits(tmp_path: Path):
    seed = tmp_path / "seed.csv"
    seed.write_text("pattern_json\n{}\n", encoding="utf-8")
    config = DataDesignerPipelineConfig(seed, tmp_path / "out.jsonl", max_parallel_requests=0)
    with pytest.raises(ValueError, match="max_parallel_requests"):
        config.validate()
