import { HttpResponse, http, type HttpHandler } from 'msw'

import type {
  LabelRead,
  ProjectRead,
  StateRead,
  TaskGroup,
  TaskRead,
  TeamRead,
  ViewRead,
  WorkspaceRead,
} from '@/shared/api/types'

import { ME } from './handlers'

/**
 * Маленький изменяемый мир для тестов экранов задач: пространство acme, команда
 * ENG с четырьмя статусами, метка bug и несколько задач.
 *
 * Обработчики не повторяют бэкенд целиком — только то, что видит экран: группы
 * по статусу, перестановку, правку полей. Состояние живёт в объекте `World`, и
 * тест читает из него, что именно ушло на сервер.
 */

const AT = '2026-10-08T10:00:00Z'
export const WS_ID = '019a5c1e-0000-7000-8000-0000000000a0'
export const TEAM_ID = '019a5c1e-0000-7000-8000-0000000000b0'
export const BUG_ID = '019a5c1e-0000-7000-8000-0000000000e0'

export const WORKSPACE: WorkspaceRead = {
  id: WS_ID,
  name: 'Acme',
  slug: 'acme',
  avatar_url: null,
  created_by: ME.id,
  created_at: AT,
  updated_at: AT,
}

export const TEAM: TeamRead = {
  id: TEAM_ID,
  workspace_id: WS_ID,
  key: 'ENG',
  name: 'Инженерия',
  description: null,
  is_private: false,
  created_at: AT,
  updated_at: AT,
}

function state(n: number, name: string, type: StateRead['type']): StateRead {
  return {
    id: `019a5c1e-0000-7000-8000-0000000000c${n}`,
    workspace_id: WS_ID,
    team_id: TEAM_ID,
    name,
    type,
    color: '#808080',
    position: n,
    is_default: name === 'Todo',
    created_at: AT,
  }
}

export const STATES: StateRead[] = [
  state(1, 'Todo', 'unstarted'),
  state(2, 'In Progress', 'started'),
  state(3, 'Done', 'completed'),
  state(4, 'Canceled', 'canceled'),
]

export const BUG: LabelRead = {
  id: BUG_ID,
  workspace_id: WS_ID,
  team_id: null,
  name: 'bug',
  color: '#808080',
  created_at: AT,
}

function brief(stateRead: StateRead) {
  return { id: stateRead.id, name: stateRead.name, type: stateRead.type, color: stateRead.color }
}

export function makeTask(number: number, title: string, changes: Partial<TaskRead> = {}): TaskRead {
  const stateRead = STATES.find((s) => s.id === changes.state_id) ?? STATES[0]!
  return {
    id: `019a5c1e-0000-7000-8000-${String(number).padStart(12, '0')}`,
    key: `ENG-${number}`,
    workspace_id: WS_ID,
    team_id: TEAM_ID,
    project_id: null,
    number,
    title,
    description: null,
    state_id: stateRead.id,
    assignee_id: null,
    creator_id: ME.id,
    priority: 0,
    due_date: null,
    parent_id: null,
    label_ids: [],
    sort_order: `a${number}`,
    started_at: null,
    completed_at: null,
    created_at: AT,
    updated_at: AT,
    deleted_at: null,
    state: brief(stateRead),
    assignee: null,
    labels: [],
    project: null,
    ...changes,
  }
}

export class World {
  workspaces: WorkspaceRead[] = [WORKSPACE]
  teams: TeamRead[] = [TEAM]
  projects: ProjectRead[] = []
  views: ViewRead[] = []
  tasks: TaskRead[] = [
    makeTask(1, 'Починить логин', { priority: 1 }),
    makeTask(2, 'Обновить README'),
    makeTask(3, 'Выкатить релиз', { state_id: STATES[1]!.id, state: brief(STATES[1]!) }),
  ]
  /** Тела запросов, которые изменили мир, — по порядку. */
  sent: { method: string; path: string; body: unknown }[] = []
  /** Последний запрос среза — что экран спросил у `POST /views/query`. */
  lastQuery: Record<string, unknown> | null = null

