import { useQuery } from '@tanstack/react-query'

import { getReadiness } from '@/lib/api'

export function useReadiness() {
  return useQuery({
    queryKey: ['readiness'],
    queryFn: getReadiness,
    refetchInterval: 10_000,
    retry: false,
  })
}
