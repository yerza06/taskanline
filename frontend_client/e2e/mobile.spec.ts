import { expect, test, type Page } from '@playwright/test'

import { createTeam, createWorkspace, quickCreate, signUp, unique } from './helpers.ts'

test.use({ viewport: { width: 360, height: 740 } })

/** Страница не уезжает вбок: всё, что шире экрана, прокручивается внутри себя. */
async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
}

test('на экране 360px всё помещается, меню открывается кнопкой', async ({ page }) => {
  const slug = unique('m')
  await signUp(page, `${slug}@example.com`, 'Мира Мобильная')
  await expectNoHorizontalScroll(page)
  await createWorkspace(page, 'Телефон', slug)

  // Меню на узком экране спрятано и выезжает по кнопке.
  await page.getByRole('button', { name: 'Открыть меню' }).click()
  await createTeam(page, 'ENG', 'Инженерия')
  const key = await quickCreate(page, 'Очень длинное название задачи, которое не должно растянуть страницу')
  await expectNoHorizontalScroll(page)

  for (const path of [`/w/${slug}/team/ENG`, `/w/${slug}/team/ENG?layout=board`, `/w/${slug}/task/${key}`]) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expectNoHorizontalScroll(page)
  }
})
