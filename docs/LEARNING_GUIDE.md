# 用 ElanQuant 学前后端全栈

建议先读 [第一课：从一个按钮看懂 ElanQuant 前后端全栈](LESSON_01_FULLSTACK_OVERVIEW.md)，
再按本页的四周节奏动手。

这个项目适合按一次“按钮请求”从头跟到尾学习。你已经有 C++ 类/模板和 Python
语法基础，不必先学完一整套课程。

## 第一阶段：先看懂数据怎么走

1. `frontend/src/api.ts`：浏览器怎样发送 HTTP 请求、校验 JSON。
2. `backend/src/elanquant/api/app.py`：FastAPI 怎样接收请求并返回 202。
3. `backend/src/elanquant/orchestration/jobs.py`：为什么任务要保存进 SQLite，而不是在请求里直接训练。
4. `backend/src/elanquant/orchestration/worker.py`：独立 Worker 怎样领取任务。
5. `backend/src/elanquant/pipelines/real.py`：后端怎样编排数据、GPU 推理、排名和账本。

现在可以把一条结果沿证据链追到底：

```text
data_snapshots（这天的数据是否完整）
  → inference_runs / run_model_evaluations（哪个实验和哪组哈希）
  → stock_scores / recommendation_items（为什么进入 Top 3）
  → paper_signal_publications / paper_orders（哪次运行冻结了账本）
```

前端对应查看“总览数据健康 → 实验矩阵/运行差异 → 股票排名解释 → 模拟账户”。
这条链同时练习数据库主外键、HTTP JSON、React 状态和量化审计。

新增的“历史回测”页提供第二条学习链：

```text
标准化信号回执 → Qlib Top50/Drop5/Hold5 → 历史回测目录
  → FastAPI 只读 GET → React 曲线与参数解释
```

它故意不进 SQLite，也没有 POST 接口。把它和 Top3 对照阅读，可以直观看懂
“在线选股/模拟执行”和“连续历史回测”是两种不同产品，而不是把两个账本混在一起。

## 第二阶段：前端

需要学习：HTML 语义、CSS 布局、TypeScript 类型、React 组件、state/effect、异步
fetch、轮询、表格和响应式设计。先从 `App.tsx` 和 `OverviewPage.tsx` 开始，再看
`useDashboard.ts` 如何在任务运行时每四秒轮询、空闲时降低频率。

练习顺序：

1. 给任务卡增加一个只读字段。
2. 给运行详情增加一个 provenance 展示。
3. 写 Vitest，先让测试失败，再补组件。

## 第三阶段：后端

需要学习：Python 包、类型标注、FastAPI 路由、Pydantic、SQLite 事务、幂等、状态机、
子进程和 systemd。先理解 `POST -> jobs 表 -> Worker`，再看研究模型。

练习顺序：

1. 用 TestClient 提交任务并查询。
2. 观察相同日期的两次提交为何只生成一个任务。
3. 模拟 Worker 中断，理解为什么系统选择明确失败而不是盲目续跑。
4. 修改纸面账户规则并补账本不变量测试，特别是同一信号日强制重跑不能改变
   第一次冻结发布。

## 第四阶段：模型与量化研究

需要学习：OHLCVA、复权、指数成分 PIT、训练/验证/测试、Tokenizer、Transformer、
采样温度、IC/RankIC、横截面选股、T/T+1 和涨跌停规则。先比较
`official` 与 `strict` 两套 dataset，再阅读上游 Kronos 模型层。

重点不是“预测明天一定涨”，而是回答：数据在当时是否可知？信号是否逆变换到真实
价格？模型选择是否只看验证集？订单数量是否在 T 日冻结？任何一个答案不清楚，结果
就不能称为可审计研究。

## 推荐学习节奏

- 第 1 周：HTTP、JSON、React 页面和 FastAPI 路由。
- 第 2 周：SQLite、任务队列、Worker、测试。
- 第 3 周：Pandas/PyTorch 数据集与 Kronos 推理。
- 第 4 周：PIT、指标、模拟执行和一次完整小改动。

每次只改一个可观察行为，同时补测试、在服务器验证、再看网页结果。这比先背完
JavaScript/Python/PyTorch 语法更适合你现在的基础。
