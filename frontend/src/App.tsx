import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, createMemoryRouter, RouterProvider } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { NotBuilt } from '@/pages/NotBuilt'
import { SystemMonitor } from '@/pages/SystemMonitor'
import { ROUTES } from '@/routes'

const PAGES: Record<string, React.ReactNode> = { '/system': <SystemMonitor /> }

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
    <QueryClientProvider client={queryClient ?? new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
