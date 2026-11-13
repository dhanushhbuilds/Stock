import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, createMemoryRouter, RouterProvider } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { lazy, Suspense } from 'react'

import { NotBuilt } from '@/pages/NotBuilt'
import { Overview } from '@/pages/Overview'
import { SystemMonitor } from '@/pages/SystemMonitor'
import { ROUTES } from '@/routes'

// Chart-heavy pages are code-split so the first load stays small.
const Market = lazy(() => import('@/pages/Market').then((m) => ({ default: m.Market })))
const News = lazy(() => import('@/pages/News').then((m) => ({ default: m.News })))
const Research = lazy(() => import('@/pages/Research').then((m) => ({ default: m.Research })))
const Risk = lazy(() => import('@/pages/Risk').then((m) => ({ default: m.Risk })))
const Settings = lazy(() => import('@/pages/Settings').then((m) => ({ default: m.Settings })))
const StrategyLab = lazy(() => import('@/pages/StrategyLab').then((m) => ({ default: m.StrategyLab })))
const page = (el: React.ReactNode) => <Suspense fallback={<div className="p-4 text-muted">Loading…</div>}>{el}</Suspense>

const PAGES: Record<string, React.ReactNode> = {
  '/': <Overview />,
  '/market': page(<Market />),
  '/research': page(<Research />),
  '/news': page(<News />),
  '/strategy': page(<StrategyLab />),
  '/risk': page(<Risk />),
  '/system': <SystemMonitor />,
  '/settings': page(<Settings />),
}

const routeTree = [
  {
    element: <AppShell />,
    children: [
      ...ROUTES.map((r) => ({ path: r.path, element: PAGES[r.path] ?? <NotBuilt route={r} /> })),
      { path: '*', element: <NotBuilt route={{ ...ROUTES[0], label: 'Not found', phase: 0 }} /> },
    ],
  },
]

export function App({ initialPath, queryClient }: { initialPath?: string; queryClient?: QueryClient }) {
  const router = initialPath ? createMemoryRouter(routeTree, { initialEntries: [initialPath] }) : createBrowserRouter(routeTree)
  return (
    <QueryClientProvider client={queryClient ?? new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
