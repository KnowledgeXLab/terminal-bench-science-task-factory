"""Complete batch 2 generation with a small bounded parallel request pool."""

import concurrent.futures
import json
import re
import time
from pathlib import Path

from tb_science_factory.llm_client import OpenAICompatibleJSONClient, load_env_file
from tb_science_factory.task_factory import generate_candidates, validate_candidate


ROOT = Path.cwd()
REF_DIR = ROOT / "work" / "pattern_refs"
OUT_DIR = ROOT / "work" / "new200_batch2_raw"
POOL = ROOT / "work" / "new200_batch2_candidates.jsonl"
TARGET = 200
BATCH_SIZE = 5
WORKERS = 4
ID_PREFIX = "tbds-20260905-"


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def task_path(row: dict) -> str:
    return "/".join(("tasks", str(row["domain"]), str(row["field"]), slug(row["slug"])))


def request_one(round_no: int, reference: dict) -> tuple[int, list[dict], str | None]:
    ref = dict(reference)
    ref["generation_nonce"] = f"new200-batch2-20260905-round-{round_no:03d}"
    raw_path = OUT_DIR / f"round-{round_no:03d}.jsonl"
    try:
        client = OpenAICompatibleJSONClient(
            model="gpt-5.6-sol",
            cache_dir=ROOT / "work" / "llm-cache-new200-batch2",
            timeout=240,
            max_retries=3,
        )
        rows = generate_candidates(
            ref,
            output_path=raw_path,
            cache_dir=ROOT / "work" / "llm-cache-new200-batch2",
            model="gpt-5.6-sol",
            count=BATCH_SIZE,
            client=client,
        )
        return round_no, rows, None
    except Exception as exc:
        return round_no, [], f"{type(exc).__name__}: {exc}"


existing = read_jsonl(ROOT / "generated" / "candidates" / "next_batch.jsonl")
accepted = read_jsonl(POOL)
used_paths = {str(r.get("materialized_path", "")) for r in existing + accepted if r.get("materialized_path")}
used_ids = {str(r.get("candidate_id", "")) for r in existing + accepted if r.get("candidate_id")}
next_id = 1
while f"{ID_PREFIX}{next_id:04d}" in used_ids:
    next_id += 1

references = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(REF_DIR.glob("*.json"))]
if not references:
    raise SystemExit("no pattern references found")
load_env_file(ROOT / ".env")
existing_rounds = []
for p in OUT_DIR.glob("round-*.jsonl"):
    try:
        existing_rounds.append(int(p.stem.rsplit("-", 1)[1]))
    except ValueError:
        pass
next_round = max(existing_rounds, default=0) + 1
errors: list[str] = []
invalid = duplicates = 0

with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
    while len(accepted) < TARGET:
        futures = {
            pool.submit(request_one, n, references[(n - 1) % len(references)]): n
            for n in range(next_round, next_round + WORKERS)
        }
        next_round += WORKERS
        for future in concurrent.futures.as_completed(futures):
            round_no, rows, error = future.result()
            if error:
                errors.append(f"round {round_no}: {error}")
                print(json.dumps({"round": round_no, "error": error}, ensure_ascii=False), flush=True)
                continue
            added = 0
            for row in rows:
                row["validation_errors"] = validate_candidate(row)
                if row["validation_errors"]:
                    invalid += 1
                    continue
                path = task_path(row)
                if path in used_paths:
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
                row["generation"] = {**row.get("generation", {}), "batch": "new200-batch2", "round": round_no}
                accepted.append(row)
                used_paths.add(path)
                used_ids.add(candidate_id)
                added += 1
                if len(accepted) >= TARGET:
                    break
            POOL.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in accepted[:TARGET]) + "\n", encoding="utf-8")
            print(json.dumps({"round": round_no, "returned": len(rows), "added": added, "accepted": len(accepted), "invalid": invalid, "duplicates": duplicates}, ensure_ascii=False), flush=True)

if len(accepted) < TARGET:
    raise SystemExit(json.dumps({"accepted": len(accepted), "target": TARGET, "errors": errors[-10:]}, ensure_ascii=False))
POOL.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in accepted[:TARGET]) + "\n", encoding="utf-8")
print(json.dumps({"pool": POOL.as_posix(), "candidates": TARGET, "invalid": invalid, "duplicates": duplicates}, ensure_ascii=False))
