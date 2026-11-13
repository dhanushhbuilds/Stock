import { PageHeader } from '@/components/PageHeader'
import { StatusDot } from '@/components/StatusDot'
import { useReadiness } from '@/hooks/useReadiness'

export function SystemMonitor() {
  const { data, isPending, isError, error, dataUpdatedAt, refetch, isFetching } = useReadiness()

  return (
    <>
      <PageHeader title="System Monitor">
        {dataUpdatedAt > 0 && (
          <span className="num text-[11px] text-dim">updated {new Date(dataUpdatedAt).toLocaleTimeString()}</span>
        )}
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="h-6 border border-line px-2 text-[11px] text-muted hover:bg-panel-2 hover:text-fg disabled:opacity-50"
        >
          {isFetching ? 'Checking…' : 'Recheck'}
        </button>
      </PageHeader>

      <div className="p-4">
        {isPending && <p className="text-muted">Checking backend…</p>}

        {isError && (
          <div role="alert" className="max-w-lg border border-down/40 bg-down/10 p-3 text-down">
            Backend unreachable ({error.message}). Start it with <code className="num">make backend</code>.
          </div>
        )}

        {data && (
          <section aria-label="Service checks" className="max-w-2xl">
            <p className="mb-3 text-muted">
              API <span className="num text-fg">v{data.version}</span> · env{' '}
              <span className="num text-fg">{data.env}</span> · overall{' '}
              <span className={data.status === 'ok' ? 'text-up' : 'text-down'}>{data.status.toUpperCase()}</span>
            </p>
            <table className="w-full border border-line text-left">
              <thead className="bg-panel text-[11px] uppercase tracking-wider text-dim">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Service</th>
                  <th className="px-3 py-1.5 font-medium">Status</th>
                  <th className="px-3 py-1.5 text-right font-medium">Latency</th>
                  <th className="px-3 py-1.5 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.checks).map(([name, c]) => (
                  <tr key={name} className="border-t border-line">
                    <td className="px-3 py-1.5">{name}</td>
                    <td className="px-3 py-1.5">
                      <span className="flex items-center gap-1.5">
                        <StatusDot status={c.status} />
                        {c.status}
                      </span>
                    </td>
                    <td className="num px-3 py-1.5 text-right">
                      {c.latency_ms != null ? `${c.latency_ms.toFixed(2)} ms` : '—'}
                    </td>
                    <td className="num px-3 py-1.5 text-muted">{c.detail ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-muted">
              Live trading:{' '}
              <span className={data.live_trading_enabled ? 'text-down' : 'text-up'}>
                {data.live_trading_enabled ? 'ENABLED' : 'disabled'}
              </span>
            </p>
          </section>
        )}
      </div>
    </>
  )
}
