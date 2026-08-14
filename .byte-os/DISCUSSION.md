# ElanQuant 可移植推理与公开复现讨论

## Date

2026-08-14

## User request

优化 ElanQuant，使项目同时支持本地推理和远程服务器推理，并完善 README
或提供初始化脚本，让第三方能够从零准备数据、下载官方预训练权重并复现项目。

## Current understanding

- “两种模型”暂按“同一套模型与协议的两种推理执行后端”理解：Local 与 Remote，
  而不是新增两种模型架构。
- 现有六格 Small/Base × zero-shot/official-ft/strict-PIT 身份必须保持不变；
  执行位置不能改变模型身份、信号公式或证据语义。
- 当前工程硬编码了个人服务器路径、校园 VPN/SSH、服务目录和研究依赖，尚不是
  第三方可移植安装包。
- 公开复现应分层：快速运行官方零样本、下载可公开 checkpoint 运行完整推理、
  以及从头训练六格研究矩阵；三者的硬件和耗时完全不同。
- 市场数据、用户 token、训练产物和 checkpoint 不应进入 Git。下载脚本必须生成
  数据来源、版本、哈希和许可边界回执。

## Open questions

None for the product direction. Detailed packaging, model-hosting and provider
licensing choices move into shaping.

## Suggested defaults

- 把产品叫作两种 execution profile：`local` 与 `remote`，不称为两种模型。
- Local MVP：macOS Apple Silicon + CPU/MPS 探测，默认 Small；Base 允许尝试但明确
  标注内存和耗时要求；训练仍为 Linux NVIDIA 服务器专属。
- Remote：用户自己的 Linux/NVIDIA 主机，通过同一 FastAPI job contract 执行；
  主机、路径和 SSH 信息全部配置化，不保留公开仓库中的个人地址。
- 提供一个统一入口 `elanquant bootstrap --profile local|remote`，内部按阶段执行
  preflight、依赖安装、固定上游、官方权重下载、数据导入/获取、数据准入、启动服务，
  并支持 `--dry-run`、断点续跑和每阶段 receipt。
- 数据默认同时提供“用户自备标准文件”与“可选 provider adapter”。凭据只从环境或
  0600 文件读取；绝不输出、上传或写入回执。
- README 采用三层复现路线：5 分钟 UI/契约演示、可公开权重的 zero-shot 推理、
  完整六格训练与历史回测。每层明确硬件、磁盘、预计耗时、可获得结果和限制。
- 官方权重直接从固定 Hugging Face revision 下载并校验 SHA；ElanQuant 微调权重若要
  公开，放到独立模型仓库/Release，并单独审查许可证、体积和模型卡。

## Confirmed decisions

- 保留当前在线 Top3、历史 Top50/Top3、六格实验和审计边界。
- 新能力必须支持本地推理与服务器推理。
- 第三方应能依据公开说明从零完成环境、数据和权重准备，而不是依赖个人服务器目录。
- 公开流程必须可复算并保留数据、代码、配置和权重身份。
- Local 首版支持 Apple Silicon macOS。
- Local 默认运行 Small；Base 作为高内存、高耗时的可选模型。
- 公开 ElanQuant 自己训练的 A 股 official-ft 与 strict-PIT checkpoint，并为每个
  checkpoint 提供模型卡、训练/数据边界、许可证说明和 SHA-256。
- 数据入口同时支持用户自备标准 CSV/Parquet，以及用户自备 Tushare token 的自动获取。
- Remote 面向用户自己的任意 Linux/NVIDIA 服务器；个人校园服务器仅作为一个私有部署实例，
  不进入公开默认配置。

## Non-goals

- 不向第三方开放项目所有者的服务器、VPN、账号或数据 token。
- 不把原始 A 股数据、私有凭据、数据库、日志或 checkpoint 直接提交到 Git。
- 不在本地 MVP 中承诺训练或高性能 Base 推理。
- 不因执行位置不同而产生两个不可比较的研究协议。

