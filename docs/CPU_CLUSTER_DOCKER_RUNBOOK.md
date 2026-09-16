# CPU 集群 Docker/Harbor 验证手册

本手册对应 `/private/通算平台起docker（+qemu虚拟机）.pdf`，用于在没有 Modal/Daytona 账号时，使用 ECP CPU 作业完成本项目任务的真实 Docker/Harbor 验证。

## 目标和边界

ECP 的私有镜像仓库只负责保存镜像；Harbor 仍需要在一个能访问 Docker daemon 的 ECP 作业（或集群提供的 Docker 节点）里运行。把镜像推送到仓库后，还必须让 Harbor 使用这些镜像并执行 5 次 Oracle + verifier。

当前三个任务不需要 QEMU、`--privileged`、`/dev/kvm` 或 `NET_ADMIN`。PDF 中的 QEMU 配置只适用于确实需要虚拟机的任务。

## 1. 在控制台准备空间

1. 登录集群控制台，进入 CCR 镜像管理，确认团队 namespace（示例：`ccr-tscpu-qyts-data-explore`）。
2. 在镜像管理页面取得该 namespace 对应的 registry 用户名和密码。密码只在集群终端交互输入，不写进脚本、Git、task 文件或聊天记录。
3. 创建一个 ECP CPU 作业：官方 Ubuntu 镜像、启动命令 `sleep infinity`，挂载团队/个人共享存储。后续命令都在这个作业的 Web Terminal 执行。

如果平台已经给该作业提供 Docker daemon，直接使用它；否则按平台允许的 Docker-in-Docker 方式启动 daemon。当前作业必须能执行 `docker info`，否则 Harbor 的 Docker backend 无法工作。系统没有 systemd 时，不能使用 PDF 中的 systemd drop-in，要把代理环境直接传给 `dockerd` 或 Docker build/run。

## 2. 配置变量和登录 registry

在 ECP 作业中执行（替换为平台实际 namespace；不要把密码写在命令行）：

```bash
export REGISTRY=registry2-cloud.d.pjlab.org.cn
export REGISTRY_NAMESPACE=ccr-tscpu-qyts-data-explore
export TASK_ROOT=/mnt/shared/terminal-bench-science-task-factory
cd "$TASK_ROOT"
docker login "$REGISTRY" --username '<registry-user>'
```

输入密码时使用交互提示。PDF 中的 registry 主机名、tag 和 push 形式为：
`registry2-cloud.d.pjlab.org.cn/<namespace>/<image>:<tag>`。

若要由 Docker daemon 出网拉取基础镜像，先在启动 daemon 的 shell 中设置集群代理（使用管理员提供的实际值）：

```bash
export HTTP_PROXY='http://<proxy-user>:<proxy-password>@<proxy-host>:<proxy-port>/'
export HTTPS_PROXY="$HTTP_PROXY"
export NO_PROXY='localhost,127.0.0.1,*.sensetime.com,10.0.0.0/8,100.0.0.0/8,*.pjlab.org.cn'
```

不要把带密码的变量保存到仓库或终端日志。若 registry 本身是内网地址，确认它包含在 `NO_PROXY` 中。

## 3. 构建并推送环境镜像和 verifier 镜像

Harbor 的任务环境和 verifier 是两个独立容器，因此每个任务通常要推送两张镜像。构建上下文必须是任务根目录（不能把 `environment/` 单独作为上下文，否则 `COPY environment/...` 会失败）。下面先处理一个任务；对三个任务重复即可：

```bash
TASK=generated/tasks/mathematical-sciences/applied-mathematics/noisy-map-discovery
TAG=20260902-v1
NAME=noisy-map-discovery

docker build \
  --build-arg HTTP_PROXY="$HTTP_PROXY" \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --build-arg NO_PROXY="$NO_PROXY" \
  -f "$TASK/environment/Dockerfile" \
  -t "$REGISTRY/$REGISTRY_NAMESPACE/tbs-${NAME}-env:$TAG" "$TASK"
docker push "$REGISTRY/$REGISTRY_NAMESPACE/tbs-${NAME}-env:$TAG"

docker build \
  --build-arg HTTP_PROXY="$HTTP_PROXY" \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --build-arg NO_PROXY="$NO_PROXY" \
  -f "$TASK/tests/Dockerfile" \
  -t "$REGISTRY/$REGISTRY_NAMESPACE/tbs-${NAME}-verifier:$TAG" "$TASK"
docker push "$REGISTRY/$REGISTRY_NAMESPACE/tbs-${NAME}-verifier:$TAG"
```

