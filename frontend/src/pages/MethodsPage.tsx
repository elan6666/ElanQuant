const sections = [
  {
    index: '01',
    title: '前端与后端如何协作',
    body: '浏览器只提交任务并轮询状态。FastAPI把任务写入SQLite，独立Worker领取后调用数据与GPU进程。因此页面关闭或VPN断开，只会让你暂时看不到进度，不会杀死服务器任务。',
    tag: 'FULL STACK',
  },
  {
    index: '02',
    title: 'Small和Base如何比较',
    body: 'Small先完成数据、训练、评估和在线闭环；Base现在用同一份扩展数据和三条实验轨补跑。参数更多不代表必然更好，只有同支持集正式指标才能比较，而且不会因Base训完就自动切换在线模型。',
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
    body: '先把模型预测反归一化回真实价格，再计算未来10个预测收盘价均值相对当前收盘价的收益。Small严格PIT分数决定模型排名；输入不完整会阻止发布，而T+1可交易条件只决定成交或拒绝，绝不会反过来改T日排名。',
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
    title: 'Top3和官方Demo版为什么同时保留',
    body: 'Top3是收盘后手动运行的在线研究与模拟订单：反归一化百分比信号、10条采样、T日冻结、T+1执行。官方Demo版是独立连续历史回测：标准化空间差值、5条采样、Top50、Drop5、最少持有5日。它们回答不同问题，绝不共享账本。',
    tag: 'TWO TRACKS',
  },
  {
    index: '07',
    title: '最新预测为什么尚不可评分',
    body: '今天收盘后可以预测未来10日，但真实未来尚未发生。只有第10个未来交易日结束后，这个anchor才能进入IC、RankIC和收益评价；在线预测与已成熟评估必须分开显示。',
    tag: 'EVALUATION',
  },
]

export function MethodsPage() {
  return (
    <>
      <header className="page-heading methods-heading">
        <span className="eyebrow">07 / Methods</span>
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