  find(ref: string): TaskRead | undefined {
    return this.tasks.find((task) => task.id === ref || task.key === ref.toUpperCase())
  }

  private groups(groupBy: string | null): TaskGroup[] {
    const live = this.tasks.filter((task) => task.deleted_at === null)
    const sorted = [...live].sort((a, b) => a.sort_order.localeCompare(b.sort_order))
    if (groupBy !== 'state') {
      return [{ key: null, count: sorted.length, items: sorted, next_cursor: null, has_more: false }]
    }
    return STATES.filter((s) => sorted.some((task) => task.state_id === s.id)).map((s) => {
      const items = sorted.filter((task) => task.state_id === s.id)
      return { key: s.id, count: items.length, items, next_cursor: null, has_more: false }
    })
  }

  handlers(): HttpHandler[] {
    const record = (method: string, path: string, body: unknown) => this.sent.push({ method, path, body })
    return [
      http.get('/api/v1/workspaces', () => HttpResponse.json({ items: this.workspaces })),
      http.post('/api/v1/workspaces', async ({ request }) => {
        const body = (await request.json()) as { name: string; slug: string }
        record('POST', '/workspaces', body)
        const space = { ...WORKSPACE, id: crypto.randomUUID(), ...body }
        this.workspaces.push(space)
        return HttpResponse.json(space, { status: 201 })
      }),
      http.get('/api/v1/workspaces/:id/teams', () => HttpResponse.json({ items: this.teams })),
      http.post('/api/v1/workspaces/:id/teams', async ({ request }) => {
        const body = (await request.json()) as Partial<TeamRead>
        record('POST', '/teams', body)
        const team = { ...TEAM, id: crypto.randomUUID(), ...body }
        this.teams.push(team)
        return HttpResponse.json(team, { status: 201 })
      }),
      http.get('/api/v1/workspaces/:id/members', () =>
        HttpResponse.json({
          items: [{ user_id: ME.id, email: ME.email, full_name: ME.full_name, avatar_url: null, joined_at: AT, role: 'owner' }],
        }),
      ),
      http.get('/api/v1/teams/:id/states', () => HttpResponse.json({ items: STATES })),
      http.get('/api/v1/teams/:id/projects', () => HttpResponse.json({ items: this.projects })),
      http.post('/api/v1/teams/:id/projects', async ({ request, params }) => {
        const body = (await request.json()) as Partial<ProjectRead>
        record('POST', '/projects', body)
        const project = {
          id: crypto.randomUUID(),
          workspace_id: WS_ID,
          team_id: String(params.id),
          description: null,
          status: 'planned',
          lead_id: null,
          start_date: null,
          target_date: null,
          archived_at: null,
          created_at: AT,
          updated_at: AT,
          ...body,
        } as ProjectRead
        this.projects.push(project)
        return HttpResponse.json(project, { status: 201 })
      }),
      http.get('/api/v1/projects/:id', ({ params }) => {
        const project = this.projects.find((p) => p.id === params.id)
        return project
          ? HttpResponse.json(project)
          : HttpResponse.json({ error: { code: 'project_not_found', message: '', details: {} } }, { status: 404 })
      }),
      http.get('/api/v1/labels', () => HttpResponse.json({ items: [BUG] })),
      http.get('/api/v1/views', () => HttpResponse.json({ items: this.views })),
      http.post('/api/v1/views', async ({ request }) => {
        const body = (await request.json()) as Partial<ViewRead>
        record('POST', '/views', body)
        const view = {
          id: crypto.randomUUID(),
          owner_id: ME.id,
          team_id: null,
          description: null,
          icon: null,
          color: null,
          position: 0,
          created_by: ME.id,
          created_at: AT,
          updated_at: AT,
          can_edit: true,
          group_by: null,
          sort_by: 'manual',
          sort_direction: 'asc',
          layout: 'list',
          filters: {},
          ...body,
        } as ViewRead
        this.views.push(view)
        return HttpResponse.json(view, { status: 201 })
      }),
      http.get('/api/v1/views/:id', ({ params }) => {
        const view = this.views.find((v) => v.id === params.id)
        return view
          ? HttpResponse.json(view)
          : HttpResponse.json({ error: { code: 'view_not_found', message: '', details: {} } }, { status: 404 })
      }),
      http.get('/api/v1/me/notifications', () =>
        HttpResponse.json({ items: [], next_cursor: null, has_more: false }),
      ),
      http.get('/api/v1/invitations', () => HttpResponse.json({ items: [] })),
      http.post('/api/v1/views/query', async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        this.lastQuery = body
        return HttpResponse.json({
          group_by: body.group_by ?? null,
          groups: this.groups((body.group_by as string | null) ?? null),
        })
      }),
      http.post('/api/v1/tasks', async ({ request }) => {
        const body = (await request.json()) as Partial<TaskRead>
        record('POST', '/tasks', body)
        const task = makeTask(this.tasks.length + 1, body.title ?? '', {
          ...body,
          state_id: body.state_id ?? STATES[0]!.id,
        })
        this.tasks.push(task)
        return HttpResponse.json(task, { status: 201 })
      }),
      http.get('/api/v1/tasks/:ref', ({ params }) => {
        const task = this.find(String(params.ref))
        return task
          ? HttpResponse.json({ ...task, relations: [], parent: null, creator: { id: ME.id, email: ME.email, full_name: ME.full_name, avatar_url: null } })
          : HttpResponse.json({ error: { code: 'task_not_found', message: '', details: {} } }, { status: 404 })
      }),
      http.patch('/api/v1/tasks/:ref', async ({ request, params }) => {
        const body = (await request.json()) as Partial<TaskRead>
        record('PATCH', `/tasks/${String(params.ref)}`, body)
        const task = this.find(String(params.ref))!
        Object.assign(task, body)
        const newState = STATES.find((s) => s.id === task.state_id)
        if (newState) task.state = brief(newState)
        return HttpResponse.json({ ...task, relations: [] })
      }),
      http.post('/api/v1/tasks/:ref/move', async ({ request, params }) => {
        const body = (await request.json()) as { state_id?: string; after_id?: string; before_id?: string }
        record('POST', `/tasks/${String(params.ref)}/move`, body)
        const task = this.find(String(params.ref))!
        if (body.state_id) {
          task.state_id = body.state_id
          task.state = brief(STATES.find((s) => s.id === body.state_id)!)
        }
        const anchor = this.find(body.after_id ?? body.before_id ?? '')
        if (anchor) task.sort_order = anchor.sort_order + (body.after_id ? 'm' : '')
        if (body.before_id && anchor) task.sort_order = anchor.sort_order.slice(0, -1) + '0'
        return HttpResponse.json(task)
      }),
      http.get('/api/v1/tasks/:ref/subtasks', ({ params }) => {
        const parent = this.find(String(params.ref))
        return HttpResponse.json({ items: this.tasks.filter((t) => parent && t.parent_id === parent.id) })
      }),
      http.get('/api/v1/tasks/:ref/comments', () =>
        HttpResponse.json({ items: [], next_cursor: null, has_more: false }),
      ),
      http.post('/api/v1/tasks/:ref/comments', async ({ request, params }) => {
        const body = (await request.json()) as { body: string }
        record('POST', `/tasks/${String(params.ref)}/comments`, body)
        return HttpResponse.json(
          { id: crypto.randomUUID(), task_id: params.ref, author_id: ME.id, author_token_id: null, parent_id: null, body: body.body, mention_ids: [], created_at: AT, updated_at: AT },
          { status: 201 },
        )
      }),
      http.get('/api/v1/tasks/:ref/activities', () =>
        HttpResponse.json({ items: [], next_cursor: null, has_more: false }),
      ),
    ]
  }
}

/** Мир с пространством acme для `server.use(...)`; сам объект — для проверок. */
export function world(target: World = new World()): HttpHandler[] {
  return target.handlers()
}
