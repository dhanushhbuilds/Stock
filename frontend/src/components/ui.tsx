import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Tone = 'dark' | 'raised' | 'light'
const SURFACE: Record<Tone, string> = { dark: 'tile', raised: 'tile-raised', light: 'tile-light' }

/** Bento tile. `tone="light"` gives Apple's white highlight tile with ink text. */
export function Panel({ title, right, children, className, padded, tone = 'dark' }: {
  title?: ReactNode
  right?: ReactNode
  children: ReactNode
  className?: string
  padded?: boolean
  tone?: Tone
}) {
  return (
    <section className={cn(SURFACE[tone], 'fade-in flex min-w-0 flex-col overflow-hidden rounded-[var(--radius-card)]', className)}>
      {title && (
        <header className="flex min-h-12 shrink-0 items-center gap-3 px-6 pt-5 pb-2">
          <h2 className={cn('text-[15px] font-semibold tracking-[-0.02em]', tone === 'light' ? 'text-ink' : 'text-fg')}>{title}</h2>
          <div className="ml-auto flex items-center gap-2">{right}</div>
        </header>
      )}
      <div className={cn('min-h-0 flex-1', padded && 'px-6 pb-6')}>{children}</div>
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
    <div className="min-w-0 px-6 py-3">
      <div className="truncate text-[12px] font-medium text-dim">{label}</div>
      <div className={cn('num headline mt-1 truncate text-[28px] text-fg', valueClass)}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-[12px] text-muted">{sub}</div>}
    </div>
  )
}

const BADGE = {
  up: 'bg-up/[0.14] text-up',
  down: 'bg-down/[0.14] text-down',
  warn: 'bg-warn/[0.14] text-warn',
  info: 'bg-white text-ink',
  muted: 'bg-white/[0.08] text-muted',
} as const

export function Badge({ tone = 'muted', children }: { tone?: keyof typeof BADGE; children: ReactNode }) {
  return (
    <span className={cn('inline-flex h-6 items-center whitespace-nowrap rounded-full px-2.5 text-[11.5px] font-semibold', BADGE[tone])}>
      {children}
    </span>
  )
}

export function Button({ children, onClick, disabled, variant = 'default', type = 'button', title, size = 'md' }: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'default' | 'primary' | 'danger' | 'ghost'
  type?: 'button' | 'submit'
  title?: string
  size?: 'md' | 'lg'
}) {
  const v = {
    default: 'bg-white/[0.1] text-fg hover:bg-white/[0.16]',
    primary: 'bg-white text-black hover:bg-[#e8e8ed]',
    danger: 'bg-down text-white hover:brightness-110',
    ghost: 'text-fg hover:text-white hover:underline underline-offset-4',
  }[variant]
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled}
      className={cn('inline-flex items-center justify-center gap-1.5 rounded-full font-medium transition-all active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-35',
        size === 'lg' ? 'h-12 px-7 text-[15px]' : 'h-9 px-4 text-[13px]', v)}>
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
    <div role="tablist" aria-label={label} className="inline-flex rounded-full bg-white/[0.08] p-1">
      {options.map(([v, text]) => (
        <button key={v} role="tab" type="button" aria-selected={value === v} onClick={() => onChange(v)}
          className={cn('h-7 rounded-full px-4 text-[12.5px] font-medium transition-all',
            value === v ? 'bg-white text-black shadow-[0_2px_10px_rgba(0,0,0,0.5)]' : 'text-muted hover:text-fg')}>
          {text}
        </button>
      ))}
    </div>
  )
}

export function QueryState({ isPending, error, isEmpty, empty, children }: {
  isPending: boolean
  error: Error | null
  isEmpty?: boolean
  empty?: ReactNode
  children: ReactNode
}) {
  if (isPending) return <div className="flex items-center gap-2 px-6 py-5 text-muted"><Spinner /> Loading…</div>
  if (error)
    return <div role="alert" className="mx-6 my-5 rounded-2xl bg-down/10 px-4 py-3 text-[13px] text-down">{error.message}</div>
  if (isEmpty) return <div className="px-6 py-5 text-muted">{empty ?? 'No data.'}</div>
  return <>{children}</>
}

export function Spinner({ className }: { className?: string }) {
  return <span aria-hidden className={cn('inline-block size-3.5 animate-spin rounded-full border-2 border-white/20 border-t-white', className)} />
}

export function Table({ head, children, dense }: { head: ReactNode[]; children: ReactNode; dense?: boolean }) {
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-left text-[13px]">
        <thead className="sticky top-0 z-10 bg-[#0e0e10]/95 text-[11.5px] font-medium text-dim backdrop-blur-xl">
          <tr>
            {head.map((h, i) => (
              <th key={i} className={cn('whitespace-nowrap px-6 font-medium', dense ? 'py-2' : 'py-3')}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="[&_td]:whitespace-nowrap [&_td]:px-6 [&_td]:py-2.5 [&_tr]:border-t [&_tr]:border-white/[0.06] [&_tr]:transition-colors [&_tr:hover]:bg-white/[0.035]">
          {children}
        </tbody>
      </table>
    </div>
  )
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="text-[13px] leading-relaxed text-dim">{children}</p>
}

/** Decorative chrome composition for hero sections. */
export function ChromeArt({ className }: { className?: string }) {
  return (
    <div aria-hidden className={cn('pointer-events-none relative', className)} style={{ perspective: '900px' }}>
      <div className="chrome-torus float-a absolute left-[8%] top-[4%] aspect-square w-[80%]" />
      <div className="chrome-sphere float-b absolute right-[2%] top-[0%] aspect-square w-[24%]" />
      <div className="chrome-sphere float-b absolute bottom-[6%] left-[4%] aspect-square w-[11%]" style={{ animationDelay: '-6s' }} />
    </div>
  )
}
