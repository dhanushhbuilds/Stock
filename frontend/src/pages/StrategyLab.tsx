import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { PageHeader } from '@/components/PageHeader'
import { Badge, Segmented, Note, Panel, QueryState, Table } from '@/components/ui'
import { apiGet, type Perf, type StrategyResult } from '@/lib/api'
import { num, pct, tone } from '@/lib/format'
import { cn } from '@/lib/utils'

type Report = Record<string, StrategyResult | Record<string, unknown>> & {
  _benchmark_equal_weight_buy_hold?: { in_sample: Perf; out_of_sample: Perf; equity_curve_weekly?: [string, number][] }
  _benchmark_nifty50_index?: { in_sample: Perf; out_of_sample: Perf }
  _meta?: { capital: number; symbols: number; run_date: string; notes: string[]; round_trip_cost_pct_on_20k_delivery: number }
}
const COLORS = ['#5b9bd5', '#26a269', '#d9a23a', '#c678dd', '#56b6c2', '#e0524a']

export function StrategyLab() {
  const [period, setPeriod] = useState<'out_of_sample' | 'in_sample'>('out_of_sample')
  const rep = useQuery({ queryKey: ['strategy-report'], queryFn: () => apiGet<Report>('/strategies/report') })
  const strategies = useMemo(() => Object.entries(rep.data ?? {})
    .filter(([k, v]) => !k.startsWith('_') && typeof v === 'object' && v !== null && 'timeframe' in v)
    .map(([k, v]) => [k, v as StrategyResult] as const)
    .sort((a, b) => (b[1][period]?.sharpe ?? -99) - (a[1][period]?.sharpe ?? -99)), [rep.data, period])
  const [shown, setShown] = useState<string[] | null>(null)
  const visible = shown ?? strategies.filter(([, v]) => v.timeframe === '1day').slice(0, 4).map(([k]) => k)
  const [regimeOf, setRegimeOf] = useState<string | null>(null)
  const regimeKey = regimeOf ?? strategies[0]?.[0]

  const curve = useMemo(() => {
    const byDate = new Map<string, Record<string, number | string>>()
    const add = (name: string, pts?: [string, number][]) =>
      (pts ?? []).forEach(([d, v]) => byDate.set(d, { ...(byDate.get(d) ?? { date: d }), [name]: v }))
    visible.forEach((k) => add(k, (rep.data?.[k] as StrategyResult | undefined)?.equity_curve_weekly))
    add('buy & hold', rep.data?._benchmark_equal_weight_buy_hold?.equity_curve_weekly)
    return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)))
  }, [rep.data, visible])

  const bench = rep.data?._benchmark_equal_weight_buy_hold?.[period]
  const nifty = rep.data?._benchmark_nifty50_index?.[period]
  const meta = rep.data?._meta

  return (
    <>
      <PageHeader title="Strategy Lab">
        <Segmented label="Period" value={period} onChange={setPeriod} options={[['out_of_sample', 'Out of sample 2020→'], ['in_sample', 'In sample 2017–2019']] as const} />
      </PageHeader>
      <div className="flex flex-col gap-3 p-3">
        <QueryState isPending={rep.isPending} error={rep.error} isEmpty={!strategies.length}
          empty="No backtest report yet (python -m app.engines.strategy.runner).">
          <Panel title="Backtest results (after full NSE/Upstox charges + slippage)">
            <Table head={['', 'Strategy', 'TF', 'Total', 'Ann.', 'Sharpe', 'Sortino', 'Max DD', 'Profit factor', 'Trades', 'Avg net/trade', 'Costs ÷ gross profit']}>
              {strategies.map(([k, v]) => {
                const s = v[period]
                return (
                  <tr key={k} className={cn(regimeKey === k && 'bg-panel-2')}>
                    <td>
                      <input type="checkbox" aria-label={`plot ${k}`} disabled={!v.equity_curve_weekly}
                        checked={visible.includes(k)}
                        onChange={(e) => setShown(e.target.checked ? [...visible, k] : visible.filter((x) => x !== k))} />
                    </td>
                    <td><button type="button" className="text-left hover:text-info" onClick={() => setRegimeOf(k)}
                      title={v.description}>{k.replaceAll('_', ' ')}</button></td>
                    <td><Badge tone={v.timeframe === '1day' ? 'info' : 'warn'}>{v.timeframe === '1day' ? 'daily' : 'intraday'}</Badge></td>
                    <td className={`num ${tone(s?.total_return)}`}>{pct(s?.total_return)}</td>
                    <td className="num">{pct(s?.annualized_return)}</td>
                    <td className="num">{num(s?.sharpe)}</td>
                    <td className="num">{num(s?.sortino)}</td>
                    <td className="num text-down">{pct(s?.max_drawdown)}</td>
                    <td className="num">{num(s?.profit_factor)}</td>
                    <td className="num">{s?.trades?.toLocaleString('en-IN')}</td>
                    <td className={`num ${tone(s?.avg_trade_net_pct)}`}>{pct(s?.avg_trade_net_pct, 2)}</td>
                    <td className={cn('num', (s?.costs_pct_of_gross_profit ?? 0) > 0.5 && 'text-down')}>{num(s?.costs_pct_of_gross_profit)}</td>
                  </tr>
                )
              })}
              {[['equal-weight buy & hold', bench], ['NIFTY 50 index', nifty]].map(([name, b]) => b && (
                <tr key={name as string} className="text-muted">
                  <td /><td className="italic">{name as string}</td><td>benchmark</td>
                  <td className="num">{pct((b as Perf).total_return)}</td><td className="num">{pct((b as Perf).annualized_return)}</td>
                  <td className="num">{num((b as Perf).sharpe)}</td><td className="num">{num((b as Perf).sortino)}</td>
                  <td className="num">{pct((b as Perf).max_drawdown)}</td><td className="num">{num((b as Perf).profit_factor)}</td>
                  <td>—</td><td>—</td><td>—</td>
                </tr>
              ))}
            </Table>
          </Panel>

          <div className="grid gap-3 xl:grid-cols-[3fr_2fr]">
            <Panel title="Growth of ₹1 (weekly, from 2017) — tick strategies in the table to compare">
              <div className="h-[340px] p-2">
                <ResponsiveContainer>
                  <LineChart data={curve} margin={{ left: 8, right: 8 }}>
                    <CartesianGrid stroke="var(--color-line)" vertical={false} />
                    <XAxis dataKey="date" minTickGap={60} tick={{ fill: 'var(--color-muted)', fontSize: 10 }} />
                    <YAxis tick={{ fill: 'var(--color-muted)', fontSize: 10 }} width={40} />
                    <Tooltip contentStyle={{ background: 'var(--color-panel-2)', border: '1px solid var(--color-line)', fontSize: 11 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    {visible.map((k, i) => <Line key={k} dataKey={k} dot={false} strokeWidth={1.5} stroke={COLORS[i % COLORS.length]} />)}
                    <Line dataKey="buy & hold" dot={false} strokeWidth={1.5} strokeDasharray="4 3" stroke="var(--color-muted)" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title={`Out-of-sample trades by regime at entry — ${regimeKey?.replaceAll('_', ' ') ?? ''}`}>
              <Table dense head={['Trend / VIX', 'Trades', 'Win rate', 'Avg net return']}>
                {Object.entries((rep.data?.[regimeKey ?? ''] as StrategyResult | undefined)?.regimes_oos ?? {}).map(([r, g]) => (
                  <tr key={r}>
                    <td>{r.replace('_vol', '').replace('/', ' / ')}</td>
                    <td className="num">{g.trades.toLocaleString('en-IN')}</td>
                    <td className="num">{pct(g.win_rate)}</td>
                    <td className={`num ${tone(g.avg_net_return_pct)}`}>{g.avg_net_return_pct.toFixed(2)}%</td>
                  </tr>
                ))}
              </Table>
            </Panel>
          </div>
          {meta && (
            <Note>
              {meta.symbols} current NIFTY 50 stocks, ₹{meta.capital.toLocaleString('en-IN')} equal capital, long-only, signals at the close executed
              at the next open, 2×ATR stop on every trade. {meta.notes.join(' ')}
            </Note>
          )}
        </QueryState>
      </div>
    </>
  )
}
