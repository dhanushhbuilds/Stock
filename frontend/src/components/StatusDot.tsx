import type { CheckStatus } from '@/lib/api'
import { cn } from '@/lib/utils'

const COLOR: Record<CheckStatus | 'loading', string> = {
  ok: 'bg-up',
  error: 'bg-down',
  not_configured: 'bg-white/30',
  loading: 'bg-white/20',
}

export function StatusDot({ status }: { status: CheckStatus | 'loading' }) {
  return <span aria-hidden className={cn('inline-block size-[6px] rounded-full', COLOR[status])} />
}
