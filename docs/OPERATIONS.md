# ElanQuant 运维手册

## 固定路径

- Mac 源码：`/Users/elan/Documents/量化/ElanQuant`
- 服务器根目录：`/data/yilangliu/a_share_research/elanquant`
- 服务器源码：`/data/yilangliu/a_share_research/elanquant/source`
- 数据、权重、训练和运行产物只保留在服务器根目录的忽略目录中。

## 服务

```bash
systemctl --user status elanquant-api elanquant-worker
journalctl --user -u elanquant-api -n 100 --no-pager
journalctl --user -u elanquant-worker -n 100 --no-pager
```

API 和 Worker 都必须显示 loopback 配置；服务器防火墙无需开放 8765。Mac 通过：

```bash
ssh -N -L 8765:127.0.0.1:8765 yilangliu@10.24.1.91
```

访问 `http://127.0.0.1:8765/api/v1/health` 应返回 `status=ok`。

## 服务安装

```bash
cd /data/yilangliu/a_share_research/elanquant/source
bash scripts/bootstrap_server.sh
systemctl --user daemon-reload
systemctl --user enable --now elanquant-api elanquant-worker
```

`bootstrap_server.sh` 会先创建应用虚拟环境、安装开发依赖并执行后端门禁，
再安装 service 文件。如果服务器没有 Node/npm，先在 Mac 运行：

```bash
cd /Users/elan/Documents/量化/ElanQuant/frontend
npm ci && npm test && npm run lint && npm run build
rsync -az --delete dist/ \
  yilangliu@10.24.1.91:/data/yilangliu/a_share_research/elanquant/source/frontend/dist/
```

`frontend/dist/` 是已忽略的构建产物，不进 Git；bootstrap 会验证入口文件并
使用该已验证构建。只有正式训练矩阵和正式评估回执封存到 `releases/current/` 后，才允许
启动真实 Worker。

`systemd --user` 在 `Linger=yes` 后可保证 VPN/最后一个 SSH 会话断开时服务继续运行。
主机重启后，永久启用的 API/Worker 会重新启动，但当时正在运行的任务会被标记为失败，
必须由用户显式重试；临时训练服务也不会从中间 checkpoint 自动续跑。当前已验证
`Linger=yes`。新服务器若为 `Linger=no`，需要管理员执行：

```bash
loginctl enable-linger yilangliu
```

不要把 `tmux`/`nohup` 当作正式部署，只可用于开发排障。

## 手动更新和推理

前端按钮调用 `POST /api/v1/jobs/update-infer`。API 立即返回 202，Worker 独立执行：

```text
解析交易日 -> 下载不可变快照 -> 数据门禁 -> Small
-> 严格PIT排名 -> 模拟账本 -> 原子发布
```

重复点击同一交易日会返回已有任务。失败任务只能显式重试；Worker 重启后会把遗留
运行任务标为失败，不会从半写 GPU 结果自动续跑。

## 训练

训练不是网页按钮能力。它只在服务器通过独立、可追踪的服务单元运行。正式参数由
`scripts/server/kronos_config.py` 固定，训练顺序由
`scripts/server/run_training_matrix.sh` 固定。检查：

```bash
systemctl --user status elanquant-training-small-a-share-v2-20260813-r2
journalctl --user -u elanquant-training-small-a-share-v2-20260813-r2 -n 100 --no-pager
systemctl --user status elanquant-finalize-small-a-share-v2-20260813
journalctl --user -u elanquant-finalize-small-a-share-v2-20260813 -n 100 --no-pager
find /data/yilangliu/a_share_research/elanquant/runs/training -name terminal.json -print
readlink /data/yilangliu/a_share_research/elanquant/releases/current
cat /data/yilangliu/a_share_research/elanquant/releases/current/manifest.json
```

Follower 必须设置 `RESEARCH_DEPS=/data/yilangliu/a_share_research/elanquant/research-deps`；
Kronos 的 `huggingface_hub` 等只读推理依赖由该隔离目录提供，不能临时写入上游仓库。

每个 `terminal.json` 必须为 PASS，且包含数据、workspace、日志和 checkpoint 哈希。
完成后必须先存在不可变的 `runs/admission/extended-v2.json`，再运行
`compile_training_matrix.py`；后端只接受由数据准入和各阶段真实回执派生的 sealed
matrix，不能靠手写 JSON 标记 PASS。Base 使用同一准入数据单独生成候选 matrix 和
FORMAL 评估；完成后只进入 `research-catalog.json`，不会替换 `releases/current`。
如果四段训练和 Base matrix 已经封存，而 follower 在评估前因环境或路径错误退出，
禁止重训、重编或覆盖 matrix。先确认 smoke/formal/catalog 都不存在，再用新的 transient
unit 调用 `scripts/server/resume_base_evaluation.sh`；该入口只消费现有 matrix，并要求
显式提供正确的 pinned upstream、PASS 在线快照和不可变 Small release。失败 unit 不复用，
每次恢复都使用新的 unit 名，并保留旧 journal 作为审计证据。
首次准入命令为：

