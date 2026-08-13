# ElanQuant

ElanQuant 是一个面向单用户的 A 股研究与模拟交易系统。它把清华团队开源的
Kronos Small/Base 作为金融 K 线基础模型，保留官方零样本和官方风格微调作
对照，并增加可审计的严格 PIT（point-in-time）数据、评估和执行协议。

> 仅供研究和编程学习，不构成投资建议。系统不接入真实券商，不保存券商凭据，
> 不会自动更新或自动下单。

## 第一版能做什么

- 一个按钮在服务器执行“更新数据并推理”；关闭浏览器不影响已接收任务。VPN/最后
  SSH 会话断开后的持续运行必须先通过 `Linger=yes` 和真实断连测试。
- 展示 Small/Base × 零样本/官方风格/严格 PIT 的六格研究矩阵，分开标注
  2025 验证与 2026 `TEST_VIEWED`，并可比较最近两次运行。
- 展示数据健康、最新 A 股横截面评分、Top 3、三轨分歧和模型来源哈希。
- 维护 10 万元虚拟账户：T 日收盘冻结意图，下一真实交易日只成交或拒绝，拒单不递补；
  同一信号日强制重算只更新研究结果，不改第一次冻结的模拟账本。
- 保留上述 Top3，同时增加一个完全隔离的官方 Demo 方法对齐版：标准化空间差值、
  5条预测采样、Top-50、Drop-5、最少持有5日的连续历史回测。它只有只读接口，
  不会生成或修改 Top3 订单、持仓和净值。
- 在同一封存信号上增加历史 Qlib Top3/Drop1/Hold5 组合敏感性版本，并可按评估期
  交易日查看 Top50/Top3 的实际持仓、数量、权重和市值。这个历史 Top3 不等同在线
  Top3，也永久不用于选模或晋级。
- 记录数据、代码、配置、上游 commit、权重和运行回执，明确标记 2026 为已查看测试。

已封存的官方方法对齐版同时保留两个明确角色：2025-01-02 至
2025-12-17 是参与 validation loss/best-checkpoint 选择的训练验证；
2026-01-05 至 2026-07-29 是已开封的样本外诊断。它已修正未来成分/缺行对
T 日候选资格的影响，但不伪装成新的盲测。2026 预先指定的
mean 信号含费累计收益为 -7.65%，同期沪深300为 0.45%，含费超额为
-8.09%，最大回撤为 -13.31%。它已开封且明显跑输基准，不支持稳定 alpha
或实盘有效性的主张，也不得用于新一轮调参。

当前正式结果的指标和正确解释见
[2026-08-12 Small 正式评估说明](docs/RESULTS_20260812.md)和
[2026-08-13 Base 正式评估说明](docs/RESULTS_BASE_20260813.md)，官方 Demo 连续回测见
[2026 已开封样本外诊断](docs/RESULTS_OFFICIAL_DEMO_FINAL_TEST_20260813.md)，组合规模对照见
[历史 Qlib Top3 敏感性结果](docs/RESULTS_HISTORICAL_TOP3_20260813.md)。严格 PIT 轨在 2025
验证集没有稳定超过零样本，因此系统只能称为可审计研究与模拟工具，不能宣称稳定 alpha。

## 架构

```text
浏览器（React）
      │ SSH 本地端口转发 / 同源 HTTP
FastAPI（只监听服务器 127.0.0.1:8765）
      │ SQLite WAL 持久任务队列
独立 Worker ── 数据快照 ── Kronos GPU 子进程 ── 排名/模拟账本

封存历史产物 ── 只读 FastAPI GET ── 官方Demo对齐版回测页
                     └── Top50/Top3 逐日封存持仓
```

API 和 Worker 由两个 `systemd --user` 服务管理。API 只提交和查询任务；GPU
模型仅在 Worker 创建的研究子进程中加载，子进程结束即释放显存。项目不用
Redis、Celery、Kubernetes 或真实交易接口。

## 本地开发验证

Mac 只运行源码检查和前端；研究数据、训练、推理和结果必须在指定服务器执行。

```bash
npm --prefix frontend install
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

服务器源码验证：

```bash
../app-venv/bin/python -m pytest -q
../app-venv/bin/ruff check backend/src tests scripts
../app-venv/bin/pyright --pythonpath ../app-venv/bin/python backend/src scripts/research
../app-venv/bin/python -m compileall -q backend/src tests scripts
```

## 使用

1. 连接学校 EasyConnect（仅在校园隧道不存在时）。
2. 建立本地端口转发：

   ```bash
   ssh -N -L 8765:127.0.0.1:8765 yilangliu@10.24.1.91
   ```

3. 浏览器打开 `http://127.0.0.1:8765`。
4. 点击“更新数据并推理”。提交成功后可关闭网页；只有运维检查确认 `Linger=yes`
   且断连测试通过后，才主动断开 VPN，重连后从任务页查看结果。

服务器部署、训练、故障检查见 [运维手册](docs/OPERATIONS.md)，研究边界见
[研究协议](docs/RESEARCH_PROTOCOL.md)，零基础学习顺序见
[第一课全栈总览](docs/LESSON_01_FULLSTACK_OVERVIEW.md)和
[全栈学习指南](docs/LEARNING_GUIDE.md)。

## 数据与凭据边界

- Tushare token 只存在服务器 `~/.config/tushare/token`，权限 0600。
- 数据客户端只能通过服务器批准的 `scripts/tushare_proxy_client.py:get_pro` 创建。
- 教程代理为 `http://jiaoch.site`，传输是明文 HTTP；每份数据回执都会披露这一限制。
- `index_weight` 没有历史首次可得/修订回执；严格轨延迟一个完整交易日使用，并在
  产物中明确保留“不能排除供应商后来修订”的限制。
- 数据、预测、日志、权重、checkpoint、数据库和报告均被 `.gitignore` 排除，不进入 Git。

## 上游

- Kronos 上游固定到 commit `67b630e67f6a18c9e9be918d9b4337c960db1e9a`。
- 本轮训练使用固定 revision/SHA-256 的 Tokenizer-base、Small 和 Base；Base 只进入
  研究对照目录，不会自动替换当前 Small 严格PIT在线版本。
- 上游代码只读保存；A 股数据适配、严格 PIT、评估和模拟执行放在 ElanQuant 外层。

## License

ElanQuant 源码采用 [MIT License](LICENSE)。Kronos 仍归其原作者所有，并遵循上游
仓库自己的 MIT License；模型权重和数据还需分别遵守其来源条款。
