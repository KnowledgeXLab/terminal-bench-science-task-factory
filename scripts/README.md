# Pipeline scripts

这些脚本从仓库根目录运行，生成和验证过程产生的 JSONL、Harbor jobs、缓存及压缩包统一写入被忽略的 `work/` 或 `jobs/` 目录。

- `generate_*`：批量调用模型生成候选任务；
- `make_*_harbor_config.py`：生成 Harbor 批量运行配置；
- `merge_*`、`sync_candidates.py`：合并候选并同步 materialized 任务；
- `record_harbor_rewards.*`：把 Harbor reward 写入验证清单；
- `package_*`：打包已通过本机 Harbor 验证的任务；
- `static_check.py`、`scan_*`：交付前静态和产物检查。
