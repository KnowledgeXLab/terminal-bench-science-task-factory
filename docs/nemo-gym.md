# NeMo Gym task dataset export

The factory can export verified Harbor task candidates as a NeMo Gym dataset:

```bash
python -m tb_science_factory.task_factory export-gym \
  --candidates generated/candidates/pilot.jsonl \
  --verification generated/VERIFICATION.json \
  --out generated/gym/pilot_verified.jsonl
```

Each output line is a NeMo Gym task row. It contains:

- `responses_create_params.input`: the task instruction as an OpenAI
  Responses API user message;
- `id` and `question`: stable task identity and a human-readable copy of the
  prompt; and
- `verifier_metadata`: the candidate ID, task slug/path, scientific metadata,
  success signal, and Harbor verification evidence for a resources server.

The exporter does not write `agent_ref`. NeMo Gym's `gym dataset collate`
command adds that routing field from the selected agent configuration. NeMo
Gym then constructs the response trajectory while the agent interacts with
the configured environment; this file is the task dataset that seeds those
rollouts, not a fabricated trajectory.

The exporter accepts both the factory's native candidate JSONL and the
versioned JSONL envelopes produced by the NeMo Data Designer pipeline. For an
enveloped input, its `dataset_name`, `run_id`, and `row_id` are retained under
`metadata.data_designer` for run correlation.

By default, only candidates with `status=verified` and
`verification.reward=1` are emitted. `--allow-unverified` is available for
local format checks and should not be used for production training data.

The format follows [NeMo Gym's dataset preparation
contract](https://docs.nvidia.com/nemo/gym/data), which requires
`responses_create_params` and permits task-specific verifier fields.
