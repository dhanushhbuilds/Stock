import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, Download, FileUp, Sparkles, X } from 'lucide-react'
import { type DragEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { CandleChart } from '@/components/CandleChart'
import { PageHeader } from '@/components/PageHeader'
import { Badge, Button, Note, Panel, Segmented, Spinner, Table } from '@/components/ui'
import { ApiError, apiGet, type Member, type Perf } from '@/lib/api'
import { int, num, pct } from '@/lib/format'
import { cn } from '@/lib/utils'

type Action = 'BUY' | 'SELL' | 'HOLD' | 'NO_TRADE'
interface Check { name: string; passed: boolean; value: unknown; limit: unknown; detail: string | null }
interface Day {
  date: string; open: number; high: number; low: number; close: number; volume: number; action: Action; position: number
  executed: string | null; p_up: number | null; p_neutral: number | null; p_down: number | null; score: number | null
  vol_pred_annual: number | null; vol_pct: number | null; uptrend: boolean; sma50: number | null; sma200: number | null
  atr14: number | null; stop: number | null; reasons: string[]
  risk: { approved: boolean; quantity: number; stop: number | null; target: number | null; checks: Check[]; reasons: string[] } | null
}
interface Trade { entry_date: string; exit_date: string | null; entry: number; exit: number; qty: number; net: number; return_pct: number; reason: string; costs: number }
interface SymbolResult {
  symbol: string; rows: number; first_date: string; last_date: string; notes: string[]; error?: string
  quality: { passed?: boolean; warnings?: Record<string, unknown>; errors?: Record<string, unknown> }
  final: Day & { next_session: string }; days: Day[]; trades: Trade[]; equity: [string, number, number][]
  metrics: { strategy: Perf; buy_and_hold: Perf; closed_trades: number; win_rate_trades: number | null; exposure: number | null; period: [string, string] }
}
interface LabResult {
  source: string; capital: number
  models: { direction: { name: string; status: string; trained_through: string }; volatility: { name: string; version: string; holdout_r2: number | null } }
  results: SymbolResult[]
}

const ACTION_STYLE: Record<Action, { label: string; color: string; glow: string; tone: 'up' | 'down' | 'info' | 'muted' }> = {
  BUY: { label: 'BUY', color: 'text-up', glow: 'shadow-[0_0_90px_-20px_rgba(111,213,154,0.45)]', tone: 'up' },
  SELL: { label: 'SELL', color: 'text-down', glow: 'shadow-[0_0_90px_-20px_rgba(255,122,107,0.45)]', tone: 'down' },
  HOLD: { label: 'HOLD', color: 'chrome-text', glow: 'shadow-[0_0_90px_-20px_rgba(255,255,255,0.35)]', tone: 'info' },
  NO_TRADE: { label: 'NO TRADE', color: 'chrome-text', glow: '', tone: 'muted' },
}
const STEPS = ['Validating the dataset', 'Engineering 77 features', 'Running the AI models', 'Risk-evaluating every signal']

async function postUpload(file: File, capital: number): Promise<LabResult> {
  const body = new FormData()
  body.append('file', file)
  body.append('capital', String(capital))
  const res = await fetch('/api/v1/signal-lab/analyze', { method: 'POST', body }).catch(() => {
    throw new ApiError(0, null, 'Backend unreachable')
  })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data, typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`)
  return data as LabResult
}

async function postSymbol(symbol: string, capital: number): Promise<LabResult> {
  const res = await fetch(`/api/v1/signal-lab/analyze-symbol/${encodeURIComponent(symbol)}?capital=${capital}`, { method: 'POST' })
    .catch(() => { throw new ApiError(0, null, 'Backend unreachable') })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data, typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`)
  return data as LabResult
}

function fmtVal(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'number') return Math.abs(v) >= 1000 ? v.toLocaleString('en-IN', { maximumFractionDigits: 0 }) : String(+v.toPrecision(4))
  const s = String(v)
  return s.startsWith('UPLOAD|') ? s.slice(7) : s.length > 18 ? `${s.slice(0, 16)}…` : s
}

