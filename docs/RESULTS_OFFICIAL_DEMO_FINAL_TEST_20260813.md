# 官方 Demo 方法对齐版：2026 已开封样本外诊断

这是已冻结 `small-official-ft` checkpoint、mean 主信号和
Top50/Drop5/Hold5 策略在 2026 分区上的连续样本外回测。它用于评估这一个
已冻结版本，不参与选模、信号选择或调参。

## 为什么改用 2026

- 训练完整运行 30 epochs，但每个 epoch 都用 2025 validation loss 判断
  是否覆盖 `best_model`。Predictor 最终使用 epoch 5 的最低验证 loss
  `3.2969183349609374`，而非 epoch 30 checkpoint。
- 因此 2025 只能称为 checkpoint-selection / method validation。
- 2026 没有参与训练或 best-checkpoint 选择，所以它更适合作为独立样本外
  诊断。但它之前已在模型指标报告中被查看，因此页面永久显示
  `TEST_VIEWED / OPENED`，不宣称这是 blind 或 untouched test。

## 冻结支持

- 信号区间：2026-01-05 至 2026-07-29。
- 十日目标最晚结束：2026-08-12。
- 39,072 个股票-交易日信号，137 个完整横截面。
- 每日候选数量 min/median/max：278 / 283 / 297。
- 模型、checkpoint、数据、mean 主信号、四个辅助信号、Top50/Drop5/Hold5、
  次日开盘执行、成本和 Qlib 版本均在打开结果前进入 analysis lock。

Analysis lock 在运行前直接锁定模型、数据、支持集、推理参数、策略和执行常数；
generator/provider/backtest 源码与 Qlib 实体哈希由终态回执和保存的源码副本
封存。因此本项目不把这一版夸大为“所有可执行代码在结果前完整密码学预注册”。
下一个新方法 schema 若要进一步提高证据等级，应将这些 executable/environment
哈希也纳入 pre-run lock；不能回写当前已开封回执伪装成事前证据。

## 结果

| 标准化空间信号 | 含费算术累计收益 | 沪深300 | 含费超额 | 信息比率 | 最大回撤 |
|---|---:|---:|---:|---:|---:|
| mean（预先指定主信号） | -7.65% | 0.45% | -8.09% | -1.322 | -13.31% |
| last | -10.62% | 0.45% | -11.07% | -1.912 | -16.33% |
| max | 3.50% | 0.45% | 3.05% | 0.470 | -10.27% |
| min | -15.02% | 0.45% | -15.46% | -2.241 | -23.32% |

## 正确结论

1. 官方 Demo 方法对齐轨的工程、不可变证据和 Top3 隔离门禁通过。
2. 预先指定的 mean 策略在修正后的 2026 已开封样本外诊断中明显跑输基准，并出现
   较大回撤。这不支持 alpha、实盘或策略有效性主张。
3. max 在打开后的数字相对较好，但它是预先标记的辅助描述信号，不能在看到
   结果后改成主信号。
4. 若要开发新版本，必须先指定新方法和新的未查看评估边界，不能继续消费
   这一份 2026 结果做调参循环。

## 审计身份

- Catalog canonical receipt：`032cb3e7009790d7c825e6114347cddcb9fa61f5688b2c67364adabe9c128359`
- 2026 backtest canonical receipt：`372df4291a7a53dc2a31f3f941104fdc38ea18aa7e2ae263b0c64fc5dcaf50dc`
- 独立审计：2025 67,349/233 与 2026 39,072/137 均 PASS，
  `paper_tables_unchanged=true`。
- r5 全部文件与 v3 catalog 在最终审计后收紧为 0440，目录为 0550；
  收紧权限后重算审计仍 PASS。
- `turnover_mean` 由 Qlib 运行报告进入回执，但现有 daily-series 没有封存逐日
  turnover；它不用于页面主结论。收益、基准、超额、IR 和回撤都已从日序列独立复算。
- 在线主版本仍为 `kronos-a-share-v2-20260813-r2`；Top3 推荐、订单、持仓和净值未改变。
