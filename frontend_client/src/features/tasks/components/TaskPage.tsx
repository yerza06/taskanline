import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { Trash2, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import Markdown from 'react-markdown'

import { canWrite, useSession } from '@/features/auth/api/session'
import { useMembers } from '@/features/members/api/members'
import { useProjects } from '@/features/projects/api/projects'
import {
  useActivities,
  useAddComment,
  useAddRelation,
  useComments,
  useCreateTask,
  useDeleteTask,
  useRemoveRelation,
  useSetLabels,
  useSubtasks,
  useTask,
  useUpdateTask,
} from '@/features/tasks/api/tasks'
import { Avatar, PriorityIcon, StateIcon } from '@/features/tasks/components/TaskIcons'
import { TaskRow } from '@/features/tasks/components/TaskItems'
import { ACTIVITY_LABELS, PRIORITY_LABELS, RELATION_LABELS } from '@/features/tasks/model/labels'
import { useLabels, useStates } from '@/features/teams/api/teams'
import { useCurrentWorkspace } from '@/features/workspaces/api/workspaces'
import { humanMessage } from '@/shared/api/messages'
import type { RelationCreate, TaskRead, WorkspaceRead } from '@/shared/api/types'
import { formatDateTime } from '@/shared/lib/format'
import { Alert } from '@/shared/ui/Alert'
import { Button } from '@/shared/ui/Button'
import { Dialog } from '@/shared/ui/Dialog'
import { Input } from '@/shared/ui/Input'
import { Select } from '@/shared/ui/Select'
import { Textarea } from '@/shared/ui/Textarea'

/**
 * Markdown без сырого HTML: `react-markdown` по умолчанию его не исполняет, так что
 * описание задачи не может стать XSS. Ссылки открываются в новой вкладке.
 */
export function MarkdownText({ children }: { children: string }) {
  return (
    <div className="prose-sm max-w-none space-y-2 text-sm leading-relaxed [&_a]:underline [&_code]:bg-surface-hover [&_code]:rounded [&_code]:px-1 [&_li]:ml-5 [&_ol]:list-decimal [&_pre]:overflow-x-auto [&_ul]:list-disc">
      <Markdown
        components={{
          a: ({ href, children: text }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {text}
            </a>
          ),
        }}
      >
        {children}
      </Markdown>
    </div>
  )
}

function Property({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] items-center gap-2">
      <span className="text-fg-muted text-sm">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-fg-muted text-xs tracking-wide uppercase">{title}</h2>
      {children}
    </section>
  )
}

function Title({ task, writable }: { task: TaskRead; writable: boolean }) {
  const update = useUpdateTask(task)
  const [value, setValue] = useState(task.title)
  if (!writable) return <h1 className="font-display text-2xl font-semibold tracking-tight">{task.title}</h1>
  return (
    <h1>
      <label className="sr-only" htmlFor="task-title">
        Название задачи
      </label>
      <input
        id="task-title"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          const title = value.trim()
          if (title && title !== task.title) update.mutate({ title })
          else setValue(task.title)
        }}
        onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
        className="font-display focus-visible:outline-accent w-full rounded bg-transparent text-2xl font-semibold tracking-tight focus-visible:outline-2"
      />
    </h1>
  )
}

function Description({ task, writable }: { task: TaskRead; writable: boolean }) {
  const update = useUpdateTask(task)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(task.description ?? '')

  if (editing) {
    return (
      <div className="space-y-2">
        <Textarea
          aria-label="Описание"
          rows={10}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus
          className="font-mono"
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() =>
              update.mutate(
                { description: value.trim() || null },
                { onSuccess: () => setEditing(false) },
              )
            }
            disabled={update.isPending}
          >
            Сохранить
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            Отмена
          </Button>
        </div>
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {task.description ? (
        <MarkdownText>{task.description}</MarkdownText>
      ) : (
        <p className="text-fg-muted text-sm">Описания нет.</p>
      )}
      {writable && (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setValue(task.description ?? '')
            setEditing(true)
          }}
        >
          {task.description ? 'Изменить описание' : 'Добавить описание'}
        </Button>
      )}
    </div>
  )
}

