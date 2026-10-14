import json
from pathlib import Path

import pytest

from tb_science_factory.task_factory import CANARY, export_opd_records, materialize_candidate, validate_candidate


def candidate():
    text = f"# {CANARY}\n"
    return {
        "slug": "ode-derived",
        "title": "Derived ODE",
        "domain": "mathematical-sciences",
        "field": "applied-mathematics",
        "subfield": "dynamical-systems",
        "description": "Recover a dynamical law.",
        "difficulty": "simple",
        "instruction_md": text + "Write `/results/output.json`.\n\nYou have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.\n",
        "task_toml": text + "schema_version=\"1.4\"\nartifacts=[\"/results/output.json\"]\n[task]\nname='terminal-bench-science/ode-derived'\nauthors=[{name=\"Test\",email=\"test@example.com\"}]\nkeywords=[\"ode\"]\n[metadata]\nauthor_name=\"Test\"\nauthor_email=\"test@example.com\"\nauthor_organization=\"Independent Researcher\"\ndomain=\"mathematical-sciences\"\nfield=\"applied-mathematics\"\ntags=[\"ode\"]\n[verifier.environment]\nnetwork_mode=\"no-network\"\n[agent]\ntimeout_sec=3600\n[environment]\nnetwork_mode=\"public\"\n",
        "files": {
            "environment/Dockerfile": text + "FROM python:3.11-slim\n",
            "solution/solve.sh": text + "#!/bin/sh\n",
            "tests/Dockerfile": text + "FROM python:3.11-slim\n",
            "tests/test.sh": text + "#!/bin/sh\n",
        },
        "opd": {"teacher_prompt": "solve", "success_signal": "reward 1"},
    }


def test_valid_candidate_and_materialize(tmp_path: Path):
    row = candidate()
    assert validate_candidate(row) == []
    root = materialize_candidate(row, tmp_path)
    assert (root / "instruction.md").is_file()
    assert (root / "tests/test.sh").is_file()


def test_materialize_transfers_workdir_artifacts_to_separate_verifier(tmp_path: Path):
    import tomllib

    row = candidate()
    row["task_toml"] = row["task_toml"].replace('/results/output.json', 'outputs/output.json')
    row["files"]["environment/Dockerfile"] += "WORKDIR /app\n"
    row["files"]["tests/Dockerfile"] += 'CMD ["/tests/test.sh"]\n'
    root = materialize_candidate(row, tmp_path)
    assert tomllib.loads((root / "task.toml").read_text())["artifacts"] == ["/app/outputs/output.json"]
    assert 'CMD ["sleep", "infinity"]' in (root / "tests/Dockerfile").read_text()
    assert 'CMD ["/tests/test.sh"]' not in (root / "tests/Dockerfile").read_text()


def test_rejects_secret_and_traversal():
    row = candidate()
    row["files"]["../secret"] = "API_KEY=oops"
    errors = validate_candidate(row)
    assert any("unsafe" in error for error in errors)


def test_secret_scan_distinguishes_task_paths_from_api_keys():
    row = candidate()
    row["instruction_md"] += "Read /task-data/data.csv and write /task-results/result.json.\n"
    assert validate_candidate(row) == []
    row["files"]["environment/leaked.txt"] = "token: sk-" + "a" * 32
    assert any("credential" in error for error in validate_candidate(row))


def test_export_opd_skips_invalid(tmp_path: Path):
    good = candidate()
    good["status"] = "verified"
    good["verification"] = {"reward": 1, "oracle_exit_code": 0, "tests_exit_code": 0}
    bad = dict(good)
    bad["slug"] = ""
    bad["validation_errors"] = ["invalid"]
    source = tmp_path / "candidates.jsonl"
    source.write_text("\n".join(json.dumps(x) for x in (good, bad)) + "\n", encoding="utf-8")
    output = tmp_path / "opd.jsonl"
    assert export_opd_records(source, output) == 1
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["data_source"] == "terminal_bench_science_derived"
    assert record["prompt"][0]["role"] == "user"


def test_materialize_normalizes_harbor_verifier_context(tmp_path: Path):
    row = candidate()
    row["files"].update(
        {
            "environment/rollout_requests.csv": f"# {CANARY}\nrequest_id,horizon\nprobe,1\n",
            "tests/test_outputs.py": (
                f"# {CANARY}\nfrom pathlib import Path\n"
                "requests = ROOT / 'rollout_requests.csv'\n"
            ),
            "tests/Dockerfile": (
                f"# {CANARY}\nFROM python:3.11-slim\n"
                "COPY tests/test_outputs.py /tests/test_outputs.py\n"
                "ENTRYPOINT [\"/tests/test.sh\"]\n"
            ),
        }
    )
    root = materialize_candidate(row, tmp_path)
    dockerfile = (root / "tests/Dockerfile").read_text(encoding="utf-8")
    test_code = (root / "tests/test_outputs.py").read_text(encoding="utf-8")
    assert "COPY test_outputs.py /tests/test_outputs.py" in dockerfile
    assert "ENTRYPOINT" not in dockerfile
    assert 'CMD ["sleep", "infinity"]' in dockerfile
    assert "COPY rollout_requests.csv /tests/rollout_requests.csv" in dockerfile
    assert "Path('/tests/rollout_requests.csv')" in test_code
    assert (root / "tests/rollout_requests.csv").is_file()


