import { QueryClient } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { App } from '@/App'
import type { Readiness } from '@/lib/api'

const READY: Readiness = {
  status: 'ok',
  version: '0.1.0',
  env: 'test',
  live_trading_enabled: false,
  checks: {
    database: { status: 'ok', latency_ms: 1.23, detail: 'migration=abc' },
    redis: { status: 'ok', latency_ms: 0.4, detail: 'pong' },
    upstox: { status: 'not_configured', latency_ms: null, detail: 'UPSTOX_API_KEY/SECRET missing' },
  },
}

function mockFetch(impl: () => Promise<Response>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(impl)
}

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))

const renderApp = (path = '/') =>
  render(<App initialPath={path} queryClient={new QueryClient({ defaultOptions: { queries: { retry: false } } })} />)

describe('App shell', () => {
  it('renders all ten required pages in navigation', () => {
    mockFetch(() => json(READY))
    renderApp()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getAllByRole('link')).toHaveLength(10)
    for (const label of ['Overview', 'Market Data', 'AI Research', 'News Intelligence', 'Strategy Lab',
      'Risk Centre', 'Paper Trading', 'Portfolio', 'System Monitor', 'Settings']) {
      expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument()
    }
  })

  it('postponed pages say so and show no numbers', () => {
    mockFetch(() => json(READY))
    renderApp('/paper')
    expect(screen.getByRole('heading', { name: 'Paper Trading' })).toBeInTheDocument()
    expect(screen.getByText('Not built yet.')).toBeInTheDocument()
    expect(screen.getByText(/Postponed by the project owner/)).toBeInTheDocument()
  })

  it('navigation switches page', async () => {
    mockFetch(() => json(READY))
    renderApp('/')
    await userEvent.click(screen.getByRole('link', { name: 'Strategy Lab' }))
    expect(await screen.findByRole('heading', { name: 'Strategy Lab' })).toBeInTheDocument()
  })
})

describe('System monitor + status bar', () => {
  it('shows real readiness checks from the backend', async () => {
    const spy = mockFetch(() => json(READY))
    renderApp('/system')
    expect(await screen.findByText('migration=abc')).toBeInTheDocument()
    expect(screen.getByText('1.23 ms')).toBeInTheDocument()
    expect(spy).toHaveBeenCalledWith('/api/v1/health/ready', expect.anything())
    const bar = screen.getByRole('status', { name: 'System status' })
    expect(within(bar).getByText('not configured')).toBeInTheDocument()
    expect(within(bar).getByText(/PAPER TRADING ONLY/)).toBeInTheDocument()
  })

  it('shows degraded body on 503', async () => {
    mockFetch(() => json({ ...READY, status: 'degraded',
      checks: { ...READY.checks, redis: { status: 'error', latency_ms: 2, detail: 'ConnectionError' } } }, 503))
    renderApp('/system')
    expect(await screen.findByText('DEGRADED')).toBeInTheDocument()
    expect(screen.getByText('ConnectionError')).toBeInTheDocument()
  })

  it('shows failure state when backend unreachable', async () => {
    mockFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    renderApp('/system')
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unreachable')
    expect(screen.getByText(/API unreachable/)).toBeInTheDocument()
  })

  it('shows loading state before response', () => {
    mockFetch(() => new Promise(() => {}))
    renderApp('/system')
    expect(screen.getByText('Checking backend…')).toBeInTheDocument()
    expect(screen.getByText(/API connecting/)).toBeInTheDocument()
  })

  it('recheck button refetches', async () => {
    const spy = mockFetch(() => json(READY))
    renderApp('/system')
    await screen.findByText('migration=abc')
    const before = spy.mock.calls.length
    await userEvent.click(screen.getByRole('button', { name: 'Recheck' }))
    await vi.waitFor(() => expect(spy.mock.calls.length).toBeGreaterThan(before))
  })
})
