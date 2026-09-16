# 当前流程、问题与 CPU 集群迁移记录

更新时间：2026-09-03

## 一句话结论

代码和 6 个衍生任务已经完成“任务生成/物化 → 本机 Docker Desktop 上的 Harbor Docker backend 五次验证”的闭环；六个任务共 30/30 个 trial reward=1。如果要作为正式 benchmark 训练集，仍需把同一独立目录迁移到 CPU 集群，在 ECP 作业内复现 Docker daemon 和 Harbor 五次运行，确认集群侧基础镜像/代理后，再标记为正式 verified 并导出 OPD 数据。

## 当前已经完成的内容

项目目录：

```text
/private/codebase/terminal-bench-science-task-factory
```

目录与其他项目独立，不依赖 `relax_recipe`，也不依赖 `brainarena_handoff` 的数据工作流。旧项目只参考了 OpenAI-compatible HTTP 调用方式。

当前代码包括：

- `tb_science_factory/llm_client.py`：调用外部 `/v1/chat/completions` 的最小客户端，从环境变量读取 key/base URL，不把 key 写入 cache、JSONL、task 文件或日志。
- `prompts.py`：根据公开 workflow pattern 生成全新的科学任务，不复制原 benchmark 的答案、hidden fixture 或 solution。
- `task_factory.py`：候选生成、字段/路径/网络/超时/秘密泄漏检查、Harbor task 目录物化、OPD 导出门禁。
- `references/pattern_cards.json`：非答案型的任务模式卡。
- `generated/tasks/`：6 个可审阅任务。
- `generated/candidates/pilot.jsonl`：原始 3 条候选记录；`generated/candidates/next_batch.jsonl` 与 `generated/NEXT_BATCH.json` 登记新增的 3 个已物化任务。
- `generated/VERIFICATION.json`：当前记录为 `validated_local`。
- `generated/opd/pilot_smoke.jsonl`：仅用于格式 smoke test，不能直接用于正式训练。
- `generated/candidates/next_batch.jsonl` 与 `generated/opd/next_batch_smoke.jsonl`：新增 3 个任务的候选/OPD 格式 smoke 记录；仍未标记为正式 `verified`。
- `docs/CPU_CLUSTER_DOCKER_RUNBOOK.md`：ECP/CCR/Docker/Harbor 的具体操作手册。

首批 3 个任务：

1. `noisy-map-discovery`
2. `thermal-array-calibration`
3. `enzyme-response-selection`

三者的本地路径适配模拟均为 `oracle_exit_code=0`、`tests_exit_code=0`、`reward=1`；随后在本机 Harbor Docker backend 各运行 5 次，15/15 个 trial 的 verifier reward 均为 `1`。这仍不等于 ECP/CCR 集群验收；`docker_harbor_verified=false` 继续保留，直到集群侧完成同样的 5 次审计运行。

新增的 3 个任务也在本机 Harbor Docker backend 各运行 5 次，15/15 个 trial 的 verifier reward 均为 `1`：

4. `fluorescence-field-reconstruction`
5. `dose-response-selection`

新增的第 3 个任务也已完成 smoke 和五次稳定性回归：

6. `atmospheric-change-point`

它们同样保持 `status=validated_local` 和 `docker_harbor_verified=false`，不因本机通过而声称已经完成 ECP/CCR 集群验收。

## 生成流程（需要外部模型时）

生成新任务才需要 API key；验证已经生成的任务不需要调用模型 API。API key 只在 shell 或受限 env 文件中注入：

```bash
cd /path/to/terminal-bench-science-task-factory
export API_BASE='http://<provider>/v1'
export API_KEY='<secret>'
PYTHONPATH=. python -m tb_science_factory.task_factory generate \
  --reference references/pattern_cards.json \
  --out work/candidates.jsonl \
  --cache-dir work/llm-cache \
  --model '<provider-model>' \
  --count 3 --use-env-proxy
```

