import type { ReactNode } from 'react'

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end gap-4 pb-5">
      <div className="min-w-0">
        <h1 className="chrome-text text-[34px] font-light leading-tight tracking-[-0.025em]">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-[70ch] text-[13.5px] font-light text-muted">{subtitle}</p>}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>
    </header>
  )
}
