import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function Panel({ title, right, children, className }: {
  title?: ReactNode
  right?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('flex min-w-0 flex-col overflow-hidden border border-line bg-panel', className)}>
      {title && (
        <header className="flex h-8 shrink-0 items-center gap-2 border-b border-line px-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">{title}</h2>
          <div className="ml-auto flex items-center gap-2">{right}</div>
        </header>
      )}
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  )
}

export function Stat({ label, value, sub, valueClass }: {
  label: string
  value: ReactNode
  sub?: ReactNode
  valueClass?: string
}) {
  return (
    <div className="min-w-0 px-3 py-2">
      <div className="truncate text-[10px] uppercase tracking-wider text-dim">{label}</div>
      <div className={cn('num truncate text-[17px] leading-6 text-fg', valueClass)}>{value}</div>
      {sub && <div className="truncate text-[11px] text-muted">{sub}</div>}
    </div>
  )
}

const BADGE = {
  up: 'border-up/40 bg-up/10 text-up',
  down: 'border-down/40 bg-down/10 text-down',
  warn: 'border-warn/40 bg-warn/10 text-warn',
  info: 'border-info/40 bg-info/10 text-info',
  muted: 'border-line bg-panel-2 text-muted',
} as const

export function Badge({ tone = 'muted', children }: { tone?: keyof typeof BADGE; children: ReactNode }) {
  return (
    <span className={cn('inline-flex h-[18px] items-center border px-1.5 text-[10px] font-medium uppercase tracking-wide', BADGE[tone])}>
      {children}
    </span>
  )
}

export function Button({ children, onClick, disabled, variant = 'default', type = 'button', title }: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'default' | 'primary' | 'danger'
  type?: 'button' | 'submit'
  title?: string
}) {
  const v = {
    default: 'border-line text-muted hover:bg-panel-2 hover:text-fg',
    primary: 'border-info/60 bg-info/15 text-info hover:bg-info/25',
    danger: 'border-down/60 bg-down/15 text-down hover:bg-down/25',
  }[variant]
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled}
      className={cn('h-7 border px-2.5 text-[11px] font-medium disabled:cursor-not-allowed disabled:opacity-50', v)}>
      {children}
    </button>
  )
}

/** Loading / error / empty states, shown instead of content. Returns null when there is data to render. */
export function QueryState({ isPending, error, isEmpty, empty, children }: {
  isPending: boolean
  error: Error | null
  isEmpty?: boolean
  empty?: ReactNode
  children: ReactNode
}) {
  if (isPending) return <div className="p-3 text-muted">Loading…</div>
  if (error)
    return (
      <div role="alert" className="m-3 border border-down/40 bg-down/10 p-2 text-down">
        {error.message}
      </div>
    )
  if (isEmpty) return <div className="p-3 text-muted">{empty ?? 'No data.'}</div>
  return <>{children}</>
}

export function Table({ head, children, dense }: { head: ReactNode[]; children: ReactNode; dense?: boolean }) {
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-left">
        <thead className="sticky top-0 bg-panel-2 text-[10px] uppercase tracking-wider text-dim">
          <tr>
            {head.map((h, i) => (
              <th key={i} className={cn('whitespace-nowrap px-3 font-medium', dense ? 'py-1' : 'py-1.5')}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="[&_td]:whitespace-nowrap [&_td]:px-3 [&_td]:py-1 [&_tr]:border-t [&_tr]:border-line">
          {children}
        </tbody>
      </table>
    </div>
  )
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="border-l-2 border-warn/60 bg-warn/5 px-3 py-1.5 text-[12px] text-muted">{children}</p>
}
