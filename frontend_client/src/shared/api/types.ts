/**
 * Короткие имена для типов из сгенерированной схемы.
 *
 * `components['schemas']['MeResponse']` в сигнатуре читается плохо, а сам
 * `schema.d.ts` править нельзя — он пересобирается из OpenAPI.
 */

import type { components } from './schema'

export type Me = components['schemas']['MeResponse']
export type UserRead = components['schemas']['UserRead']
export type UserUpdate = components['schemas']['UserUpdate']
export type SessionResponse = components['schemas']['SessionResponse']
export type LoginRequest = components['schemas']['LoginRequest']
export type RegisterRequest = components['schemas']['RegisterRequest']
export type TokenRead = components['schemas']['TokenRead']
export type TokenCreate = components['schemas']['TokenCreate']
export type TokenCreated = components['schemas']['TokenCreated']
export type TokenList = components['schemas']['TokenList']
export type InstanceRole = components['schemas']['InstanceRole']
export type TokenScope = components['schemas']['TokenScope']
export type AuthMethod = components['schemas']['AuthMethod']
export type Memberships = components['schemas']['Memberships']
export type InvitationPreview = components['schemas']['InvitationPreview']
export type InvitationAccept = components['schemas']['InvitationAccept']
export type InvitationAccepted = components['schemas']['InvitationAccepted']

type Schemas = components['schemas']

export type WorkspaceRead = Schemas['WorkspaceRead']
export type WorkspaceCreate = Schemas['WorkspaceCreate']
export type WorkspaceRole = Schemas['WorkspaceRole']
export type WorkspaceMemberRead = Schemas['WorkspaceMemberRead']
export type TeamRead = Schemas['TeamRead']
export type TeamCreate = Schemas['TeamCreate']
export type TeamRole = Schemas['TeamRole']
export type TeamMemberRead = Schemas['TeamMemberRead']
export type ProjectRead = Schemas['ProjectRead']
export type ProjectCreate = Schemas['ProjectCreate']
export type ProjectStatus = Schemas['ProjectStatus']
export type ProjectRole = Schemas['ProjectRole']
export type ProjectMemberRead = Schemas['ProjectMemberRead']
export type StateRead = Schemas['StateRead']
export type StateCreate = Schemas['StateCreate']
export type StateUpdate = Schemas['StateUpdate']
export type StateType = Schemas['StateType']
export type LabelRead = Schemas['LabelRead']
export type LabelCreate = Schemas['LabelCreate']
export type TaskRead = Schemas['TaskRead']
export type TaskCreate = Schemas['TaskCreate']
export type TaskUpdate = Schemas['TaskUpdate']
export type TaskMove = Schemas['TaskMove']
export type TaskGroup = Schemas['TaskGroup']
export type RelationRead = Schemas['RelationRead']
export type RelationCreate = Schemas['RelationCreate']
export type CommentRead = Schemas['CommentRead']
export type ActivityRead = Schemas['ActivityRead']
export type ActivityType = Schemas['ActivityType']
export type NotificationRead = Schemas['NotificationRead']
export type NotificationType = Schemas['NotificationType']
export type ViewRead = Schemas['ViewRead']
export type ViewCreate = Schemas['ViewCreate']
export type ViewUpdate = Schemas['ViewUpdate']
export type ViewQuery = Schemas['ViewQuery']
export type ViewGroupBy = Schemas['ViewGroupBy']
export type ViewSortBy = Schemas['ViewSortBy']
export type ViewLayout = Schemas['ViewLayout']
export type ViewScope = Schemas['ViewScope']
export type SortDirection = Schemas['SortDirection']
export type QueryTasks = Schemas['QueryTasks']
export type ViewTasks = Schemas['ViewTasks']
export type InvitationRead = Schemas['InvitationRead']
export type InvitationCreate = Schemas['InvitationCreate']
export type InvitationScope = Schemas['InvitationScope']

/** Условие фильтра грамматики views (§4 модели данных): `{op, value}` на поле. */
export interface FilterCondition {
  op: string
  value?: unknown
}
export type Filters = Record<string, FilterCondition>
