# ElanQuant

ElanQuant 是一个可审计的 A 股 Kronos 研究与模拟交易项目。当前公开版本只保留
四个主动实验：Small / Base × 官方零样本 / 官方方式微调。网页负责更新数据、查看
模型比较、股票排名、历史回测与模拟账户；不会连接真实券商，也不会自动下单。

> 仅用于研究和编程学习，不构成投资建议。模型分数、预测涨跌和历史收益都不是
> 对未来收益的保证。

## 当前研究设计

数据按 Kronos 官方 A 股 Demo 的原始日期边界组织：

| 数据切片 | 日期范围 | 用途 |
| --- | --- | --- |
| 训练 | 2011-01-01 ～ 2022-12-31 | 训练 Tokenizer 和 Predictor |
| 验证 | 2022-09-01 ～ 2024-06-30 | 每轮计算 validation loss，保存最佳 checkpoint |
| 滚动测试 | 2024-04-01 ～ 封存的最近收盘日 | 微调完成后的预测与成熟标签评估 |
| 历史回测 | 请求从 2024-07-01 开始 ～ 同一封存日 | Top50 / Drop5 / Hold5 与 Top3 / Drop1 / Hold5 |

这些是原始数据切片，前面的重叠区间用于提供模型所需的历史窗口。系统会另外审计
每只股票真正被模型消费的 101 行训练/验证窗口，以及测试信号的 90 日上下文和
10 日成熟目标，不能只凭日期表判断是否泄漏。

滚动测试一旦运行就永久标记为 `TEST_VIEWED`。它可以描述模型表现，但不能再用于
选择模型、调整参数或宣称是未查看的最终测试。最新在线预测还没有未来 10 日标签，
因此只能用于排名，不能计算 IC、RankIC 或实现收益。

当前公开矩阵：

| 模型规模 | 官方零样本 | 官方方式微调 |
| --- | --- | --- |
| Small | 官方 Small 权重 | 官方训练流程 + A 股自备数据 |
| Base | 官方 Base 权重 | 官方训练流程 + A 股自备数据 |

旧 Strict PIT 结果只作为退役审计证据保留，不再出现在网页选择器，也不会被新发布
冒充或覆盖。

## 选择运行位置

模型身份和运行位置是两件不同的事。同一个 checkpoint 在本机或服务器执行时，模型、
配置与数据回执不变；设备、系统、PyTorch、批量大小和执行代码作为另一组运行身份记录。

| 运行位置 | 默认模型 | 适合用途 | 限制 |
| --- | --- | --- | --- |
| Apple Silicon Mac | Small | 本地复现与按需推理 | Base 需要显式选择并通过内存/设备 smoke test；不做训练 |
| Linux + NVIDIA GPU | Small 或 Base | 推理、微调和历史研究 | 需要用户自己的服务器与 CUDA 环境 |

单个网页实例只提交到它已经配置好的运行位置；不会把“本机/远程”误当成两种模型，
也不会在另一端未配置时显示一个无法执行的按钮。

## 三种复现方式

### A. 五分钟检查代码和界面

不需要行情凭据，也不下载研究数据。使用仓库中的合成样例检查安装、数据契约与网页：

