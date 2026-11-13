import type { CheckStatus } from '@/lib/api'
import { cn } from '@/lib/utils'

const COLOR: Record<CheckStatus | 'loading', string> = {
  ok: 'bg-up shadow-[0_0_8px_rgba(48,209,88,0.8)]',
  error: 'bg-down shadow-[0_0_8px_rgba(255,69,58,0.8)]',
  not_configured: 'bg-warn',
  loading: 'bg-white/30',
}

export function StatusDot({ status }: { status: CheckStatus | 'loading' }) {
  return <span aria-hidden className={cn('inline-block size-[7px] rounded-full', COLOR[status])} />
}
