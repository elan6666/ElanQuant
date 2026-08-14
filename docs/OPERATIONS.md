# ElanQuant 运维手册

本手册使用公开占位路径，不包含项目维护者的主机名、校园 VPN 或账户信息。

## 运行目录

```bash
export ELANQUANT_ROOT="$HOME/.local/share/elanquant"
export ELANQUANT_SOURCE="$ELANQUANT_ROOT/source"
```

源码与状态分开：`source/` 可以由 Git 重建；`artifacts/`、`data/`、`models/`、
`runs/`、`releases/` 和数据库属于不可提交状态。

## Linux/NVIDIA 服务安装

```bash
cd "$ELANQUANT_SOURCE"
ELANQUANT_ROOT="$ELANQUANT_ROOT" \
ELANQUANT_EXECUTION_PROFILE=remote-linux-nvidia \
ELANQUANT_MODEL_RELEASE=small \
ELANQUANT_EXECUTION_DEVICE=cuda \
bash scripts/bootstrap_server.sh

systemctl --user enable --now elanquant-api elanquant-worker
systemctl --user status elanquant-api elanquant-worker
```

脚本从 `.service.in` 模板渲染本机绝对路径，不把维护者私有路径提交到仓库。API 只监听
`127.0.0.1:8765`；通过用户自己的 SSH 主机建立端口转发：

```bash
ssh -N -L 8765:127.0.0.1:8765 USER@YOUR_SERVER
```

浏览器访问 `http://127.0.0.1:8765`。不要向公网开放 8765。

## Apple Silicon

先运行：

```bash
elanquant bootstrap --profile local-apple-silicon --release small
elanquant doctor --check-only --profile local-apple-silicon --release small --device mps
elanquant smoke --fixture synthetic --profile local-apple-silicon --release small --device mps
```

doctor/smoke 通过前不要把本机标记为可推理；系统禁止 MPS/CUDA 失败后静默改用 CPU。
Base 只在显式选择且能力门通过时可用，并保持 research-only。

## 服务语义

- API 接收任务后立即返回，Worker 独立领取；浏览器关闭不等于取消任务。
- job 幂等身份包含交易日、execution profile、Small/Base release 和设备。
- retry 继承原 execution identity，不能悄悄换机器或模型。
- 训练不是网页按钮能力，只能用独立、可追踪的服务器任务运行。
- Linux 用户服务若要在最后一个 SSH 会话退出后继续，需要由管理员正确配置 linger；
  主机重启会恢复服务，但不会从半写的 GPU 阶段自动续跑。

## 数据与凭据

- 用户自行提供已授权的 CSV/Parquet 或 Tushare-compatible `get_pro()` 适配器。
- token 放在用户私有配置文件中，权限 0600；禁止放命令行、日志、回执或 Git。
- provider、传输方式、PIT 声明、许可标签和内容哈希必须写入数据回执。
- 不完整 CSI300 成分快照只保留原始证据并排除，绝不能当成完整集合向前填充。

详见 [DATA_POLICY.md](DATA_POLICY.md)。

## 官方分割训练顺序

固定顺序：

```text
fetch raw
  -> materialize official slices
  -> payload admission
  -> Small tokenizer + predictor
  -> Base tokenizer + predictor
  -> exact four-cell matrix
  -> pre-result analysis lock
  -> mature evaluation + 8 historical backtests
  -> independent audit
  -> atomic release switch
```

所有输出目录必须是新的、此前不存在的 run id。失败后保留日志与 partial 证据，修复后
换新 id；禁止覆盖旧 checkpoint、receipt 或 release。旧 Strict PIT 目录不物理删除，
只通过 retirement receipt 从活动产品退役。

## SQLite 迁移

结构变更必须先停 API/Worker、备份，再由单进程迁移：

```bash
systemctl --user stop elanquant-api elanquant-worker
PYTHONPATH=backend/src .venv/bin/python scripts/server/migrate_app_database.py \
  --database "$ELANQUANT_ROOT/artifacts/elanquant.sqlite3" \
  --backup-dir "$ELANQUANT_ROOT/backups" \
  --confirm-services-stopped
systemctl --user start elanquant-api elanquant-worker
```

只有 `integrity_check=ok`、外键检查为 0、旧账本哈希不变时才完成。不要手工修改或删除
历史订单。

## 发布前门禁

```bash
python -m pytest -q
ruff check backend/src tests scripts
PYTHONPATH=backend/src pyright --pythonpath .venv/bin/python backend/src scripts/research
python -m compileall -q backend/src tests scripts

npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

还必须检查：

- API/Worker 只绑定 loopback，恶意 Host 被拒绝；
- active profile、设备、Small/Base 与 execution receipt 一致；
- 新数据、matrix、evaluation、historical catalog 全部 canonical hash 通过；
- Top50/Top3 同模型共享同一个 signal/provider hash；
- 旧 release、在线模拟账本和历史订单未被新研究任务改写；
- 桌面与 390px 页面无横向溢出、console error，键盘焦点可见。

## 常见故障

- `UNAVAILABLE`：能力门未通过；安装正确 runtime 或选择真实可用设备，不要解除门禁。
- `DATA_INCOMPLETE`：查看 snapshot/admission 排除原因，不能沿用昨天结果冒充今天。
- Worker 拒绝 profile：网页提交到了不同部署位置；连接对应实例，而不是修改 job。
- GPU 常驻：空闲时应接近 0；检查研究子进程 PID 与日志。
- SSH 端口可达但认证失败：这是认证问题，不是路由问题；重新建立用户自己的安全会话。
