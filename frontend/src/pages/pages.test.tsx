import { QueryClient } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { App } from '@/App'

vi.mock('@/components/CandleChart', () => ({ CandleChart: ({ candles }: { candles: unknown[] }) => <div data-testid="chart">{candles.length} candles</div> }))

const READY = { status: 'ok', version: '0.1.0', env: 'test', live_trading_enabled: false, checks: {} }
const perf = (sharpe: number, total = 0.5) => ({ sharpe, total_return: total, annualized_return: 0.1, max_drawdown: -0.12, sortino: 1, profit_factor: 1.2, trades: 100, win_rate: 0.55 })
const metrics = (ll: number, auc: number) => ({
  n: 1000, accuracy: 0.46, macro_f1: 0.3, log_loss: ll, brier: 0.63, roc_auc_ovr_macro: 0.57, direction_auc: auc,
  ic_mean: 0.018, ic_t: 3.5, confusion_matrix: [[10, 20, 5], [8, 40, 9], [4, 22, 12]],
  baseline_prior: { log_loss: 1.066, accuracy: 0.47, brier: 0.64 },
  trading: { strategy: perf(0.8), benchmark_equal_weight: perf(1.2, 2.9) },
})

type Handler = (url: string, init?: RequestInit) => unknown
function mockApi(routes: Record<string, Handler | unknown>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const key = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => url.includes(k))
    if (!key) return new Response(JSON.stringify(READY), { status: 200 })
    const r = routes[key]
    const body = typeof r === 'function' ? (r as Handler)(url, init) : r
    if (body instanceof Response) return body
    return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
  })
}
const renderAt = (path: string) =>
  render(<App initialPath={path} queryClient={new QueryClient({ defaultOptions: { queries: { retry: false } } })} />)

describe('Overview', () => {
  it('shows regime, data lake, registry and an honest empty decisions state', async () => {
    mockApi({
      '/decisions/regime': { trend: 'bull', volatility: 'normal', nifty_close: 25299.35, nifty_ema200: 23969.8, india_vix: 16.62, vix_1y_percentile: 0.75, as_of: '2026-11-12' },
      '/data/coverage': [{ instrument_key: 'A', timeframe: '1day', files: 1, rows: 100, first_ts: '', last_ts: '', quality_passed: true }],
      '/ml/models': [{ version: 'v1', pipeline: 'swing', model: 'logreg', promoted: false, promotion_reasons: [], created_at: '' }],
      '/decisions?limit': [],
      '/news?limit': [],
      '/strategies/report': { ema_crossover: { timeframe: '1day', description: '', out_of_sample: perf(1.22) } },
    })
    renderAt('/')
    expect(await screen.findByText('BULL')).toBeInTheDocument()
    expect(screen.getByText('1/1')).toBeInTheDocument()
    expect(await screen.findByText(/none passed the gate/)).toBeInTheDocument()
    expect(screen.getByText(/the engine refuses to decide/)).toBeInTheDocument()
    expect(await screen.findByText('ema crossover')).toBeInTheDocument()
  })

  it('run decisions button posts and surfaces a server refusal', async () => {
    const spy = mockApi({
      '/decisions/run': () => new Response(JSON.stringify({ detail: 'no promoted swing model' }), { status: 409 }),
      '/decisions?limit': [], '/ml/models': [], '/data/coverage': [], '/news?limit': [], '/strategies/report': {},
      '/decisions/regime': { trend: 'bear', volatility: 'high', nifty_close: 1, nifty_ema200: 2, india_vix: 30, vix_1y_percentile: 0.9, as_of: 'x' },
    })
    renderAt('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Run swing decisions' }))
    expect(await screen.findByText('no promoted swing model')).toBeInTheDocument()
    expect(spy.mock.calls.some(([u, i]) => String(u).includes('/decisions/run') && i?.method === 'POST')).toBe(true)
  })
})

