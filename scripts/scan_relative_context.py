import tomllib
from pathlib import Path

root = Path("generated/tasks")
if not root.is_dir():
    print("generated/tasks is not present; outputs are ignored")
    raise SystemExit(0)
for task_toml in sorted(root.rglob("task.toml")):
    cfg = tomllib.loads(task_toml.read_text(encoding="utf-8"))
    values = cfg.get("artifacts", [])
    relative = [value for value in values if not value.startswith("/")]
    if not relative:
        continue
    solution = task_toml.parent / "solution"
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in solution.glob("*") if p.is_file())
    output_refs = sorted({token for token in text.split() if "output" in token or "result" in token or "artifact" in token})
    print(task_toml.parent.relative_to(root).as_posix(), "artifacts=", relative, "refs=", output_refs[:16])
