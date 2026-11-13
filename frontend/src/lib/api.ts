/** Typed client for the AstraQuant FastAPI backend. All requests go through the Vite /api proxy. */

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown
  constructor(status: number, body: unknown, message: string) {
    super(message)
    this.status = status
    this.body = body
  }
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, { ...init, headers: { Accept: 'application/json', ...init?.headers } })
  } catch {
    throw new ApiError(0, null, 'Backend unreachable')
  }
  const body: unknown = await res.json().catch(() => null)
  // Readiness returns 503 with a valid body when degraded; let callers see that body.
  if (!res.ok && !(res.status === 503 && body)) {
    throw new ApiError(res.status, body, `HTTP ${res.status}`)
  }
  return body as T
}

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

export const getReadiness = () => apiGet<Readiness>('/health/ready')
