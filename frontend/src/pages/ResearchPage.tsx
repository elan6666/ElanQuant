import { Badge } from '../components/Badge'
import { experimentStateLabel, formatDateTime, formatNumber, formatPercent, shortHash } from '../format'
import type {
  ExperimentCell,
  ExperimentTrack,
  ResearchRun,
  RunDiff,
  RunSummary,
} from '../types'

const tracks: ExperimentTrack[] = ['zero_shot', 'official_style', 'strict_pit']
const sizes = ['small', 'base'] as const

const trackMeta: Record<ExperimentTrack, { label: string; code: string; description: string }> = {
  zero_shot: {
    label: '官方零样本',
    code: 'ZS',
    description: '官方预训练权重，不在扩展A股数据上训练。',
  },
  official_style: {
    label: '官方风格微调',
    code: 'FT',
    description: '保留作者架构与训练默认值，用A股数据重训Tokenizer和Predictor。',
  },
  strict_pit: {
    label: '严格PIT适配',
    code: 'PIT',
    description: '动态成分、完整目标划分与因果数据；供应商修订限制保留披露。',
  },
}

const emptyCell = (
  model: 'small' | 'base',
  track: ExperimentTrack,
): ExperimentCell => ({
  id: `${model}-${track}`,
  model_size: model,
  track,
  state: 'pending',
  rank_ic: null,
  pearson_ic: null,
  top10_mean_return: null,
  model_hash: null,
  receipt: null,
  note: model === 'base' ? 'Base服务器实验正在运行，未有终态回执前不展示结果。' : '等待服务器训练或评估回执。',
  evaluations: {},
})

interface ResearchPageProps {
  run: ResearchRun | null
  catalog: ExperimentCell[]
  catalogAvailable: boolean
  runs: RunSummary[]
  diff: RunDiff | null
}

export function ResearchPage({ run, catalog, catalogAvailable, runs, diff }: ResearchPageProps) {
  const evidence = catalogAvailable ? catalog : []
  const cells = sizes.flatMap((model) =>
    tracks.map(
      (track) =>
        evidence.find((cell) => cell.model_size === model && cell.track === track) ??
        emptyCell(model, track),
    ),
  )

  return (
    <>
      <header className="page-heading page-heading--split">
        <div>
          <span className="eyebrow">03 / Experiment evidence</span>
          <h1>Small 与 Base <span className="title-phrase">六格实验</span></h1>
          <p>两个规模都只比较三条预先定义的轨道。正式验证和已查看测试分开展示，在线结果不参与评分。</p>
        </div>
        <div className="identity-card">
          <span>当前在线主轨</span>
          <strong>{run ? `${run.as_of} / ${run.model_id}` : '尚无正式回执'}</strong>
          <small>严格PIT资格≠验证集最优；Base完成后也不会自动替换Small。</small>
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

      {!catalogAvailable ? (
        <section className="state-panel state-panel--warning">
          <div><Badge tone="warning">证据目录不可用</Badge><h2>Small/Base 回执未通过消费端校验</h2></div>
          <p>主控面和模拟账户仍可查看，但这里不会展示未封存或身份不一致的实验数字。</p>
        </section>
      ) : null}

      {sizes.map((size) => (
        <section className="model-evidence" key={size}>
          <div className="section-heading model-evidence__heading">
            <div><span className="eyebrow">Kronos {size.toUpperCase()}</span><h2>{size === 'small' ? 'Small · 当前在线基线' : 'Base · 补充规模对照'}</h2></div>
            <span className="count-label">3 CELLS</span>
          </div>
          <div className="research-matrix">
            {cells.filter((cell) => cell.model_size === size).map((cell, index) => (
              <ExperimentCard
                cell={cell}
                index={index}
                zeroShot={cells.find(
                  (candidate) =>
                    candidate.model_size === size && candidate.track === 'zero_shot',
                )}
                key={cell.id}
              />
            ))}
          </div>
        </section>
      ))}

      <RunEvidence runs={runs} diff={diff} />

      <section className="method-note">
        <span className="method-note__index">RULE / 01</span>
        <div>
          <h2>评估与上线是两件事</h2>
          <p>2025 validation用于比较；2026已查看结果只做描述。严格PIT轨才有模拟组合资格，但这不等于它的指标最高，也不构成投资有效性证明。</p>
        </div>
      </section>
    </>
  )
}