生成后先看 `validation_errors`，再执行：

```bash
PYTHONPATH=. python -m tb_science_factory.task_factory materialize \
  --candidates work/candidates.jsonl --out-root generated/tasks
```

模型生成的是 task package 草稿；真正能进入 OPD 的条件是 verifier 在目标执行后端得到 reward `1`。

## 已遇到的问题和处理方式

### 1. 本机 Harbor 验证与集群验收的边界

本机 Docker Desktop 已能运行 Harbor 的 Docker backend，并完成三个任务各 5 次、全部 reward=1；这验证了 Dockerfile、artifact 上传和 verifier 生命周期。它不覆盖 ECP 作业的 Docker daemon、CCR 镜像权限、集群代理和资源配额，因此不能替代正式集群验收。

处理方式：把正式验收放到 CPU 集群 ECP 作业，在那里使用平台提供/允许的 Docker daemon，并保留本机 `jobs/local-*-5` 作为回归证据。

### 2. 外部基础镜像拉取受限

本机通过当前代理访问 Docker Hub 时返回 403，直接访问也不稳定。即使 Dockerfile 正确，`python:3.11-slim`、`python:3.12-slim` 仍可能在 build 阶段失败。

处理顺序：

1. 在 ECP 作业中按集群文档设置 Docker daemon/build 的代理，并先测试 `docker pull`。
2. 如果外网仍不可用，从集群允许的镜像源或官方 Ubuntu 作业中取得基础镜像，推送到 CCR，再把 Dockerfile 的 `FROM` 改为内网镜像。
3. `enzyme-response-selection` 还需要安装 numpy/scipy；若 pip 出网受限，使用集群 PyPI 镜像或制作一个预装依赖的内网基础镜像。

所有 Dockerfile 已加入 `ARG HTTP_PROXY/HTTPS_PROXY/NO_PROXY`，可由 cluster build 命令注入；凭据不会写入文件。

### 3. systemd 不可用

当前开发容器不是 systemd PID 1，因此 PDF 中的 `/etc/systemd/system/docker.service.d/http-proxy.conf` 不能直接套用。

处理方式：在真正的 ECP 节点按平台方式配置 systemd；如果是在无 systemd 的作业内启动 daemon，就在启动 `dockerd` 的同一个 shell 直接导出代理变量。不要假设改了宿主机 drop-in 后当前容器会继承。

### 4. CCR 私有镜像凭据不能自动传给 Harbor

在 ECP 前端创建私有镜像作业时需要 image secret；如果 Harbor 在另一台机器/另一作业内运行，前端的 secret 不会自动变成该机器的 `docker login`。

处理方式：优先在同一个 ECP 作业内运行 Harbor 和 Docker daemon，并在该作业内交互执行 `docker login`；或者显式给 Harbor 所在节点配置只读 registry 凭据。密码只通过交互输入或平台 secret 注入。

### 5. 预构建镜像可能丢失 task 文件

使用 `task.toml` 的 `docker_image` 后，Harbor 不再执行对应 Dockerfile。镜像必须自己包含 `/workspace`、`/data`、`/tests`、入口命令以及需要的依赖。

处理方式：首轮推荐保留 Dockerfile，让 Harbor 在集群 Docker daemon 上构建；只有集群策略要求“必须先推送镜像”时，才采用 runbook 中的 env/verifier 双镜像方式，并检查容器内路径。

### 6. Harbor verifier 的启动顺序与 Dockerfile 上下文

Harbor 0.22 的 verifier 会先以常驻进程启动 `tests/Dockerfile`，上传 artifacts 后再通过 `exec` 调用 `tests/test.sh`。如果 verifier Dockerfile 用测试脚本作为 `ENTRYPOINT`，容器会在 artifacts 上传前退出，表现为 reward 文件为 `0` 或缺少 `/workspace`。此外，Docker build context 是各自的 `environment/` 或 `tests/` 目录，`COPY` 源必须相对该目录。

