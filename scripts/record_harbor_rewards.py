"""Record completed local Harbor oracle rewards in the audit manifests.

The verifier reward file is the source of truth; this helper never promotes a
task from a plain Docker smoke pass without a Harbor trial artifact.
"""

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path.cwd()
VERIFICATION = ROOT / "generated" / "VERIFICATION.json"
CANDIDATES = ROOT / "generated" / "candidates" / "next_batch.jsonl"


EVIDENCE = {
    "tasks/life-sciences/biochemistry/fluorescence-crosstalk-unmixing":
        "jobs/harbor-postrepair-bio-3/2026-09-04__19-27-29",
    "tasks/physical-sciences/condensed-matter-physics/resonance-drift-selection":
        "jobs/harbor-postrepair-condensed-2/2026-09-04__19-31-41",
    "tasks/physical-sciences/condensed-matter-physics/resonator-load-inversion":
        "jobs/harbor-postrepair-condensed-2/2026-09-04__19-31-41",
    "tasks/engineering-sciences/mechanical-engineering/cooling-law-selection":
        "jobs/harbor-postrepair-mech-3/2026-09-04__19-34-25",
    "tasks/engineering-sciences/mechanical-engineering/acoustic-source-map":
        "jobs/harbor-postrepair-mech-3/2026-09-04__19-34-25",
    "tasks/engineering-sciences/mechanical-engineering/fin-profile-selection":
        "jobs/harbor-postrepair-mech-3/2026-09-04__19-34-25",
    "tasks/engineering-sciences/electrical-engineering/dual-magnetometer-alignment":
        "jobs/harbor-postrepair-dual-fixed/2026-09-04__19-49-10",
    "tasks/physical-sciences/physics/coupled-mode-discovery":
        "jobs/harbor-postrepair-coupled-fixed/2026-09-04__20-02-13",
    "tasks/mathematical-sciences/applied-mathematics/diffusion-front-selection":
        "jobs/harbor-postrepair-math-3/2026-09-04__19-37-27",
    "tasks/mathematical-sciences/applied-mathematics/radial-spiral-recovery":
        "jobs/harbor-postrepair-math-3/2026-09-04__19-37-27",
    "tasks/mathematical-sciences/applied-mathematics/spectral-axis-standardization":
        "jobs/harbor-postrepair-math-3/2026-09-04__19-37-27",
    "tasks/earth-sciences/hydrology/moisture-flux-law":
        "jobs/harbor-postrepair-hydro-3/2026-09-04__19-40-01",
    "tasks/earth-sciences/hydrology/catchment-response-selection":
        "jobs/harbor-postrepair-hydro-3/2026-09-04__19-40-01",
    "tasks/earth-sciences/hydrology/aquifer-recession-selection":
        "jobs/harbor-postrepair-hydro-3/2026-09-04__19-40-01",
    "tasks/life-sciences/systems-biology/enzyme-flux-inference":
        "jobs/harbor-postrepair-sysbio-3/2026-09-04__20-04-34",
    "tasks/life-sciences/systems-biology/enzyme-curve-selection":
        "jobs/harbor-postrepair-sysbio-3/2026-09-04__20-04-34",
    "tasks/life-sciences/systems-biology/enzyme-map-recovery":
        "jobs/harbor-postrepair-sysbio-3/2026-09-04__20-04-34",
    "tasks/engineering-sciences/electrical-engineering/battery-knee-forecast":
        "jobs/harbor-postrepair-electrical-3/2026-09-04__19-42-36",
    "tasks/engineering-sciences/electrical-engineering/gas-array-calibration":
        "jobs/harbor-postrepair-electrical-3/2026-09-04__19-42-36",
    "tasks/physical-sciences/physics/limited-angle-tomogram":
        "jobs/harbor-postrepair-physics-3/2026-09-04__19-51-34",
    "tasks/physical-sciences/physics/thermal-shell-decay":
        "jobs/harbor-postrepair-physics-3/2026-09-04__19-51-34",
}


def discover_evidence() -> dict[str, str]:
    """Discover reward files from every Harbor job, not only hand-listed jobs."""
    discovered: dict[str, str] = {}
    for reward_file in (ROOT / "jobs").glob("*/**/verifier/reward.txt"):
        try:
            if float(reward_file.read_text(encoding="utf-8").strip()) != 1.0:
                continue
        except (OSError, ValueError):
            continue
        trial_dir = reward_file.parent.parent
        task_path: str | None = None
        config_file = trial_dir / "config.json"
        result_file = trial_dir / "result.json"
        for candidate in (config_file, result_file):
            if not candidate.is_file():
                continue
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            task = payload.get("task", {})
            path = task.get("path") if isinstance(task, dict) else None
            if path:
                path = str(path).replace("\\", "/")
                marker = "/generated/tasks/"
                if marker in path:
                    task_path = "tasks/" + path.split(marker, 1)[1]
                elif path.startswith("generated/tasks/"):
                    task_path = "tasks/" + path.split("generated/tasks/", 1)[1]
                break
        if task_path:
            job_result = result_file
            if job_result.is_file():
                discovered.setdefault(task_path, trial_dir.parent.relative_to(ROOT).as_posix())
    return discovered


