const sections = [
  {
    index: '01',
    title: '前端与后端如何协作',
    body: '浏览器只提交任务并轮询状态。FastAPI把任务写入SQLite，独立Worker领取后调用数据与GPU进程。因此页面关闭或VPN断开，只会让你暂时看不到进度，不会杀死服务器任务。',
    tag: 'FULL STACK',
  },
  {
    index: '02',
    title: '为什么本轮先做Small',
    body: 'Kronos Small约24.7M参数，使用官方Tokenizer-base，读取过去90根日K线并生成未来10日的多条可能路径。先用Small完成数据、训练、评估和产品闭环；Base不在本轮训练范围。',
    tag: 'MODEL',
  },
  {
    index: '03',
    title: '严格PIT为什么重要',
    body: 'PIT意为Point-in-Time：历史任意一天只能使用当时可得的数据。价格、复权、划分和交易状态按因果规则处理；成分权重保守延迟一个完整交易日，但供应商没有历史首次可得回执，因此不能隐瞒其修订风险。',
    tag: 'DATA',
  },
  {
    index: '04',
    title: '股票分数怎样产生',
    body: '先把模型预测反归一化回真实价格，再计算未来10个预测收盘价均值相对当前收盘价的收益。Small严格PIT分数、覆盖率和可交易条件共同形成排名，不直接等同于真实买入建议。',
    tag: 'SIGNAL',
  },
  {
    index: '05',
    title: '模拟交易怎样避免偷看未来',
    body: 'T日收盘后冻结Top-3和股数；T+1开盘只执行或拒绝既定订单。涨跌停、停牌、ST限制或现金不足都不会触发临时递补。MVP尚不宣称公司行动、滑点、最少持有期或完整NAV再平衡。',
    tag: 'EXECUTION',
  },
  {
    index: '06',
    title: '最新预测为什么尚不可评分',
    body: '今天收盘后可以预测未来10日，但真实未来尚未发生。只有第10个未来交易日结束后，这个anchor才能进入IC、RankIC和收益评价；在线预测与已成熟评估必须分开显示。',
    tag: 'EVALUATION',
  },
]

export function MethodsPage() {
  return (
    <>
      <header className="page-heading methods-heading">
        <span className="eyebrow">06 / Methods</span>
        <h1>从一次点击，理解完整系统</h1>
        <p>这里解释产品为什么这样设计。所有方法都围绕同一个原则：今天做出的判断，只能使用今天已经知道的事实。</p>
      </header>
      <section className="methods-list">
        {sections.map((section) => (
          <article key={section.index}>
            <span className="methods-list__index">{section.index}</span>
            <div><small>{section.tag}</small><h2>{section.title}</h2><p>{section.body}</p></div>
          </article>
        ))}
      </section>
      <section className="method-note method-note--dark">
        <span className="method-note__index">BOUNDARY</span>
        <div><h2>这不是自动炒股软件</h2><p>ElanQuant v0没有券商接口、账户密码、真实委托、自动调度或融资融券。它是一套让模型实验、数据证据和模拟交易可理解、可追溯的学习系统。</p></div>
      </section>
    </>
  )
}
