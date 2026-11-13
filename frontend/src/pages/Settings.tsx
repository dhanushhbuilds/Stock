import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import { PageHeader } from '@/components/PageHeader'
import { Badge, Button, Note, Panel, QueryState } from '@/components/ui'
import { apiGet, apiPut, type RiskState } from '@/lib/api'

const LABELS: Record<string, string> = {
  risk_per_trade_pct: 'Capital at risk per trade (fraction)',
  atr_stop_multiple: 'Stop distance (× ATR)',
  take_profit_r: 'Take-profit (× risk)',
  trailing_atr_multiple: 'Trailing stop (× ATR)',
  max_single_stock_pct: 'Max single stock (fraction of equity)',
  max_gross_exposure_pct: 'Max gross exposure (fraction)',
  max_sector_pct: 'Max sector exposure (fraction)',
  max_concurrent_positions: 'Max open positions',
  daily_loss_limit_pct: 'Daily loss limit (fraction)',
  max_drawdown_pct: 'Max drawdown (fraction)',
  max_data_age_s: 'Max data age, intraday (s)',
  max_eod_data_age_s: 'Max data age, delivery (s)',
  min_confidence: 'Min model confidence',
  max_avg_correlation: 'Max avg correlation with holdings',
  var_confidence: 'VaR confidence',
  max_portfolio_var_pct: 'Max 1-day VaR (fraction of equity)',
}

export function Settings() {
  const qc = useQueryClient()
  const state = useQuery({ queryKey: ['risk-state'], queryFn: () => apiGet<RiskState>('/risk/state') })
  const [edits, setEdits] = useState<Record<string, string>>({})
  const server = Object.fromEntries(Object.entries(state.data?.limits ?? {}).map(([k, v]) => [k, String(v)]))
  const draft = { ...server, ...edits }
  const setDraft = (d: Record<string, string>) => setEdits(d)
  const save = useMutation({
    mutationFn: () => apiPut('/risk/limits', Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, Number(v)]))),
    onSuccess: () => { setEdits({}); qc.invalidateQueries({ queryKey: ['risk-state'] }) },
  })
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate() }

  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid min-w-0 gap-5 xl:grid-cols-[2fr_1fr]">
        <Panel title="Risk limits" right={save.isSuccess && <Badge tone="up">saved</Badge>}>
          <QueryState isPending={state.isPending} error={state.error}>
            <form onSubmit={submit} className="grid gap-2 p-3 sm:grid-cols-2">
              {Object.keys(draft).map((k) => (
                <label key={k} className="flex items-center justify-between gap-3 border-b border-line py-1 text-muted">
                  <span>{LABELS[k] ?? k}</span>
                  <input aria-label={LABELS[k] ?? k} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
                    className="num h-7 w-28 border border-line bg-bg px-2 text-right text-fg" />
                </label>
              ))}
              <div className="flex items-center gap-2 sm:col-span-2">
                <Button type="submit" variant="primary" disabled={save.isPending}>Save limits</Button>
                {save.error && <span role="alert" className="text-down">Rejected by server validation: {save.error.message}</span>}
              </div>
            </form>
          </QueryState>
        </Panel>
        <div className="flex min-w-0 flex-col gap-3">
          <Panel title="Execution">
            <div className="space-y-2 p-3 text-[12px] text-muted">
              <div className="flex items-center justify-between"><span>Live trading</span><Badge tone="up">disabled</Badge></div>
              <div className="flex items-center justify-between"><span>Paper trading</span><Badge tone="muted">postponed</Badge></div>
              <div className="flex items-center justify-between"><span>Upstox live feed</span><Badge tone="warn">not connected</Badge></div>
            </div>
          </Panel>
          <Note>Every change is validated by the server (e.g. risk per trade ≤ 5%) and written to the audit trail. Live trading cannot be enabled from configuration.</Note>
        </div>
      </div>
    </>
  )
}
