import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

project = Path.cwd()
generated = project / "generated"
verification = json.loads((generated / "VERIFICATION.json").read_text(encoding="utf-8"))
selected = [entry for entry in verification["tasks"] if entry.get("status") == "validated_local"]
if len(selected) != 100:
    raise SystemExit(f"expected 100 validated_local tasks, found {len(selected)}")
selected_ids = {entry["candidate_id"] for entry in selected}
candidates = [json.loads(line) for line in (generated / "candidates/next_batch.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
candidates = [row for row in candidates if row["candidate_id"] in selected_ids]
if len(candidates) != 100:
    raise SystemExit(f"expected 100 selected candidates, found {len(candidates)}")

stamp = "20260904-202526"
archive = project / "work" / f"terminal-bench-science-verified-local-{stamp}.zip.new"
subset_verification = {
    "generated_at": verification.get("generated_at"),
    "scope": "100 tasks with recorded local Harbor Docker oracle reward=1 evidence",
    "backend_note": verification.get("backend_note"),
    "docker_harbor_verified": False,
    "formal_ecp_gate": {"required": True, "status": "pending"},
    "tasks": selected,
}
readme = """# Terminal-Bench Science synthetic task delivery

This archive contains 100 complete synthetic task directories. Each directory includes the instruction, task metadata, independent environment/data generation, oracle solution, and verifier tests.

Selection criterion: the task has recorded local Harbor/Docker oracle verification with reward equal to 1 (one or more local trials; seven tasks also have five repeated trials). The latest direct Docker solution/test smoke evidence is included as supplemental evidence. Formal ECP/CCR cluster verification remains pending and is not claimed by this archive.

The archive intentionally excludes factory source code, API credentials, `.env`, jobs, caches, and Docker images.
"""

with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for entry in sorted(selected, key=lambda item: item["path"]):
        task_root = generated / entry["path"]
        if not task_root.is_dir():
            raise SystemExit(f"missing task directory: {task_root}")
        for path in sorted(task_root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(generated).as_posix())
    zf.writestr("candidates.jsonl", "\n".join(json.dumps(row, ensure_ascii=False) for row in candidates) + "\n")
    zf.writestr("VERIFICATION.json", json.dumps(subset_verification, ensure_ascii=False, indent=2) + "\n")
    zf.writestr("README.md", readme)

secret_pattern = re.compile(r"(?i)(OPENAI_API_KEY|Authorization:\s*Bearer|sk-[A-Za-z0-9])")
with zipfile.ZipFile(archive) as zf:
    names = zf.namelist()
    instructions = [name for name in names if name.endswith("/instruction.md")]
    test_scripts = [name for name in names if name.endswith("/tests/test.sh")]
    forbidden = [name for name in names if Path(name).name == ".env" or name.startswith(("jobs/", "work/", "tb_science_factory/"))]
    empty_required = []
    bad_shebang = []
    secret_hits = []
    for name in names:
        if name.endswith(("instruction.md", "task.toml", "/environment/Dockerfile", "/solution/solve.sh", "/tests/Dockerfile", "/tests/test.sh")) and not zf.read(name):
            empty_required.append(name)
        if name.endswith("/tests/test.sh") and not zf.read(name).startswith(b"#!"):
            bad_shebang.append(name)
        if not name.endswith("/"):
            text = zf.read(name).decode("utf-8", errors="ignore")
            if secret_pattern.search(text):
                secret_hits.append(name)
    if len(instructions) != 100 or len(test_scripts) != 100 or forbidden or empty_required or bad_shebang or secret_hits:
        raise SystemExit(json.dumps({"instructions": len(instructions), "tests": len(test_scripts), "forbidden": forbidden, "empty_required": empty_required, "bad_shebang": bad_shebang, "secret_hits": secret_hits}, ensure_ascii=False))
print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "entries": len(names), "tasks": len(instructions), "secret_hits": 0, "formal_ecp_pending": True}, ensure_ascii=False))
