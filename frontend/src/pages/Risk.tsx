import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import { PageHeader } from '@/components/PageHeader'
import { Badge, Button, Note, Panel, QueryState, Table } from '@/components/ui'
import { apiGet, apiPost, type CandlesResponse, type RiskState, type RiskVerdict } from '@/lib/api'
import { dateTime, num } from '@/lib/format'

interface Assessment {
  id: number
  intent_id: string
  instrument_key: string
  approved: boolean
  quantity: number
  reasons: string[]
  created_at: string
}

export function Risk() {
  const qc = useQueryClient()
  const state = useQuery({ queryKey: ['risk-state'], queryFn: () => apiGet<RiskState>('/risk/state') })
  const log = useQuery({ queryKey: ['risk-log'], queryFn: () => apiGet<Assessment[]>('/risk/assessments?limit=30') })
  const [reason, setReason] = useState('')
  const toggle = useMutation({
    mutationFn: (on: boolean) => apiPost('/risk/kill-switch', { on, reason: reason || (on ? 'manual halt' : 'manual resume') }),
    onSuccess: () => { setReason(''); qc.invalidateQueries({ queryKey: ['risk-state'] }) },
  })

  const [form, setForm] = useState({ symbol: 'RELIANCE', side: 'BUY', product: 'DELIVERY', confidence: '0.55', equity: '1000000', stop: '' })
  const check = useMutation({
    mutationFn: async () => {
      const c = await apiGet<CandlesResponse>(`/data/candles/${form.symbol}?timeframe=1day&limit=30`)
      const last = c.candles.at(-1)
      if (!last) throw new Error('no price data for this symbol')
      const tr = c.candles.slice(1).map((k, i) => Math.max(k.high - k.low, Math.abs(k.high - c.candles[i].close), Math.abs(k.low - c.candles[i].close)))
      const atr = tr.slice(-14).reduce((a, b) => a + b, 0) / Math.min(14, tr.length)
      const eq = Number(form.equity)
      const now = new Date().toISOString()
      return apiPost<RiskVerdict>('/risk/evaluate', {
        intent: { intent_id: `ui-${Date.now()}`, instrument_key: c.instrument_key, side: form.side, product: form.product,
          entry_price: last.close, stop_price: form.stop ? Number(form.stop) : null, confidence: Number(form.confidence), created_at: now },
        // Last completed daily close; delivery orders accept end-of-day data, intraday orders require a live tick.
        market: { instrument_key: c.instrument_key, last_price: last.close, atr, data_ts: last.ts },
        portfolio: { equity: eq, cash: eq, start_of_day_equity: eq, peak_equity: eq },
      })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risk-log'] }),
  })
  const submit = (e: FormEvent) => { e.preventDefault(); check.mutate() }
  const on = state.data?.kill_switch

  return (
    <>
      <PageHeader title="Risk Centre" />
      <div className="grid min-w-0 gap-5 xl:grid-cols-[1fr_2fr]">
        <div className="flex min-w-0 flex-col gap-3">
          <Panel title="Emergency kill switch">
            <QueryState isPending={state.isPending} error={state.error}>
              <div className="flex flex-col gap-2 p-3">
                <div className="flex items-center gap-2">
                  <Badge tone={on ? 'down' : 'up'}>{on ? 'ON — all new orders blocked' : 'OFF — trading allowed'}</Badge>
                  <span className="text-[11px] text-dim">{state.data?.reason} · {state.data?.changed_by} · {dateTime(state.data?.updated_at)}</span>
                </div>
                <input aria-label="Reason" placeholder="Reason (required for the audit trail)" value={reason}
                  onChange={(e) => setReason(e.target.value)} className="h-7 border border-line bg-bg px-2 text-fg placeholder:text-dim" />
                <Button variant={on ? 'primary' : 'danger'} disabled={toggle.isPending} onClick={() => toggle.mutate(!on)}>
                  {on ? 'Release kill switch' : 'Activate kill switch'}
                </Button>
                {toggle.error && <span role="alert" className="text-down">{toggle.error.message}</span>}
              </div>
            </QueryState>
          </Panel>
          <Panel title="Check an order">
            <form onSubmit={submit} className="grid grid-cols-2 gap-2 p-3 text-[12px]">
              {([['symbol', 'Symbol'], ['confidence', 'Confidence (0–1)'], ['equity', 'Equity (₹)'], ['stop', 'Stop (blank = 2×ATR)']] as const).map(([k, label]) => (
                <label key={k} className="flex flex-col gap-0.5 text-muted">{label}
                  <input value={form[k]} onChange={(e) => setForm({ ...form, [k]: k === 'symbol' ? e.target.value.toUpperCase() : e.target.value })}
                    className="h-7 border border-line bg-bg px-2 text-fg" />
                </label>
              ))}
              <label className="flex flex-col gap-0.5 text-muted">Side
                <select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })} className="h-7 border border-line bg-bg px-1 text-fg">
                  <option>BUY</option><option>SELL</option>
                </select>
              </label>
              <label className="flex flex-col gap-0.5 text-muted">Product
                <select value={form.product} onChange={(e) => setForm({ ...form, product: e.target.value })} className="h-7 border border-line bg-bg px-1 text-fg">
                  <option>DELIVERY</option><option>INTRADAY</option>
                </select>
              </label>
              <div className="col-span-2"><Button type="submit" variant="primary" disabled={check.isPending}>{check.isPending ? 'Checking…' : 'Run risk checks'}</Button></div>
              {check.error && <span role="alert" className="col-span-2 text-down">{check.error.message}</span>}
            </form>
          </Panel>
        </div>
        <div className="flex min-w-0 flex-col gap-3">
          <Panel title="Verdict" right={check.data && <Badge tone={check.data.approved ? 'up' : 'down'}>{check.data.approved ? 'Approved' : 'Rejected'}</Badge>}>
            {check.data ? (
              <>
                <div className="num flex gap-6 border-b border-line px-3 py-2">
                  <span>Qty <span className="text-fg">{check.data.quantity}</span></span>
                  <span>Stop <span className="text-down">{num(check.data.stop_price)}</span></span>
                  <span>Target <span className="text-up">{num(check.data.take_profit)}</span></span>
                </div>
                <Table dense head={['Check', 'Result', 'Value', 'Limit', 'Detail']}>
                  {check.data.checks.map((c) => (
                    <tr key={c.name}>
                      <td>{c.name.replaceAll('_', ' ')}</td>
                      <td><Badge tone={c.passed ? 'up' : 'down'}>{c.passed ? 'pass' : 'fail'}</Badge></td>
                      <td className="num">{c.value ?? '—'}</td>
                      <td className="num text-muted">{c.limit ?? '—'}</td>
                      <td className="max-w-[360px] truncate text-muted" title={c.detail ?? ''}>{c.detail ?? ''}</td>
                    </tr>
                  ))}
                </Table>
              </>
            ) : <div className="p-3 text-muted">Submit an order to see every risk check. Intraday orders on end-of-day data are rejected as stale — by design.</div>}
          </Panel>
          <Panel title="Recent risk decisions (audit)">
            <QueryState isPending={log.isPending} error={log.error} isEmpty={!log.data?.length} empty="No orders evaluated yet.">
              <div className="max-h-[320px] overflow-auto">
                <Table dense head={['Time', 'Instrument', 'Result', 'Qty', 'Reasons']}>
                  {(log.data ?? []).map((a) => (
                    <tr key={a.id}>
                      <td className="text-dim">{dateTime(a.created_at)}</td>
                      <td>{a.instrument_key}</td>
                      <td><Badge tone={a.approved ? 'up' : 'down'}>{a.approved ? 'approved' : 'rejected'}</Badge></td>
                      <td className="num">{a.quantity}</td>
                      <td className="max-w-[420px] truncate text-muted" title={a.reasons?.join(' · ')}>{a.reasons?.join(' · ')}</td>
                    </tr>
                  ))}
                </Table>
              </div>
            </QueryState>
          </Panel>
          <Note>No signal can reach an order without passing these checks. Every verdict is stored with its full check list.</Note>
        </div>
      </div>
    </>
  )
}
