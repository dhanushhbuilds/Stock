import { NavLink, Outlet } from 'react-router-dom'

import { StatusBar } from '@/components/layout/StatusBar'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/routes'

export function AppShell() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Main" className="flex w-48 shrink-0 flex-col border-r border-line bg-panel max-md:w-12">
          <div className="flex h-10 items-center border-b border-line px-3 text-[12px] font-semibold tracking-wider">
            <span className="max-md:hidden">ASTRAQUANT X</span>
            <span className="md:hidden">AQ</span>
          </div>
          <ul className="flex flex-col py-1">
            {ROUTES.map(({ path, label, icon: Icon }) => (
              <li key={path}>
                <NavLink
                  to={path}
                  end={path === '/'}
                  title={label}
                  className={({ isActive }) =>
                    cn(
                      'flex h-8 items-center gap-2.5 border-l-2 px-3 text-muted hover:bg-panel-2 hover:text-fg',
                      isActive ? 'border-info bg-panel-2 text-fg' : 'border-transparent',
                    )
                  }
                >
                  <Icon className="size-3.5 shrink-0" aria-hidden />
                  <span className="truncate max-md:hidden">{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main className="min-w-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <StatusBar />
    </div>
  )
}
