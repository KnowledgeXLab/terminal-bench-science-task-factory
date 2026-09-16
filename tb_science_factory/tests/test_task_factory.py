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
        "instruction_md": text + "Write `/results/output.json`.\n\nYou have 120 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.\n",
        "task_toml": text + "schema_version=\"1.4\"\n[task]\nname='terminal-bench-science/ode-derived'\nauthors=[{name=\"Test\",email=\"test@example.com\"}]\nkeywords=[\"ode\"]\n[metadata]\nauthor_name=\"Test\"\nauthor_email=\"test@example.com\"\nauthor_organization=\"Independent Researcher\"\ndomain=\"mathematical-sciences\"\nfield=\"applied-mathematics\"\ntags=[\"ode\"]\n[verifier.environment]\nnetwork_mode=\"no-network\"\n[agent]\ntimeout_sec=120\n[environment]\nnetwork_mode=\"public\"\n",
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


def test_rejects_secret_and_traversal():
    row = candidate()
    row["files"]["../secret"] = "API_KEY=oops"
    errors = validate_candidate(row)
    assert any("unsafe" in error for error in errors)


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
            "environment/rollout_requests.csv": "request_id,horizon\nprobe,1\n",
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
            "environment/input.csv": "x,y\n1,2\n",
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
