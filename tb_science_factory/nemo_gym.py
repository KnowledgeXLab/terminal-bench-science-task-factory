"""Export verified task candidates as a NeMo Gym dataset.

NeMo Gym constructs agent trajectories from dataset rows at rollout time.  The
factory therefore exports the task prompt in the OpenAI Responses API shape
and keeps Harbor-specific routing data in ``verifier_metadata``.  The output
is intentionally JSONL: one independent task per line.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator

from .task_factory import _slug

GYM_SCHEMA_VERSION = "tb-science-factory.nemo-gym.dataset.v1"


def _verification_index(path: Path | None) -> dict[str, dict[str, Any]]:
    """Index optional Harbor verification evidence by candidate ID and slug."""
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("verification file must contain a JSON object")
    indexed: dict[str, dict[str, Any]] = {}
    for entry in payload.get("tasks", []):
        if not isinstance(entry, dict):
            continue
        verification = entry.get("verification") or {}
        if not isinstance(verification, dict):
            verification = {}
        merged = {"status": entry.get("status"), "verification": verification}
        for key in (entry.get("candidate_id"), entry.get("slug")):
            if isinstance(key, str) and key:
                indexed[key] = merged
    return indexed


def _candidate_rows(
    candidates_path: Path,
    verification_path: Path | None,
    *,
    allow_unverified: bool,
) -> Iterator[dict[str, Any]]:
    verification_by_key = _verification_index(verification_path)
    for line_number, raw in enumerate(candidates_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            candidate = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid candidate JSON on line {line_number}") from exc
        if not isinstance(candidate, dict):
            raise ValueError(f"candidate must be an object on line {line_number}")
        # Data Designer writes a versioned envelope around each generated
        # candidate. Accept that interchange format as well as the factory's
        # native candidate JSONL so the two stages can be chained directly.
        if isinstance(candidate.get("record"), dict):
            context = {
                key: candidate[key]
                for key in ("schema_version", "dataset_name", "run_id", "row_id")
                if key in candidate
            }
            candidate = dict(candidate["record"])
            candidate["_data_designer_context"] = context
        if candidate.get("validation_errors"):
            continue

        candidate = dict(candidate)
        recorded = verification_by_key.get(candidate.get("candidate_id"))
        if recorded is None:
            recorded = verification_by_key.get(candidate.get("slug"))
        if recorded is not None:
            candidate["status"] = recorded["status"]
            candidate["verification"] = {
                **(candidate.get("verification") or {}),
                **recorded["verification"],
            }
        verification = candidate.get("verification") or {}
        if not isinstance(verification, dict):
            verification = {}
        if not allow_unverified and not (
            candidate.get("status") == "verified" and verification.get("reward") == 1
        ):
            continue
        yield candidate


def _gym_record(candidate: dict[str, Any]) -> dict[str, Any]:
    """Convert one validated candidate into NeMo Gym's dataset contract."""
    instruction = candidate.get("instruction_md")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("candidate.instruction_md must be non-empty")
    slug = _slug(candidate.get("slug"))
    candidate_id = candidate.get("candidate_id") or slug
    verification = candidate.get("verification") or {}
    opd = candidate.get("opd") or {}
    if not isinstance(verification, dict):
        verification = {}
    if not isinstance(opd, dict):
        opd = {}
    data_designer_context = candidate.get("_data_designer_context")
    if not isinstance(data_designer_context, dict):
        data_designer_context = None

    # ``agent_ref`` is deliberately absent.  ``gym dataset collate`` adds it
    # from the selected agent configuration, as required by NeMo Gym.
    return {
        "id": candidate_id,
        "question": instruction,
        "responses_create_params": {
            "input": [{"role": "user", "content": instruction}],
        },
        "verifier_metadata": {
            "candidate_id": candidate_id,
            "task_slug": slug,
            "task_path": candidate.get("materialized_path", ""),
            "task_title": candidate.get("title", ""),
            "task_domain": candidate.get("domain", ""),
            "task_field": candidate.get("field", ""),
            "task_subfield": candidate.get("subfield", ""),
            "teacher_prompt": opd.get("teacher_prompt", instruction),
            "success_signal": opd.get("success_signal", "verifier reward equals 1"),
            "verification": verification,
        },
        "metadata": {
            "schema_version": GYM_SCHEMA_VERSION,
            "data_source": "terminal_bench_science_derived",
            **({"data_designer": data_designer_context} if data_designer_context else {}),
        },
    }


def export_gym_records(
    candidates_path: Path,
    output_path: Path,
    *,
    allow_unverified: bool = False,
    verification_path: Path | None = None,
) -> int:
    """Write candidates in the NeMo Gym JSONL task format.

    Unless ``allow_unverified`` is set, only candidates with Harbor verifier
    evidence ``status=verified`` and ``verification.reward=1`` are emitted.
    This matches the factory's existing training-data gate.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as sink:
        for candidate in _candidate_rows(
            candidates_path,
            verification_path,
            allow_unverified=allow_unverified,
        ):
            sink.write(json.dumps(_gym_record(candidate), ensure_ascii=False) + "\n")
            count += 1
    return count


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()
    count = export_gym_records(
        args.candidates,
        args.out,
        allow_unverified=args.allow_unverified,
        verification_path=args.verification,
    )
    print(json.dumps({"records": count, "output": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
