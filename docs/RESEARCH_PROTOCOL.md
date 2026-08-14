# ElanQuant 研究协议

## 活动模型矩阵

活动版本严格限定为四格：

| 模型规模 | 官方零样本 | 官方方式微调 |
| --- | --- | --- |
| Small | 官方 Tokenizer + Small | 新训练 Tokenizer + Small Predictor |
| Base | 官方 Tokenizer + Base | 新训练 Tokenizer + Base Predictor |

零样本格不训练。微调格各自按作者代码训练 Tokenizer 和 Predictor。旧 Strict PIT
实验只保留退役回执和原始哈希，不进入网页选择器、新矩阵、在线晋级或历史目录。

## 官方日期切片

| 原始切片 | 日期范围 | 角色 |
| --- | --- | --- |
| train | 2011-01-01 ～ 2022-12-31 | Tokenizer/Predictor 训练 |
| validation | 2022-09-01 ～ 2024-06-30 | 每轮 validation loss 与 best checkpoint |
| rolling test | 2024-04-01 ～ frozen latest | 微调后的预测和成熟标签评估 |
| requested backtest | 2024-07-01 ～ frozen latest | Top50 与 Top3 历史组合 |

原始切片的重叠用于 lookback buffer，不等于有效标签或信号重叠。作者训练 Dataset
实际消费 `90 + 10 + 1 = 101` 行；推理使用 90 日上下文和未来 10 个全市场交易日
时间戳。因此每次发布必须逐股票重开处理后的 pickle，记录并验证：

- train/validation 每个 101 行窗口的 first input、anchor、target end 和 consumed end；
- rolling test 每个 100 行窗口的 90 日上下文与 10 日成熟目标；
- train consumed end 早于 validation anchor；validation consumed end 早于 test anchor；
- 实际首个信号/成交日可以晚于请求的 2024-07-01，回执同时保存 requested/actual。

测试一旦打开即永久标记 `TEST_VIEWED`，只允许描述，不允许选模、调参、晋级或称作
untouched/final test。最新信号在未来十日未成熟前不可进入 IC、RankIC 或收益指标。

## 数据可得性

- 成分股使用供应商 `index_weight.trade_date` 后的下一个完整交易日生效。
- 供应商偶尔返回 100/200 行的不完整快照。原始响应保留并写入回执，但不进入成员集合，
  也不向前填充；此前最后一份完整 300 只快照继续有效。
- 供应商不提供历史 first-seen/revision receipt，因此不能证明历史文件从未被后来修订；
  该限制必须保留在每次数据与结果回执。
- T 日候选资格只使用截至 T 已知的成员与过去 90 个全市场交易日，不读取个股未来
  是否仍有成分或行情行。未来 10 日只定义目标时间戳。
- 行情代理若为明文 HTTP，回执必须披露传输限制；凭据不得进入日志和产物。

## 训练

作者协议保持：

- lookback 90、predict 10、OHLCVA 六字段、clip 5；
- 30 epochs，不使用 patience 提前停止；
- 每 GPU batch 50；每 epoch 100,000 个训练样本、20,000 个验证样本；
- Tokenizer AdamW `2e-4`；Predictor AdamW `4e-5`；
- betas `(0.9, 0.95)`、weight decay `0.1`、作者 OneCycleLR、seed 100。

每轮都计算 validation loss，只覆盖当时更优的 `best_model`；训练仍跑满 30 epoch。
每个阶段必须封存 fresh checkpoint、日志、数据、配置、上游 commit、输入/输出权重与
运行环境哈希。Small 与 Base 使用新的独立 run id；禁止覆盖旧 checkpoint。

## 成熟标签评估

每个模型使用自己的 checkpoint 和信号。统一报告：

- Pearson IC：预测值与实际 10 日收益的线性相关；
- RankIC：预测排序与实际 10 日收益排序的 Spearman 相关；
- Top10 实际收益：每个成熟横截面预测前十的实际收益均值；
- 股票样本数、交易日截面数、共同支持集与 anchor hash。

rolling test 全部为 `TEST_VIEWED / non-selection / non-promotion`。缺未来十日成熟目标的
在线预测只能排名，不能被填写成 0 或借用昨日标签。

## 历史回测

四个模型分别以作者标准化空间产生 mean/last/max/min 信号：

```text
signal = aggregate(predicted normalized close) - last normalized context close
```

`sample_count=5`、`T=0.6`、`top_p=0.9`、`top_k=0`；预先固定 mean 为主信号，
其他三种只作伴随诊断。每个模型的同一份信号分别运行：

1. 官方方法：Top50 / Drop5 / Hold5；
2. 组合敏感性：Top3 / Drop1 / Hold5。

两者均使用 Qlib 日频延迟执行、次日开盘、1 亿元假设账户、沪深300基准、买入
0.10%、卖出 0.15%、最低费用 5 元、9.5% 涨跌停阈值。Top3 是事后组合规模
敏感性，不等同网页在线 Top3，也不能用于选择模型或修改在线账户。

活动历史目录恰有 `4 models × 2 portfolios = 8` 项；缺一项整体拒绝发布。同一模型的
Top50/Top3 必须绑定完全相同的 signal/provider hash。每日收益、成本、换手、实际
持仓数和持仓明细都需可复算。Qlib 的 TopK 是目标数量，持有期和可交易限制可能使
某日实际持仓数偏离目标。

## 在线模拟账户

在线账户与历史 Qlib 回测隔离：

- T 日收盘冻结排名、数量与当时已知价格；T+1 开盘只成交或拒绝；
- 100 股整手、现金与费用约束；拒单不递补；错过执行日不补历史成交；
- 同一信号日首次发布唯一，强制重算只更新研究结果，不改冻结账本；
- 本地/远程只改变 execution identity，不改变模型证据；
- Base 在没有单独 promotion receipt 前只能研究推理，不允许写在线模拟账本。

## 发布门禁

正式发布顺序固定：数据 fetch → materialize → payload admission → Small/Base 训练 →
四格 matrix → pre-result lock → 成熟评估与八格回测 → 独立审计 → 原子切换目录。

pre-result lock 必须在任何新测试结果出现前绑定数据、模型、代码、Qlib、provider、
calendar、策略和所有 runner/helper 哈希。旧 release 不改、不删；新目录完全通过后
才切换 `current`，并另写 retirement receipt。
