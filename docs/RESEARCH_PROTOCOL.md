# ElanQuant 研究协议

## Small/Base 六格实验

| 模型规模 | 零样本 | 官方风格微调 | 严格 PIT 微调 |
|---|---|---|---|
| Small | 官方 Tokenizer + Small | A 股 Tokenizer + Small Predictor | 严格 A 股 Tokenizer + Small Predictor |
| Base | 官方 Tokenizer + Base | A 股 Tokenizer + Base Predictor | 严格 A 股 Tokenizer + Base Predictor |

Small 与 Base 使用同一份准入数据、划分和官方训练协议；每个规模的官方风格和
严格PIT各自训练 Tokenizer 与对应 Predictor。
零样本格不训练，只固定官方
权重作基线。官方风格轨保留作者架构、损失、优化器与随机数据集行为，但使用 ElanQuant
扩展 A 股数据、`sample_count=10` 百分比信号和 Top-3 模拟策略，因此不是作者 qlib
`sample_count=5`、Top-50/Drop-5/Hold-5 回测的逐项复现；
严格 PIT 轨才有资格进入模拟组合。

## 数据与划分

- 原始范围：2011-01-01 至运行时最新完整收盘交易日。
- 训练：10 日经济目标以及作者移位损失额外消费的第 101 行，都不晚于 2024 最后交易日。
- 验证：信号日从 2025 首个交易日开始，目标结束日不晚于 2025 最后交易日。
- 测试：信号日从 2026 首个交易日开始；本项目已经查看，因此永久标记 `TEST_VIEWED`。
- 最新交易日：仅用于在线排名，目标未成熟前不进入指标。

严格轨将供应商 `index_weight.trade_date` 保守延迟到下一个完整交易日使用，并保存
source/available session 对照。供应商没有公告时间、历史首次可得时间和修订版本回执，
因此这里明确披露：该规则避免同日偷看，但不能证明历史权重从未被后来回填。严格轨
使用全局交易日窗口和信号日尺度复权；股票首次出现后的缺失交易日按价格不变、成交量/
金额为零的停牌约定编码，未来缺行只影响 outcome mask，不会反向改变 T 日候选资格。
正式矩阵还必须引用独立的数据准入回执；该回执重新验证原始 CSV 的 closed-world 清单、
endpoint、股票代码、行数、日期范围和哈希，并绑定处理后数据 manifest。
十日实际收益在三条模型轨上使用同一个信号日尺度复权 outcome，与各模型自己的输入
变换彻底分离；缺失交易日只使用此前已知收盘价向前延续，并标记
`MISSING_SESSION_LAST_CLOSE_CARRY`。供应商没有独立、可审计的历史退市
结算价回执，因此本轮不另造退市价格；该限制写入评估回执，且不会改变 T 日候选资格。

## 官方训练参数

- `lookback=90`，`predict=10`，OHLCVA 六字段。
- 30 epochs，2 GPU，每 GPU batch size 50。
- 每 epoch 100,000 个训练样本、20,000 个验证样本。
- Tokenizer AdamW 学习率 `2e-4`。
- Predictor AdamW 学习率 `4e-5`，betas `(0.9, 0.95)`，weight decay `0.1`。
- OneCycleLR，seed 100。

严格轨只改变数据可得性、目标边界和 DDP 确定性采样；模型结构、损失、优化器、
调度器和推理采样保持作者实现。每个阶段写终态回执和 checkpoint SHA-256。

作者 Dataset 实际为 `90 + 10 + 1 = 101` 行，用于移位的 next-token loss；这是
官方代码的一个额外上下文行，不改变十日推理信号。严格轨保留该行为，并要求第 101
行也位于同一数据分区，避免它跨过 2024/2025/2026 边界。

服务器 PyTorch/NCCL 在作者 `setup_ddp` 的“先初始化进程组、后绑定 GPU”顺序上会
卡在首个 barrier。隔离 workspace 只做一个运行时修复：先按 `LOCAL_RANK` 绑定
GPU，再用该 `device_id` 初始化 NCCL。此修复不改变模型、损失、优化器、调度器、
Dataset 或推理，并单独写入 workspace 哈希和偏差说明。

两张 5090 位于不同 NUMA/PCIe Host Bridge 且没有 NVLink。服务器最小 collective
门禁验证后，训练设置 `NCCL_P2P_DISABLE=1` 和 `NCCL_IB_DISABLE=1`，使用已验证的
纯 Socket collective（`NCCL_SHM_DISABLE=1`、loopback）；64 MiB collective 与完整
Kronos DDP backward 均通过。它只改变跨卡传输路径，不改变数值目标或训练参数。