function Properties({
  task,
  workspace,
  writable,
}: {
  task: TaskRead
  workspace: WorkspaceRead
  writable: boolean
}) {
  const update = useUpdateTask(task)
  const setLabels = useSetLabels(task)
  const states = useStates(task.team_id).data ?? []
  const members = useMembers('workspace', workspace.id).data ?? []
  const projects = useProjects(task.team_id).data ?? []
  const labels = useLabels(workspace.id, task.team_id).data ?? []
  const disabled = !writable
  const error = update.error ?? setLabels.error

  return (
    <div className="space-y-3">
      {error && <Alert>{humanMessage(error)}</Alert>}
      <Property label="Статус">
        <div className="flex items-center gap-2">
          {task.state && <StateIcon type={task.state.type} />}
          <Select
            aria-label="Статус"
            className="w-full"
            disabled={disabled}
            value={task.state_id}
            onChange={(e) => update.mutate({ state_id: e.target.value })}
          >
            {states.map((state) => (
              <option key={state.id} value={state.id}>
                {state.name}
              </option>
            ))}
          </Select>
        </div>
      </Property>
      <Property label="Приоритет">
        <div className="flex items-center gap-2">
          <PriorityIcon priority={task.priority} />
          <Select
            aria-label="Приоритет"
            className="w-full"
            disabled={disabled}
            value={task.priority}
            onChange={(e) => update.mutate({ priority: Number(e.target.value) })}
          >
            {[0, 1, 2, 3, 4].map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABELS[p]}
              </option>
            ))}
          </Select>
        </div>
      </Property>
      <Property label="Исполнитель">
        <div className="flex items-center gap-2">
          {task.assignee && <Avatar name={task.assignee.full_name} />}
          <Select
            aria-label="Исполнитель"
            className="w-full"
            disabled={disabled}
            value={task.assignee_id ?? ''}
            onChange={(e) => update.mutate({ assignee_id: e.target.value || null })}
          >
            <option value="">Не назначен</option>
            {members.map((member) => (
              <option key={member.user_id} value={member.user_id}>
                {member.full_name}
              </option>
            ))}
          </Select>
        </div>
      </Property>
      <Property label="Срок">
        <Input
          aria-label="Срок"
          type="date"
          className="h-9"
          disabled={disabled}
          value={task.due_date ?? ''}
          onChange={(e) => update.mutate({ due_date: e.target.value || null })}
        />
      </Property>
      <Property label="Проект">
        <Select
          aria-label="Проект"
          className="w-full"
          disabled={disabled}
          value={task.project_id ?? ''}
          onChange={(e) => update.mutate({ project_id: e.target.value || null })}
        >
          <option value="">Без проекта</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </Select>
      </Property>
      <Property label="Метки">
        <fieldset className="flex flex-wrap gap-1.5" aria-label="Метки">
          {labels.length === 0 && <span className="text-fg-muted text-sm">Меток нет</span>}
          {labels.map((label) => {
            const on = task.label_ids.includes(label.id)
            return (
              <label
                key={label.id}
                className={`border-border cursor-pointer rounded-full border px-2 py-0.5 text-xs ${on ? 'bg-accent text-accent-fg font-semibold' : ''}`}
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={on}
                  disabled={disabled}
                  onChange={() =>
                    setLabels.mutate(
                      on ? task.label_ids.filter((id) => id !== label.id) : [...task.label_ids, label.id],
                    )
                  }
                />
                {label.name}
              </label>
            )
          })}
        </fieldset>
      </Property>
      {task.creator && (
        <Property label="Автор">
          <span className="text-sm">{task.creator.full_name}</span>
        </Property>
      )}
      <Property label="Создана">
        <span className="text-sm">{formatDateTime(task.created_at)}</span>
      </Property>
    </div>
  )
}

