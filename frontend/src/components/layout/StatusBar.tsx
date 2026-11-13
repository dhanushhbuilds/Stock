import { StatusDot } from '@/components/StatusDot'
import { useReadiness } from '@/hooks/useReadiness'

const LABELS: Record<string, string> = { database: 'DB', redis: 'REDIS', upstox: 'UPSTOX' }

export function StatusBar() {
  const { data, isPending, isError } = useReadiness()

  return (
    <footer
      role="status"
      aria-label="System status"
      className="flex h-6 shrink-0 items-center gap-4 border-t border-line bg-panel px-3 text-[11px] text-muted"
    >
      <span className="flex items-center gap-1.5">
        <StatusDot status={isPending ? 'loading' : isError ? 'error' : 'ok'} />
        API {isPending ? 'connecting…' : isError ? 'unreachable' : `v${data.version}`}
      </span>
      {data &&
        Object.entries(data.checks).map(([name, c]) => (
          <span key={name} className="flex items-center gap-1.5" title={c.detail ?? undefined}>
            <StatusDot status={c.status} />
            {LABELS[name] ?? name.toUpperCase()}
            {c.latency_ms != null && <span className="num text-dim">{c.latency_ms.toFixed(1)}ms</span>}
            {c.status === 'not_configured' && <span className="text-warn">not configured</span>}
          </span>
        ))}
      <span className="ml-auto font-medium tracking-wide text-warn">PAPER TRADING ONLY · NO LIVE ORDERS</span>
    </footer>
  )
}
