import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'

/**
 * Куда вернуть человека после входа.
 *
 * Только внутренний путь: подставленный в параметр чужой адрес превратил бы
 * форму входа в открытый редирект на фишинговую копию.
 */
function internalPath(value: string | undefined): string | undefined {
  if (!value?.startsWith('/') || value.startsWith('//')) {
    return undefined
  }
  return value
}

const searchSchema = z.object({
  redirect: z.string().optional().transform(internalPath),
})

export const Route = createFileRoute('/login')({
  validateSearch: searchSchema,
  component: LoginPage,
})

function LoginPage() {
  return (
    <div className="bg-canvas text-fg flex min-h-full items-center justify-center p-6">
      <h1 className="text-xl font-medium">Вход</h1>
    </div>
  )
}