```bash
git clone https://github.com/elan6666/ElanQuant.git
cd ElanQuant
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,repro]'

elanquant data import \
  --input examples/data/synthetic_daily.csv \
  --output .elanquant/data/synthetic \
  --calendar synthetic-weekday \
  --universe-policy synthetic-fixture \
  --pit-declaration research-demo-only \
  --source-license repository-fixture

npm --prefix frontend install
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

合成数据仅用于验证管线，不会生成可解释为 A 股研究结果的指标。

### B. 下载官方权重并运行零样本基线

先检查将要执行的步骤：

```bash
elanquant bootstrap --profile local-apple-silicon --release small --dry-run
```

准备 Apple Silicon Small，或在 Linux/NVIDIA 上准备 Small/Base：

```bash
elanquant bootstrap --profile local-apple-silicon --release small
# 或
elanquant bootstrap --profile remote-linux-nvidia --release base
```

下载器只接受固定的官方 Tokenizer、Small、Base 仓库与文件清单，并为本地文件生成
SHA-256 回执。`--offline` 模式只验证已有文件，不访问网络。bootstrap 当前先完成权重
与基础目录准备；设备 doctor、数据准入和服务配置必须继续通过后才能标记为可推理。

```bash
elanquant doctor --check-only --profile local-apple-silicon --release small --device mps
elanquant smoke --fixture synthetic --profile local-apple-silicon --release small --device mps
```

synthetic smoke 只检查执行环境和证据链，明确不是 Kronos 模型推理。

### C. 用自己的数据复现微调与历史回测

1. 准备 CSV 或 Parquet。最少字段为
   `instrument,timestamp,open,high,low,close`；`volume,amount` 可选。
2. 使用 `elanquant data import` 导入。CSV 与 Parquet 会归一化到同一契约并生成内容哈希。
3. 构建官方日期切片并运行准入检查：训练/验证必须满足真实 101 行窗口，测试必须满足
   90 日上下文与成熟的未来 10 个交易日目标。
4. 在 Linux/NVIDIA 服务器依次训练 Small、Base 的 Tokenizer 和 Predictor；每个阶段
   跑满 30 epoch，并封存 validation loss 选择的 best checkpoint。
5. 四个模型分别生成自己的标准化空间信号，再分别运行 Top50 与 Top3 历史组合。

项目不会把原始行情、处理数据、checkpoint 或权重提交到 Git。若使用 Tushare-compatible
数据源，token 必须由用户自行保管；也可以提供自己的、返回兼容 DataFrame 的 `get_pro()`
适配器。数据许可、明文 HTTP 代理风险和可发布边界见 [数据政策](docs/DATA_POLICY.md)。

## 网页中的数字怎么读

- **10 日预测涨跌 2.04%**：`未来 10 个预测收盘价的平均值 ÷ 当前收盘价 − 1`。
  它表示模型预测均价比当前收盘价高 2.04%，不是上涨概率，也不是已经实现的收益。
- **RankIC**：预测排序与实际 10 日收益排序的相关性，范围 -1 到 1；接近 0 表示排序能力弱。
- **Pearson IC**：预测值与实际 10 日收益的线性相关性，范围 -1 到 1。
- **Top10 实际收益**：每天预测排名前 10、且未来标签已经成熟的股票，其实际收益平均值。
- **历史累计收益**：当前官方 Demo 对齐页采用每日收益算术累加，不能称为真实账户 NAV。
- **输入数据完整度**：满足本次准入输入项的比例，不是置信度。

网页主路径只显示决策需要的数字；原始模型分数、哈希与运行身份收进“查看审计信息”。

## 开发与验证

```bash
python -m pytest -q
ruff check backend/src tests scripts
pyright --pythonpath .venv/bin/python backend/src scripts/research
python -m compileall -q backend/src tests scripts

npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

研究数据下载、微调、正式推理和历史回测应在研究服务器执行；本机可以运行源码检查、
前端和通过准入的本地推理。服务器长任务由独立服务托管，不依赖浏览器持续打开。

## 项目边界与来源

- Kronos 上游固定到 commit `67b630e67f6a18c9e9be918d9b4337c960db1e9a`。
- 官方公开的是通用 Tokenizer、Small 和 Base 权重；ElanQuant 的 A 股微调 checkpoint
  不是“官方 A 股权重”。
- 训练数据、预测、日志、数据库和模型产物都在 `.gitignore` 范围内。
- 旧实验不会物理删除；退役回执记录其身份和未参与新产品选择的状态。
- 私有服务器部署、服务恢复与备份见 [运维手册](docs/OPERATIONS.md)，研究语义见
  [研究协议](docs/RESEARCH_PROTOCOL.md)，第三方许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## License

ElanQuant 源码采用 [MIT License](LICENSE)。Kronos、官方模型权重和行情数据分别遵守
各自来源的许可；源码许可不自动授予重新分发数据或微调权重的权利。