def trial_rewards(job_dir: Path, slug: str, expected_path: str | None = None) -> list[float]:
    rewards: list[float] = []
    for trial in sorted(job_dir.iterdir() if job_dir.is_dir() else []):
        if not trial.is_dir():
            continue
        matched = trial.name.startswith(f"{slug}__")
        config_file = trial / "config.json"
        if config_file.is_file():
            try:
                payload = json.loads(config_file.read_text(encoding="utf-8"))
                task = payload.get("task", {})
                task_path = str(task.get("path", "")).replace("\\", "/")
                if expected_path:
                    normalized = task_path
                    if "/generated/tasks/" in normalized:
                        normalized = "tasks/" + normalized.split("/generated/tasks/", 1)[1]
                    elif normalized.startswith("generated/tasks/"):
                        normalized = "tasks/" + normalized.split("generated/tasks/", 1)[1]
                    matched = normalized.rstrip("/") == expected_path.rstrip("/")
                else:
                    matched = matched or task_path.rstrip("/").endswith(f"/{slug}")
            except (OSError, json.JSONDecodeError):
                pass
        if not matched:
            continue
        reward_file = trial / "verifier" / "reward.txt"
        if not reward_file.is_file():
            continue
        try:
            rewards.append(float(reward_file.read_text(encoding="utf-8").strip()))
        except ValueError:
            continue
    return rewards


verification = json.loads(VERIFICATION.read_text(encoding="utf-8"))
entries = {entry["path"]: entry for entry in verification["tasks"]}
candidate_rows = [
    json.loads(line)
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

discovered = discover_evidence()
for task_path, job_rel in discovered.items():
    EVIDENCE.setdefault(task_path, job_rel)

promoted = 0
for task_path, job_rel in EVIDENCE.items():
    entry = entries.get(task_path)
    if entry is None:
        continue
    job_dir = ROOT / job_rel
    rewards = trial_rewards(job_dir, entry["slug"], task_path)
    if not rewards or any(reward != 1.0 for reward in rewards):
        # A job directory can contain repeated attempts for the same slug;
        # mixed or incomplete attempts are not evidence for promotion.  Keep
        # scanning the remaining jobs/entries instead of aborting the whole
        # ledger update because of one stale mixed job.
        print(f"skip non-all-1 Harbor evidence for {task_path}: {rewards}")
        continue
    result_rel = (job_dir / "result.json").relative_to(ROOT).as_posix()
    if entry.get("status") != "validated_local":
        promoted += 1
    entry["status"] = "validated_local"
    entry["verification"] = {
        **entry.get("verification", {}),
        "reward": 1,
        "oracle_exit_code": 0,
        "tests_exit_code": 0,
        "backend": "Harbor Docker on local Docker Desktop",
        "docker_harbor_verified": False,
        "local_harbor": {
            "backend": "harbor/docker on local Docker Desktop",
            "oracle_trials": len(rewards),
            "rewards": [int(r) if r.is_integer() else r for r in rewards],
            "jobs_result": result_rel,
        },
    }
    for row in candidate_rows:
        if row.get("materialized_path") == task_path:
            row["status"] = "validated_local"
            row["verification"] = entry["verification"]

verification["tasks"] = list(entries.values())
VERIFICATION.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
CANDIDATES.write_text(
    "\n".join(json.dumps(row, ensure_ascii=False) for row in candidate_rows) + "\n",
    encoding="utf-8",
)

next_path = ROOT / "generated" / "NEXT_BATCH.json"
next_batch = json.loads(next_path.read_text(encoding="utf-8"))
validated = sum(entry.get("status") == "validated_local" for entry in verification["tasks"])
valid = sum(not bool(row.get("validation_errors")) for row in candidate_rows)
next_batch["validated_local_count"] = validated
next_batch["valid_candidate_count"] = valid
next_batch["formal_ecp_pending_count"] = valid - validated
next_path.write_text(json.dumps(next_batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(json.dumps({"new_harbor_tasks": promoted, "validated_local_count": validated,
                  "formal_ecp_pending_count": valid - validated}, ensure_ascii=False))
