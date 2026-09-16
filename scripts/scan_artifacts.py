import tomllib
from pathlib import Path

root = Path("generated/tasks")
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