## 推理和选股

每个模型使用作者 `KronosPredictor.predict_batch`，参数 `T=0.6`、`top_p=0.9`、
`top_k=0`、`sample_count=10`。作者函数已把标准化预测逆变换回价格尺度。
在线横截面固定 `online_batch_size=50`，与 Worker 一致；正式历史评估也使用
`evaluation_batch_size=50` 加速，但不能改变附带在线排名的采样批次身份。

单模型信号：

```text
未来 10 个交易日预测 close 的平均值 / T 日 close - 1
```

页面保留六个实验格的正式证据；主排名仍只取已准入的严格 PIT Small 信号，
Base 完成不等于自动切换在线模型。不会
因为 T+1 是否可买而在 T 日改排名。

## 评估

模型选择只看 2025 验证集。统一记录 Pearson IC、Spearman RankIC、Top-10
未来十日实际 close 均值收益、样本量和横截面数量。正式评估每月冻结五个分散交易日
并使用这些日期的完整共同支持横截面，同时记录 eligible/evaluated 覆盖、anchor hash；
600 行快速结果只允许标记 `SMOKE`，不能做模型选择。2026 指标只做带 `TEST_VIEWED` 标签的
描述性报告，不允许反向选择参数。

Small formal 的旧回执用 `batch_size=50`，Base formal 将同一实际协议拆成
`evaluation_batch_size=50` 与 `online_batch_size=50`。六格目录不得简单忽略两套原始
代码/配置哈希；它必须保留原始身份，并通过固定提交、规范化协议哈希和源码 diff
白名单生成 `elanquant_evaluation_compatibility_v1` 后才可发布。

## 新增：官方 Demo 方法对齐版历史回测

原有在线 `Top3` 策略完整保留。本项目另外增加
`official-demo-method-extended-pit-v1`，它是独立、只读、连续历史回测，不读取或写入
模拟账户、订单、持仓和 NAV，也不由“更新数据并推理”按钮触发。

这一版本逐项固定作者 Demo 的方法语义：每个股票用 90 日上下文单独计算均值/标准差，
`epsilon=1e-5`、`clip=5`；使用底层 `auto_regressive_inference`，`T=0.6`、
`top_p=0.9`、`top_k=0`、`sample_count=5`；保留 mean/last/max/min 四个标准化
close 差信号，且预先指定 mean 为主信号。组合使用 Qlib TopkDropout 的 Top-50、
Drop-5、最少持有 5 日、日频延迟执行、次日开盘价、1亿元假设账户、沪深300基准、
买入0.1%、卖出0.15%、最低费用5元和9.5%涨跌停阈值。

它对齐的是官方方法，而不是伪装成相同数据实验：当前 checkpoint 与作者固定时间窗
不同，因此只使用因果准入的 `validation_2025`，绝不读取 2026 TEST_VIEWED 指标做选择；
数据来自扩展动态 PIT 沪深300与本项目供应商，成交额使用供应商真值；作者没有固定
pyqlib版本或推理seed，本项目为审计固定 pyqlib 0.9.7 与 seed 100。以上差异全部进入
不可变回执。作者图中的曲线是每日收益算术累计，不标成在线账户 NAV。

## 模拟执行

- T 日收盘后冻结 Top 3、权重、数量和已知价格。
- 数量按 100 股整手，并只使用 T 日已知现金和价格计算。
- 下一真实交易日用开盘价模拟；涨停买入、跌停卖出、停牌、缺价或资金不足会拒单。
- 拒单保留现金，不递补下一名；错过执行日不补做历史成交。
- 用户未点击的交易日记录为缺口，不能伪装成连续自动策略。
- 一个信号日只能有一次冻结发布。`force` 重跑可生成新的研究 run，但账本记录
  `SKIPPED_EXISTING_FROZEN_RUN`，不得把多个运行的 Top 3 合并、替换或补买。
- Top 3 中持仓、已有待执行订单或现金不足一手，都必须生成显式决策回执；不能
  用“没有订单”掩盖原因。
- 当前 MVP 不宣称公司行动、滑点、最少持有期或完整 NAV 目标再平衡；实现这些能力前，
  页面和报告不得展示相应绩效承诺。
