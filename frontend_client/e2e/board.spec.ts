import { expect, test } from '@playwright/test'

import { createTeam, createWorkspace, quickCreate, signUp, unique } from './helpers.ts'

/** Перетаскивание на доске — и мышью, и с клавиатуры. */
test('доска: перенос задачи между колонками мышью и клавиатурой', async ({ page }) => {
  const slug = unique('d')
  await signUp(page, `${slug}@example.com`, 'Дина Доска')
  await createWorkspace(page, 'Доска', slug)
  await createTeam(page, 'ENG', 'Инженерия')
  await quickCreate(page, 'Тащить мышью')
  await page.goto(`/w/${slug}/team/ENG`)
  await quickCreate(page, 'Тащить клавиатурой')
  await page.goto(`/w/${slug}/team/ENG?layout=board`)

  const column = (name: string) => page.getByRole('main').getByRole('region', { name })
  await expect(column('Todo')).toContainText('Тащить мышью')

  // Мышью: за ручку карточки в колонку «In Progress».
  const handle = page.getByRole('button', { name: 'Переместить ENG-1' })
  const target = column('In Progress')
  const from = await handle.boundingBox()
  const to = await target.boundingBox()
  if (!from || !to) throw new Error('Нет координат')
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(from.x + 20, from.y + 20, { steps: 5 })
  await page.mouse.move(to.x + to.width / 2, to.y + 60, { steps: 15 })
  await page.mouse.up()
  await expect(column('In Progress')).toContainText('Тащить мышью')

  // Клавиатурой: пробел — взять, стрелка вправо — соседняя колонка, пробел — положить.
  // dnd-kit обрабатывает клавиши по кадрам анимации — между нажатиями нужна пауза.
  await page.getByRole('button', { name: 'Переместить ENG-2' }).focus()
  for (const key of ['Space', 'ArrowRight', 'Space']) {
    await page.keyboard.press(key)
    await page.waitForTimeout(250)
  }
  await expect(column('In Progress')).toContainText('Тащить клавиатурой')

  // Перенос сохранён на сервере, а не только на экране.
  await page.reload()
  await expect(column('In Progress')).toContainText('Тащить мышью')
  await expect(column('In Progress')).toContainText('Тащить клавиатурой')
})
