"""Build one Harbor job config for unverified tasks from the post-60 batch."""

import json
import zipfile
from pathlib import Path


root = Path.cwd()
verification = json.loads((root / "generated/VERIFICATION.json").read_text(encoding="utf-8"))
with zipfile.ZipFile(root / "work/terminal-bench-science-verified-local-20260904-174001.zip") as archive:
    original = json.loads(archive.read("VERIFICATION.json"))
original_paths = {entry["path"] for entry in original["tasks"]}

pending = [
    entry
    for entry in verification["tasks"]
    if entry["path"] not in original_paths and entry.get("status") != "validated_local"
]
config = {
    "jobs_dir": "jobs/harbor-new-batch-pending",
    "n_concurrent_trials": 8,
    "tasks": [{"path": f"generated/{entry['path']}"} for entry in pending],
    "agents": [{"name": "oracle"}],
    "environment": {"type": "docker", "delete": False},
}
output = root / "work/harbor-new-batch-pending.json"
output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"config": output.as_posix(), "pending_tasks": len(pending), "concurrency": 8}))
