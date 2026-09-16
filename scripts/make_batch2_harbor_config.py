import json
from pathlib import Path

root = Path.cwd()
verification = json.loads((root / "generated/VERIFICATION.json").read_text(encoding="utf-8"))
selected = [
    entry for entry in verification["tasks"]
    if 201 <= int(str(entry.get("candidate_id", "0")).rsplit("-", 1)[-1]) <= 400
]
if len(selected) != 200:
    raise SystemExit(f"expected 200 batch2 tasks, found {len(selected)}")
config = {
    "jobs_dir": "jobs/harbor-new200-batch2",
    "n_concurrent_trials": 8,
    "tasks": [{"path": "generated/" + entry["path"]} for entry in selected],
    "agents": [{"name": "oracle"}],
    "environment": {"type": "docker", "delete": False},
}
(root / "work/harbor-batch2.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"tasks": len(selected), "config": "work/harbor-batch2.json"}))
