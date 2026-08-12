# 第一课：从一个按钮看懂 ElanQuant 前后端全栈

这节课不要求你会 JavaScript、数据库或深度学习。目标只有一个：点击网页里的
“更新数据并运行推理”后，你能说清楚数据经过了哪些程序，以及为什么要这样设计。

## 1. 前端、后端和模型分别是什么

可以先把 ElanQuant 想成一家只服务你的研究室：

- **前端**是研究室前台。它显示按钮、任务进度、股票排名和模拟账户。
- **后端 API**是接待员。它接收请求、检查格式、分配任务编号，并回答查询。
- **数据库**是登记簿。即使浏览器关闭，任务、事件和账户仍然存在。
- **Worker**是后台研究员。它从登记簿领取任务，运行耗时的数据和模型流程。
- **Kronos**是研究员使用的预测工具。它读取过去 90 根日 K，生成未来 10 日的
  多条可能路径。

前端不会训练模型，API 也不会在一次网页请求里完成 GPU 推理。它们只负责各自最
擅长的部分。

## 2. 一次按钮请求的完整旅程

```text
你点击按钮
  ↓
React 调用 POST /api/v1/jobs/update-infer
  ↓
FastAPI 验证 JSON，把任务写入 SQLite，立即返回 202 + job_id
  ↓
独立 Worker 领取任务
  ↓
确定最近完整收盘日 → 更新并校验 300 只股票数据
  ↓
调用 Kronos Small 三格模型推理
  ↓
严格 PIT Small 分数排序，冻结 Top 3 模拟订单
  ↓
一次 SQLite 事务同时发布 run、分数、账户和任务成功状态
  ↓
React 每几秒查询 API，页面出现结果
```

这里最关键的是 `202 Accepted`。它的意思不是“推理已经完成”，而是“服务器已经
可靠接收任务”。所以网页、SSH 隧道或 VPN 后来断开，不会让 Worker 的 GPU 子进程
跟着消失。

## 3. 前端做了什么

入口是 `frontend/src/App.tsx`。它根据当前页面选择总览、任务、实验矩阵、排名、
模拟账户或方法说明。

你会遇到四个基础概念：

1. **组件**：可重复使用的页面小块，例如状态徽章和任务进度。
2. **state**：页面此刻记住的数据，例如“任务是否运行中”。
3. **fetch**：浏览器通过 HTTP 向后端请求 JSON。
4. **runtime decoder**：`frontend/src/api.ts` 不盲信服务器数据；缺字段或出现未知
   状态时直接报契约错误，不伪造成功页面。

网页每隔几秒轮询一次，而不是使用 WebSocket。这个单用户系统不需要更复杂的实时
连接；轮询更容易调试，VPN 重连后也能自然恢复。

## 4. 后端 API 做了什么

入口是 `backend/src/elanquant/api/app.py`。FastAPI 把 Python 函数映射成 HTTP 路由：

- `POST /api/v1/jobs/update-infer`：提交任务。
- `GET /api/v1/jobs/{id}`：查询一个任务。
- `GET /api/v1/runs/latest`：读取最新研究结果。
- `GET /api/v1/paper/account`：读取模拟账户。

Pydantic 负责检查请求。例如日期必须是合法的 `YYYY-MM-DD`。后端只监听服务器的
`127.0.0.1:8765`，外网不能直接访问；你的 Mac 通过 SSH 端口转发看到它。

## 5. 为什么还要 SQLite 和 Worker

如果 FastAPI 收到请求后直接运行模型，会出现三个问题：

- HTTP 连接可能超时。
- 浏览器或 VPN 断开时很难判断任务是否仍在运行。
- API 被 GPU 工作阻塞后，页面连进度也查不到。

因此 `jobs.py` 先把任务写进 SQLite，`worker.py` 再独立领取。SQLite 使用 WAL 模式，
API 可以读状态，Worker 同时写进度。相同日期的重复点击会命中幂等键，只返回已有
任务，不会启动两份 GPU 推理。

Worker 的状态机大致是：

```text
QUEUED → RESOLVING_SESSION → UPDATING_DATA → VALIDATING_DATA
       → INFER_SMALL → SCORING → PAPER_LEDGER → SUCCEEDED
```

任何数据不完整都会安全停止；系统不会拿昨天的排名冒充今天结果。

## 6. 模型在后端流程中的位置

Kronos 不直接输出“买入”或“卖出”。每个模型只完成预测：

```text
输入：过去 90 个交易日的 open/high/low/close/volume/amount
输出：未来 10 个交易日的多条 OHLCVA 可能路径
信号：未来 10 日预测 close 的平均值 ÷ T 日 close - 1
```

本轮有三个 Small 实验身份：

- `small-zero-shot`：官方权重，不训练。
- `small-official-ft`：按作者风格在扩展 A 股数据上微调。
- `small-strict-pit`：使用严格时间可得数据和边界训练，作为主排名。

页面同时展示三格用于比较，但选股排序只使用严格 PIT Small。模型之后还有独立的
排名和模拟执行层，所以“预测模型”不等于“交易策略”。

## 7. 严格 PIT 为什么重要

PIT 是 point-in-time，意思是“回到当时，只允许使用当时已经知道的信息”。

常见泄漏包括：

- 用今天的沪深 300 成分股回测十年前。
- T 日选股时偷看 T+1 是否停牌或涨停。
- 训练样本的第 101 行跨过训练/验证边界。
- 反复查看 2026 测试结果后再调 2025 参数。

ElanQuant 的严格轨把成分生效延迟、90+10+1 窗口、缺失交易日、复权尺度、
`TEST_VIEWED` 和 T/T+1 执行全部写进回执。严格不代表供应商数据绝对完美；供应商
没有历史首次可得和修订回执的限制也会明确披露。

## 8. 模拟账户不是回测魔法

T 日收盘后，系统冻结 Top 3、数量和已知价格；下一真实交易日才用开盘价尝试成交。

- 100 股一手。
- 涨停买不进、跌停卖不出、停牌或资金不足都会拒单。
- 拒单保留现金，不递补第 4 名。
- 当天买入的股票当天不可卖，下一交易日解锁。
- 你没有点击的日期会记录缺口，不伪装成自动连续策略。

这只是研究账本，不连接中信证券或任何真实账户。

## 9. 你现在最值得先读的五个文件

按下面顺序，每次只回答一个问题：

1. `frontend/src/pages/OverviewPage.tsx`：按钮和状态在页面上怎样表达？
2. `frontend/src/api.ts`：HTTP JSON 怎样变成 TypeScript 数据？
3. `backend/src/elanquant/api/app.py`：POST 请求怎样变成任务？
4. `backend/src/elanquant/orchestration/jobs.py`：任务怎样持久化和去重？
5. `backend/src/elanquant/orchestration/worker.py`：后台怎样领取并执行任务？

读完后再进入 `pipelines/real.py`，把数据、模型、排名和账本串起来。

## 10. 第一课完成标准

如果你能不用术语回答下面四题，就已经真正入门：

1. 为什么按钮返回 202，而不是等模型跑完再返回 200？
2. 为什么关闭浏览器后任务还在？
3. 为什么模型分数和模拟订单必须分成两层？
4. 为什么最新在线预测不能立即拿来计算十日 RankIC？

下一课可以从前端开始：亲手给任务卡增加一个字段，再沿着 TypeScript、API JSON、
FastAPI 和 SQLite 把它接通。
