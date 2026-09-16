"""Generate a fresh pool of 200 candidates after the 2026-09-05 batch."""

import json
import re
import time
from pathlib import Path

from tb_science_factory.llm_client import OpenAICompatibleJSONClient, load_env_file
from tb_science_factory.task_factory import generate_candidates, validate_candidate


ROOT = Path.cwd()
REF_DIR = ROOT / "work" / "pattern_refs"
OUT_DIR = ROOT / "work" / "new200_batch2_raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)
POOL = ROOT / "work" / "new200_batch2_candidates.jsonl"
TARGET = 200
MAX_CALLS = 100
BATCH_SIZE = 5
MODEL = "gpt-5.6-sol"
ID_PREFIX = "tbds-20260905-"


def slug(value: object) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def task_path(row: dict) -> str:
    return "/".join(("tasks", str(row["domain"]), str(row["field"]), slug(row["slug"])))


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


existing_rows = read_jsonl(ROOT / "generated" / "candidates" / "next_batch.jsonl")
used_paths = {str(row.get("materialized_path", "")) for row in existing_rows if row.get("materialized_path")}
used_ids = {str(row.get("candidate_id", "")) for row in existing_rows if row.get("candidate_id")}
accepted = read_jsonl(POOL)
accepted_paths = {str(row.get("materialized_path", "")) for row in accepted}
used_ids.update(str(row.get("candidate_id", "")) for row in accepted)

invalid = 0
duplicates = 0
errors: list[str] = []
next_id = 1
while f"{ID_PREFIX}{next_id:04d}" in used_ids:
    next_id += 1

load_env_file(ROOT / ".env")
client = OpenAICompatibleJSONClient(
    model=MODEL,
    cache_dir=ROOT / "work" / "llm-cache-new200-batch2",
    timeout=240,
    max_retries=3,
)
references = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(REF_DIR.glob("*.json"))]
if not references:
    raise SystemExit("no pattern references found")

existing_rounds = []
for path in OUT_DIR.glob("round-*.jsonl"):
    try:
        existing_rounds.append(int(path.stem.rsplit("-", 1)[1]))
    except ValueError:
        pass
start_call = max(existing_rounds, default=0) + 1

for call_no in range(start_call, MAX_CALLS + 1):
    if len(accepted) >= TARGET:
        break
    reference = dict(references[(call_no - 1) % len(references)])
    reference["generation_nonce"] = f"new200-batch2-20260905-round-{call_no:03d}"
    raw_path = OUT_DIR / f"round-{call_no:03d}.jsonl"
    try:
        rows = generate_candidates(
            reference,
            output_path=raw_path,
            cache_dir=ROOT / "work" / "llm-cache-new200-batch2",
            model=MODEL,
            count=BATCH_SIZE,
            client=client,
        )
    except Exception as exc:
        errors.append(f"round {call_no}: {type(exc).__name__}: {exc}")
        print(json.dumps({"round": call_no, "error": str(exc)}, ensure_ascii=False), flush=True)
        time.sleep(1)
        continue

    added = 0
    for row in rows:
        row["validation_errors"] = validate_candidate(row)
        if row["validation_errors"]:
            invalid += 1
            continue
        path = task_path(row)
        if path in used_paths or path in accepted_paths:
            duplicates += 1
            continue
        candidate_id = f"{ID_PREFIX}{next_id:04d}"
        while candidate_id in used_ids:
            next_id += 1
            candidate_id = f"{ID_PREFIX}{next_id:04d}"
        next_id += 1
        row["candidate_id"] = candidate_id
        row["status"] = "draft"
        row["materialized_path"] = path
        row["generation"] = {**row.get("generation", {}), "batch": "new200-batch2", "round": call_no}
        accepted.append(row)
        accepted_paths.add(path)
        used_ids.add(candidate_id)
        added += 1
        if len(accepted) >= TARGET:
            break

    POOL.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in accepted) + "\n", encoding="utf-8")
    print(json.dumps({
        "round": call_no,
        "reference": reference.get("pattern_id"),
        "returned": len(rows),
        "added": added,
        "accepted": len(accepted),
        "invalid": invalid,
        "duplicates": duplicates,
    }, ensure_ascii=False), flush=True)

if len(accepted) < TARGET:
    print(json.dumps({"accepted": len(accepted), "target": TARGET, "errors": errors[-10:]}, ensure_ascii=False))
    raise SystemExit(2)

POOL.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in accepted[:TARGET]) + "\n", encoding="utf-8")
print(json.dumps({"pool": POOL.as_posix(), "candidates": TARGET, "invalid": invalid, "duplicates": duplicates}, ensure_ascii=False))
