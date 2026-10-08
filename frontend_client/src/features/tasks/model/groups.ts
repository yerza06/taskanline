import { useQueries } from '@tanstack/react-query'

import { membersQueryOptions } from '@/features/members/api/members'
import { useAllProjects } from '@/features/projects/api/projects'
import { labelsQueryOptions, statesQueryOptions, useTeams } from '@/features/teams/api/teams'
import { PRIORITY_LABELS } from '@/features/tasks/model/labels'
import type { StateRead, TaskGroup, ViewGroupBy } from '@/shared/api/types'

const DATE = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })

export function formatDate(value: string): string {
  return DATE.format(new Date(`${value}T00:00:00`))
}

/**
 * Справочники пространства для подписей и выбора: статусы всех команд, метки,
 * участники, проекты. Каждый — из своего кэша, так что повторные вызовы не
 * порождают запросов.
 */
export function useDirectory(workspaceId: string | undefined) {
  const teams = useTeams(workspaceId).data ?? []
  const states = useQueries({ queries: teams.map((team) => statesQueryOptions(team.id)) })
  const [labels, members] = useQueries({
    queries: [
      { ...labelsQueryOptions(workspaceId ?? ''), enabled: Boolean(workspaceId) },
      { ...membersQueryOptions('workspace', workspaceId ?? ''), enabled: Boolean(workspaceId) },
    ],
  })
  const projects = useAllProjects(teams)
  return {
    teams,
    states: states.flatMap((result) => result.data ?? []),
    labels: labels?.data ?? [],
    members: members?.data ?? [],
    projects,
  }
}

export type Directory = ReturnType<typeof useDirectory>

/** Подпись группы по ключу из ответа: id статуса → «In Progress», 1 → «Срочный». */
export function groupTitle(groupBy: ViewGroupBy | null, key: string | null, dir: Directory): string {
  if (groupBy === null) return 'Все задачи'
  if (key === null) {
    return {
      state: 'Без статуса',
      assignee: 'Без исполнителя',
      priority: 'Без приоритета',
      project: 'Без проекта',
      label: 'Без метки',
      due_date: 'Без срока',
    }[groupBy]
  }
  switch (groupBy) {
    case 'state': {
      const state = dir.states.find((item) => item.id === key)
      if (!state) return 'Статус'
      const team = dir.teams.length > 1 ? dir.teams.find((t) => t.id === state.team_id) : undefined
      return team ? `${state.name} · ${team.key}` : state.name
    }
    case 'assignee':
      return dir.members.find((member) => member.user_id === key)?.full_name ?? 'Участник'
    case 'priority':
      return PRIORITY_LABELS[Number(key)] ?? key
    case 'project':
      return dir.projects.find((project) => project.id === key)?.name ?? 'Проект'
    case 'label':
      return dir.labels.find((label) => label.id === key)?.name ?? 'Метка'
    case 'due_date':
      return formatDate(key)
  }
}

/**
 * Колонки доски: все статусы команды по порядку, включая пустые, — иначе в пустую
 * колонку нельзя перетащить задачу. Без известной команды — только непустые группы.
 */
export function boardColumns(groups: TaskGroup[], teamStates: StateRead[] | undefined): TaskGroup[] {
  if (!teamStates || teamStates.length === 0) return groups
  const byKey = new Map(groups.map((group) => [group.key, group]))
  return teamStates.map(
    (state) =>
      byKey.get(state.id) ?? { key: state.id, count: 0, items: [], next_cursor: null, has_more: false },
  )
}
