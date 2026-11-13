import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/PageHeader'
import { Badge, Button, Panel, QueryState, Stat, Table } from '@/components/ui'
import {
  apiGet, apiPost, type Coverage, type Decision, type NewsRow, type Regime, type RegisteredModel, type StrategyResult,
} from '@/lib/api'
import { compact, dateTime, int, num, pct, signed, tone } from '@/lib/format'

const ACTION_TONE = { BUY: 'up', SELL: 'down', HOLD: 'info', NO_TRADE: 'muted' } as const

export function ActionBadge({ action }: { action: Decision['action'] }) {
  return <Badge tone={ACTION_TONE[action]}>{action.replace('_', ' ')}</Badge>
}

export function Overview() {
  const qc = useQueryClient()
  const regime = useQuery({ queryKey: ['regime'], queryFn: () => apiGet<Regime>('/decisions/regime') })
  const coverage = useQuery({ queryKey: ['coverage'], queryFn: () => apiGet<Coverage[]>('/data/coverage') })
  const models = useQuery({ queryKey: ['models'], queryFn: () => apiGet<RegisteredModel[]>('/ml/models') })
  const decisions = useQuery({ queryKey: ['decisions'], queryFn: () => apiGet<Decision[]>('/decisions?limit=50') })
  const news = useQuery({ queryKey: ['news', 'overview'], queryFn: () => apiGet<NewsRow[]>('/news?limit=8') })
  const strat = useQuery({ queryKey: ['strategy-report'],
    queryFn: () => apiGet<Record<string, StrategyResult>>('/strategies/report') })
  const run = useMutation({
    mutationFn: () => apiPost<{ summary: { count: number; actions: Record<string, number> } }>('/decisions/run?pipeline=swing'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['decisions'] }),
  })

  // Defensive: a malformed response must degrade to an empty state, never crash the page.
  const cov = Array.isArray(coverage.data) ? coverage.data : []
  const rows = cov.reduce((a, c) => a + c.rows, 0)
  const instruments = new Set(cov.map((c) => c.instrument_key)).size
  const checked = cov.filter((c) => c.quality_passed !== null)
  const modelList = Array.isArray(models.data) ? models.data : []
  const promoted = modelList.filter((m) => m.promoted)
  const top = Object.entries(strat.data ?? {})
    .filter(([k, v]) => !k.startsWith('_') && typeof v === 'object' && v.out_of_sample)
    .sort((a, b) => (b[1].out_of_sample?.sharpe ?? -99) - (a[1].out_of_sample?.sharpe ?? -99))
    .slice(0, 5)
  const bench = strat.data?._benchmark_equal_weight_buy_hold?.out_of_sample

  // latest batch of decisions = same created_at minute as the newest one
  const latest = Array.isArray(decisions.data) ? decisions.data : []
  const counts = latest.reduce<Record<string, number>>((a, d) => ({ ...a, [d.action]: (a[d.action] ?? 0) + 1 }), {})

  return (
    <>
      <PageHeader title="Overview">
        <span className="text-[11px] text-dim">Historical data · live feed not connected · paper trading postponed</span>
      </PageHeader>
      <div className="grid min-w-0 gap-3 p-3 xl:grid-cols-3">
        <Panel title="Market regime">
          <QueryState isPending={regime.isPending} error={regime.error} isEmpty={!regime.data?.trend}
            empty="Regime unavailable (needs NIFTY 50 and India VIX daily data).">
            {regime.data?.trend && (
              <div className="grid grid-cols-2">
                <Stat label="Trend" value={regime.data.trend.toUpperCase()}
                  valueClass={regime.data.trend === 'bull' ? 'text-up' : regime.data.trend === 'bear' ? 'text-down' : 'text-warn'}
                  sub={`NIFTY ${num(regime.data.nifty_close)} vs EMA200 ${num(regime.data.nifty_ema200)}`} />
                <Stat label="Volatility" value={regime.data.volatility.toUpperCase()}
                  sub={`India VIX ${num(regime.data.india_vix)} · ${pct(regime.data.vix_1y_percentile, 0)} pct-ile`} />
                <div className="col-span-2 px-3 pb-2 text-[11px] text-dim">As of session {regime.data.as_of}</div>
              </div>
            )}
          </QueryState>
        </Panel>
        <Panel title="Data lake">
          <QueryState isPending={coverage.isPending} error={coverage.error} isEmpty={!cov.length}
            empty="No data downloaded yet.">
            <div className="grid grid-cols-3">
              <Stat label="Candles" value={compact(rows)} sub={`${int(rows)} rows`} />
              <Stat label="Instruments" value={int(instruments)} />
              <Stat label="Quality checks" value={`${checked.filter((c) => c.quality_passed).length}/${checked.length}`}
                valueClass={checked.every((c) => c.quality_passed) ? 'text-up' : 'text-warn'} sub="passed" />
            </div>
          </QueryState>
        </Panel>
        <Panel title="Model registry" right={<Link to="/research" className="text-[11px] text-info hover:underline">Research →</Link>}>
          <QueryState isPending={models.isPending} error={models.error} isEmpty={!modelList.length}
            empty="No models trained yet.">
            <div className="grid grid-cols-2">
              <Stat label="Registered" value={int(modelList.length)} />
              <Stat label="Promoted" value={int(promoted.length)} valueClass={promoted.length ? 'text-up' : 'text-warn'}
                sub={promoted.length ? promoted.map((m) => `${m.pipeline}:${m.model}`).join(', ')
                  : 'none passed the gate → no live decisions'} />
            </div>
          </QueryState>
        </Panel>

        <Panel className="xl:col-span-2" title="Latest decisions (swing)"
          right={
            <>
              {run.error && <span className="text-[11px] text-down">{run.error.message}</span>}
              {run.data && <span className="num text-[11px] text-muted">{run.data.summary.count} decided</span>}
              <Button variant="primary" onClick={() => run.mutate()} disabled={run.isPending}>
                {run.isPending ? 'Running…' : 'Run swing decisions'}
              </Button>
            </>
          }>
          <QueryState isPending={decisions.isPending} error={decisions.error} isEmpty={!latest.length}
            empty={<span>No swing decisions: the direction model did not pass the promotion gate, so the live engine refuses to decide. For risk-evaluated BUY · SELL · HOLD on any stock or dataset, use <Link to="/signal-lab" className="text-[#5ac8fa] hover:underline">Signal Lab →</Link></span>}>
            <div className="flex gap-2 border-b border-line px-3 py-1.5">
              {Object.entries(counts).map(([a, n]) => (
                <span key={a} className="flex items-center gap-1.5"><ActionBadge action={a as Decision['action']} />
                  <span className="num text-muted">{n}</span></span>
              ))}
            </div>
            <div className="max-h-[340px] overflow-auto">
              <Table dense head={['Symbol', 'Action', 'Score', 'P(up)', 'P(down)', 'News', 'Reason', 'At']}>
                {latest.slice(0, 50).map((d) => (
                  <tr key={d.decision_id}>
                    <td className="font-medium">{d.symbol}</td>
                    <td><ActionBadge action={d.action} /></td>
                    <td className={`num ${tone(d.score)}`}>{signed(d.score)}</td>
                    <td className="num">{pct(d.contributions.ml?.p_up)}</td>
                    <td className="num">{pct(d.contributions.ml?.p_down)}</td>
                    <td className="num text-muted">{d.contributions.news?.items ?? 0}</td>
                    <td className="max-w-[420px] truncate text-muted" title={d.reasons.join(' · ')}>{d.reasons.at(-1)}</td>
                    <td className="text-dim">{dateTime(d.created_at)}</td>
                  </tr>
                ))}
              </Table>
            </div>
          </QueryState>
        </Panel>

        <Panel title="Best strategies (out of sample)" right={<Link to="/strategy" className="text-[11px] text-info hover:underline">Lab →</Link>}>
          <QueryState isPending={strat.isPending} error={strat.error} isEmpty={!top.length}>
            <Table dense head={['Strategy', 'Sharpe', 'Max DD', 'Total']}>
              {top.map(([k, v]) => (
                <tr key={k}>
                  <td>{k.replaceAll('_', ' ')}</td>
                  <td className="num">{num(v.out_of_sample?.sharpe)}</td>
                  <td className="num text-down">{pct(v.out_of_sample?.max_drawdown)}</td>
                  <td className={`num ${tone(v.out_of_sample?.total_return)}`}>{pct(v.out_of_sample?.total_return, 0)}</td>
                </tr>
              ))}
              {bench && (
                <tr className="text-muted">
                  <td className="italic">buy &amp; hold (equal weight)</td>
                  <td className="num">{num(bench.sharpe)}</td>
                  <td className="num">{pct(bench.max_drawdown)}</td>
                  <td className="num">{pct(bench.total_return, 0)}</td>
                </tr>
              )}
            </Table>
          </QueryState>
        </Panel>

        <Panel className="xl:col-span-3" title="Latest news (NSE · RBI · SEBI)"
          right={<Link to="/news" className="text-[11px] text-info hover:underline">News →</Link>}>
          <QueryState isPending={news.isPending} error={news.error} isEmpty={!Array.isArray(news.data) || !news.data.length}
            empty="No news ingested yet — use the News page to fetch the official feeds.">
            <Table dense head={['Time', 'Source', 'Symbols', 'Event', 'Sentiment', 'Headline']}>
              {(Array.isArray(news.data) ? news.data : []).map((n) => (
                <tr key={n.id}>
                  <td className="text-dim">{dateTime(n.usable_from)}</td>
                  <td className="text-muted">{n.source.replace('_', ' ')}</td>
                  <td>{n.symbols.join(', ') || '—'}</td>
                  <td className="text-muted">{n.event_type.replaceAll('_', ' ')}</td>
                  <td className={`num ${tone(n.sentiment_score)}`}>{signed(n.sentiment_score, 2)}</td>
                  <td className="max-w-[640px] truncate" title={n.title}>{n.title}</td>
                </tr>
              ))}
            </Table>
          </QueryState>
        </Panel>
      </div>
    </>
  )
}
