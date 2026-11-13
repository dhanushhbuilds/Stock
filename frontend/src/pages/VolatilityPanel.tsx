import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Badge, Note, Panel, QueryState, Stat, Table } from '@/components/ui'
import { apiGet, type RegisteredModel, type Run } from '@/lib/api'
import { dateTime, num, pct } from '@/lib/format'
import { cn } from '@/lib/utils'

interface VolMetrics { n: number; r2_log: number; rmse_log: number; mae_log: number; qlike: number; corr: number; rank_corr: number }
interface VolExp {
  model: string
  walk_forward: VolMetrics
  folds?: (VolMetrics & { test_start: string })[]
  holdout: VolMetrics
}

const LABEL: Record<string, string> = {
  persistence: 'Persistence (vol20)',
  har: 'HAR (5/20/60-day vol)',
  harx: 'HAR-X (+ VIX, market, range)',
  lightgbm: 'LightGBM (all 77 features)',
}
const COLORS: Record<string, string> = { persistence: '#48484a', har: '#7c7c80', harx: '#c7c7cc', lightgbm: '#ffffff' }

export function VolatilityPanel() {
  const runs = useQuery({ queryKey: ['runs'], queryFn: () => apiGet<Run[]>('/ml/runs') })
  const run = (Array.isArray(runs.data) ? runs.data : []).find((r) => r.pipeline === ('swing_vol' as Run['pipeline']))
  const exps = useQuery({ queryKey: ['experiments', run?.run_id], enabled: !!run,
    queryFn: () => apiGet<VolExp[]>(`/ml/experiments/${run!.run_id}`) })
  const models = useQuery({ queryKey: ['models'], queryFn: () => apiGet<RegisteredModel[]>('/ml/models') })
  const reg = (Array.isArray(models.data) ? models.data : []).find((m) => run && m.version.endsWith(run.run_id))
  const order = ['persistence', 'har', 'harx', 'lightgbm']
  const ex = [...(exps.data ?? [])].sort((a, b) => order.indexOf(a.model) - order.indexOf(b.model))
  const base = ex.find((e) => e.model === 'persistence')
  const best = ex.find((e) => e.model === reg?.model)
  const lift = (m?: VolMetrics, b?: VolMetrics) => (m && b ? 1 - m.rmse_log / b.rmse_log : null)

  const folds = (base?.folds ?? []).map((f, i) => {
    const row: Record<string, string | number> = { window: f.test_start.slice(0, 7) }
    for (const e of ex) { const x = e.folds?.[i]; if (x) row[e.model] = +x.r2_log.toFixed(3) }
    return row
  })

  return (
    <QueryState isPending={runs.isPending} error={runs.error} isEmpty={!run}
      empty="No volatility run yet (python -m app.engines.ml.volatility).">
      <div className="grid gap-3 lg:grid-cols-[2fr_1fr]">
        <Panel title="Next-week volatility forecast">
          <div className="grid grid-cols-2 md:grid-cols-4">
            <Stat label="Selected model" value={reg ? LABEL[reg.model] ?? reg.model : '—'} valueClass="text-[14px]" sub={dateTime(run?.created_at)} />
            <Stat label="Holdout R² (log vol)" value={num(best?.holdout.r2_log, 3)} valueClass="text-up"
              sub={`persistence ${num(base?.holdout.r2_log, 3)}`} />
            <Stat label="Error vs persistence" value={pct(-(lift(best?.holdout, base?.holdout) ?? 0), 1)} valueClass="text-up"
              sub="holdout RMSE change" />
            <Stat label="Rank correlation" value={num(best?.holdout.rank_corr, 3)} sub="predicted vs realised" />
          </div>
        </Panel>
        <Panel title="Promotion gate" right={reg && <Badge tone={reg.promoted ? 'up' : 'down'}>{reg.promoted ? 'promoted' : 'not promoted'}</Badge>}>
          <ul className="space-y-0.5 p-3 text-[12px]">
            {(reg?.promotion_reasons ?? []).map((r) => (
              <li key={r} className={r.startsWith('PASS') ? 'text-up' : 'text-down'}>{r}</li>
            ))}
          </ul>
        </Panel>
      </div>
      <QueryState isPending={exps.isPending} error={exps.error} isEmpty={!ex.length}>
        <Panel title="Out-of-sample accuracy — target: log realised volatility of the next 5 sessions">
          <Table head={['Model', 'WF R²', 'WF RMSE', 'WF QLIKE', 'Holdout R²', 'Holdout RMSE', 'Holdout QLIKE', 'Holdout rank corr', 'n (holdout)']}>
            {ex.map((e) => (
              <tr key={e.model} className={cn(e.model === reg?.model && 'bg-panel-2')}>
                <td className="font-medium"><span className="mr-2 inline-block size-2" style={{ background: COLORS[e.model] }} />{LABEL[e.model] ?? e.model}</td>
                <td className="num">{num(e.walk_forward.r2_log, 3)}</td>
                <td className="num">{num(e.walk_forward.rmse_log, 4)}</td>
                <td className="num">{num(e.walk_forward.qlike, 4)}</td>
                <td className={cn('num', e.model === reg?.model && 'text-up')}>{num(e.holdout.r2_log, 3)}</td>
                <td className="num">{num(e.holdout.rmse_log, 4)}</td>
                <td className="num">{num(e.holdout.qlike, 4)}</td>
                <td className="num">{num(e.holdout.rank_corr, 3)}</td>
                <td className="num text-dim">{e.holdout.n.toLocaleString('en-IN')}</td>
              </tr>
            ))}
          </Table>
        </Panel>
        <Panel title="R² per walk-forward window (higher is better; every window is unseen data)">
          <div className="h-[280px] p-2">
            <ResponsiveContainer>
              <BarChart data={folds} margin={{ left: 8, right: 8 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="window" tick={{ fill: 'var(--color-muted)', fontSize: 10 }} />
                <YAxis tick={{ fill: 'var(--color-muted)', fontSize: 10 }} width={40} />
                <Tooltip contentStyle={{ background: 'var(--color-panel-2)', border: '1px solid var(--color-line)', fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} formatter={(v) => LABEL[v] ?? v} />
                {ex.map((e) => <Bar key={e.model} dataKey={e.model} fill={COLORS[e.model] ?? '#888'} isAnimationActive={false} />)}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Note>
          Volatility is far more predictable than direction (volatility clusters). The risk engine uses this forecast for
          position sizing: a higher predicted volatility means a wider stop and a smaller position for the same rupee risk.
          Persistence and HAR are the standard baselines from the volatility literature; a model is promoted only if it beats
          both on walk-forward AND the once-only holdout.
        </Note>
      </QueryState>
    </QueryState>
  )
}