三个当前任务的 `NAME` 分别是：`noisy-map-discovery`、`thermal-array-calibration`、`enzyme-response-selection`。最后一个环境镜像需要安装 numpy/scipy，构建时必须能访问 PyPI 或集群镜像源；若集群不允许 Docker build 出网，应先做一个含这两个依赖的基础镜像并在 Dockerfile 中改用该内网镜像。

推送后记录两个完整镜像引用。不要把 registry 密码、模型 API key 或代理密码作为 Docker `ARG` 以外的持久化环境变量写入镜像层。

## 4. 让 Harbor 使用私有镜像

有两种方式：

### 方式 A（推荐：最少改 task）

在运行 Harbor 的同一个 ECP 作业中先 `docker login`，保留现有 `environment/Dockerfile` 和 `tests/Dockerfile`，执行 Harbor 时让它本地构建。这样不需要在 `task.toml` 中写私有 registry 地址；构建和测试最接近源码状态。

### 方式 B（平台要求必须使用推送镜像）

在每个任务的 `task.toml` 中增加完整的预构建镜像引用：

```toml
[environment]
docker_image = "registry2-cloud.d.pjlab.org.cn/<namespace>/tbs-noisy-map-discovery-env:20260902-v1"

[verifier]
  [verifier.environment]
  docker_image = "registry2-cloud.d.pjlab.org.cn/<namespace>/tbs-noisy-map-discovery-verifier:20260902-v1"
```

具体缩进和字段名以当前 Harbor 版本的 schema 检查为准。ECP 前端创建使用私有镜像的作业时，按 PDF 创建 image secret（registry URL、用户名、密码），并把 secret 绑定到作业。若 Harbor 在 ECP 作业内直接调用本机 Docker daemon，则在该作业内 `docker login` 即可；若 Harbor 在另一台机器运行，必须额外配置该机器对私有 registry 的凭据，单纯在 ECP 前端登录并不会自动传给另一台机器。

方式 B 的前提是镜像中已经包含 task 所需的 `/workspace`、`/data`、`/tests` 和入口命令；改成预构建镜像后，Dockerfile 不会再替你复制文件。

## 5. 在 CPU 集群运行 5 次 Oracle

在能看到 Docker daemon 的 ECP 作业中：

```bash
cd "$TASK_ROOT"
source .venv/bin/activate

# 先做单任务、单并发 smoke
harbor run \
  --path generated/tasks/mathematical-sciences/applied-mathematics/noisy-map-discovery \
  --agent oracle --env docker --n-attempts 1 --n-concurrent 1 \
  --jobs-dir jobs/cluster-smoke --yes

# smoke 通过后，对三个任务各跑 5 次
for task in generated/tasks/*/*/*; do
  harbor run --path "$task" --agent oracle --env docker \
    --n-attempts 5 --n-concurrent 1 \
    --jobs-dir "jobs/$(basename "$task")-oracle5" --yes
done
```

`--n-concurrent 1` 是 CPU 集群的安全起点；确认资源足够后再提高并发。每次运行都要检查 5 个 trial 的 verifier reward 是否全部为 `1`，并保存 jobs 目录中的日志/trajectory 作为审计证据。若出现 build 拉取失败，先分别验证 `docker pull`、`docker login` 和代理；若只有 verifier 失败，检查 artifact 是否按任务约定写入 `/output`。

## 6. 回填验证记录并导出 OPD

当前 `generated/VERIFICATION.json` 中的状态是 `validated_local`，表示只做过路径适配的本地模拟，不能直接作为正式训练集。Harbor 5 次真实运行全部 reward=1 后，才把对应记录更新为：

```json
{
  "status": "verified",
  "reward": 1,
  "verification_backend": "harbor/docker on ECP CPU cluster",
  "docker_harbor_verified": true,
  "oracle_trials": 5
}
```

然后运行：

```bash
PYTHONPATH=. python -m tb_science_factory.task_factory export-opd \
  --candidates generated/candidates/pilot.jsonl \
  --verification generated/VERIFICATION.json \
  --out generated/opd/pilot_verified.jsonl
```

不建议使用 `--allow-unverified` 生成训练数据；该选项只用于检查 JSONL 格式。

## 验收清单

- [ ] ECP 作业内 `docker info` 成功，且 Harbor 与 Docker daemon 在同一可达环境。
- [ ] 每个任务的 env/verifier 镜像都能 pull（若采用方式 B）。
- [ ] 三个任务各有 5 个 Oracle trial，verifier reward 全为 `1`。
- [ ] 保存 Harbor jobs 目录和镜像 digest（不要只保存 tag）。
- [ ] `VERIFICATION.json` 标记 `docker_harbor_verified=true` 后才导出 OPD。
- [ ] 正式训练 JSONL 不含 API key、代理密码、registry 密码或隐藏答案。
