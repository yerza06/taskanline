import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/register')({
  component: RegisterPage,
})

function RegisterPage() {
  return (
    <div className="bg-canvas text-fg flex min-h-full items-center justify-center p-6">
      <h1 className="text-xl font-medium">Регистрация</h1>
    </div>
  )
}
