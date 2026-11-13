import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { PageHeader } from '@/components/PageHeader'
import { VolatilityPanel } from '@/pages/VolatilityPanel'
import { Badge, Segmented, Note, Panel, QueryState, Stat, Table } from '@/components/ui'
import { apiGet, type Experiment, type Metrics, type RegisteredModel, type Run } from '@/lib/api'
import { dateTime, num, pct, tone } from '@/lib/format'
import { cn } from '@/lib/utils'

const COLORS = ['#f5f5f7', '#a1a1a6', '#6fd59a', '#6e6e73', '#d4d4d8', '#48484a']
const PIPE = {
  swing: 'Swing · daily bars → next 5 sessions (label: excess return vs universe)',
  intraday: 'Intraday · 5-min bars → next 30 minutes',
} as const

function MetricRows({ exps, part }: { exps: Experiment[]; part: 'walk_forward' | 'holdout' }) {
  const best = Math.min(...exps.map((e) => e[part].log_loss))
  return (
    <Table head={['Model', 'Log loss', 'No-skill', 'Δ vs no-skill', 'Direction AUC', 'IC', 'IC t', 'Accuracy', 'Macro-F1', 'Brier', 'n']}>
      {exps.map((e) => {
        const m: Metrics = e[part]
        const gain = m.baseline_prior.log_loss - m.log_loss
        return (
          <tr key={e.model}>
            <td className="font-medium">{e.model}</td>
            <td className={cn('num', m.log_loss === best && 'text-up')}>{m.log_loss.toFixed(4)}</td>
            <td className="num text-muted">{m.baseline_prior.log_loss.toFixed(4)}</td>
            <td className={`num ${tone(gain)}`}>{gain >= 0 ? '+' : ''}{gain.toFixed(4)}</td>
            <td className={`num ${tone((m.direction_auc ?? 0.5) - 0.5)}`}>{num(m.direction_auc, 4)}</td>
            <td className={`num ${tone(m.ic_mean)}`}>{num(m.ic_mean, 4)}</td>
            <td className="num">{num(m.ic_t, 2)}</td>
            <td className="num">{pct(m.accuracy)}</td>
            <td className="num">{num(m.macro_f1, 3)}</td>
            <td className="num">{num(m.brier, 4)}</td>
            <td className="num text-dim">{m.n.toLocaleString('en-IN')}</td>
          </tr>
        )
      })}
    </Table>
  )
}

function TradingRows({ exps, part }: { exps: Experiment[]; part: 'walk_forward' | 'holdout' }) {
  const bench = exps[0]?.[part].trading.benchmark_equal_weight
  return (
    <Table head={['Model', 'Total', 'Ann.', 'Sharpe', 'Max DD', 'Profit factor', 'Win rate', 'Trades']}>
      {exps.map((e) => {
        const s = e[part].trading.strategy
        return (
          <tr key={e.model}>
            <td className="font-medium">{e.model}</td>
            <td className={`num ${tone(s.total_return)}`}>{pct(s.total_return)}</td>
            <td className="num">{pct(s.annualized_return)}</td>
            <td className="num">{num(s.sharpe)}</td>
            <td className="num text-down">{pct(s.max_drawdown)}</td>
            <td className="num">{num(s.profit_factor)}</td>
            <td className="num">{pct(s.win_rate)}</td>
            <td className="num">{s.trades?.toLocaleString('en-IN')}</td>
          </tr>
        )
      })}
      {bench && (
        <tr className="text-muted">
          <td className="italic">equal-weight buy &amp; hold</td>
          <td className="num">{pct(bench.total_return)}</td>
          <td className="num">{pct(bench.annualized_return)}</td>
          <td className="num">{num(bench.sharpe)}</td>
          <td className="num">{pct(bench.max_drawdown)}</td>
          <td className="num">{num(bench.profit_factor)}</td>
          <td className="num">{pct(bench.win_rate)}</td>
          <td>—</td>
        </tr>
      )}
    </Table>
  )
}

