import { NavLink, Outlet } from 'react-router-dom'

import { StatusBar } from '@/components/layout/StatusBar'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/routes'

export function AppShell() {
  return (
    <div className="flex min-h-full flex-col">
      {/* apple.com-style global navigation */}
      <nav aria-label="Main" className="glass-bar sticky top-0 z-50 border-b border-white/[0.06]">
        <div className="mx-auto flex h-12 max-w-[1400px] items-center gap-6 px-6">
          <div className="flex shrink-0 items-center gap-2.5">
            <span className="chrome-sphere block size-[22px]" />
            <span className="text-[15px] font-semibold tracking-[-0.02em]">AstraQuant</span>
          </div>
          <ul className="flex min-w-0 flex-1 items-center justify-center gap-0.5 overflow-x-auto [scrollbar-width:none]">
            {ROUTES.map(({ path, label }) => (
              <li key={path}>
                <NavLink
                  to={path}
                  end={path === '/'}
                  className={({ isActive }) =>
                    cn('block whitespace-nowrap rounded-full px-3 py-1.5 text-[12.5px] transition-colors',
                      isActive ? 'bg-white/[0.12] text-white' : 'text-[#d2d2d7]/80 hover:text-white')
                  }
                >
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
          <span className="hidden shrink-0 rounded-full border border-white/15 px-3 py-1 text-[11px] font-medium text-muted xl:inline">
            Paper only
          </span>
        </div>
      </nav>
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-6 pb-16 pt-8">
        <Outlet />
      </main>
      <StatusBar />
    </div>
  )
}