describe('AI Research', () => {
  it('renders the latest run, metrics vs no-skill, gate and fold wins', async () => {
    const fold = (i: number, ll: number) => ({ fold: { k: i, test_start: `202${i}-01-01`, test_end: '' }, metrics: { n: 10, log_loss: ll, accuracy: 0.4, direction_auc: 0.51 }, baseline: { log_loss: 1.06 }, best_iteration: null })
    mockApi({
      '/ml/runs': [{ run_id: 'R1', pipeline: 'swing', dataset_version: 'D1', created_at: '2026-11-13T09:00:00Z', models: ['logreg', 'xgboost'] }],
      '/ml/experiments/R1': [
        { model: 'logreg', dataset_version: 'D1', walk_forward: metrics(1.047, 0.514), holdout: metrics(1.05, 0.51), folds: [fold(0, 1.04), fold(1, 1.07)], train_seconds: 1 },
        { model: 'xgboost', dataset_version: 'D1', walk_forward: metrics(1.049, 0.503), holdout: metrics(1.06, 0.5), folds: [fold(0, 1.05), fold(1, 1.05)], train_seconds: 1 },
      ],
      '/ml/models': [{ version: 'swing-logreg-R1', pipeline: 'swing', model: 'logreg', promoted: true, promotion_reasons: ['PASS: walk-forward log loss < prior baseline', 'FAIL: something'], created_at: '' }],
    })
    renderAt('/research')
    expect(await screen.findByText('promoted: logreg')).toBeInTheDocument()
    expect(screen.getByText('FAIL: something')).toHaveClass('text-down')
    expect(await screen.findByText('+0.0190')).toBeInTheDocument()  // 1.066 - 1.047
    expect(screen.getAllByText(/beat no-skill in/).length).toBe(2)
    expect(screen.getAllByText('1/2').length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('tab', { name: 'Locked holdout' }))
    expect(screen.getAllByText('1.0500').length).toBeGreaterThan(0)
  })

  it('empty state when no run exists for the pipeline', async () => {
    mockApi({ '/ml/runs': [], '/ml/models': [] })
    renderAt('/research')
    await userEvent.click(await screen.findByRole('tab', { name: 'intraday' }))
    expect(await screen.findByText(/No intraday training run yet/)).toBeInTheDocument()
  })
})

describe('Strategy Lab', () => {
  it('lists strategies sorted by Sharpe with benchmarks and regime table', async () => {
    mockApi({ '/strategies/report': {
      file: 'x.json',
      vwap_trend: { timeframe: '5minute', description: '', out_of_sample: { ...perf(-20.9), costs_pct_of_gross_profit: 1.57 }, equity_curve_weekly: [['2020-01-03', 1]] },
      ema_crossover: { timeframe: '1day', description: '', out_of_sample: perf(1.22), equity_curve_weekly: [['2020-01-03', 1]], regimes_oos: { 'bull/low_vol': { trades: 161, win_rate: 0.39, avg_net_return_pct: 9.61 } } },
      _benchmark_equal_weight_buy_hold: { in_sample: perf(1.27), out_of_sample: perf(1.22, 2.95), equity_curve_weekly: [['2020-01-03', 1]] },
      _benchmark_nifty50_index: { in_sample: perf(1.1), out_of_sample: perf(0.7) },
      _meta: { capital: 5000000, symbols: 50, run_date: '2026-11-13', notes: ['Survivorship bias.'], round_trip_cost_pct_on_20k_delivery: 0.0068 },
    } })
    renderAt('/strategy')
    const rows = (await screen.findAllByRole('row')).map((r) => r.textContent ?? '')
    const iEma = rows.findIndex((t) => t.includes('ema crossover'))
    const iVwap = rows.findIndex((t) => t.includes('vwap trend'))
    expect(iEma).toBeGreaterThan(0)
    expect(iEma).toBeLessThan(iVwap)
    expect(screen.getByText('1.57')).toHaveClass('text-down')
    expect(screen.getByText('equal-weight buy & hold')).toBeInTheDocument()
    expect(screen.getByText('9.61%')).toBeInTheDocument()
    expect(screen.getByText(/Survivorship bias/)).toBeInTheDocument()
  })
})

