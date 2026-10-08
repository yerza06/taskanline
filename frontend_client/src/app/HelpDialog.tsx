import { SHORTCUTS } from '@/app/hotkeys'
import { useUi } from '@/app/ui-store'
import { Dialog } from '@/shared/ui/Dialog'

export function HelpDialog() {
  const open = useUi((state) => state.helpOpen)
  const setOpen = useUi((state) => state.setHelpOpen)
  return (
    <Dialog open={open} onOpenChange={setOpen} title="Горячие клавиши" description="Работают вне полей ввода.">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        {SHORTCUTS.map(([keys, action]) => (
          <div key={keys} className="contents">
            <dt>
              {keys.split(' ').map((key) => (
                <kbd key={key} className="border-border bg-surface-hover mr-1 rounded border px-1.5 font-mono text-xs">
                  {key}
                </kbd>
              ))}
            </dt>
            <dd className="text-fg-muted">{action}</dd>
          </div>
        ))}
      </dl>
    </Dialog>
  )
}