## Recommended next command

回答开放问题后使用 `$byte-shape` 更新产品、技术、UX 和复现规格；规格确认后再用
`$byte-plan` 拆分迁移与交付步骤。

---

# 官方分割重置讨论

## Date

2026-08-14

## User request

退出现有 ElanQuant 微调模型和 Strict-PIT 版本，改用 pinned Kronos A 股
fine-tune Demo 的日期切片：train 2011-01-01..2022-12-31，validation
2022-09-01..2024-06-30，test 2024-04-01..latest；在测试期运行官方
Top50/Drop5/Hold5 与 Top3 组合回测。

## Current understanding

- 这是模型和实验身份重置，不是简单修改网页日期。
- 官方日期是带 lookback overlap 的原始切片。官方说明 validation/test 提前开始是为了
  90 日 lookback；官方 backtest 实际从 2024-07-01 开始。
- 官方训练 Dataset 消费 90 lookback + 10 prediction + 1 行，需另外封存每个 split 的
  effective context、target 和 consumed-row 边界。
- “测试到今天”必须在每次 release 固定成 latest closed session 和 immutable manifest；
  一旦查看并比较 Top50/Top3，它就是 TEST_VIEWED，不再是盲测。
- 官方仓库提供处理方法和配置，不提供一份可直接复用、持续到今天的原始 A 股数据；
  使用项目供应商数据只能称 official-method/date aligned。

## Open questions

None for implementation. The owner authorized Byte Auto with the recommended
defaults. Physical deletion and fine-tuned-weight publication remain separately
gated destructive/license actions.

## Suggested defaults

- 不物理删除。将旧 release 标为 `RETIRED_SUPERSEDED`、从活动目录/UI 移除并保留只读哈希证据。
- Small 与 Base 都重训；公开矩阵为四格，严格 PIT 不再是产品版本。
- 训练/验证严格沿用 pinned 官方 Dataset、30 epochs、每轮 validation loss 选 best checkpoint。
- Test raw slice 从 2024-04-01 开始提供 lookback；历史回测从 2024-07-01 到冻结的 latest closed session。
- Top50/Drop5/Hold5 为官方基线；Top3/Drop1/Hold5 明确标为 portfolio-size extension。
- 两种策略复用同一个模型预测、标准化空间 mean 信号、sample_count=5；不得按测试结果改主信号。
- 测试结果发布后标 `TEST_VIEWED`，只用于报告，不再反向调模型或参数。

## Confirmed decisions

- 目标日期切片采用 pinned Kronos Demo 的 train/validation/test 起点和用途。
- 测试/回测数据扩展到每个 release 的最新已收盘交易日。
- 历史回测同时需要 Top50 和 Top3 组合版本。
- Strict-PIT 版本不再作为网页活动版本。
- 旧微调产物从活动产品退役但不物理删除，保留只读审计链。
- Small 与 Base 都使用新分割重新微调；新公开矩阵为四格。
- 日期、101 行 Dataset、30 epochs 和 best-validation checkpoint 对齐官方；
  provider、动态成分、真实 amount 等数据差异必须披露，不伪称 byte-identical。
- Top3 固定 3/1/Hold5，与 Top50 共用 sample-count-5 标准化空间 mean 信号。
- 新 Small Official FT 只能在候选 release 全部通过后接替旧在线版本；
  Base 仍需显式选择，不因已查看测试结果自动晋级。

## Non-goals

- 不把重叠的 raw slices 错称为重叠标签。
- 不把已反复查看的扩展测试期称为 untouched final test。
- 不在讨论阶段删除 checkpoint、数据、回执或数据库记录。
- 不把 Top3 组合扩展伪装成 Kronos 官方参数。

## Recommended next command

确认六个开放问题后使用 `$byte-shape` 重写产品、研究和迁移规格。