function Subtasks({ task, workspace, writable }: { task: TaskRead; workspace: WorkspaceRead; writable: boolean }) {
  const subtasks = useSubtasks(task.id).data ?? []
  const create = useCreateTask()
  const [title, setTitle] = useState('')
  return (
    <Section title={`Подзадачи · ${subtasks.length}`}>
      <div className="border-border divide-border divide-y rounded-md border">
        {subtasks.map((sub) => (
          <TaskRow key={sub.id} workspace={workspace.slug} task={sub} />
        ))}
        {writable && (
          <form
            className="flex gap-2 p-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (!title.trim()) return
              create.mutate(
                {
                  title: title.trim(),
                  team_id: task.team_id,
                  project_id: task.project_id,
                  parent_id: task.id,
                  priority: 0,
                },
                { onSuccess: () => setTitle('') },
              )
            }}
          >
            <Input
              aria-label="Новая подзадача"
              placeholder="Новая подзадача"
              className="h-9"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <Button type="submit" size="sm" disabled={create.isPending}>
              Добавить
            </Button>
          </form>
        )}
      </div>
      {create.error && <Alert>{humanMessage(create.error)}</Alert>}
    </Section>
  )
}

function Relations({ task, workspace, writable }: { task: TaskRead; workspace: WorkspaceRead; writable: boolean }) {
  const add = useAddRelation(task)
  const remove = useRemoveRelation(task)
  const [type, setType] = useState<RelationCreate['type']>('relates_to')
  const [target, setTarget] = useState('')
  const relations = task.relations ?? []
  return (
    <Section title="Связи">
      {relations.length > 0 && (
        <ul className="space-y-1">
          {relations.map((relation) => (
            <li key={relation.id} className="flex items-center gap-2 text-sm">
              <span className="text-fg-muted w-28 shrink-0">{RELATION_LABELS[relation.type]}</span>
              <Link
                to="/w/$workspace/task/$key"
                params={{ workspace: workspace.slug, key: relation.task.key }}
                className="min-w-0 flex-1 truncate hover:underline"
              >
                <span className="text-fg-muted font-mono text-xs">{relation.task.key}</span>{' '}
                {relation.task.title}
              </Link>
              {writable && (
                <button
                  type="button"
                  aria-label={`Удалить связь с ${relation.task.key}`}
                  onClick={() => remove.mutate(relation.id)}
                  className="text-fg-muted hover:text-fg rounded p-1"
                >
                  <X aria-hidden="true" className="size-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {writable && (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (!target.trim()) return
            add.mutate({ type, target_id: target.trim() }, { onSuccess: () => setTarget('') })
          }}
        >
          <Select aria-label="Тип связи" value={type} onChange={(e) => setType(e.target.value as RelationCreate['type'])}>
            {(['relates_to', 'blocks', 'blocked_by', 'duplicates'] as const).map((value) => (
              <option key={value} value={value}>
                {RELATION_LABELS[value]}
              </option>
            ))}
          </Select>
          <Input
            aria-label="Ключ задачи"
            placeholder="ENG-12"
            className="h-9 w-32"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
          <Button type="submit" size="sm" variant="secondary" disabled={add.isPending}>
            Связать
          </Button>
        </form>
      )}
      {(add.error ?? remove.error) && <Alert>{humanMessage(add.error ?? remove.error)}</Alert>}
    </Section>
  )
}

function Discussion({ task, workspace, writable }: { task: TaskRead; workspace: WorkspaceRead; writable: boolean }) {
  const comments = useComments(task.id).data ?? []
  const activities = useActivities(task.id).data ?? []
  const members = useMembers('workspace', workspace.id).data ?? []
  const add = useAddComment(task.id)
  const [body, setBody] = useState('')
  const name = (id: string) => members.find((m) => m.user_id === id)?.full_name ?? 'Участник'

  // Комментарии и история — одна лента по времени: так читается, что за чем было.
  const feed = [
    ...comments.map((c) => ({ at: c.created_at, kind: 'comment' as const, item: c })),
    ...activities
      .filter((a) => a.type !== 'commented')
      .map((a) => ({ at: a.created_at, kind: 'activity' as const, item: a })),
  ].sort((a, b) => a.at.localeCompare(b.at))

  return (
    <Section title="Обсуждение и история">
      <ol className="space-y-3">
        {feed.map((entry) =>
          entry.kind === 'comment' ? (
            <li key={`c${entry.item.id}`} className="border-border bg-surface rounded-md border p-3">
              <p className="text-fg-muted mb-1 flex items-center gap-2 text-xs">
                <Avatar name={name(entry.item.author_id)} className="size-5" />
                <span className="text-fg font-semibold">{name(entry.item.author_id)}</span>
                {entry.item.author_token_id && <span>через токен</span>}
                <span>{formatDateTime(entry.item.created_at)}</span>
              </p>
              <MarkdownText>{entry.item.body}</MarkdownText>
            </li>
          ) : (
            <li key={`a${entry.item.id}`} className="text-fg-muted flex flex-wrap gap-1 px-1 text-xs">
              <span className="text-fg">{name(entry.item.actor_id)}</span>
              {ACTIVITY_LABELS[entry.item.type]}
              {entry.item.actor_token_id && <span>(через токен)</span>}
              <span>· {formatDateTime(entry.item.created_at)}</span>
            </li>
          ),
        )}
      </ol>
      {writable && (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (!body.trim()) return
            add.mutate(body.trim(), { onSuccess: () => setBody('') })
          }}
        >
          <Textarea
            aria-label="Комментарий"
            placeholder="Комментарий — Markdown, @email для упоминания"
            rows={3}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit()
            }}
          />
          {add.error && <Alert>{humanMessage(add.error)}</Alert>}
          <Button type="submit" size="sm" disabled={add.isPending}>
            Отправить
          </Button>
        </form>
      )}
    </Section>
  )
}