def test_materialize_normalizes_environment_context_copy(tmp_path: Path):
    row = candidate()
    row["files"].update(
        {
            "environment/input.csv": f"# {CANARY}\nx,y\n1,2\n",
            "environment/Dockerfile": (
                f"# {CANARY}\nFROM python:3.11-slim\n"
                "COPY environment/input.csv /workspace/input.csv\n"
            ),
        }
    )
    root = materialize_candidate(row, tmp_path)
    dockerfile = (root / "environment/Dockerfile").read_text(encoding="utf-8")
    assert "COPY input.csv /workspace/input.csv" in dockerfile
    assert "COPY environment/input.csv" not in dockerfile


def test_materialize_rewrites_python_heredoc_dockerfile(tmp_path: Path):
    row = candidate()
    row["files"]["environment/Dockerfile"] = (
        f"# {CANARY}\nFROM python:3.11-slim\n"
        "RUN mkdir -p /data && python - <<'PY'\n"
        "import json\n"
        "json.dump({'value': 3}, open('/data/value.json', 'w'))\n"
        "PY\n"
    )
    root = materialize_candidate(row, tmp_path)
    env_dockerfile = (root / "environment/Dockerfile").read_text(encoding="utf-8")
    verifier_dockerfile = (root / "tests/Dockerfile").read_text(encoding="utf-8")
    assert "RUN python - <<" not in env_dockerfile
    assert "RUN python - <<" not in verifier_dockerfile
    assert "base64 -d" in env_dockerfile


def test_materialize_normalizes_shell_line_endings(tmp_path: Path):
    row = candidate()
    row["files"]["tests/test.sh"] = f"#!/bin/sh\r\n# {CANARY}.\r\nexit 0\r\n"
    root = materialize_candidate(row, tmp_path)
    assert b"\r" not in (root / "tests/test.sh").read_bytes()


def test_materialize_adds_harbor_reward_hook(tmp_path: Path):
    row = candidate()
    row["files"]["tests/test.sh"] = f"#!/bin/sh\n# {CANARY}.\nset -eu\ntrue\n"
    root = materialize_candidate(row, tmp_path)
    script = (root / "tests/test.sh").read_text(encoding="utf-8")
    assert "reward=/logs/verifier/reward.txt" in script
    assert "trap 'status=$?" in script


def test_repair_normalization_synchronizes_timeout_without_changing_science():
    from tb_science_factory.task_factory import normalize_candidate
    row = candidate()
    row["instruction_md"] = row["instruction_md"].replace("3600 seconds", "900 seconds")
    normalized = normalize_candidate(row)
    assert validate_candidate(normalized) == []
    assert "900 seconds" not in normalized["instruction_md"]
    assert "3600 seconds" in normalized["instruction_md"]
    assert "Write `/results/output.json`." in normalized["instruction_md"]
    assert normalized["description"] == row["description"]


def test_conflicting_top_level_files_cannot_override_contract():
    row = candidate()
    row["files"]["instruction.md"] = "Conflicting task contract"
    assert any("conflicts" in e for e in validate_candidate(row))


def test_nested_artifacts_are_hoisted_to_the_top_level():
    import tomllib
    from tb_science_factory.task_factory import normalize_candidate

    # A model that appends ``artifacts`` after the last table nests it under that table,
    # which hides the key from Harbor's top-level lookup.
    for declaration in ('artifacts = ["/results/output.json"]\n',
                        'artifacts = [\n  "/results/output.json",\n]\n'):
        row = candidate()
        row["task_toml"] = row["task_toml"].replace('artifacts=["/results/output.json"]\n', "")
        row["task_toml"] += declaration
        assert any("artifacts" in error for error in validate_candidate(row))
        normalized = normalize_candidate(row)
        assert validate_candidate(normalized) == []
        parsed = tomllib.loads(normalized["task_toml"])
        assert parsed["artifacts"] == ["/results/output.json"]
        assert "artifacts" not in parsed["environment"]


def test_already_top_level_artifacts_are_left_alone():
    from tb_science_factory.task_factory import normalize_candidate

    row = candidate()
    assert normalize_candidate(row)["task_toml"] == row["task_toml"]


def test_ambiguous_nested_artifacts_are_not_repaired():
    from tb_science_factory.task_factory import normalize_candidate

    row = candidate()
    row["task_toml"] = row["task_toml"].replace('artifacts=["/results/output.json"]\n', "")
    row["task_toml"] = row["task_toml"].replace("[metadata]\n", '[metadata]\nartifacts = ["/a.json"]\n', 1)
    row["task_toml"] += 'artifacts = ["/b.json"]\n'
    assert normalize_candidate(row)["task_toml"] == row["task_toml"]


def test_truncated_artifact_path_is_rejected():
    from tb_science_factory.task_factory import normalize_candidate

    row = candidate()
    row["task_toml"] = row["task_toml"].replace("/results/output.json", "/results/output.")
    errors = validate_candidate(normalize_candidate(row))
    assert any("must name a file" in error for error in errors)


def test_difficulty_tier_derives_the_agent_timeout():
    from tb_science_factory.task_factory import normalize_candidate

    for tier, seconds in (("simple", 3600), ("medium", 7200), ("hard", 10800)):
        row = candidate()
        row["difficulty"] = tier
        # whatever the model wrote is replaced by the host-derived budget
        row["task_toml"] = row["task_toml"].replace("timeout_sec=3600", "timeout_sec=7")
        normalized = normalize_candidate(row)
        assert validate_candidate(normalized) == []
        assert f"timeout_sec={seconds}" in normalized["task_toml"]
        assert f"You have {seconds} seconds" in normalized["instruction_md"]


def test_difficulty_tier_is_required_and_must_match_the_budget():
    row = candidate()
    row["difficulty"] = "medium"
    assert any("must be 7200" in error for error in validate_candidate(row))
    row["difficulty"] = "why the scientific reasoning is hard"
    assert any("difficulty must be one of" in error for error in validate_candidate(row))
