import { StatusDot } from '@/components/StatusDot'
import { useReadiness } from '@/hooks/useReadiness'

const LABELS: Record<string, string> = { database: 'Database', redis: 'Redis', upstox: 'Upstox' }

export function StatusBar() {
  const { data, isPending, isError } = useReadiness()

  return (
    <footer role="status" aria-label="System status"
      className="relative z-10 flex h-8 shrink-0 items-center gap-5 px-6 text-[11.5px] text-dim">
      <span className="flex items-center gap-1.5">
        <StatusDot status={isPending ? 'loading' : isError ? 'error' : 'ok'} />
        API {isPending ? 'connecting…' : isError ? 'unreachable' : `v${data.version}`}
      </span>
      {data?.checks &&
        Object.entries(data.checks).map(([name, c]) => (
          <span key={name} className="flex items-center gap-1.5" title={c.detail ?? undefined}>
            <StatusDot status={c.status} />
            {LABELS[name] ?? name}
            {c.latency_ms != null && <span className="num text-dim/80">{c.latency_ms.toFixed(1)} ms</span>}
            {c.status === 'not_configured' && <span className="text-warn/80">not configured</span>}
          </span>
        ))}
      <span className="ml-auto font-medium text-warn/80">PAPER TRADING ONLY · NO LIVE ORDERS</span>
    </footer>
  )
}
