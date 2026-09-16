import json
from pathlib import Path

from tb_science_factory.task_factory import validate_candidate

root = Path("generated")
candidate_path = root / "candidates" / "next_batch.jsonl"
rows = [json.loads(line) for line in candidate_path.read_text(encoding="utf-8").splitlines() if line.strip()]
valid = 0
invalid = []
for row in rows:
    task_root = root / row["materialized_path"]
    if task_root.exists():
        row["instruction_md"] = (task_root / "instruction.md").read_text(encoding="utf-8")
        row["task_toml"] = (task_root / "task.toml").read_text(encoding="utf-8")
        files = {}
        for path in sorted(task_root.rglob("*")):
            if path.is_file() and path.name not in {"instruction.md", "task.toml"}:
                files[path.relative_to(task_root).as_posix()] = path.read_text(encoding="utf-8")
        row["files"] = files
        errors = validate_candidate(row)
        row["validation_errors"] = errors
        if errors:
            row["status"] = "invalid"
            invalid.append((row["candidate_id"], row["materialized_path"], errors))
        else:
            valid += 1
            if row.get("status") == "invalid":
                row["status"] = "draft"
    else:
        row["validation_errors"] = ["materialized task directory is missing"]
        row["status"] = "invalid"
        invalid.append((row["candidate_id"], row.get("materialized_path"), row["validation_errors"]))
candidate_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
print(json.dumps({"rows": len(rows), "valid": valid, "invalid": len(invalid), "invalid_rows": invalid}, ensure_ascii=False))