export function TaskPage() {
  const workspace = useCurrentWorkspace()
  const { key = '' } = useParams({ strict: false })
  const task = useTask(key)
  const writable = canWrite(useSession())
  const remove = useDeleteTask(task.data ?? { id: '', key })
  const navigate = useNavigate()
  const [deleting, setDeleting] = useState(false)

  if (!workspace) return null
  if (task.isError) {
    return (
      <div className="p-8 text-center">
        <p className="text-fg-muted text-sm">Задача {key.toUpperCase()} не найдена или недоступна.</p>
      </div>
    )
  }
  if (!task.data) return null
  const data = task.data

  return (
    <article className="mx-auto grid w-full max-w-6xl gap-6 p-4 sm:p-6 lg:grid-cols-[1fr_20rem]">
      <div className="min-w-0 space-y-6">
        <div className="space-y-1">
          <p className="text-fg-muted flex flex-wrap items-center gap-2 text-sm">
            <span className="font-mono">{data.key}</span>
            {data.parent && (
              <>
                <span aria-hidden="true">·</span>
                <span>подзадача</span>
                <Link
                  to="/w/$workspace/task/$key"
                  params={{ workspace: workspace.slug, key: data.parent.key }}
                  className="hover:underline"
                >
                  {data.parent.key} {data.parent.title}
                </Link>
              </>
            )}
          </p>
          <Title key={data.title} task={data} writable={writable} />
        </div>
        <Description key={data.description ?? ''} task={data} writable={writable} />
        <Subtasks task={data} workspace={workspace} writable={writable} />
        <Relations task={data} workspace={workspace} writable={writable} />
        <Discussion task={data} workspace={workspace} writable={writable} />
      </div>
      <aside className="border-border bg-surface h-fit space-y-4 rounded-lg border p-4 lg:sticky lg:top-4">
        <Properties task={data} workspace={workspace} writable={writable} />
        {writable && (
          <Button variant="danger" size="sm" onClick={() => setDeleting(true)}>
            <Trash2 aria-hidden="true" className="size-4" />
            Удалить
          </Button>
        )}
      </aside>
      <Dialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Удалить ${data.key}?`}
        description="Задача пропадёт из списков. Её можно восстановить через API и CLI: tkl task restore."
      >
        {remove.error && <Alert className="mb-3">{humanMessage(remove.error)}</Alert>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDeleting(false)}>
            Отмена
          </Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(undefined, {
                onSuccess: () => void navigate({ to: '/w/$workspace', params: { workspace: workspace.slug } }),
              })
            }
          >
            Удалить
          </Button>
        </div>
      </Dialog>
    </article>
  )
}