describe('Risk Centre', () => {
  it('checks an order and shows each risk check', async () => {
    const spy = mockApi({
      '/risk/state': { kill_switch: false, reason: null, changed_by: 'system', updated_at: '2026-11-13T09:00:00Z', limits: {} },
      '/risk/assessments': [],
      '/data/candles/RELIANCE': { instrument_key: 'NSE_EQ|INE002A01018', trading_symbol: 'RELIANCE', timeframe: '1day', count: 3, truncated: false,
        candles: [1, 2, 3].map((i) => ({ ts: `2026-11-1${i}T00:00:00+05:30`, open: 1330, high: 1342, low: 1320, close: 1339.7, volume: 1 })) },
      '/risk/evaluate': { intent_id: 'x', approved: false, quantity: 0, stop_price: 1300, take_profit: 1400,
        checks: [{ name: 'kill_switch_off', passed: true, value: 'OFF', limit: 'OFF', detail: null },
          { name: 'market_data_fresh', passed: false, value: 999999, limit: 120, detail: 'stale or future-dated market data' }],
        reasons: ['market_data_fresh: stale'] },
    })
    renderAt('/risk')
    await userEvent.click(await screen.findByRole('button', { name: 'Run risk checks' }))
    expect(await screen.findByText('Rejected')).toBeInTheDocument()
    expect(screen.getByText('market data fresh')).toBeInTheDocument()
    const call = spy.mock.calls.find(([u]) => String(u).includes('/risk/evaluate'))!
    const body = JSON.parse(String(call[1]!.body))
    expect(body.intent.instrument_key).toBe('NSE_EQ|INE002A01018')
    expect(body.intent.entry_price).toBe(1339.7)
    expect(body.market.atr).toBeGreaterThan(0)
  })

  it('kill switch toggle posts with the typed reason', async () => {
    const spy = mockApi({
      '/risk/state': { kill_switch: false, reason: 'resume', changed_by: 'op', updated_at: '2026-11-13T09:00:00Z', limits: {} },
      '/risk/assessments': [], '/risk/kill-switch': { kill_switch: true, reason: 'demo halt' },
    })
    renderAt('/risk')
    await userEvent.type(await screen.findByLabelText('Reason'), 'demo halt')
    await userEvent.click(screen.getByRole('button', { name: 'Activate kill switch' }))
    await vi.waitFor(() => {
      const call = spy.mock.calls.find(([u]) => String(u).includes('/risk/kill-switch'))
      expect(JSON.parse(String(call![1]!.body))).toEqual({ on: true, reason: 'demo halt' })
    })
  })
})

