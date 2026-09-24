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
