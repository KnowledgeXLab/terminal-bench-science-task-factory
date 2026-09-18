import tomllib
from pathlib import Path

root = Path("generated/tasks")
if not root.is_dir():
    print("relative_artifact_tasks=0 (generated/tasks is not present; outputs are ignored)")
    raise SystemExit(0)
bad = []
for task_toml in sorted(root.rglob("task.toml")):
    text = task_toml.read_text(encoding="utf-8")
    values = tomllib.loads(text).get("artifacts", [])
    relative = [value for value in values if not value.startswith("/")]
    if relative:
        bad.append((task_toml.parent.relative_to(root).as_posix(), relative))
print(f"relative_artifact_tasks={len(bad)}")
for path, values in bad:
    print(path, values)
