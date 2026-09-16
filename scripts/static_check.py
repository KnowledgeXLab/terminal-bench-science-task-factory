import ast
import json
import re
from pathlib import Path

root = Path("generated/tasks")
tasks = sorted({p.parent for p in root.rglob("instruction.md")})
missing, empty, shebang, reward, canary, heredoc, secret, pybad = [], [], [], [], [], [], [], []
required = ["instruction.md", "task.toml", "environment/Dockerfile", "solution/solve.sh", "tests/Dockerfile", "tests/test.sh"]
for task in tasks:
    for rel in required:
        path = task / rel
        if not path.exists():
            missing.append((str(task), rel))
        elif path.stat().st_size == 0:
            empty.append((str(task), rel))
    test_sh = task / "tests/test.sh"
    if test_sh.exists():
        content = test_sh.read_text(encoding="utf-8", errors="replace")
        if not content.startswith("#!"):
            shebang.append(str(task))
        if "harbor-canary" not in content or "reward.txt" not in content:
            reward.append(str(task))
    for path in task.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        if "harbor-canary" not in content:
            canary.append(str(path))
        if re.search(r"RUN\s+(?:python3?|[A-Za-z0-9_./-]+)\s+-\s+<<", content) or re.search(r"RUN\s+<<[A-Za-z0-9_'\"]+\s+python", content):
            heredoc.append(str(path))
        if re.search(r"(?i)(OPENAI_API_KEY|Authorization:\s*Bearer|sk-[A-Za-z0-9])", content):
            secret.append(str(path))
        if path.suffix == ".py":
            try:
                ast.parse(content)
            except Exception as exc:
                pybad.append((str(path), str(exc)))
print(json.dumps({
    "tasks": len(tasks),
    "missing_count": len(missing), "missing": missing[:10],
    "empty_count": len(empty), "empty": empty[:10],
    "shebang_count": len(shebang), "shebang": shebang[:10],
    "reward_count": len(reward), "reward": reward[:10],
    "canary_count": len(canary), "canary": canary[:10],
    "heredoc_count": len(heredoc), "heredoc": heredoc[:10],
    "secret_count": len(secret), "secret": secret[:10],
    "python_bad_count": len(pybad), "python_bad": pybad[:10],
}, ensure_ascii=False))
