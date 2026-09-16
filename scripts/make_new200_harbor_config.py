"""Build a Harbor config for the 200 tasks generated on 2026-09-05."""

import json
import zipfile
from pathlib import Path


root = Path.cwd()
verification = json.loads((root / "generated/VERIFICATION.json").read_text(encoding="utf-8"))
baseline_zip = root / "work/terminal-bench-science-verified-local-20260904-174001.zip"
with zipfile.ZipFile(baseline_zip) as archive:
    baseline = json.loads(archive.read("VERIFICATION.json"))
baseline_paths = {entry["path"] for entry in baseline["tasks"]}

pending = [
    entry
    for entry in verification["tasks"]
    if entry["path"] not in baseline_paths and entry.get("status") != "validated_local"
]
if len(pending) != 200:
    raise SystemExit(f"expected 200 pending tasks, found {len(pending)}")

config = {
    "jobs_dir": "jobs/harbor-new200",
    "n_concurrent_trials": 8,
    "tasks": [{"path": f"generated/{entry['path']}"} for entry in pending],
    "agents": [{"name": "oracle"}],
    "environment": {"type": "docker", "delete": False},
}
output = root / "work/harbor-new200.json"
output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"config": output.as_posix(), "pending_tasks": len(pending), "concurrency": 8}))
