import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/login')({
  component: LoginPage,
})

function LoginPage() {
  return (
    <div className="bg-canvas text-fg flex min-h-full items-center justify-center p-6">
      <h1 className="text-xl font-medium">Вход</h1>
    </div>
  )
}
