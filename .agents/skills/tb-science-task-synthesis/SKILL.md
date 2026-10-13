---
name: tb-science-task-synthesis
description: Transfer a scientific workflow from papers, code, examples or method descriptions into new independent Harbor tasks. Prepare reference pattern cards, generate candidates and materialize validated packages.
---

# TB Science task synthesis

## Capability

Choose TB Science to abstract a reusable scientific workflow and design a new independent problem with new inputs. It may transfer parameter estimation, boundary handling or verification patterns without copying the source equations, constants, data and answers. Choose SAF when retaining a concrete reference method is essential, Omega for paper/KG design, or Sci for exploration grounded in mixed real materials.

## Prepare inputs

Extract an actual workflow and observable scientific outputs from supplied materials; record sources/licenses. Create reference JSON at `seed/tb-science/reference.json` under the run. The CLI parses JSON and supplies it to the model without a fixed input schema. Recommended pattern-card fields are `pattern_id`, `source_family`, `workflow`, `scientific_outputs`, `hardness_knobs`, `derivation_rules`; see [pattern cards](../../../references/pattern_cards.json). An array of cards is not automatically one task per card.

Distinguish source facts from proposed task variations. Do not fabricate missing scientific content or use empty JSON to satisfy preparation. If the goal requires reproducing the source problem rather than transferring a pattern, reconsider the other skills.

## End-to-end entrypoint

In TTF hosted mode, submit `tb.generate` with `reference` and optional positive `count`, then `tasks.collect` with `pipeline: tb-science`. Omitted count uses the host's bounded redundancy target. The host prepares JSONL with `request_id`, `reference`, `model` and `count`, then runs the existing Data Designer entrypoint:

```bash
python -m tb_science_factory.designer --requests "$REQUESTS" --out "$OUT" --concurrency 1 --env-file /dev/null
```

One native command generates candidates, validates and materializes packages. The planner does not shell-run it. An existing `tb.materialize` step is only a compatibility check of these results; it does not rerun generation or materialization. Do not force overwrite packages or use new step IDs to repeat generation after failure. No hosted native checkpoint resume is supplied for this integration.

## Results

Read `items/<request_id>/result.json`, `candidates.jsonl`, and the reported task paths. Native candidates, cache and materialized tasks remain in that item directory. Count actual materialized packages; partial or failed native results are not proof that every requested task exists. Preserve rejected candidates and errors.

TB performs structural/file-contract validation and materialization, with no native independent Auditor or Harbor Oracle execution. Do not label this evidence as Oracle-certified or scientifically execution-proven. TTF retains evidence under `tb-science/`, checks Harbor structure and collects eligible packages into the shared `tasks/` and `task_manifest.json`; downstream real solver rollout remains a separate host step.
