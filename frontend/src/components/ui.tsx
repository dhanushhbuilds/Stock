import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function Panel({ title, right, children, className, padded }: {
  title?: ReactNode
  right?: ReactNode
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <section className={cn('glass fade-in flex min-w-0 flex-col overflow-hidden rounded-[var(--radius-card)]', className)}>
      {title && (
        <header className="flex min-h-11 shrink-0 items-center gap-3 px-5 pt-3.5 pb-2">
          <h2 className="eyebrow !text-[10.5px] !text-muted">{title}</h2>
          <div className="ml-auto flex items-center gap-2">{right}</div>
        </header>
      )}
      <div className={cn('min-h-0 flex-1', padded && 'px-5 pb-5')}>{children}</div>
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
    <div className="min-w-0 px-5 py-3">
      <div className="eyebrow truncate">{label}</div>
      <div className={cn('num mt-1 truncate text-[22px] font-light leading-8 tracking-[-0.02em] text-fg', valueClass)}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-[11.5px] text-dim">{sub}</div>}
    </div>
  )
}

const BADGE = {
  up: 'bg-up/15 text-up ring-up/25',
  down: 'bg-down/15 text-down ring-down/25',
  warn: 'bg-warn/15 text-warn ring-warn/25',
  info: 'bg-white/[0.10] text-fg ring-white/20',
  muted: 'bg-white/[0.06] text-muted ring-white/10',
} as const

export function Badge({ tone = 'muted', children }: { tone?: keyof typeof BADGE; children: ReactNode }) {
  return (
    <span className={cn('inline-flex h-[22px] items-center whitespace-nowrap rounded-full px-2.5 text-[11px] font-medium ring-1 ring-inset', BADGE[tone])}>
      {children}
    </span>
  )
}

export function Button({ children, onClick, disabled, variant = 'default', type = 'button', title, size = 'md' }: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'default' | 'primary' | 'danger'
  type?: 'button' | 'submit'
  title?: string
  size?: 'md' | 'lg'
}) {
  const v = {
    default: 'bg-white/[0.07] text-fg/90 ring-1 ring-inset ring-white/12 hover:bg-white/[0.12]',
    primary: 'bg-gradient-to-b from-white to-[#d8d8dc] text-[#111] shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_10px_28px_-10px_rgba(255,255,255,0.35)] hover:from-white hover:to-white',
    danger: 'bg-down/90 text-[#1a0806] shadow-[0_10px_28px_-12px_rgba(255,122,107,0.6)] hover:bg-down',
  }[variant]
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled}
      className={cn('inline-flex items-center justify-center gap-1.5 rounded-full font-medium transition-[background,transform] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-45',
        size === 'lg' ? 'h-11 px-6 text-[14px]' : 'h-8 px-4 text-[12.5px]', v)}>
      {children}
    </button>
  )
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T
  options: readonly (readonly [T, string])[]
  onChange: (v: T) => void
  label?: string
}) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex rounded-full bg-white/[0.06] p-0.5 ring-1 ring-inset ring-white/10">
      {options.map(([v, text]) => (
        <button key={v} role="tab" type="button" aria-selected={value === v} onClick={() => onChange(v)}
          className={cn('h-7 rounded-full px-3.5 text-[12px] font-medium transition-colors',
            value === v ? 'bg-white/[0.88] text-[#111] shadow-[0_2px_8px_rgba(0,0,0,0.4)]' : 'text-muted hover:text-fg')}>
          {text}
        </button>
      ))}
    </div>
  )
}

/** Loading / error / empty states, shown instead of content. */
export function QueryState({ isPending, error, isEmpty, empty, children }: {
  isPending: boolean
  error: Error | null
  isEmpty?: boolean
  empty?: ReactNode
  children: ReactNode
}) {
  if (isPending) return <div className="flex items-center gap-2 px-5 py-4 text-muted"><Spinner /> Loading…</div>
  if (error)
    return (
      <div role="alert" className="mx-5 my-4 rounded-2xl bg-down/10 px-4 py-3 text-[12.5px] text-down ring-1 ring-inset ring-down/25">
        {error.message}
      </div>
    )
  if (isEmpty) return <div className="px-5 py-4 text-muted">{empty ?? 'No data.'}</div>
  return <>{children}</>
}

export function Spinner({ className }: { className?: string }) {
  return <span aria-hidden className={cn('inline-block size-3.5 animate-spin rounded-full border-2 border-white/20 border-t-white/80', className)} />
}

export function Table({ head, children, dense }: { head: ReactNode[]; children: ReactNode; dense?: boolean }) {
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-left">
        <thead className="sticky top-0 z-10 bg-[#141416]/85 text-[10.5px] font-medium uppercase tracking-[0.1em] text-dim backdrop-blur-xl">
          <tr>
            {head.map((h, i) => (
              <th key={i} className={cn('whitespace-nowrap px-5 font-medium', dense ? 'py-2' : 'py-2.5')}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="[&_td]:whitespace-nowrap [&_td]:px-5 [&_td]:py-2 [&_tr]:border-t [&_tr]:border-white/[0.05] [&_tr:hover]:bg-white/[0.03]">
          {children}
        </tbody>
      </table>
    </div>
  )
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="rounded-2xl bg-white/[0.04] px-4 py-3 text-[12px] leading-relaxed text-muted ring-1 ring-inset ring-white/[0.06]">{children}</p>
}
