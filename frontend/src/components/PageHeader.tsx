import type { ReactNode } from 'react'

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end gap-4 px-2 pb-4 pt-3">
      <div className="min-w-0">
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em]">{title}</h1>
        {subtitle && <p className="mt-1 text-[13px] text-muted">{subtitle}</p>}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>
    </header>
  )
}
