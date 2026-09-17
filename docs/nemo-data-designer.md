# NeMo Data Designer pipeline

The `feature/nemo-data-designer-pipeline` branch adds an optional NVIDIA NeMo
Data Designer backend. It makes the seed dataset and generated candidates a
stable tabular contract while Data Designer handles row groups, concurrency,
retry behavior, and resumable checkpoints.

Install the optional dependency:

```bash
python -m pip install -e ".[nemo]"
```

Prepare a CSV or Parquet seed dataset with a `pattern_json` column. Each row is
one public workflow pattern card. Then run:

```bash
python -m tb_science_factory.data_designer_pipeline \
  --seed references/pattern_cards.csv \
  --out work/data-designer/candidates.jsonl \
  --num-records 32 \
  --buffer-size 8 \
  --max-parallel-requests 8 \
  --max-concurrent-row-groups 3
```

The output is JSONL with `schema_version`, `dataset_name`, `run_id`, `row_id`,
and `record`. The `record` object has the same candidate fields consumed by
the existing validation and materialization code. This keeps downstream
Harbor and OPD steps independent of the Data Designer runtime.

Data Designer uses the configured model provider's credentials. For NVIDIA's
default provider set `NVIDIA_API_KEY`; for another provider configure its
provider and endpoint according to the Data Designer model configuration.
Never put credentials in seed files or generated output.

The defaults use `ResumeMode.IF_POSSIBLE`, a row-group buffer of 100, three
active row groups, and eight concurrent requests per model. Tune these values
against the inference server's capacity; Data Designer's request-admission
controller reduces concurrency when the server returns rate-limit responses.

References: [NVIDIA Data Designer welcome](https://docs.nvidia.com/nemo/datadesigner/getting-started/welcome),
[architecture and performance](https://docs.nvidia.com/nemo/datadesigner/concepts/architecture-performance),
and [structured outputs](https://docs.nvidia.com/nemo/datadesigner/tutorials/structured-outputs-jinja-expressions-and-conditional-generation).
