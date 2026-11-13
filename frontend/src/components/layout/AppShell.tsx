import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { StatusBar } from '@/components/layout/StatusBar'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/routes'

/** Chrome objects floating behind the frosted window (pure CSS, decorative). */
function Scene() {
  return (
    <div className="scene" aria-hidden>
      <div className="chrome torus t1" />
      <div className="chrome torus t2" />
      <div className="chrome sphere s1" />
      <div className="chrome sphere s2" />
      <div className="chrome sphere s3" />
    </div>
  )
}

export function AppShell() {
  const { pathname } = useLocation()
  const current = ROUTES.find((r) => (r.path === '/' ? pathname === '/' : pathname.startsWith(r.path)))
  return (
    <div className="relative h-full">
      <Scene />
      <div className="relative z-10 h-full p-3 md:p-5">
        <div className="window flex h-full flex-col overflow-hidden rounded-[30px]">
          {/* macOS title bar */}
          <div className="relative flex h-11 shrink-0 items-center border-b border-white/[0.07] px-5">
            <div className="flex gap-2" aria-hidden>
              <span className="size-3 rounded-full bg-[#ff5f57] shadow-[inset_0_0_0_0.5px_rgba(0,0,0,0.3)]" />
              <span className="size-3 rounded-full bg-[#febc2e] shadow-[inset_0_0_0_0.5px_rgba(0,0,0,0.3)]" />
              <span className="size-3 rounded-full bg-[#28c840] shadow-[inset_0_0_0_0.5px_rgba(0,0,0,0.3)]" />
            </div>
            <div className="pointer-events-none absolute inset-x-0 text-center text-[12px] text-dim">
              astraquant.local — {current?.label ?? 'AstraQuant'}
            </div>
          </div>
          <div className="flex min-h-0 flex-1">
            <nav aria-label="Main" className="flex w-[228px] shrink-0 flex-col border-r border-white/[0.06] px-3 py-4 max-md:w-[62px]">
              <div className="flex items-center gap-3 px-2.5 pb-6">
                <div className="relative size-8 shrink-0 rounded-full bg-[radial-gradient(circle_at_32%_28%,#fff_0%,#d8d8da_14%,#77777c_42%,#1d1d20_75%)] shadow-[inset_-4px_-6px_10px_rgba(0,0,0,0.6),0_6px_16px_-6px_rgba(0,0,0,0.9)]" />
                <div className="leading-tight max-md:hidden">
                  <div className="chrome-text text-[17px] font-semibold tracking-tight">AstraQuant</div>
                  <div className="eyebrow mt-0.5">NSE · X-2026</div>
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
                          'flex h-9 items-center gap-3 rounded-[11px] px-2.5 text-[13px] transition-all',
                          isActive
                            ? 'bg-white/[0.10] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.10)]'
                            : 'text-muted hover:bg-white/[0.05] hover:text-fg',
                        )
                      }
                    >
                      <Icon className="size-[16px] shrink-0" strokeWidth={1.6} aria-hidden />
                      <span className="truncate max-md:hidden">{label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
              <div className="mt-auto px-2.5 pt-4 text-[11px] leading-relaxed text-dim max-md:hidden">
                Research platform. Simulated decisions only — no live orders.
              </div>
            </nav>
            <main className="min-w-0 flex-1 overflow-auto px-6 py-5">
              <Outlet />
            </main>
          </div>
          <StatusBar />
        </div>
      </div>
    </div>
  )
}
