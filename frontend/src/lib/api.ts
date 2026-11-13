/** Typed client for the AstraQuant FastAPI backend. All requests go through the /api proxy. */

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown
  constructor(status: number, body: unknown, message: string) {
    super(message)
    this.status = status
    this.body = body
  }
}

async function request<T>(method: string, path: string, body?: unknown, allow503 = false): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, {
      method,
      headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, null, 'Backend unreachable')
  }
  const data: unknown = await res.json().catch(() => null)
  if (!res.ok && !(allow503 && res.status === 503 && data)) {
    const detail = (data as { detail?: unknown } | null)?.detail
    throw new ApiError(res.status, data, typeof detail === 'string' ? detail : `HTTP ${res.status}`)
  }
  return data as T
}

export const apiGet = <T>(path: string) => request<T>('GET', path)
export const apiPost = <T>(path: string, body?: unknown) => request<T>('POST', path, body)
export const apiPut = <T>(path: string, body?: unknown) => request<T>('PUT', path, body)

// ---------- health ----------
export type CheckStatus = 'ok' | 'error' | 'not_configured'
export interface Check {
  status: CheckStatus
  latency_ms: number | null
  detail: string | null
}
export interface Readiness {
  status: 'ok' | 'degraded'
  version: string
  env: string
  live_trading_enabled: boolean
  checks: Record<string, Check>
}
export const getReadiness = () => request<Readiness>('GET', '/health/ready', undefined, true)

// ---------- data ----------
export interface Member {
  symbol: string
  company_name: string
  industry: string
  instrument_key: string
  sector_index_key: string | null
  as_of: string
}
export interface Candle {
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}
export interface CandlesResponse {
  instrument_key: string
  trading_symbol: string
  timeframe: string
  count: number
  truncated: boolean
  candles: Candle[]
}
export interface Coverage {
  instrument_key: string
  timeframe: string
  files: number
  rows: number
  first_ts: string
  last_ts: string
  quality_passed: boolean | null
}

// ---------- ML ----------
export interface Perf {
  periods?: number
  total_return?: number
  annualized_return?: number | null
  sharpe?: number | null
  sortino?: number | null
  max_drawdown?: number
  profit_factor?: number | null
  win_rate?: number | null
  trades?: number
}
export interface Trading {
  strategy: Perf
  benchmark_equal_weight?: Perf
  long_short_gross_diagnostic?: Perf
  avg_net_return_per_trade_bps?: number
}
export interface Metrics {
  n: number
  accuracy: number
  macro_f1: number
  log_loss: number
  brier: number
  roc_auc_ovr_macro: number
  direction_auc?: number
  ic_mean?: number
  ic_t?: number
  confusion_matrix?: number[][]
  baseline_prior: { log_loss: number; accuracy: number; brier: number }
  trading: Trading
}
export interface FoldRow {
  fold: { k: number; test_start: string; test_end: string }
  metrics: { n: number; log_loss: number; direction_auc?: number; accuracy: number }
  baseline: { log_loss: number }
  best_iteration: number | null
}
export interface Experiment {
  model: string
  dataset_version: string
  walk_forward: Metrics
  folds: FoldRow[]
  holdout: Metrics
  train_seconds: number
}
export interface Run {
  run_id: string
  pipeline: 'swing' | 'intraday'
  dataset_version: string
  created_at: string
  models: string[]
}
export interface RegisteredModel {
  version: string
  pipeline: string
  model: string
  promoted: boolean
  promotion_reasons: string[]
  created_at: string
}

// ---------- strategies ----------
export interface StrategyResult {
  description: string
  timeframe: string
  in_sample?: Perf & { avg_trade_net_pct?: number; costs_pct_of_gross_profit?: number }
  out_of_sample?: Perf & { avg_trade_net_pct?: number; costs_pct_of_gross_profit?: number }
  regimes_oos?: Record<string, { trades: number; win_rate: number; avg_net_return_pct: number }>
  equity_curve_weekly?: [string, number][]
}

// ---------- news ----------
export interface NewsRow {
  id: number
  source: string
  title: string
  url: string
  published_at: string | null
  usable_from: string
  timestamp_status: string
  symbols: string[]
  event_type: string
  importance: number
  sentiment: string | null
  sentiment_score: number | null
}

// ---------- risk ----------
export interface RiskState {
  kill_switch: boolean
  reason: string | null
  changed_by: string
  updated_at: string
  limits: Record<string, number>
}
export interface RiskCheck {
  name: string
  passed: boolean
  value: number | string | null
  limit: number | string | null
  detail: string | null
}
export interface RiskVerdict {
  intent_id: string
  approved: boolean
  quantity: number
  stop_price: number | null
  take_profit: number | null
  checks: RiskCheck[]
  reasons: string[]
}

// ---------- decisions ----------
export interface Decision {
  decision_id: string
  instrument_key: string
  symbol: string
  pipeline: string
  action: 'BUY' | 'SELL' | 'HOLD' | 'NO_TRADE'
  confidence: number
  score: number | null
  contributions: {
    ml?: { p_up: number; p_neutral: number; p_down: number; score: number }
    news?: { items: number; score: number; sentiment?: number; top?: string[] }
    total_score?: number
  }
  reasons: string[]
  model_version: string | null
  market_conditions: Regime | null
  risk: { approved: boolean; quantity: number; stop: number | null; take_profit: number | null; failed_checks: string[] } | null
  quantity: number
  created_at: string
}
export interface Regime {
  trend: 'bull' | 'bear' | 'sideways'
  volatility: 'high' | 'normal' | 'low'
  nifty_close: number
  nifty_ema200: number
  india_vix: number
  vix_1y_percentile: number
  as_of: string
}