```bash
python -m scripts.server.audit_dataset_admission \
  --root /data/yilangliu/a_share_research/elanquant \
  --out /data/yilangliu/a_share_research/elanquant/runs/admission/extended-v2.json
```

该路径已存在时命令会拒绝覆盖；新数据版本必须使用新的数据根、回执名和对应矩阵配置。
训练或封存服务失败时，先读取对应 terminal/日志；修复后创建新的不可变 run/release id，
不得覆盖旧 checkpoint、旧回执或旧 release。

## SQLite 备份与单进程迁移

涉及表结构变更时，禁止 API 和 Worker 同时执行 `ALTER TABLE`。先保留恢复点，再由
一个 Python 进程运行 `Database.initialize()`：

```bash
systemctl --user stop elanquant-api elanquant-worker
PYTHONPATH=backend/src ../app-venv/bin/python scripts/server/migrate_app_database.py \
  --database /data/yilangliu/a_share_research/elanquant/artifacts/elanquant.sqlite3 \
  --backup-dir /data/yilangliu/a_share_research/elanquant/backups \
  --confirm-services-stopped
systemctl --user start elanquant-api elanquant-worker
```

命令使用 SQLite backup API 生成权限 0600 的恢复点，然后单进程执行迁移；只有
`integrity_check=ok` 且 `foreign_key_violations=0` 才返回 PASS。启动后再只读检查
`/system/status`、`/runs`、`/paper/summary`。

迁移只会保存新证据的表结构，不会伪造旧 run 当时没有持久化的
`data_health` 和双 split 评估。因此部署这一版后，须在 GPU 研究任务全部结束时
安全执行一次同日 force 研究 run；同日首次 paper publication 保持冻结，新 run
必须标记 `SKIPPED_EXISTING_FROZEN_RUN`。验收时必须确认：

- latest run 的 `data_health` 非空；
- Small 三格每格都有 `validation_2025` 和 `test_viewed_2026`；
- 旧订单集合、数量和 source run 不变；
- 新 run 的 data/model/tokenizer/config/code/evaluation hash 在 API 和页面可见。

不要手工修改或删掉历史订单。若旧信号日已混入多个 source run，迁移只增加
`LEGACY_MIXED_RUNS` 警告并保留原数据；回滚时停止两个服务，恢复整份备份数据库，
不能只回退某几张表。

## 官方 Demo 方法对齐版历史回测

这条轨道不由网页按钮触发，也不写 SQLite。它与 Top3 线上模拟产品并存：

```text
2025标准化信号（Small official-ft, sample_count=5）
  -> Qlib Top50/Drop5/Hold5 连续回测
2026已开封且修正 future-support conditioning 的样本外诊断
  -> Qlib 同参数连续回测
  -> releases/historical-backtest-catalog-v3.json
  -> GET /api/v1/research/backtests
```

信号生成和回测必须使用各自新的 transient systemd unit，输出目录存在时拒绝覆盖。
pyqlib固定为0.9.7，其安装元数据、RECORD和源码树哈希进入回执；Kronos仓库没有固定
Qlib版本，因此这是为了可审计而增加的基础设施决定。发布前运行
`scripts/server/audit_paper_boundary.py` 封存 recommendation/paper 各表的行数与哈希，
发布后用 `--compare` 重算；任一表改变都会让发布失败。

API服务需设置：

```text
ELANQUANT_HISTORICAL_BACKTEST_CATALOG=/data/yilangliu/a_share_research/elanquant/releases/historical-backtest-catalog-v3.json
```

目录缺失时页面显示“服务器生成中”；目录、回执或逐日曲线任一哈希不一致时 API 返回
503，不得回退到模拟数据。新轨只允许 GET，不添加 POST、重试或每日自动调度。

2026 补跑不重训模型，不覆盖 2025 产物。它必须先生成不可变
analysis lock，锁定已有 Small official-ft checkpoint、mean 主信号和完整策略参数，
再以全新 run id 执行 `scripts/server/finalize_official_demo_final_test_2026.sh`。
发布后目录必须精确包含 2025 checkpoint-selection validation 和已修正的
2026 opened out-of-sample diagnostic
两个 entry；`releases/current`、SQLite Top3 账本和旧 2025 回执的哈希必须保持不变。
独立审计通过后，将最终 run 文件收紧为 0440、目录为 0550，catalog 为
0440，然后再运行一次完整审计。中途失败的 r0–r3 只是 `ABORTED`
审计证据，不进入 catalog，不得被人工当成可发布结果。

## 常见故障

- `nc -zvw5 10.24.1.91 22` 不通：校园 VPN/路由问题；再使用 EasyConnect 技能检查。
- 22 端口通但 SSH permission denied：VPN 已正常，只需重新建立交互式 ControlMaster。
- `DATA_INCOMPLETE`：查看在线 snapshot manifest 的排除原因；不得沿用昨天推荐冒充今天。
- Worker 失败：网页明确重试；不要直接改 SQLite 或删除运行目录。
- GPU 常驻：正常空闲时应接近 0 MiB；研究子进程退出后若仍占用，先查 PID 和日志。