function downloadCsv(r: SymbolResult) {
  const head = ['date', 'close', 'action', 'position', 'p_up', 'p_neutral', 'p_down', 'score', 'vol_forecast_annual', 'uptrend', 'stop', 'reasons']
  const rows = r.days.map((d) => [d.date, d.close, d.action, d.position, d.p_up, d.p_neutral, d.p_down, d.score, d.vol_pred_annual,
    d.uptrend, d.stop ?? '', `"${d.reasons.join(' | ').replaceAll('"', "'")}"`].join(','))
  const url = URL.createObjectURL(new Blob([[head.join(','), ...rows].join('\n')], { type: 'text/csv' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: `${r.symbol}_signals.csv` })
  a.click()
  URL.revokeObjectURL(url)
}

/** Mounted only while an analysis runs, so it always starts at step 0. */
function Progress() {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1100)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="glass fade-in rounded-[var(--radius-card)] p-6" role="status" aria-label="Analysis progress">
      <ol className="grid gap-3 sm:grid-cols-4">
        {STEPS.map((s, i) => (
          <li key={s} className="flex items-center gap-2.5 text-[13px]">
            <span className={cn('grid size-6 place-items-center rounded-full ring-1 ring-inset', i < step ? 'bg-up/20 text-up ring-up/30' : i === step ? 'ring-white/30' : 'ring-white/10 text-dim')}>
              {i < step ? <Check className="size-3.5" /> : i === step ? <Spinner className="size-3" /> : i + 1}
            </span>
            <span className={i <= step ? 'text-fg' : 'text-dim'}>{s}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function ProbBar({ up, neutral, down }: { up: number; neutral: number; down: number }) {
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div className="bg-down/80" style={{ width: `${down * 100}%` }} />
        <div className="bg-white/25" style={{ width: `${neutral * 100}%` }} />
        <div className="bg-up/85" style={{ width: `${up * 100}%` }} />
      </div>
      <div className="num mt-2 flex justify-between text-[11.5px]">
        <span className="text-down">Down {pct(down, 0)}</span><span className="text-muted">Neutral {pct(neutral, 0)}</span><span className="text-up">Up {pct(up, 0)}</span>
      </div>
    </div>
  )
}

function Gauge({ value }: { value: number }) {
  return (
    <div className="relative h-2.5 rounded-full bg-gradient-to-r from-up/70 via-warn/70 to-down/80">
      <span className="absolute -top-1 size-[18px] -translate-x-1/2 rounded-full bg-white shadow-[0_2px_10px_rgba(0,0,0,0.6)] ring-2 ring-black/30"
        style={{ left: `${Math.max(2, Math.min(98, value * 100))}%` }} />
    </div>
  )
}

const VERDICT_DOT: Record<Action, string> = { BUY: 'bg-up', SELL: 'bg-down', HOLD: 'bg-ink', NO_TRADE: 'bg-[#86868b]' }

function Verdict({ r }: { r: SymbolResult }) {
  const f = r.final
  const st = ACTION_STYLE[f.action]
  const rv = f.risk
  const riskAmt = rv?.approved && rv.stop != null ? rv.quantity * (f.close - rv.stop) : null
  const cells: [string, string][] = [
    ['Last close', `₹${num(f.close)}`],
    ['Quantity', rv?.approved ? int(rv.quantity) : f.action === 'HOLD' ? int(f.position) : '—'],
    ['Stop-loss', rv?.approved ? `₹${num(rv.stop)}` : f.stop ? `₹${num(f.stop)}` : '—'],
    ['Target (2R)', rv?.approved ? `₹${num(rv.target)}` : '—'],
    ['Capital at risk', riskAmt != null ? `₹${int(riskAmt)}` : '—'],
    ['Model score', f.score != null ? `${f.score >= 0 ? '+' : ''}${f.score.toFixed(2)}` : '—'],
  ]
  return (
    <section className="tile-light fade-in grid gap-8 rounded-[32px] p-8 md:p-10 lg:grid-cols-[1.15fr_1fr]" aria-label="Final signal">
      <div>
        <div className="flex items-center gap-2 text-[14px] text-[#6e6e73]">
          <span className={cn('size-2.5 rounded-full', VERDICT_DOT[f.action])} />
          <span className="font-semibold text-ink">{r.symbol}</span> · for the session after {f.date}
        </div>
        <div className="headline mt-4 text-[88px] text-ink md:text-[112px]" data-testid="verdict">{st.label}</div>
        <p className="mt-5 max-w-[42ch] text-[19px] font-medium leading-snug text-ink">{f.next_session}</p>
        <ul className="mt-4 space-y-1.5 text-[14px] text-[#424245]">
          {f.reasons.map((x) => <li key={x} className="flex gap-2.5"><span className="mt-[8px] size-1 shrink-0 rounded-full bg-[#86868b]" />{x}</li>)}
        </ul>
      </div>
      <div className="grid grid-cols-2 gap-2.5 self-center">
        {cells.map(([k, v]) => (
          <div key={k} className="rounded-[20px] bg-[#f0f0f3] px-5 py-4">
            <div className="text-[12px] font-medium text-[#6e6e73]">{k}</div>
            <div className="num headline mt-1 text-[26px] text-ink">{v}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

function Drivers({ r }: { r: SymbolResult }) {
  const f = r.final
  const dist = f.sma200 ? f.close / f.sma200 - 1 : null
  return (
    <div className="grid gap-5 md:grid-cols-3">
      <Panel title="Trend" right={<Badge tone={f.uptrend ? 'up' : 'muted'}>{f.uptrend ? 'Uptrend' : 'No uptrend'}</Badge>} padded>
        <div className="num headline text-[40px]">{pct(dist, 1)}</div>
        <div className="text-[12px] text-muted">vs 200-day average (₹{num(f.sma200)}). 50-day ₹{num(f.sma50)}.</div>
      </Panel>
      <Panel title="AI direction model" right={<Badge tone="warn">research</Badge>} padded>
        {f.p_up != null ? <ProbBar up={f.p_up} neutral={f.p_neutral ?? 0} down={f.p_down ?? 0} /> : <span className="text-muted">—</span>}
        <div className="mt-3 text-[11.5px] text-dim">Next 5 sessions vs the market. Used to confirm, never alone.</div>
      </Panel>
      <Panel title="AI volatility forecast" right={<Badge tone="up">promoted</Badge>} padded>
        <div className="num headline text-[40px]">{pct(f.vol_pred_annual, 1)}</div>
        <div className="mb-3 text-[12px] text-muted">annualised, next 5 sessions · {pct(f.vol_pct, 0)} percentile of its own history</div>
        {f.vol_pct != null && <Gauge value={f.vol_pct} />}
      </Panel>
    </div>
  )
}

function RiskPanel({ r }: { r: SymbolResult }) {
  const last = [...r.days].reverse().find((d) => d.risk)
  const isFinal = last?.date === r.final.date
  return (
    <Panel title="Risk evaluation" right={last?.risk && <Badge tone={last.risk.approved ? 'up' : 'down'}>{last.risk.approved ? 'approved' : 'rejected'}</Badge>}>
      {!last?.risk ? (
        <div className="px-5 pb-5 text-muted">No trade was proposed in this dataset, so the risk engine was not invoked.</div>
      ) : (
        <>
          <p className="px-5 pb-2 text-[12px] text-muted">
            {isFinal ? 'Checks for today’s proposed trade.' : `No trade proposed today. Showing the most recent evaluation (${last.date}).`}
          </p>
          <div className="max-h-[300px] overflow-auto">
            <Table dense head={['Check', 'Result', 'Value', 'Limit']}>
              {last.risk.checks.map((c) => (
                <tr key={c.name}>
                  <td className="text-fg/90">{c.name.replaceAll('_', ' ')}</td>
                  <td><Badge tone={c.passed ? 'up' : 'down'}>{c.passed ? 'pass' : 'fail'}</Badge></td>
                  <td className="num text-muted">{fmtVal(c.value)}</td>
                  <td className="num text-dim">{fmtVal(c.limit)}</td>
                </tr>
              ))}
            </Table>
          </div>
        </>
      )}
    </Panel>
  )
}

function Backtest({ r }: { r: SymbolResult }) {
  const s = r.metrics.strategy
  const b = r.metrics.buy_and_hold
  const data = useMemo(() => r.equity.filter((_, i) => i % 2 === 0 || i === r.equity.length - 1)
    .map(([date, strat, bh]) => ({ date, strategy: strat, hold: bh })), [r.equity])
  const rows: [string, string, string][] = [
    ['Total return', pct(s.total_return), pct(b.total_return)],
    ['Sharpe', num(s.sharpe), num(b.sharpe)],
    ['Max drawdown', pct(s.max_drawdown), pct(b.max_drawdown)],
    ['Annualised', pct(s.annualized_return), pct(b.annualized_return)],
  ]
  return (
    <Panel title={`Backtest of these signals · ${r.metrics.period?.[0]} → ${r.metrics.period?.[1]}`}>
      <div className="grid gap-4 px-5 pb-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="h-[260px]">
          <ResponsiveContainer>
            <AreaChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="gS" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ffffff" stopOpacity={0.28} /><stop offset="100%" stopColor="#ffffff" stopOpacity={0} /></linearGradient>
                <linearGradient id="gH" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8e8e93" stopOpacity={0.10} /><stop offset="100%" stopColor="#8e8e93" stopOpacity={0} /></linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis dataKey="date" minTickGap={70} tick={{ fill: 'rgba(235,235,245,0.45)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'rgba(235,235,245,0.45)', fontSize: 10 }} width={36} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: 'rgba(28,28,30,0.85)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, fontSize: 12, backdropFilter: 'blur(20px)' }}
                formatter={(v, n) => [`₹${Number(v).toFixed(3)} per ₹1`, n === 'strategy' ? 'AstraQuant signals' : 'Buy & hold']} />
              <Area dataKey="hold" stroke="rgba(142,142,147,0.8)" strokeDasharray="4 4" fill="url(#gH)" strokeWidth={1.5} isAnimationActive={false} />
              <Area dataKey="strategy" stroke="#ffffff" fill="url(#gS)" strokeWidth={2} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div>
          <table className="num w-full text-[13px]">
            <thead className="text-[11px] text-dim"><tr><th className="py-1.5 text-left font-medium" /><th className="text-right font-medium">Signals</th><th className="text-right font-medium">Buy &amp; hold</th></tr></thead>
            <tbody>
              {rows.map(([k, a, c]) => <tr key={k} className="border-t border-white/[0.06]"><td className="py-2 text-muted">{k}</td><td className="text-right font-semibold">{a}</td><td className="text-right text-muted">{c}</td></tr>)}
              <tr className="border-t border-white/[0.06]"><td className="py-2 text-muted">Trades / win rate</td><td className="text-right font-semibold">{r.metrics.closed_trades} · {pct(r.metrics.win_rate_trades, 0)}</td><td className="text-right text-muted">—</td></tr>
              <tr className="border-t border-white/[0.06]"><td className="py-2 text-muted">Time invested</td><td className="text-right font-semibold">{pct(r.metrics.exposure, 0)}</td><td className="text-right text-muted">100%</td></tr>
            </tbody>
          </table>
          <p className="mt-3 text-[11.5px] leading-relaxed text-dim">Fills at the next open; full NSE delivery charges and slippage on every trade.</p>
        </div>
      </div>
    </Panel>
  )
}

function Results({ data }: { data: LabResult }) {
  const [sym, setSym] = useState(data.results[0]?.symbol)
  const [mode, setMode] = useState<'area' | 'candles'>('area')
  const r = data.results.find((x) => x.symbol === sym) ?? data.results[0]
  const candles = useMemo(() => (r?.days ?? []).map((d) => ({ ts: `${d.date}T00:00:00+05:30`, open: d.open, high: d.high, low: d.low, close: d.close, volume: d.volume })), [r])
  const markers = useMemo(() => (r?.days ?? []).filter((d) => d.action === 'BUY' || d.action === 'SELL').map((d) => ({ ts: `${d.date}T00:00:00+05:30`, side: d.action as 'BUY' | 'SELL' })), [r])
  const lines = useMemo(() => [{ name: 'SMA200', color: 'rgba(255,255,255,0.45)', points: (r?.days ?? []).map((d) => ({ ts: `${d.date}T00:00:00+05:30`, value: d.sma200 })) }], [r])
  if (!r) return null
  if (r.error) return <Note>{r.symbol}: {r.error}</Note>
  const recent = [...r.days].reverse().slice(0, 30)
  return (
    <div className="flex flex-col gap-5">
      {data.results.length > 1 && <Segmented label="Symbol" value={r.symbol} onChange={setSym} options={data.results.map((x) => [x.symbol, x.symbol] as const)} />}
      <Verdict r={r} />
      <Drivers r={r} />
      <div className="grid gap-5 xl:grid-cols-[1.7fr_1fr]">
        <Panel tone="raised" title={`${r.symbol} · price and signals`} right={<Segmented label="Chart type" value={mode} onChange={setMode} options={[['area', 'Line'], ['candles', 'Candles']] as const} />}>
          <div className="flex items-center gap-4 px-6 text-[12px] text-dim"><span>▲ white = BUY</span><span>▼ grey = SELL</span><span>- - 200-day average</span></div>
          <div className="h-[440px] px-2 pb-3"><CandleChart candles={candles} intraday={false} markers={markers} lines={lines} mode={mode} height={430} /></div>
        </Panel>
        <RiskPanel r={r} />
      </div>
      <Backtest r={r} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Recent signals" right={<Button onClick={() => downloadCsv(r)}><Download className="size-3.5" />Download all signals</Button>}>
          <div className="max-h-[380px] overflow-auto">
            <Table dense head={['Date', 'Close', 'Signal', 'P(up)', 'Vol fcst', 'Why']}>
              {recent.map((d) => (
                <tr key={d.date}>
                  <td className="num text-muted">{d.date}</td>
                  <td className="num">₹{num(d.close)}</td>
                  <td><Badge tone={ACTION_STYLE[d.action].tone}>{ACTION_STYLE[d.action].label}</Badge></td>
                  <td className="num">{pct(d.p_up, 0)}</td>
                  <td className="num">{pct(d.vol_pred_annual, 0)}</td>
                  <td className="max-w-[300px] truncate text-muted" title={d.reasons.join(' ')}>{d.reasons[0]}</td>
                </tr>
              ))}
            </Table>
          </div>
        </Panel>
        <Panel title={`Trades (${r.trades.length})`}>
          <div className="max-h-[380px] overflow-auto">
            <Table dense head={['Entry', 'Exit', 'Qty', 'Return', 'Net ₹', 'Exit reason']}>
              {[...r.trades].reverse().map((t) => (
                <tr key={t.entry_date}>
                  <td className="num text-muted">{t.entry_date}</td>
                  <td className="num text-muted">{t.exit_date ?? 'open'}</td>
                  <td className="num">{int(t.qty)}</td>
                  <td className={cn('num', t.return_pct >= 0 ? 'text-up' : 'text-down')}>{t.return_pct.toFixed(1)}%</td>
                  <td className={cn('num', t.net >= 0 ? 'text-up' : 'text-down')}>{int(t.net)}</td>
                  <td className="text-muted">{t.reason}</td>
                </tr>
              ))}
            </Table>
          </div>
        </Panel>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Dataset" right={<Badge tone={r.quality.passed === false ? 'warn' : 'up'}>{r.quality.passed === false ? 'quality warnings' : 'quality passed'}</Badge>} padded>
          <div className="num text-[13px] text-muted">{int(r.rows)} daily rows · {r.first_date} → {r.last_date}</div>
          <ul className="mt-2 space-y-1 text-[12px] text-dim">{r.notes.map((n) => <li key={n}>• {n}</li>)}</ul>
        </Panel>
        <Panel title="Models used" padded>
          <div className="space-y-2 text-[12.5px]">
            <div className="flex items-center gap-2"><Badge tone="up">promoted</Badge><span>Volatility: {data.models.volatility.name} · holdout R² {num(data.models.volatility.holdout_r2, 3)}</span></div>
            <div className="flex items-center gap-2"><Badge tone="warn">research</Badge><span>Direction: {data.models.direction.name} · trained through {data.models.direction.trained_through}</span></div>
            <p className="text-[11.5px] leading-relaxed text-dim">The direction model did not pass the strict promotion gate, so it can only confirm or veto a trend signal. Every BUY is sized and checked by the independent risk engine.</p>
          </div>
        </Panel>
      </div>
    </div>
  )
}

export function SignalLab() {
  const [file, setFile] = useState<File | null>(null)
  const [capital, setCapital] = useState('1000000')
  const [stored, setStored] = useState('RELIANCE')
  const [drag, setDrag] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const universe = useQuery({ queryKey: ['universe'], queryFn: () => apiGet<Member[]>('/data/universe') })
  const run = useMutation({
    mutationFn: (v: { kind: 'file'; file: File } | { kind: 'symbol'; symbol: string }) =>
      v.kind === 'file' ? postUpload(v.file, Number(capital)) : postSymbol(v.symbol, Number(capital)),
  })
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDrag(false)
    const f = e.dataTransfer.files?.[0]
    if (f) setFile(f)
  }
  const cap = Number(capital)
  const capOk = Number.isFinite(cap) && cap >= 10000

  return (
    <div className="flex flex-col gap-5">
      <PageHeader eyebrow="Signal Lab" title="Any stock. One clear answer." subtitle="Upload any daily price file, or pick a NIFTY 50 stock. The models forecast, the rules propose, the risk engine decides — with every reason shown." />
      <section className="tile-raised fade-in grid gap-6 rounded-[32px] p-7 lg:grid-cols-[1.4fr_1fr]">
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
          className={cn('flex min-h-[200px] flex-col items-center justify-center rounded-[22px] border border-dashed p-6 text-center transition-colors',
            drag ? 'border-white/60 bg-white/[0.08]' : 'border-white/[0.16] bg-white/[0.025]')}>
          <div className="grid size-12 place-items-center rounded-2xl bg-white/[0.07] ring-1 ring-inset ring-white/10"><FileUp className="size-5 text-fg/80" /></div>
          {file ? (
            <div className="mt-3 flex items-center gap-2 text-[14px]"><span className="font-medium">{file.name}</span>
              <span className="text-dim">{(file.size / 1024).toFixed(0)} KB</span>
              <button type="button" aria-label="Remove file" onClick={() => setFile(null)} className="rounded-full p-1 text-dim hover:bg-white/10 hover:text-fg"><X className="size-3.5" /></button>
            </div>
          ) : (
            <p className="mt-3 text-[14px] text-fg/90">Drop a CSV here, or <button type="button" className="text-fg underline decoration-white/30 underline-offset-4 hover:decoration-white" onClick={() => input.current?.click()}>browse</button></p>
          )}
          <p className="mt-1.5 text-[12px] text-dim">Date, Open, High, Low, Close, Volume · Yahoo / NSE / broker exports · optional Symbol column · ≥ 260 days</p>
          <input ref={input} type="file" accept=".csv,text/csv" className="hidden" aria-label="Choose dataset file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <div className="mt-5 flex items-center gap-2">
            <Button variant="primary" size="lg" disabled={!file || !capOk || run.isPending} onClick={() => file && run.mutate({ kind: 'file', file })}>
              <Sparkles className="size-4" />Analyze dataset
            </Button>
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] text-muted">Capital allocated to this stock (₹)</span>
            <input inputMode="numeric" value={capital} onChange={(e) => setCapital(e.target.value.replace(/[^0-9]/g, ''))}
              aria-label="Capital"
              className={cn('num h-11 rounded-2xl bg-white/[0.06] px-4 text-[17px] font-semibold tracking-tight ring-1 ring-inset outline-none focus:ring-white/40', capOk ? 'ring-white/10' : 'ring-down/50')} />
            {!capOk && <span className="text-[11.5px] text-down">Minimum ₹10,000</span>}
          </label>
          <div className="h-px bg-white/[0.07]" />
          <div className="flex flex-col gap-1.5">
            <span className="text-[12px] text-muted">No file? Analyze a stored NIFTY 50 stock</span>
            <div className="flex gap-2">
              <select aria-label="Stored stock" value={stored} onChange={(e) => setStored(e.target.value)}
                className="h-9 flex-1 rounded-full bg-white/[0.06] px-3.5 text-[13px] ring-1 ring-inset ring-white/10 outline-none">
                {(universe.data ?? [{ symbol: 'RELIANCE' } as Member]).map((m) => <option key={m.symbol} value={m.symbol}>{m.symbol}</option>)}
              </select>
              <Button disabled={!capOk || run.isPending} onClick={() => run.mutate({ kind: 'symbol', symbol: stored })}>Analyze</Button>
            </div>
            <a href={`/api/v1/signal-lab/sample/${stored}.csv`} className="mt-1 inline-flex items-center gap-1.5 text-[12px] text-fg underline decoration-white/30 underline-offset-4 hover:decoration-white">
              <Download className="size-3.5" />Download {stored} as a sample CSV to try the upload
            </a>
          </div>
        </div>
      </section>
      {run.isPending && <Progress />}
      {run.error && <div role="alert" className="rounded-2xl bg-down/10 px-5 py-3.5 text-[13px] text-down ring-1 ring-inset ring-down/25">{run.error.message}</div>}
      {run.data && <Results data={run.data} />}
      {!run.data && !run.isPending && (
        <Note>
          How it works: the dataset is validated, then the same 77 features used in training are computed (with NIFTY, VIX,
          sector and global context joined by date). The promoted volatility model and the research direction model score each
          day; the trend rule proposes trades; the independent risk engine sizes and approves or rejects every one. Decisions at
          each date only use data up to that date.
        </Note>
      )}
    </div>
  )
}