function ExperimentCard({
  cell,
  index,
  zeroShot,
}: {
  cell: ExperimentCell
  index: number
  zeroShot: ExperimentCell | undefined
}) {
  const validation = cell.evaluations.validation_2025
  const viewed = cell.evaluations.test_viewed_2026
  const validationRankIc = validation?.rank_ic ?? cell.rank_ic
  const zeroRankIc =
    zeroShot?.evaluations.validation_2025?.rank_ic ?? zeroShot?.rank_ic ?? null
  const delta =
    validationRankIc === null || zeroRankIc === null ? null : validationRankIc - zeroRankIc
  return (
    <article className={`experiment-card experiment-card--${cell.track}`}>
      <div className="experiment-card__number">{String(index + 1).padStart(2, '0')}</div>
      <div className="experiment-card__head">
        <div><span>{cell.model_size.toUpperCase()}</span><h2>{trackMeta[cell.track].label}</h2></div>
        <Badge state={cell.state}>{experimentStateLabel[cell.state]}</Badge>
      </div>
      <div className="split-label"><b>VALIDATION / 2025</b><span>用于比较</span></div>
      <div className="experiment-card__metrics">
        <div><span>RankIC</span><strong>{formatNumber(validationRankIc, 4)}</strong></div>
        <div><span>Pearson IC</span><strong>{formatNumber(validation?.pearson_ic ?? cell.pearson_ic, 4)}</strong></div>
        <div><span>Top10十日收益</span><strong>{formatPercent(validation?.top10_mean_return ?? cell.top10_mean_return)}</strong></div>
      </div>
      <div className="metric-context">
        <span>对零样本 RankIC Δ</span><b className={(delta ?? 0) >= 0 ? 'positive' : 'negative'}>{delta === null ? '—' : formatNumber(delta, 4)}</b>
        <small>{validation ? `${validation.rows.toLocaleString()} rows · ${validation.cross_sections} sections` : '尚无样本支持回执'}</small>
      </div>
      <div className="viewed-strip">
        <span>TEST_VIEWED / 2026</span>
        <b>RankIC {formatNumber(viewed?.rank_ic ?? null, 4)}</b>
        <small>{viewed ? `${viewed.rows.toLocaleString()} rows · 不可反向调参` : '尚无终态回执'}</small>
      </div>
      <p>{cell.note || trackMeta[cell.track].description}</p>
      <footer><code title={cell.model_hash || undefined}>MODEL {shortHash(cell.model_hash)}</code><span>{cell.receipt ? 'SEALED RECEIPT' : 'NO RECEIPT'}</span></footer>
    </article>
  )
}

function RunEvidence({ runs, diff }: { runs: RunSummary[]; diff: RunDiff | null }) {
  return (
    <section className="two-column research-evidence-row">
      <div className="content-section">
        <div className="section-heading"><div><span className="eyebrow">Run lineage</span><h2>最近运行</h2></div><span className="count-label">{runs.length} RUNS</span></div>
        <div className="run-list">
          {runs.slice(0, 5).map((item) => (
            <div key={item.id}><span>{item.as_of}</span><code>{shortHash(item.id)}</code><b>{item.paper_publication_state || 'RESEARCH_ONLY'}</b><small>{formatDateTime(item.created_at)}</small></div>
          ))}
          {runs.length === 0 ? <p className="muted">还没有可比较的完成运行。</p> : null}
        </div>
      </div>
      <div className="content-section">
        <div className="section-heading"><div><span className="eyebrow">Run diff</span><h2>本次与上次</h2></div>{diff?.same_session ? <Badge tone="warning">同日重算</Badge> : null}</div>
        {diff?.comparable ? (
          <>
          <div className="diff-grid">
            <div><span>Top 3 重合</span><strong>{diff.top3_overlap}/3</strong></div>
            <div><span>Top 10 重合</span><strong>{diff.top10_overlap}/10</strong></div>
            <div><span>新进 Top 3</span><strong>{diff.top3_added.join(' · ') || '无'}</strong></div>
            <div><span>移出 Top 3</span><strong>{diff.top3_dropped.join(' · ') || '无'}</strong></div>
          </div>
          <div className="identity-change-list">
            {Object.entries(diff.identity_changes).map(([identity, changed]) => (
              <span key={identity}><b>{identity}</b>{changed ? '已变化' : '未变'}</span>
            ))}
          </div>
          {diff.largest_rank_changes.length > 0 ? (
            <div className="rank-change-list">
              {diff.largest_rank_changes.slice(0, 5).map((change) => (
                <span key={change.code}><b>{change.code}</b>#{change.from_rank} → #{change.to_rank}</span>
              ))}
            </div>
          ) : null}
          </>
        ) : <p className="muted">{diff?.reason === 'STRICT_RANK_COVERAGE_INCOMPLETE' ? '两次严格PIT排名的共同覆盖不足，已阻止空比较。' : '只有一次完成运行，暂时无法比较。'}</p>}
        <p className="micro-copy">这里只描述排名变化，不把同日重算说成“模型提升”。</p>
      </div>
    </section>
  )
}
