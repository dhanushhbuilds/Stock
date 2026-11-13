import type { ReactNode } from 'react'

export function PageHeader({ title, subtitle, eyebrow, children }: {
  title: string
  subtitle?: ReactNode
  eyebrow?: string
  children?: ReactNode
}) {
  return (
    <header className="fade-in flex flex-wrap items-end gap-6 pb-8">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
        <h1 className="headline text-gradient text-[48px] md:text-[56px]">{title}</h1>
        {subtitle && <p className="mt-3 max-w-[62ch] text-[17px] leading-snug text-muted">{subtitle}</p>}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>
    </header>
  )
}
