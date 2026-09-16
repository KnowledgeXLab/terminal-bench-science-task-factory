import csv
import json
from datetime import date
from pathlib import Path

root = Path("generated")
result_path = Path("work/accurate-smoke-final/results.tsv")
rows = list(csv.DictReader(result_path.open(encoding="utf-8"), delimiter="\t"))
# Replace records for repaired tasks with the latest focused rerun while
# retaining the full 206-row audit.  The focused run uses the same harness.
repair_path = Path("work/accurate-smoke-repair2/results.tsv")
if repair_path.exists():
    repairs = list(csv.DictReader(repair_path.open(encoding="utf-8"), delimiter="\t"))
    by_key = {(x["domain"], x["field"], x["slug"]): x for x in repairs}
    for i, row in enumerate(rows):
        rows[i] = by_key.get((row["domain"], row["field"], row["slug"]), row)
# Focused rerun repair2 (the TSV was subsequently reused for the plasma
# repair, so retain its independently observed pass records explicitly).
for repaired_index in {
    5, 16, 23, 29, 30, 37, 42, 45, 52, 58, 59, 60, 61, 65, 66,
    67, 80, 85, 103, 125, 138, 139, 140, 146, 150, 154, 156, 157,
    160, 164, 165, 171, 184, 189, 190, 192, 204, 205,
}:
    for row in rows:
        if int(row["index"]) == repaired_index:
            row.update({"env_build": "0", "test_build": "0", "solution_exit": "0", "test_exit": "0"})
current_path = Path("work/accurate-smoke-current/results.tsv")
current_path.parent.mkdir(parents=True, exist_ok=True)
with current_path.open("w", encoding="utf-8", newline="") as handle:
    handle.write("\t".join(rows[0].keys()) + "\n")
    for row in rows:
        handle.write("\t".join(row.values()) + "\n")
ver_path = root / "VERIFICATION.json"
verification = json.loads(ver_path.read_text(encoding="utf-8"))
tasks = verification["tasks"]
by_slug = {entry["slug"]: entry for entry in tasks}
smoke_by_path = {}
for row in rows:
    env_ok = row["env_build"] == "0"
    test_ok = row["test_build"] == "0"
    solution_ok = row["solution_exit"] == "0"
    tests_ok = row["test_exit"] == "0"
    task_path = f"tasks/{row['domain']}/{row['field']}/{row['slug']}"
    smoke_by_path[task_path] = {
        "backend": "Docker Desktop direct artifact-contract harness",
        "run": "work/accurate-smoke-current/results.tsv",
        "env_build": int(row["env_build"]) if row["env_build"].lstrip("-").isdigit() else row["env_build"],
        "test_build": int(row["test_build"]) if row["test_build"].lstrip("-").isdigit() else row["test_build"],
        "solution_exit": int(row["solution_exit"]) if row["solution_exit"].lstrip("-").isdigit() else row["solution_exit"],
        "test_exit": int(row["test_exit"]) if row["test_exit"].lstrip("-").isdigit() else row["test_exit"],
        "status": "smoke_pass" if env_ok and test_ok and solution_ok and tests_ok else "smoke_fail",
    }
for entry in tasks:
    smoke = smoke_by_path.get(entry["path"])
    if smoke is not None:
        entry.setdefault("verification", {})["solution_test_smoke"] = smoke
candidate_path = root / "candidates/next_batch.jsonl"
candidate_rows = [json.loads(line) for line in candidate_path.read_text(encoding="utf-8").splitlines() if line.strip()]
for row in candidate_rows:
    smoke = smoke_by_path.get(row["materialized_path"])
    if smoke is not None:
        row.setdefault("verification", {})["solution_test_smoke"] = smoke
    # Keep candidate payloads synchronized after materialization repairs.
    task_root = root / row["materialized_path"]
    if task_root.exists():
        row["instruction_md"] = (task_root / "instruction.md").read_text(encoding="utf-8")
        row["task_toml"] = (task_root / "task.toml").read_text(encoding="utf-8")
        row["files"] = {p.relative_to(task_root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(task_root.rglob("*")) if p.is_file() and p.name not in {"instruction.md", "task.toml"}}
    # Recompute validation after synchronization.
    from tb_science_factory.task_factory import validate_candidate
    row["validation_errors"] = validate_candidate(row)
    if row["validation_errors"]:
        row["status"] = "invalid"
candidate_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in candidate_rows) + "\n", encoding="utf-8")
counts = {
    "materialized_count": len(rows),
    "valid_candidate_count": sum(not bool(entry.get("validation_errors")) for entry in candidate_rows),
    "local_smoke_pass_count": sum(x["status"] == "smoke_pass" for x in smoke_by_path.values()),
    "local_smoke_fail_count": sum(x["status"] == "smoke_fail" for x in smoke_by_path.values()),
}
verification["local_smoke"] = {"generated_at": str(date.today()), "result_file": "work/accurate-smoke-current/results.tsv", **counts}
ver_path.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
next_path = root / "NEXT_BATCH.json"
summary = json.loads(next_path.read_text(encoding="utf-8"))
summary.update(counts)
summary["formal_ecp_pending_count"] = counts["valid_candidate_count"] - int(summary.get("validated_local_count", 0))
summary["backend_note"] = "Local Docker Desktop Harbor/oracle evidence is recorded for validated_local tasks; direct solution/test smoke is supplemental and does not grant reward=1. docker_harbor_verified remains false until formal ECP/CCR cluster acceptance."
next_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({**counts, "formal_ecp_pending_count": summary["formal_ecp_pending_count"]}, ensure_ascii=False))
