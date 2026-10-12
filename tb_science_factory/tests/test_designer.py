"""Exercise the real Data Designer scheduler with native materialization and stub inference."""

import json
import threading

import pytest

pytest.importorskip("data_designer")
from tb_science_factory import designer
from tb_science_factory.tests.test_task_factory import candidate


def requests(tmp_path):
    (tmp_path / "reference.json").write_text('{"workflow": "parameter estimation"}')
    path = tmp_path / "requests.jsonl"
    path.write_text(
        "".join(
            json.dumps(
                {"request_id": identifier, "reference": "reference.json", "model": "test-model", "count": 1}
            )
            + "\n"
            for identifier in ("one", "two", "bad")
        )
    )
    return path


def test_real_designer_parallel_materialization_and_failure_isolation(tmp_path, monkeypatch):
    barrier = threading.Barrier(2)
    observed = []

    def generate(reference, *, output_path, **kwargs):
        identifier = output_path.parent.name
        observed.append(identifier)
        if identifier == "bad":
            raise RuntimeError("native synthesis failed")
        barrier.wait(30)
        row = candidate()
        row["candidate_id"] = identifier
        row["validation_errors"] = []
        output_path.write_text(json.dumps(row) + "\n")
        return [row]

    monkeypatch.setattr(designer, "generate_candidates", generate)
    path = requests(tmp_path)
    output = tmp_path / "batch"
    results = designer.run_batch(path, output, concurrency=2)
    assert {r["request_id"]: r["status"] for r in results} == {
        "one": "completed",
        "two": "completed",
        "bad": "failed",
    }
    for row in results:
        if row["status"] == "completed":
            from pathlib import Path

            assert (Path(row["task_paths"][0]) / "task.toml").is_file()
        assert (output / "items" / row["request_id"] / "result.json").is_file()
    with pytest.raises(FileExistsError):
        designer.run_batch(path, output)
    assert len(observed) == 3


def test_invalid_candidate_is_not_materialized(tmp_path, monkeypatch):
    def generate(*args, **kwargs):
        return [{"candidate_id": "invalid", "validation_errors": ["missing verifier"]}]

    monkeypatch.setattr(designer, "generate_candidates", generate)
    results = designer.run_batch(requests(tmp_path), tmp_path / "batch", concurrency=2)
    assert all(r["status"] == "partial" and not r["task_paths"] for r in results)
    assert not list((tmp_path / "batch").rglob("task.toml"))


@pytest.mark.parametrize(
    "change",
    [{"request_id": "../escape"}, {"request_id": "one"}, {"count": 0}, {"count": True}, {"model": ""}],
)
def test_rejects_bad_requests_before_execution(tmp_path, change):
    path = requests(tmp_path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[1].update(change)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError):
        designer.run_batch(path, tmp_path / "batch")
    assert not (tmp_path / "batch").exists()