export function Research() {
  const [pipeline, setPipeline] = useState<'swing' | 'intraday' | 'volatility'>('swing')
  const [part, setPart] = useState<'walk_forward' | 'holdout'>('walk_forward')
  const runs = useQuery({ queryKey: ['runs'], queryFn: () => apiGet<Run[]>('/ml/runs') })
  // the latest run that compared the most models for this pipeline
  const run = (runs.data ?? []).filter((r) => r.pipeline === pipeline).sort((a, b) =>
    b.models.length - a.models.length || b.created_at.localeCompare(a.created_at))[0]
  const exps = useQuery({
    queryKey: ['experiments', run?.run_id],
    queryFn: () => apiGet<Experiment[]>(`/ml/experiments/${run!.run_id}`),
    enabled: !!run && pipeline !== 'volatility',
  })
  const models = useQuery({ queryKey: ['models'], queryFn: () => apiGet<RegisteredModel[]>('/ml/models') })
  const registered = (models.data ?? []).find((m) => run && m.version.endsWith(run.run_id))
  const ex = exps.data ?? []

  const foldData = (ex[0]?.folds ?? []).map((f, i) => {
    const row: Record<string, string | number> = { window: f.fold.test_start.slice(0, 7) }
    for (const e of ex) {
      const ff = e.folds[i]
      if (ff) row[e.model] = +(ff.baseline.log_loss - ff.metrics.log_loss).toFixed(5)
    }
    return row
  })
  const beat = ex.map((e) => ({ model: e.model, n: e.folds.length,
    wins: e.folds.filter((f) => f.metrics.log_loss < f.baseline.log_loss).length }))
  const selected = registered ? ex.find((e) => e.model === registered.model) : undefined
  const cm = selected?.holdout.confusion_matrix

  return (
    <>
      <PageHeader title="AI Research">
        <Segmented label="Pipeline" value={pipeline} onChange={setPipeline} options={[['swing', 'Swing'], ['intraday', 'Intraday'], ['volatility', 'Volatility']] as const} />
      </PageHeader>
      <div className="flex flex-col gap-3 p-3">
        {pipeline === 'volatility' ? <VolatilityPanel /> : (
        <QueryState isPending={runs.isPending} error={runs.error} isEmpty={!run}
          empty={`No ${pipeline} training run yet (python -m app.engines.ml.cli train --pipeline ${pipeline}).`}>
          <div className="grid gap-3 lg:grid-cols-[2fr_1fr]">
            <Panel title="Run">
              <div className="grid grid-cols-2 md:grid-cols-4">
                <Stat label="Task" value={pipeline === 'swing' ? '5-session' : '30-minute'} sub={PIPE[pipeline]} />
                <Stat label="Run" value={<span className="text-[13px]">{run?.run_id}</span>} sub={dateTime(run?.created_at)} />
                <Stat label="Dataset" value={<span className="text-[13px]">{run?.dataset_version}</span>} sub="content-hashed version" />
                <Stat label="Models compared" value={run?.models.length} sub={run?.models.join(', ')} />
              </div>
            </Panel>
            <Panel title="Promotion gate" right={registered && <Badge tone={registered.promoted ? 'up' : 'down'}>
              {registered.promoted ? `promoted: ${registered.model}` : `not promoted (${registered.model})`}</Badge>}>
              <ul className="space-y-0.5 p-3 text-[12px]">
                {(registered?.promotion_reasons ?? []).map((r) => (
                  <li key={r} className={r.startsWith('PASS') ? 'text-up' : r.startsWith('FAIL') ? 'text-down' : 'text-warn'}>{r}</li>
                ))}
                {!registered && <li className="text-muted">Registry entry not found.</li>}
              </ul>
            </Panel>
          </div>

          <QueryState isPending={exps.isPending} error={exps.error} isEmpty={!ex.length}>
            <Panel title="Out-of-sample quality" right={
              <Segmented label="Evaluation" value={part} onChange={setPart} options={[['walk_forward', 'Walk-forward (all folds)'], ['holdout', 'Locked holdout']] as const} />
            }>
              <MetricRows exps={ex} part={part} />
              <div className="p-3">
                <Note>
                  “No-skill” = always predicting the training-period class frequencies. Direction AUC 0.5 = coin flip.
                  IC = daily rank correlation between the model’s score and next returns across stocks (t ≥ 2 ≈ statistically significant).
                  Selection uses walk-forward only; the holdout was evaluated once afterwards.
                </Note>
              </div>
            </Panel>

            <div className="grid gap-3 xl:grid-cols-[3fr_2fr]">
              <Panel title="Log-loss improvement over no-skill, per test window (above 0 = better than no-skill)">
                <div className="h-[300px] p-2">
                  <ResponsiveContainer>
                    <BarChart data={foldData} margin={{ left: 8, right: 8 }}>
                      <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                      <XAxis dataKey="window" tick={{ fill: 'var(--color-muted)', fontSize: 10 }} />
                      <YAxis tick={{ fill: 'var(--color-muted)', fontSize: 10 }} width={52} />
                      <Tooltip contentStyle={{ background: 'var(--color-panel-2)', border: '1px solid var(--color-line)', fontSize: 11 }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <ReferenceLine y={0} stroke="var(--color-muted)" />
                      {ex.map((e, i) => <Bar key={e.model} dataKey={e.model} fill={COLORS[i % COLORS.length]} />)}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex flex-wrap gap-3 border-t border-line px-3 py-1.5 text-[11px] text-muted">
                  {beat.map((b) => <span key={b.model}><span className="text-fg">{b.model}</span> beat no-skill in <span className="num text-up">{b.wins}/{b.n}</span> windows</span>)}
                </div>
              </Panel>
              <Panel title={`Holdout confusion matrix${selected ? ` — ${selected.model}` : ''}`}>
                {cm ? (
                  <div className="p-3">
                    <table className="num w-full text-center">
                      <thead className="text-[10px] text-dim"><tr><th /><th>pred DOWN</th><th>pred NEUTRAL</th><th>pred UP</th></tr></thead>
                      <tbody>
                        {cm.map((r, i) => {
                          const tot = r.reduce((a, b) => a + b, 0) || 1
                          return (
                            <tr key={i}>
                              <th className="pr-2 text-right text-[10px] text-dim">{['true DOWN', 'true NEUTRAL', 'true UP'][i]}</th>
                              {r.map((v, j) => (
                                <td key={j} className={cn('border border-line py-2', i === j && 'text-up')}
                                  style={{ background: `color-mix(in srgb, #ffffff ${Math.round((v / tot) * 60)}%, transparent)` }}>
                                  {v.toLocaleString('en-IN')}<div className="text-[10px] text-muted">{pct(v / tot, 0)}</div>
                                </td>
                              ))}
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : <div className="p-3 text-muted">Select a run with a registered model.</div>}
              </Panel>
            </div>

            <Panel title={`Trading after costs (${part === 'walk_forward' ? 'walk-forward' : 'holdout'}) — ${pipeline === 'swing' ? 'long-only top-10 weekly rebalance, turnover costs' : 'trade the most confident 10% of decisions, costs per trade'}`}>
              <TradingRows exps={ex} part={part} />
            </Panel>
          </QueryState>
        </QueryState>
        )}
      </div>
    </>
  )
}