describe('News', () => {
  it('ingests a source, reports stats, and hides routine items by default', async () => {
    mockApi({
      '/news/ingest/nse_announcements': { received: 10, inserted: 4, duplicates: 6, near_duplicates: 0, mapped_to_instrument: 2, sentiment_scored: 4 },
      '/news?': [
        { id: 1, source: 'nse_announcements', title: 'Reliance: Financial Results', url: 'u', published_at: null, usable_from: '2026-11-13T09:00:00Z', timestamp_status: 'ok', symbols: ['RELIANCE'], event_type: 'earnings', importance: 0.9, sentiment: 'positive', sentiment_score: 0.8 },
        { id: 2, source: 'nse_announcements', title: 'X: Declaration of NAV', url: 'u', published_at: null, usable_from: '2026-11-13T09:00:00Z', timestamp_status: 'ok', symbols: [], event_type: 'routine_disclosure', importance: 0.1, sentiment: 'neutral', sentiment_score: 0 },
      ],
    })
    renderAt('/news')
    expect(await screen.findByText('Reliance: Financial Results')).toBeInTheDocument()
    expect(screen.queryByText('X: Declaration of NAV')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByText('X: Declaration of NAV')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Fetch NSE announcements' }))
    expect(await screen.findByText(/4 new · 6 duplicates/)).toBeInTheDocument()
  })
})

describe('Market', () => {
  it('loads the universe and candles for the selected symbol and timeframe', async () => {
    const spy = mockApi({
      '/data/universe': [{ symbol: 'RELIANCE', company_name: 'Reliance', industry: 'Oil Gas', instrument_key: 'K1', sector_index_key: null, as_of: '' },
        { symbol: 'INFY', company_name: 'Infosys', industry: 'IT', instrument_key: 'K2', sector_index_key: null, as_of: '' }],
      '/data/candles/': (url: string) => ({ instrument_key: 'K', trading_symbol: 'X', timeframe: url.includes('5minute') ? '5minute' : '1day', count: 2, truncated: false,
        candles: [{ ts: '2026-11-11T00:00:00+05:30', open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 }, { ts: '2026-11-12T00:00:00+05:30', open: 1.5, high: 2, low: 1, close: 1.8, volume: 10 }] }),
      '/data/quality/': { passed: true, rows: 2, trading_days: 2, first_ts: '', last_ts: '', errors: {}, warnings: {}, info: {} },
    })
    renderAt('/market')
    expect(await screen.findByTestId('chart')).toHaveTextContent('2 candles')
    expect(screen.getByText('20.00%')).toBeInTheDocument()  // 1.5 -> 1.8
    await userEvent.click(within(screen.getByRole('list', { name: 'Universe' })).getByText('INFY'))
    await userEvent.click(screen.getByRole('tab', { name: '5 min' }))
    await vi.waitFor(() => expect(spy.mock.calls.some(([u]) => String(u).includes('/data/candles/INFY?timeframe=5minute'))).toBe(true))
  })
})


describe('Robustness', () => {
  it('a malformed API response degrades to empty states instead of crashing', async () => {
    mockApi({})  // every endpoint returns the readiness object
    renderAt('/')
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(await screen.findByText('No data downloaded yet.')).toBeInTheDocument()
  })
})

describe('Volatility tab', () => {
  it('shows the promoted volatility model against its baselines', async () => {
    const m = (r2: number, rmse: number) => ({ n: 9000, r2_log: r2, rmse_log: rmse, mae_log: 0.3, qlike: 0.55, corr: 0.5, rank_corr: 0.42 })
    mockApi({
      '/ml/runs': [{ run_id: 'V1-vol', pipeline: 'swing_vol', dataset_version: 'vol', created_at: '2026-11-13T09:27:00Z', models: ['persistence', 'lightgbm'] }],
      '/ml/experiments/V1-vol': [
        { model: 'lightgbm', walk_forward: m(0.292, 0.4757), holdout: m(0.184, 0.4672), folds: [{ test_start: '2020-01-01', ...m(0.4, 0.4) }] },
        { model: 'persistence', walk_forward: m(0.06, 0.5481), holdout: m(-0.074, 0.5362), folds: [{ test_start: '2020-01-01', ...m(0.17, 0.5) }] },
      ],
      '/ml/models': [{ version: 'swing_vol-lightgbm-V1-vol', pipeline: 'swing_vol', model: 'lightgbm', promoted: true,
        promotion_reasons: ['PASS: holdout RMSE(log vol) below persistence'], created_at: '' }],
    })
    renderAt('/research')
    await userEvent.click(await screen.findByRole('tab', { name: 'volatility' }))
    expect(await screen.findByText('promoted')).toBeInTheDocument()
    expect(screen.getAllByText('0.184').length).toBeGreaterThan(0)
    expect(screen.getByText('-12.9%')).toBeInTheDocument()  // 1 - 0.4672/0.5362
    expect(screen.getByText('PASS: holdout RMSE(log vol) below persistence')).toHaveClass('text-up')
  })
})
