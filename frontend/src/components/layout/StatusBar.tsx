import { StatusDot } from '@/components/StatusDot'
import { useReadiness } from '@/hooks/useReadiness'

const LABELS: Record<string, string> = { database: 'Database', redis: 'Redis', upstox: 'Upstox' }

export function StatusBar() {
  const { data, isPending, isError } = useReadiness()

  return (
    <footer role="status" aria-label="System status"
      className="flex h-9 shrink-0 items-center gap-5 border-t border-white/[0.06] px-5 text-[11.5px] text-dim">
      <span className="flex items-center gap-1.5">
        <StatusDot status={isPending ? 'loading' : isError ? 'error' : 'ok'} />
        API {isPending ? 'connecting…' : isError ? 'unreachable' : `v${data.version}`}
      </span>
      {data?.checks &&
        Object.entries(data.checks).map(([name, c]) => (
          <span key={name} className="flex items-center gap-1.5" title={c.detail ?? undefined}>
            <StatusDot status={c.status} />
            {LABELS[name] ?? name}
            {c.latency_ms != null && <span className="num opacity-70">{c.latency_ms.toFixed(1)} ms</span>}
            {c.status === 'not_configured' && <span className="opacity-80">not configured</span>}
          </span>
        ))}
      <span className="eyebrow ml-auto !text-[10px]">PAPER TRADING ONLY · NO LIVE ORDERS</span>
    </footer>
  )
}
