# Terminal-Bench-Science 衍生任务工厂

本项目的 task schema、Harbor 目录布局、Oracle/verifier 生命周期和 OPD 导出格式均按 Terminal-Bench-Science/Harbor 任务定义。

## 外部模型配置

```bash
export API_BASE="https://<provider>/v1"
export API_KEY="<secret>"
```

也接受 `OPENAI_BASE_URL` 与 `OPENAI_API_KEY`

## 流程

1. 从 `references/pattern_cards.json` 选择只含公开 workflow pattern 的 TB-Science reference card（不放原任务答案）。
2. `python -m tb_science_factory.task_factory generate ...` 调外部模型，得到 task-package 草稿 JSONL。
3. 检查 `validation_errors`，人工审阅科学性、难度和污染风险。
4. `materialize` 写出原生 Harbor task 目录；在有 Harbor/Docker 的环境执行 Oracle、nop 和 verifier 检查。
5. 只有 verifier reward 确认是 `1` 后，才用 `export-opd` 导出 VeRL 所需的 `data_source/prompt/reward_model/extra_info` JSONL。

生成器不会声称候选已经通过 benchmark：只有在 Oracle 真正得到 verifier reward `1` 后，才应将 `status` 改为 `verified` 并放入 OPD 训练集。`export-opd` 默认会跳过所有 draft/unverified 行；`--allow-unverified` 仅用于本地格式 smoke test，不能用于正式训练。

示例：

```bash
PYTHONPATH=. python -m tb_science_factory.task_factory generate \
  --reference references/pattern_cards.json \
  --out work/candidates.jsonl --cache-dir work/llm-cache \
  --model <provider-model> --count 3 --use-env-proxy
```

`--reference` 可以是包含单个 pattern card 的 JSON 文件；若传入整个数组，应先选定其中一项，避免一次 prompt 混入多个不相关 workflow。

## 仓库布局

- `tb_science_factory/`：任务生成、materialize、校验和 OPD 导出代码；
- `references/`：公开 workflow pattern cards；
- `generated/tasks/`：按 Harbor 原生格式 materialize 的任务；
- `generated/VERIFICATION.json`：本机 Harbor 验证记录与 reward；
- `docs/`：CPU/ECP 运行手册和交付说明；
- `scripts/`：可复用的批量生成、合并、验证记录和打包脚本。

运行时配置、Harbor 作业目录、LLM 缓存和交付压缩包位于 `.env`、`jobs/`、`work/`，均不纳入版本控制。

当前 `generated/VERIFICATION.json` 记录 606 个本机 Harbor reward 为 `1` 的任务；ECP/CCR 正式验收仍需按团队流程执行。

## 当前 pilot 与下一批

当前有 6 个格式独立、已通过本机 Harbor smoke/回归的候选包：

- `noisy-map-discovery`：数学科学 / 应用数学，稀疏非线性状态映射识别；
- `thermal-array-calibration`：工程科学 / 电气工程，缺失观测下的热传感器标定；
- `enzyme-response-selection`：生命科学 / 系统生物学，非线性模型选择与交叉验证。
- `fluorescence-field-reconstruction`：生命科学 / 神经科学，带离群点和缺失单元的二维荧光场重建；由 `inverse-imaging-reconstruction` 派生。
- `dose-response-selection`：生命科学 / 药理学，带相关协变量的剂量-反应模型选择；由 `scientific-model-selection` 派生。
- `atmospheric-change-point`：地球科学 / 大气科学，带季节项和异常点的稳健变点检测；由 `scientific-model-selection` 派生。

六个任务的 Oracle 与 verifier 都在本机 Docker Desktop 的 Harbor Docker backend 上各运行 5 次，30/30 个 trial 的 reward 均为 `1`。`generated/VERIFICATION.json` 和 `generated/NEXT_BATCH.json` 仍明确区分本机 Harbor 回归与 ECP/CCR 集群正式验收；新增任务的候选和 OPD 格式记录分别在 `generated/candidates/next_batch.jsonl`、`generated/opd/next_batch_smoke.jsonl`，集群验证完成前只能用于格式 smoke test，不能直接作为正式训练集。
