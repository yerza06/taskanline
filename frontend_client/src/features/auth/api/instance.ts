import { queryOptions, useQuery } from '@tanstack/react-query'

import { apiFetch } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type InstanceInfo = components['schemas']['InstanceInfo']

/** Название инстанса и режим регистрации — доступны и без входа. */
export function instanceQueryOptions() {
  return queryOptions({
    queryKey: ['instance'] as const,
    queryFn: () => apiFetch<InstanceInfo>('/instance'),
    staleTime: 5 * 60_000,
  })
}

export function useInstance() {
  return useQuery(instanceQueryOptions()).data
}
