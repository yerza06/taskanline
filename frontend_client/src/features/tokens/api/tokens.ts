import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from '@/shared/api/client'
import type { TokenCreate, TokenCreated, TokenList } from '@/shared/api/types'

export const TOKENS_KEY = ['tokens'] as const

export function tokensQueryOptions() {
  return queryOptions({
    queryKey: TOKENS_KEY,
    queryFn: () => apiFetch<TokenList>('/me/tokens'),
  })
}

export function useCreateToken() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (values: TokenCreate) =>
      apiFetch<TokenCreated>('/me/tokens', { method: 'POST', json: values }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: TOKENS_KEY })
    },
  })
}

export function useRevokeToken() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/me/tokens/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: TOKENS_KEY })
    },
  })
}
