"""Package the 146 tasks added after the original 60-task delivery."""

import json
import re
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path.cwd()
GENERATED = ROOT / "generated"
BASELINE = ROOT / "work" / "terminal-bench-science-verified-local-20260904-174001.zip"

verification = json.loads((GENERATED / "VERIFICATION.json").read_text(encoding="utf-8"))
with zipfile.ZipFile(BASELINE) as archive:
    original_verification = json.loads(archive.read("VERIFICATION.json"))
original_paths = {entry["path"] for entry in original_verification["tasks"]}

selected = [entry for entry in verification["tasks"] if entry["path"] not in original_paths]
if len(original_paths) != 60:
    raise SystemExit(f"expected 60 original baseline paths, found {len(original_paths)}")
if len(selected) != 146:
    raise SystemExit(f"expected 146 new paths, found {len(selected)}")
if any(entry.get("status") != "validated_local" for entry in selected):
    pending = [entry["path"] for entry in selected if entry.get("status") != "validated_local"]
    raise SystemExit(f"new tasks not validated_local: {pending}")

for entry in selected:
    local = entry.get("verification", {}).get("local_harbor", {})
    rewards = local.get("rewards", [])
    if not rewards or any(float(reward) != 1.0 for reward in rewards):
        raise SystemExit(f"missing all-1 local Harbor evidence: {entry['path']}")

candidate_rows = [
    json.loads(line)
    for line in (GENERATED / "candidates" / "next_batch.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
selected_ids = {entry["candidate_id"] for entry in selected}
candidates = [row for row in candidate_rows if row.get("candidate_id") in selected_ids]
if len(candidates) != 146:
    raise SystemExit(f"expected 146 selected candidates, found {len(candidates)}")

stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
archive_path = ROOT / "work" / f"terminal-bench-science-new-146-harbor-verified-{stamp}.zip"
subset_verification = {
    "generated_at": verification.get("generated_at"),
    "scope": "146 tasks added after the original 60-task delivery; original 60 excluded",
    "backend_note": "All selected tasks have recorded local Harbor Docker oracle reward=1 evidence.",
    "docker_harbor_verified": False,
    "formal_ecp_gate": {"required": True, "status": "pending"},
    "tasks": selected,
}
readme = """# Terminal-Bench Science — new 146-task delivery

This archive contains exactly the 146 synthetic task directories added after the original 60-task delivery. The original 60 paths are intentionally excluded. Each task includes its instruction, task metadata, generated data, environment, oracle solution, and independent verifier tests.

Every selected task has been run in the local Docker Desktop Harbor environment with the `oracle` agent and recorded verifier reward `1`. The evidence is summarized in `VERIFICATION.json` and `candidates.jsonl`. Formal ECP/CCR cluster verification is still pending and is not claimed by this package.

The archive excludes factory source code, API credentials, `.env`, jobs, caches, and Docker images.
"""

with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for entry in sorted(selected, key=lambda item: item["path"]):
        task_root = GENERATED / entry["path"]
        if not task_root.is_dir():
            raise SystemExit(f"missing task directory: {task_root}")
        for path in sorted(task_root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(GENERATED).as_posix())
    zf.writestr(
        "candidates.jsonl",
        "\n".join(json.dumps(row, ensure_ascii=False) for row in candidates) + "\n",
    )
    zf.writestr("VERIFICATION.json", json.dumps(subset_verification, ensure_ascii=False, indent=2) + "\n")
    zf.writestr("README.md", readme)

secret_pattern = re.compile(r"(?i)(OPENAI_API_KEY|Authorization:\s*Bearer|sk-[A-Za-z0-9])")
with zipfile.ZipFile(archive_path) as zf:
    names = zf.namelist()
    if zf.testzip() is not None:
        raise SystemExit("archive CRC test failed")
    instructions = [name for name in names if name.endswith("/instruction.md")]
    test_scripts = [name for name in names if name.endswith("/tests/test.sh")]
    task_paths = {name.rsplit("/", 1)[0] for name in instructions}
    forbidden = [
        name for name in names
        if Path(name).name == ".env" or name.startswith(("jobs/", "work/", "tb_science_factory/"))
    ]
    original_leaks = [name for name in task_paths if name.removeprefix("generated/") in original_paths]
    empty_required = []
    bad_shebang = []
    secret_hits = []
    for name in names:
        if name.endswith((
            "instruction.md", "task.toml", "/environment/Dockerfile", "/solution/solve.sh",
            "/tests/Dockerfile", "/tests/test.sh",
        )) and not zf.read(name):
            empty_required.append(name)
        if name.endswith("/tests/test.sh") and not zf.read(name).startswith(b"#!"):
            bad_shebang.append(name)
        if not name.endswith("/"):
            text = zf.read(name).decode("utf-8", errors="ignore")
            if secret_pattern.search(text):
                secret_hits.append(name)
    checks = {
        "instructions": len(instructions),
        "tests": len(test_scripts),
        "task_dirs": len(task_paths),
        "forbidden": forbidden,
        "original_leaks": original_leaks,
        "empty_required": empty_required,
        "bad_shebang": bad_shebang,
        "secret_hits": secret_hits,
    }
    if (
        len(instructions) != 146
        or len(test_scripts) != 146
        or len(task_paths) != 146
        or forbidden
        or original_leaks
        or empty_required
        or bad_shebang
        or secret_hits
    ):
        raise SystemExit(json.dumps(checks, ensure_ascii=False))

print(json.dumps({
    "archive": archive_path.as_posix(),
    "bytes": archive_path.stat().st_size,
    "entries": len(names),
    "tasks": len(task_paths),
    "selected_new_tasks": len(selected),
    "original_excluded": len(original_paths),
    "secret_hits": 0,
    "formal_ecp_pending": True,
}, ensure_ascii=False))
