import { NavLink, Outlet } from 'react-router-dom'

import { StatusBar } from '@/components/layout/StatusBar'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/routes'

export function AppShell() {
  return (
    <div className="relative flex h-full flex-col">
      <div className="ambient" aria-hidden><i /></div>
      <div className="relative z-10 flex min-h-0 flex-1 gap-3 p-3">
        <nav aria-label="Main" className="glass-strong flex w-[232px] shrink-0 flex-col rounded-[26px] p-3 max-md:w-[64px]">
          <div className="flex items-center gap-2.5 px-2 pb-5 pt-2">
            <div className="grid size-8 shrink-0 place-items-center rounded-[10px] bg-gradient-to-br from-[#0a84ff] via-[#5e5ce6] to-[#bf5af2] text-[12px] font-bold text-white shadow-[0_6px_18px_-6px_rgba(94,92,230,0.9)]">
              AX
            </div>
            <div className="leading-tight max-md:hidden">
              <div className="text-[14px] font-semibold tracking-tight">AstraQuant</div>
              <div className="text-[11px] text-dim">NSE · X-2026</div>
            </div>
          </div>
          <ul className="flex flex-col gap-0.5">
            {ROUTES.map(({ path, label, icon: Icon }) => (
              <li key={path}>
                <NavLink
                  to={path}
                  end={path === '/'}
                  title={label}
                  className={({ isActive }) =>
                    cn(
                      'flex h-9 items-center gap-3 rounded-[12px] px-2.5 text-[13px] transition-colors',
                      isActive ? 'bg-white/[0.12] text-fg shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]' : 'text-muted hover:bg-white/[0.06] hover:text-fg',
                    )
                  }
                >
                  <Icon className="size-[17px] shrink-0" strokeWidth={1.8} aria-hidden />
                  <span className="truncate max-md:hidden">{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="mt-auto px-2 pt-4 text-[11px] leading-relaxed text-dim max-md:hidden">
            Research platform · simulated decisions only · no live orders
          </div>
        </nav>
        <main className="min-w-0 flex-1 overflow-auto rounded-[26px]">
          <Outlet />
        </main>
      </div>
      <StatusBar />
    </div>
  )
}
