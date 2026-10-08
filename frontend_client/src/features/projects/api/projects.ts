import { queryOptions, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from '@/shared/api/client'
import type { ProjectCreate, ProjectRead, TeamRead } from '@/shared/api/types'

export const projectsKey = (teamId: string) => ['team', teamId, 'projects'] as const
export const projectKey = (projectId: string) => ['project', projectId] as const

export function projectsQueryOptions(teamId: string) {
  return queryOptions({
    queryKey: projectsKey(teamId),
    queryFn: () => apiFetch<{ items: ProjectRead[] }>(`/teams/${teamId}/projects`),
    select: (data) => data.items,
  })
}

export function useProjects(teamId: string | undefined) {
  return useQuery({ ...projectsQueryOptions(teamId ?? ''), enabled: Boolean(teamId) })
}

/** Проекты всех видимых команд — для бокового меню и выбора проекта у задачи. */
export function useAllProjects(teams: TeamRead[] | undefined): ProjectRead[] {
  const results = useQueries({
    queries: (teams ?? []).map((team) => projectsQueryOptions(team.id)),
  })
  return results.flatMap((result) => result.data ?? [])
}

export function useProject(projectId: string | undefined) {
  return useQuery({
    queryKey: projectKey(projectId ?? ''),
    queryFn: () => apiFetch<ProjectRead>(`/projects/${projectId}`),
    enabled: Boolean(projectId),
  })
}

export function useCreateProject(teamId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (values: ProjectCreate) =>
      apiFetch<ProjectRead>(`/teams/${teamId}/projects`, { method: 'POST', json: values }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectsKey(teamId) })
    },
  })
}
