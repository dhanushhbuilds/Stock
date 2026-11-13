import { PageHeader } from '@/components/PageHeader'
import type { RouteDef } from '@/routes'

/** Honest placeholder for pages whose engine is not built yet. Shows no numbers. */
export function NotBuilt({ route }: { route: RouteDef }) {
  return (
    <>
      <PageHeader title={route.label} />
      <div className="p-4">
        <div className="max-w-lg border border-line bg-panel p-4">
          <p className="text-fg">Not built yet.</p>
          <p className="mt-1 text-muted">
            {route.status ? `${route.status} ` : ''}This page becomes functional in{' '}
            <span className="text-fg">Phase {route.phase}</span>. It will show
            only data produced by the backend, never sample figures.
          </p>
        </div>
      </div>
    </>
  )
}
