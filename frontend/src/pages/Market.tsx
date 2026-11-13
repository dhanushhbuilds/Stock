import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { CandleChart } from '@/components/CandleChart'
import { PageHeader } from '@/components/PageHeader'
import { Badge, Segmented, Panel, QueryState, Stat, Table } from '@/components/ui'
import { apiGet, type CandlesResponse, type Member } from '@/lib/api'
import { int, num, pct, tone } from '@/lib/format'
import { cn } from '@/lib/utils'

const TF = { '1day': { label: 'Daily', limit: 1500 }, '5minute': { label: '5 min', limit: 1500 } } as const
type Tf = keyof typeof TF

interface Quality {
  passed: boolean
  rows: number
  trading_days: number
  first_ts: string
  last_ts: string
  errors: Record<string, unknown>
  warnings: Record<string, unknown>
  info: Record<string, unknown>
}

export function Market() {
  const [symbol, setSymbol] = useState('RELIANCE')
  const [tf, setTf] = useState<Tf>('1day')
  const universe = useQuery({ queryKey: ['universe'], queryFn: () => apiGet<Member[]>('/data/universe') })
  const candles = useQuery({
    queryKey: ['candles', symbol, tf],
    queryFn: () => apiGet<CandlesResponse>(`/data/candles/${encodeURIComponent(symbol)}?timeframe=${tf}&limit=${TF[tf].limit}`),
  })
  const quality = useQuery({
    queryKey: ['quality', symbol, tf],
    queryFn: () => apiGet<Quality>(`/data/quality/${encodeURIComponent(symbol)}?timeframe=${tf === '5minute' ? '1minute' : tf}`),
    retry: false,
  })
  const member = universe.data?.find((m) => m.symbol === symbol)
  const cs = candles.data?.candles ?? []
  const last = cs.at(-1)
  const prev = cs.at(-2)
  const chg = last && prev ? last.close / prev.close - 1 : null

  return (
    <>
      <PageHeader title="Market Data">
        <Badge tone="warn">Historical · live feed not connected</Badge>
      </PageHeader>
      <div className="grid min-w-0 gap-5 lg:grid-cols-[240px_1fr]">
        <Panel title="NIFTY 50" className="max-h-[calc(100vh-120px)]">
          <QueryState isPending={universe.isPending} error={universe.error} isEmpty={!universe.data?.length}>
            <ul className="max-h-[calc(100vh-170px)] overflow-auto py-1" aria-label="Universe">
              {(universe.data ?? []).map((m) => (
                <li key={m.symbol}>
                  <button type="button" onClick={() => setSymbol(m.symbol)}
                    className={cn('flex w-full items-center justify-between px-3 py-1 text-left hover:bg-panel-2',
                      m.symbol === symbol ? 'bg-panel-2 text-fg' : 'text-muted')}>
                    <span className="font-medium">{m.symbol}</span>
                    <span className="truncate pl-2 text-[10px] text-dim">{m.industry.split(' ')[0]}</span>
                  </button>
                </li>
              ))}
            </ul>
          </QueryState>
        </Panel>
        <div className="flex min-w-0 flex-col gap-3">
          <Panel
            title={<span className="normal-case tracking-normal text-fg">{symbol} <span className="text-dim">{member?.company_name}</span></span>}
            right={
              <Segmented label="Timeframe" value={tf} onChange={setTf} options={(Object.keys(TF) as Tf[]).map((k) => [k, TF[k].label] as const)} />
            }>
            <div className="grid grid-cols-2 border-b border-line sm:grid-cols-5">
              <Stat label="Last close" value={num(last?.close)} sub={last ? new Date(last.ts).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : undefined} />
              <Stat label="Change" value={pct(chg, 2)} valueClass={tone(chg)} />
              <Stat label="High" value={num(last?.high)} />
              <Stat label="Low" value={num(last?.low)} />
              <Stat label="Bars shown" value={int(candles.data?.count)} sub={candles.data?.truncated ? 'most recent' : 'all'} />
            </div>
            <div className="h-[460px]">
              <QueryState isPending={candles.isPending} error={candles.error} isEmpty={!cs.length} empty="No candles stored for this symbol.">
                <CandleChart candles={cs} intraday={tf !== '1day'} />
              </QueryState>
            </div>
          </Panel>
          <Panel title={`Data quality (${tf === '5minute' ? '1-minute source' : 'daily'})`}>
            <QueryState isPending={quality.isPending} error={quality.error}>
              {quality.data && (
                <div className="grid min-w-0 gap-5 md:grid-cols-[auto_1fr]">
                  <div className="flex flex-col items-start gap-1">
                    <Badge tone={quality.data.passed ? 'up' : 'down'}>{quality.data.passed ? 'Passed' : 'Failed'}</Badge>
                    <span className="num text-muted">{int(quality.data.rows)} rows · {int(quality.data.trading_days)} sessions</span>
                  </div>
                  <Table dense head={['Check', 'Level', 'Detail']}>
                    {(['errors', 'warnings', 'info'] as const).flatMap((lvl) =>
                      Object.entries(quality.data[lvl]).map(([k, v]) => (
                        <tr key={lvl + k}>
                          <td>{k.replaceAll('_', ' ')}</td>
                          <td><Badge tone={lvl === 'errors' ? 'down' : lvl === 'warnings' ? 'warn' : 'info'}>{lvl}</Badge></td>
                          <td className="num max-w-[560px] truncate text-muted" title={JSON.stringify(v)}>{JSON.stringify(v)}</td>
                        </tr>
                      )))}
                  </Table>
                </div>
              )}
            </QueryState>
          </Panel>
        </div>
      </div>
    </>
  )
}
