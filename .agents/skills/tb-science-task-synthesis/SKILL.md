---
name: tb-science-task-synthesis
description: Transfer a scientific workflow from papers, code, examples or method descriptions into new independent Harbor tasks. Prepare reference pattern cards, generate candidates and materialize validated packages.
---

# TB Science task synthesis

## Capability

Choose TB Science to abstract a reusable scientific workflow and design a new independent problem with new inputs. It may transfer parameter estimation, boundary handling or verification patterns without copying the source equations, constants, data and answers. Choose SAF when retaining a concrete reference method is essential, Omega for paper/KG design, or Sci for exploration grounded in mixed real materials.

## Prepare inputs

Extract an actual workflow and observable scientific outputs from supplied materials; record sources/licenses. Create reference JSON under the run. The CLI parses JSON and supplies it to the model without a fixed input schema. Recommended pattern-card fields are `pattern_id`, `source_family`, `workflow`, `scientific_outputs`, `hardness_knobs`, `derivation_rules`; see [pattern cards](../../../references/pattern_cards.json). An array of cards is not automatically one task per card.

Distinguish source facts from proposed task variations. Do not fabricate missing scientific content or use empty JSON to satisfy preparation. If the goal requires reproducing the source problem rather than transferring a pattern, reconsider the other skills.

## End-to-end entrypoint

In TTF hosted mode, submit `tb.generate` with `reference` and optional positive `count`, then `tb.materialize` with `{}`, then `tasks.collect` with `pipeline: tb-science`. Omitted count uses the host's bounded redundancy target. The host owns execution and model injection; the planner does not shell-run these commands. Native command semantics are:

```bash
python -m tb_science_factory.task_factory generate   --reference "$REF" --out "$OUT/candidates.jsonl"   --cache-dir "$OUT/cache" --count "$N" --model "$MODEL"
python -m tb_science_factory.task_factory materialize   --candidates "$OUT/candidates.jsonl" --out-root "$OUT/tasks"
```

Run materialize only after candidate generation succeeds. Keep native candidate contract checks and model-call behavior. Do not force overwrite packages or use new step IDs to repeat generation after failure. No hosted native checkpoint resume is supplied for this integration.

## Results

Candidate records and cache remain in the native output root. Packages are materialized under `tasks/tasks/<domain>/<field>/<slug>/`. Count actual valid candidates and materialized packages: a successful materialize exit may still produce zero tasks. Preserve rejected candidates and errors.

TB performs structural/file-contract validation and materialization, with no native independent Auditor or Harbor Oracle execution. Do not label this evidence as Oracle-certified or scientifically execution-proven. TTF retains evidence under `native/tb-science/`, checks Harbor structure and collects eligible packages into the shared `tasks/` and `task_manifest.json`; downstream real solver rollout remains a separate host step.
