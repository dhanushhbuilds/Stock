import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { CandleChart } from '@/components/CandleChart'
import { Badge, Button, ChromeArt, Panel, QueryState, Stat, Table } from '@/components/ui'
import {
  apiGet, apiPost, type CandlesResponse, type Coverage, type Decision, type NewsRow, type Regime, type RegisteredModel,
  type StrategyResult,
} from '@/lib/api'
import { compact, dateTime, int, num, pct, signed, tone } from '@/lib/format'
import { cn } from '@/lib/utils'

const ACTION_TONE = { BUY: 'up', SELL: 'down', HOLD: 'info', NO_TRADE: 'muted' } as const

export function ActionBadge({ action }: { action: Decision['action'] }) {
  return <Badge tone={ACTION_TONE[action]}>{action.replace('_', ' ')}</Badge>
}

type ModelWithMetrics = RegisteredModel & { metrics?: { holdout?: { r2_log?: number } } }

export function Overview() {
  const qc = useQueryClient()
  const regime = useQuery({ queryKey: ['regime'], queryFn: () => apiGet<Regime>('/decisions/regime') })
  const coverage = useQuery({ queryKey: ['coverage'], queryFn: () => apiGet<Coverage[]>('/data/coverage') })
  const models = useQuery({ queryKey: ['models'], queryFn: () => apiGet<ModelWithMetrics[]>('/ml/models') })
  const decisions = useQuery({ queryKey: ['decisions'], queryFn: () => apiGet<Decision[]>('/decisions?limit=50') })
  const news = useQuery({ queryKey: ['news', 'overview'], queryFn: () => apiGet<NewsRow[]>('/news?limit=8') })
  const nifty = useQuery({ queryKey: ['nifty-1y'], queryFn: () =>
    apiGet<CandlesResponse>(`/data/candles/${encodeURIComponent('NSE_INDEX|Nifty 50')}?timeframe=1day&limit=250`) })
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
  const volModel = promoted.find((m) => m.pipeline === 'swing_vol')
  const top = Object.entries(strat.data ?? {})
    .filter(([k, v]) => !k.startsWith('_') && typeof v === 'object' && v.out_of_sample)
    .sort((a, b) => (b[1].out_of_sample?.sharpe ?? -99) - (a[1].out_of_sample?.sharpe ?? -99))
    .slice(0, 5)
  const bench = strat.data?._benchmark_equal_weight_buy_hold?.out_of_sample
  const latest = Array.isArray(decisions.data) ? decisions.data : []
  const counts = latest.reduce<Record<string, number>>((a, d) => ({ ...a, [d.action]: (a[d.action] ?? 0) + 1 }), {})
  const nc = Array.isArray(nifty.data?.candles) ? nifty.data.candles : []
  const nLast = nc.at(-1)
  const nChg = nLast && nc[0] ? nLast.close / nc[0].close - 1 : null
  const newsRows = Array.isArray(news.data) ? news.data : []

  return (
    <div className="flex flex-col gap-5">
      {/* Hero */}
      <section className="fade-in relative grid items-center gap-6 overflow-hidden pb-4 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <h1 className="eyebrow">Overview</h1>
          <p className="headline text-gradient mt-3 text-[56px] md:text-[76px]">Markets,<br />understood.</p>
          <p className="mt-5 max-w-[46ch] text-[19px] leading-snug text-muted">
            AI forecasts, tested strategies and an independent risk engine — for every NIFTY&nbsp;50 stock.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-5">
            <Link to="/signal-lab"><Button variant="primary" size="lg">Open Signal Lab</Button></Link>
            <Link to="/research" className="inline-flex items-center gap-0.5 text-[15px] text-fg hover:underline underline-offset-4">
              See the research <ChevronRight className="size-4" />
            </Link>
          </div>
        </div>
        <ChromeArt className="hidden h-[380px] lg:block" />
      </section>

      {/* Bento */}
      <div className="grid gap-5 lg:grid-cols-12">
        <Panel tone="raised" className="lg:col-span-8" title="NIFTY 50"
          right={nChg != null && <Badge tone={nChg >= 0 ? 'up' : 'down'}>{nChg >= 0 ? '▲' : '▼'} {pct(Math.abs(nChg), 1)} · 1Y</Badge>}>
          <QueryState isPending={nifty.isPending} error={nifty.error} isEmpty={!nc.length}>
            <div className="px-6">
              <div className="num headline text-[44px]">{num(nLast?.close)}</div>
              <div className="text-[12.5px] text-dim">Close {nLast ? dateTime(nLast.ts) : ''}</div>
            </div>
            <div className="h-[260px] px-2 pb-3"><CandleChart candles={nc} intraday={false} height={250} /></div>
          </QueryState>
        </Panel>

        <Panel className="lg:col-span-4" title="Market regime">
          <QueryState isPending={regime.isPending} error={regime.error} isEmpty={!regime.data?.trend}
            empty="Regime unavailable (needs NIFTY 50 and India VIX daily data).">
            {regime.data?.trend && (
              <div className="flex h-full flex-col px-6 pb-6">
                <div className={cn('headline text-[64px]', regime.data.trend === 'bull' ? 'text-up' : regime.data.trend === 'bear' ? 'text-down' : 'text-fg')}>
                  {regime.data.trend.toUpperCase()}
                </div>
                <div className="mt-1 text-[13px] text-muted">NIFTY {num(regime.data.nifty_close)} vs 200-day {num(regime.data.nifty_ema200)}</div>
                <div className="mt-auto grid grid-cols-2 gap-3 pt-6">
                  <div className="rounded-2xl bg-white/[0.05] px-4 py-3">
                    <div className="text-[12px] text-dim">Volatility</div>
                    <div className="headline mt-0.5 text-[22px]">{regime.data.volatility.toUpperCase()}</div>
                  </div>
                  <div className="rounded-2xl bg-white/[0.05] px-4 py-3">
                    <div className="text-[12px] text-dim">India VIX</div>
                    <div className="num headline mt-0.5 text-[22px]">{num(regime.data.india_vix)}</div>
                    <div className="text-[11px] text-dim">{pct(regime.data.vix_1y_percentile, 0)} pct-ile</div>
                  </div>
                </div>
                <div className="mt-3 text-[11.5px] text-dim">Session {regime.data.as_of}</div>
              </div>
            )}
          </QueryState>
        </Panel>

        <Panel tone="light" className="lg:col-span-4" padded>
          <div className="pt-6">
            <div className="text-[12px] font-semibold text-[#6e6e73]">AI volatility model · promoted</div>
            <div className="num headline mt-3 text-[64px] text-ink">{volModel?.metrics?.holdout?.r2_log != null ? volModel.metrics.holdout.r2_log.toFixed(3) : '—'}</div>
            <p className="mt-1 text-[15px] leading-snug text-[#424245]">
              R² on the locked holdout year. Beats both standard baselines on unseen data.
            </p>
            <Link to="/research" className="mt-4 inline-flex items-center gap-1 text-[14px] font-medium text-ink hover:underline underline-offset-4">
              View the evidence <ArrowUpRight className="size-4" />
            </Link>
          </div>
        </Panel>

        <Panel className="lg:col-span-4" title="Data lake">
          <QueryState isPending={coverage.isPending} error={coverage.error} isEmpty={!cov.length} empty="No data downloaded yet.">
            <div className="grid grid-cols-3 pb-4">
              <Stat label="Candles" value={compact(rows)} sub={`${int(rows)} rows`} />
              <Stat label="Instruments" value={int(instruments)} />
              <Stat label="Quality" value={checked.filter((c) => c.quality_passed).length}
                valueClass={checked.every((c) => c.quality_passed) ? 'text-up' : 'text-warn'} sub={`of ${checked.length} checks passed`} />
            </div>
          </QueryState>
        </Panel>

        <Panel className="lg:col-span-4" title="Model registry" right={<Link to="/research" className="text-[12.5px] text-muted hover:text-white">Research ›</Link>}>
          <QueryState isPending={models.isPending} error={models.error} isEmpty={!modelList.length} empty="No models trained yet.">
            <div className="grid grid-cols-2 pb-4">
              <Stat label="Registered" value={int(modelList.length)} />
              <Stat label="Promoted" value={int(promoted.length)} valueClass={promoted.length ? 'text-up' : 'text-warn'}
                sub={promoted.length ? promoted.map((m) => `${m.pipeline}:${m.model}`).join(', ') : 'none passed the gate → no live decisions'} />
            </div>
          </QueryState>
        </Panel>

        <Panel className="lg:col-span-7" title="Best strategies · out of sample"
          right={<Link to="/strategy" className="text-[12.5px] text-muted hover:text-white">Strategy Lab ›</Link>}>
          <QueryState isPending={strat.isPending} error={strat.error} isEmpty={!top.length}>
            <Table dense head={['Strategy', 'Sharpe', 'Max drawdown', 'Total return']}>
              {top.map(([k, v]) => (
                <tr key={k}>
                  <td>{k.replaceAll('_', ' ')}</td>
                  <td className="num">{num(v.out_of_sample?.sharpe)}</td>
                  <td className="num text-down">{pct(v.out_of_sample?.max_drawdown)}</td>
                  <td className={`num ${tone(v.out_of_sample?.total_return)}`}>{pct(v.out_of_sample?.total_return, 0)}</td>
                </tr>
              ))}
              {bench && (
                <tr className="text-dim">
                  <td className="italic">Buy &amp; hold (equal weight)</td>
                  <td className="num">{num(bench.sharpe)}</td>
                  <td className="num">{pct(bench.max_drawdown)}</td>
                  <td className="num">{pct(bench.total_return, 0)}</td>
                </tr>
              )}
            </Table>
          </QueryState>
        </Panel>

        <Panel tone="raised" className="lg:col-span-5" title="Get a verdict on any stock" padded>
          <p className="text-[15px] leading-snug text-muted">
            Upload any daily price file — or pick a NIFTY 50 stock — and receive a risk-evaluated BUY, SELL or HOLD with every reason shown.
          </p>
          <Link to="/signal-lab" className="mt-5 inline-block"><Button variant="primary">Open Signal Lab</Button></Link>
        </Panel>

        <Panel className="lg:col-span-12" title="Latest decisions · swing"
          right={
            <>
              {run.error && <span className="text-[12px] text-down">{run.error.message}</span>}
              {run.data && <span className="num text-[12px] text-muted">{run.data.summary.count} decided</span>}
              <Button onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? 'Running…' : 'Run swing decisions'}</Button>
            </>
          }>
          <QueryState isPending={decisions.isPending} error={decisions.error} isEmpty={!latest.length}
            empty={<span>No swing decisions: the direction model did not pass the promotion gate, so the live engine refuses to decide. For risk-evaluated BUY · SELL · HOLD on any stock or dataset, use <Link to="/signal-lab" className="text-fg underline underline-offset-4">Signal Lab</Link>.</span>}>
            <div className="flex gap-2 px-6 pb-2">
              {Object.entries(counts).map(([a, n]) => <span key={a} className="flex items-center gap-1.5"><ActionBadge action={a as Decision['action']} /><span className="num text-muted">{n}</span></span>)}
            </div>
            <div className="max-h-[340px] overflow-auto">
              <Table dense head={['Symbol', 'Action', 'Score', 'P(up)', 'P(down)', 'Reason', 'At']}>
                {latest.slice(0, 50).map((d) => (
                  <tr key={d.decision_id}>
                    <td className="font-medium">{d.symbol}</td>
                    <td><ActionBadge action={d.action} /></td>
                    <td className={`num ${tone(d.score)}`}>{signed(d.score)}</td>
                    <td className="num">{pct(d.contributions.ml?.p_up)}</td>
                    <td className="num">{pct(d.contributions.ml?.p_down)}</td>
                    <td className="max-w-[420px] truncate text-muted" title={d.reasons.join(' · ')}>{d.reasons.at(-1)}</td>
                    <td className="text-dim">{dateTime(d.created_at)}</td>
                  </tr>
                ))}
              </Table>
            </div>
          </QueryState>
        </Panel>

        <Panel className="lg:col-span-12" title="Latest news · NSE · RBI · SEBI"
          right={<Link to="/news" className="text-[12.5px] text-muted hover:text-white">News ›</Link>}>
          <QueryState isPending={news.isPending} error={news.error} isEmpty={!newsRows.length}
            empty="No news ingested yet — use the News page to fetch the official feeds.">
            <Table dense head={['Time', 'Source', 'Symbols', 'Event', 'Sentiment', 'Headline']}>
              {newsRows.map((n) => (
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
    </div>
  )
}
