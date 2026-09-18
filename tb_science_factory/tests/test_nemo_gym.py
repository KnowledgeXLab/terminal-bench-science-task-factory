import json
from pathlib import Path

import pytest

from tb_science_factory.nemo_gym import GYM_SCHEMA_VERSION, export_gym_records
from tb_science_factory.task_factory import CANARY


def candidate() -> dict:
    return {
        "candidate_id": "tbds-20260918-001",
        "slug": "ode-derived",
        "title": "Derived ODE",
        "domain": "mathematical-sciences",
        "field": "applied-mathematics",
        "subfield": "dynamical-systems",
        "instruction_md": f"# {CANARY}\nRecover a dynamical law.\n",
        "opd": {"teacher_prompt": "solve", "success_signal": "reward 1"},
        "status": "verified",
        "verification": {"reward": 1, "oracle_exit_code": 0},
    }


def test_export_gym_uses_responses_api_shape(tmp_path: Path):
    source = tmp_path / "candidates.jsonl"
    source.write_text(json.dumps(candidate()) + "\n", encoding="utf-8")
    output = tmp_path / "gym.jsonl"

    assert export_gym_records(source, output) == 1
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["responses_create_params"]["input"] == [
        {"role": "user", "content": candidate()["instruction_md"]}
    ]
    assert record["verifier_metadata"]["task_slug"] == "ode-derived"
    assert record["metadata"]["schema_version"] == GYM_SCHEMA_VERSION
    assert "agent_ref" not in record


def test_export_gym_applies_verification_gate(tmp_path: Path):
    unverified = candidate()
    unverified["status"] = "draft"
    unverified["verification"] = {}
    source = tmp_path / "candidates.jsonl"
    source.write_text(json.dumps(unverified) + "\n", encoding="utf-8")
    output = tmp_path / "gym.jsonl"

    assert export_gym_records(source, output) == 0
    assert output.read_text(encoding="utf-8") == ""
    assert export_gym_records(source, output, allow_unverified=True) == 1


def test_export_gym_merges_verification_file(tmp_path: Path):
    row = candidate()
    row["status"] = "draft"
    row["verification"] = {}
    source = tmp_path / "candidates.jsonl"
    source.write_text(json.dumps(row) + "\n", encoding="utf-8")
    verification = tmp_path / "verification.json"
    verification.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "verified",
                        "verification": {"reward": 1},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "gym.jsonl"

    assert export_gym_records(source, output, verification_path=verification) == 1


def test_export_gym_accepts_data_designer_envelope(tmp_path: Path):
    source = tmp_path / "dataset.jsonl"
    source.write_text(
        json.dumps(
            {
                "schema_version": "tb-science-factory.dataset.v1",
                "dataset_name": "demo",
                "run_id": "run-1",
                "row_id": 7,
                "record": candidate(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "gym.jsonl"

    assert export_gym_records(source, output) == 1
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["id"] == candidate()["candidate_id"]
    assert record["metadata"]["data_designer"]["run_id"] == "run-1"
    assert record["metadata"]["data_designer"]["row_id"] == 7


def test_export_gym_rejects_empty_instruction(tmp_path: Path):
    row = candidate()
    row["instruction_md"] = ""
    source = tmp_path / "candidates.jsonl"
    source.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="instruction_md"):
        export_gym_records(source, tmp_path / "gym.jsonl")
