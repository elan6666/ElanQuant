# 2026-08-13 Base 正式评估怎么读

这份说明解释补跑的 Kronos Base 三格。Base 只进入研究对照目录；当前在线按钮、Top3
排名和模拟账本仍固定使用 Small 严格 PIT，不会因本次实验自动切换。

## 共同评估样本

- 2025 validation：18,000 行、60 个完整横截面，用于预先声明的比较。
- 2026 `TEST_VIEWED`：10,500 行、35 个完整横截面，只作描述。
- Small/Base 六格共用相同数据、成分、交易日、anchor hash 和实际收益定义。

## Base 结果

| Base 实验 | 2025 RankIC | 2025 Pearson IC | 2025 Top10 十日均值收益 | 2026 viewed RankIC |
|---|---:|---:|---:|---:|
| 官方零样本 | 0.034647 | 0.013329 | 0.4996% | -0.013525 |
| 官方风格 A 股微调 | 0.022944 | 0.004681 | 0.7290% | 0.026712 |
| 严格 PIT A 股微调 | 0.013421 | -0.003840 | 0.8972% | 0.030406 |

## 正确结论

1. Base 四段训练、三格 matrix、正式双分区评估和六格目录均通过技术与审计门禁。
2. Base 零样本在 2025 RankIC 最好；Base 严格 PIT 的 Top10 均值最高，但 Pearson IC
   为负。没有一条轨道在所有指标上稳定占优。
3. 2026 viewed 指标不能用于反向选择模型。Base 也不能因为 viewed RankIC 较高就替换
   Small。
4. 这些结果支持“Base 是可审计研究对照”，不支持“Base 更适合实盘”或“微调得到稳定
   alpha”的主张。

## 语义兼容回执

Small formal 使用旧字段 `batch_size=50`；Base formal 将同一语义明确写为
`evaluation_batch_size=50` 与 `online_batch_size=50`。两者实际评估批次、在线批次、
采样参数、共同支持和目标定义相同。项目没有改写任何 formal 文件，而是增加
`elanquant_evaluation_compatibility_v1`：它绑定两边原始配置/代码/评估哈希、指定 Git
提交、固定协议哈希和经审查的源码 diff 白名单。六格目录只在该兼容回执通过时发布。

## 保持不变的产品边界

- `releases/current` 仍指向 Small r2。
- 系统状态的 primary model 仍为 `small-strict-pit`。
- Base 不进入手动更新按钮、Top3 模拟组合或 paper 账本。

