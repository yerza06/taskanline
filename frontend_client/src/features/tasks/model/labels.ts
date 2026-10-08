import type {
  ActivityType,
  NotificationType,
  StateType,
  ViewGroupBy,
  ViewSortBy,
} from '@/shared/api/types'

/** Подписи значений API на языке интерфейса. */

export const PRIORITY_LABELS: Record<number, string> = {
  0: 'Без приоритета',
  1: 'Срочный',
  2: 'Высокий',
  3: 'Средний',
  4: 'Низкий',
}

export const STATE_TYPE_LABELS: Record<StateType, string> = {
  backlog: 'Бэклог',
  unstarted: 'Не начата',
  started: 'В работе',
  completed: 'Завершена',
  canceled: 'Отменена',
}

export const STATE_TYPES: StateType[] = ['backlog', 'unstarted', 'started', 'completed', 'canceled']

export const GROUP_LABELS: Record<ViewGroupBy | 'none', string> = {
  none: 'Без группировки',
  state: 'По статусу',
  assignee: 'По исполнителю',
  priority: 'По приоритету',
  project: 'По проекту',
  label: 'По метке',
  due_date: 'По сроку',
}

export const SORT_LABELS: Record<ViewSortBy, string> = {
  manual: 'Вручную',
  priority: 'По приоритету',
  due_date: 'По сроку',
  created_at: 'По дате создания',
  updated_at: 'По дате изменения',
  title: 'По названию',
}

export const ACTIVITY_LABELS: Record<ActivityType, string> = {
  task_created: 'создал(а) задачу',
  title_changed: 'изменил(а) название',
  description_changed: 'изменил(а) описание',
  state_changed: 'сменил(а) статус',
  assignee_changed: 'сменил(а) исполнителя',
  priority_changed: 'сменил(а) приоритет',
  due_date_changed: 'изменил(а) срок',
  project_changed: 'перенёс(ла) в другой проект',
  parent_changed: 'сменил(а) родительскую задачу',
  label_added: 'добавил(а) метку',
  label_removed: 'снял(а) метку',
  relation_added: 'добавил(а) связь',
  relation_removed: 'удалил(а) связь',
  commented: 'оставил(а) комментарий',
  task_moved: 'переставил(а) задачу',
  task_deleted: 'удалил(а) задачу',
  task_restored: 'восстановил(а) задачу',
}

export const NOTIFICATION_LABELS: Record<NotificationType, string> = {
  mentioned: 'упомянул(а) вас',
  assigned: 'назначил(а) на вас',
  commented: 'прокомментировал(а)',
  state_changed: 'сменил(а) статус',
}

export const RELATION_LABELS: Record<string, string> = {
  blocks: 'Блокирует',
  blocked_by: 'Заблокирована',
  relates_to: 'Связана с',
  duplicates: 'Дублирует',
  duplicated_by: 'Дублируется',
}
