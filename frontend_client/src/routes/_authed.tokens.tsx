import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/_authed/tokens')({
  component: TokensPage,
})

function TokensPage() {
  return (
    <div className="mx-auto w-full max-w-3xl p-4 sm:p-6">
      <h1 className="text-xl font-medium">Токены доступа</h1>
    </div>
  )
}
