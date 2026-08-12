import { Badge } from '../components/Badge'
import { experimentStateLabel, formatNumber, formatPercent, shortHash } from '../format'
import type { ExperimentCell, ExperimentTrack, ResearchRun } from '../types'

const tracks: ExperimentTrack[] = ['zero_shot', 'official_style', 'strict_pit']

const trackMeta: Record<ExperimentTrack, { label: string; code: string; description: string }> = {
  zero_shot: {
    label: '官方零样本',
    code: 'ZS',
    description: '官方预训练权重，不在扩展A股数据上训练。',
  },
  official_style: {
    label: '官方风格微调',
    code: 'FT',
    description: '保留作者架构与训练默认值，但使用本项目A股数据和排名信号；不是官方qlib回测复现。',
  },
  strict_pit: {
    label: '严格PIT适配',
    code: 'PIT',
    description: '动态成分、完整目标划分与因果数据；历史成分供应商修订限制会在回执中披露。',
  },
}

const emptyCell = (model: 'small', track: ExperimentTrack): ExperimentCell => ({
  id: `${model}-${track}`,
  model_size: model,
  track,
  state: 'pending',
  rank_ic: null,
  pearson_ic: null,
  top10_mean_return: null,
  model_hash: null,
  receipt: null,
  note: '等待服务器训练或评估回执。',
})

export function ResearchPage({ run }: { run: ResearchRun | null }) {
  const cells = (['small'] as const).flatMap((model) =>
    tracks.map(
      (track) =>
        run?.experiment_matrix.find((cell) => cell.model_size === model && cell.track === track) ??
        emptyCell(model, track),
    ),
  )

  return (
    <>
      <header className="page-heading page-heading--split">
        <div>
          <span className="eyebrow">03 / Research matrix</span>
          <h1>Small 三格实验矩阵</h1>
          <p>本轮只训练Kronos Small：官方零样本、官方风格微调和严格PIT适配。Base留待后续扩展。</p>
        </div>
        <div className="identity-card">
          <span>当前研究身份</span>
          <strong>{run ? `${run.as_of} / ${run.model_id}` : '尚无正式回执'}</strong>
          <small>{run?.viewed_test ? '2026测试已查看，后续结果必须标记viewed' : '测试集未被用于选择模型'}</small>
        </div>
      </header>

      <section className="matrix-key">
        {tracks.map((track) => (
          <div key={track}>
            <b>{trackMeta[track].code}</b>
            <span><strong>{trackMeta[track].label}</strong><small>{trackMeta[track].description}</small></span>
          </div>
        ))}
      </section>

      <section className="research-matrix">
        {cells.map((cell, index) => (
          <article className={`experiment-card experiment-card--${cell.track}`} key={cell.id}>
            <div className="experiment-card__number">{String(index + 1).padStart(2, '0')}</div>
            <div className="experiment-card__head">
              <div>
                <span>{cell.model_size.toUpperCase()}</span>
                <h2>{trackMeta[cell.track].label}</h2>
              </div>
              <Badge state={cell.state}>{experimentStateLabel[cell.state]}</Badge>
            </div>
            <div className="experiment-card__metrics">
              <div><span>RankIC</span><strong>{formatNumber(cell.rank_ic, 4)}</strong></div>
              <div><span>Pearson IC</span><strong>{formatNumber(cell.pearson_ic, 4)}</strong></div>
              <div><span>Top10十日收益</span><strong>{formatPercent(cell.top10_mean_return)}</strong></div>
            </div>
            <p>{cell.note || trackMeta[cell.track].description}</p>
            <footer>
              <code title={cell.model_hash || undefined}>MODEL {shortHash(cell.model_hash)}</code>
              <span>{cell.receipt || 'NO RECEIPT'}</span>
            </footer>
          </article>
        ))}
      </section>

      <section className="method-note">
        <span className="method-note__index">RULE / 01</span>
        <div>
          <h2>选择规则</h2>
          <p>只使用2025验证集选择生产候选；2026已查看测试结果不能反向调参。零样本和官方风格轨用于对照，严格PIT轨才有资格成为模拟组合输入。</p>
        </div>
      </section>
    </>
  )
}