当前物化器会把常见的 task-root `COPY` 写法转换为 per-directory context，把 verifier 入口转换为 `CMD ["sleep", "infinity"]`，并为 noisy-map 的 rollout fixture 写入 `/tests`。三个已物化任务的 Dockerfile 也已按此规则修正。

## 迁移到 CPU 集群的建议步骤

### A. 只迁移源码和已生成数据

不要迁移本机 `.venv`、`__pycache__`、可能含密钥的 shell history。建议使用 tar 或 rsync，并排除运行时目录：

```bash
cd /private/codebase
tar --exclude='terminal-bench-science-task-factory/.venv' \
    --exclude='terminal-bench-science-task-factory/**/__pycache__' \
    -czf /tmp/terminal-bench-science-task-factory.tgz \
    terminal-bench-science-task-factory
```

把压缩包上传到团队共享存储或按集群允许的方式传入 ECP 作业后解压。也可以只复制以下内容：`pyproject.toml`、`README.md`、`docs/`、`references/`、`tb_science_factory/`、`generated/`、`pytest.ini`。

### B. 在 ECP 作业内重建 Python 环境

```bash
cd /mnt/shared/terminal-bench-science-task-factory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install harbor
```

如果集群使用内部 PyPI，按集群文档设置 index URL；不需要安装 Modal/Daytona extra。确认：

```bash
harbor --version
docker info
```

### C. 选择镜像策略

- **Dockerfile 构建策略（推荐首轮）**：保留任务目录原样，由 Harbor 在 ECP 作业内 build；CCR 只用于必要时缓存基础镜像。
- **预构建策略**：按 `docs/CPU_CLUSTER_DOCKER_RUNBOOK.md` 为每个任务 build/push 两张镜像（agent environment 和 verifier），创建 image secret，并在 `task.toml` 中填写完整 `docker_image`。

无论哪种策略，先用一个任务、`--n-attempts 1 --n-concurrent 1` smoke，再扩展到全量。

### D. 运行正式 5 次验证

```bash
source .venv/bin/activate
harbor run -p generated/tasks/mathematical-sciences/applied-mathematics/noisy-map-discovery \
  -a oracle -e docker -k 5 -n 1 \
  -o jobs/noisy-map-discovery-oracle5 --yes
```

对另外两个任务重复。保存 jobs 目录、trial 日志、trajectory 和实际镜像 digest。CPU 资源不足时保持 `-n 1`，不要为了吞吐盲目并发。

### E. 回填状态并导出训练数据

只有当每个任务 5 次 verifier reward 都是 `1`，才把 `generated/VERIFICATION.json` 对应条目标成：

```json
"status": "verified",
"verification_backend": "harbor/docker on ECP CPU cluster",
"docker_harbor_verified": true,
"oracle_trials": 5
```

随后导出正式 OPD JSONL：

```bash
PYTHONPATH=. python -m tb_science_factory.task_factory export-opd \
  --candidates generated/candidates/pilot.jsonl \
  --verification generated/VERIFICATION.json \
  --out generated/opd/pilot_verified.jsonl
```

不要用 `--allow-unverified` 作为正式训练集；它只用于检查 JSONL 结构。

## 迁移时需要向集群管理员/操作者确认的最小信息

- ECP 项目/namespace 和共享存储挂载路径。
- 作业内 Docker daemon 的使用方式（平台 daemon、Docker-in-Docker 或专用 Docker 节点）。
- CCR registry 主机名、namespace、registry 用户名，以及 image secret 创建入口。
- 集群可用的 Docker Hub/PyPI 镜像源或代理要求。
- ECP 作业是否允许 Harbor 进程访问本机 Docker socket/daemon。

这些信息齐全后，不需要 Modal/Daytona 账号；API key 只在需要继续生成新任务时使用。
