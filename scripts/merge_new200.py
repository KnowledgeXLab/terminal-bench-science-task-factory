"""Append the newly generated 200 candidates to the canonical audit ledgers."""

import json
from datetime import date
from pathlib import Path

from tb_science_factory.task_factory import validate_candidate


ROOT = Path.cwd()
GENERATED = ROOT / "generated"
CANDIDATE_PATH = GENERATED / "candidates" / "next_batch.jsonl"
POOL_PATH = ROOT / "work" / "new200_candidates.jsonl"
VERIFICATION_PATH = GENERATED / "VERIFICATION.json"
NEXT_PATH = GENERATED / "NEXT_BATCH.json"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


current = read_jsonl(CANDIDATE_PATH)
new_rows = read_jsonl(POOL_PATH)
if len(new_rows) != 200:
    raise SystemExit(f"expected 200 generated candidates, found {len(new_rows)}")

existing_paths = {str(row.get("materialized_path", "")) for row in current}
existing_ids = {str(row.get("candidate_id", "")) for row in current}
new_paths = [str(row.get("materialized_path", "")) for row in new_rows]
new_ids = [str(row.get("candidate_id", "")) for row in new_rows]
if len(set(new_paths)) != 200 or any(path in existing_paths for path in new_paths):
    raise SystemExit("new candidate paths overlap or are not unique")
if len(set(new_ids)) != 200 or any(candidate_id in existing_ids for candidate_id in new_ids):
    raise SystemExit("new candidate IDs overlap or are not unique")

verification = json.loads(VERIFICATION_PATH.read_text(encoding="utf-8"))
entries = {entry["path"]: entry for entry in verification.get("tasks", [])}
for row in new_rows:
    path = row["materialized_path"]
    task_root = GENERATED / path
    if not task_root.is_dir():
        raise SystemExit(f"missing materialized task: {task_root}")
    row["instruction_md"] = (task_root / "instruction.md").read_text(encoding="utf-8")
    row["task_toml"] = (task_root / "task.toml").read_text(encoding="utf-8")
    row["files"] = {
        file.relative_to(task_root).as_posix(): file.read_text(encoding="utf-8")
        for file in sorted(task_root.rglob("*"))
        if file.is_file() and file.name not in {"instruction.md", "task.toml"}
    }
    row["validation_errors"] = validate_candidate(row)
    if row["validation_errors"]:
        raise SystemExit(f"materialized candidate became invalid: {row['candidate_id']}: {row['validation_errors']}")
    row["status"] = "draft"
    entries[path] = {
        "candidate_id": row["candidate_id"],
        "slug": row["slug"],
        "domain": row["domain"],
        "field": row["field"],
        "path": path,
        "status": "draft",
        "verification": {
            "reward": 0,
            "backend": "pending local Harbor Docker oracle verification",
            "docker_harbor_verified": False,
        },
    }

current.extend(new_rows)
CANDIDATE_PATH.write_text(
    "\n".join(json.dumps(row, ensure_ascii=False) for row in current) + "\n",
    encoding="utf-8",
)
verification["generated_at"] = str(date.today())
verification["tasks"] = list(entries.values())
verification["local_smoke"] = {
    **verification.get("local_smoke", {}),
    "generated_at": str(date.today()),
    "materialized_count": len(current),
    "valid_candidate_count": len(current),
    "local_smoke_pass_count": verification.get("local_smoke", {}).get("local_smoke_pass_count", 0),
    "local_smoke_fail_count": verification.get("local_smoke", {}).get("local_smoke_fail_count", 0),
}
VERIFICATION_PATH.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

next_batch = json.loads(NEXT_PATH.read_text(encoding="utf-8"))
next_batch.update({
    "generated_at": str(date.today()),
    "materialized_count": len(current),
    "valid_candidate_count": len(current),
    "validated_local_count": sum(entry.get("status") == "validated_local" for entry in entries.values()),
    "formal_ecp_pending_count": sum(entry.get("status") != "validated_local" for entry in entries.values()),
    "latest_batch_count": 200,
    "latest_batch_status": "draft_pending_local_harbor",
})
next_batch.setdefault("notes", []).append(
    "A new batch of 200 candidates was generated on 2026-09-05; local Harbor verification is pending."
)
NEXT_PATH.write_text(json.dumps(next_batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "appended": 200,
    "materialized_count": len(current),
    "validated_local_count": next_batch["validated_local_count"],
    "formal_ecp_pending_count": next_batch["formal_ecp_pending_count"],
}, ensure_ascii=False))
