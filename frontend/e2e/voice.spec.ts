import { expect, test } from '@playwright/test'

// Chromium's fake microphone; no API key on the test backend, so the live path is
// unavailable and the recording is transcribed by the (stubbed) fallback upload.
test.use({
  permissions: ['microphone'],
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
})

test('hold to talk fills the textbox; the user still sends', async ({ page, isMobile }) => {
  test.skip(!!isMobile, 'pointer-hold journey is desktop; touch uses the same pointer events')
  let uploads = 0
  await page.route('**/api/audio/transcribe', route => {
    uploads++
    return route.fulfill({ json: { transcript: 'My landlord kept my deposit', editable: true } })
  })
  await page.goto('/')
  const box = page.getByRole('textbox', { name: 'Message', exact: true })
  await expect(box).toBeEnabled()
  const mic = page.getByRole('button', { name: 'Hold to talk, or hold Space' })

  // A quick tap starts nothing.
  await mic.click()
  await expect(page.getByRole('status')).toHaveText('Hold to talk, or hold Space')

  // Hold, speak, release.
  const area = (await mic.boundingBox())!
  await page.mouse.move(area.x + area.width / 2, area.y + area.height / 2)
  await page.mouse.down()
  await expect(page.getByRole('status')).toContainText('Listening')
  await expect(page.getByRole('button', { name: 'Send message' })).toBeDisabled()
  await page.waitForTimeout(800)
  await page.mouse.up()

  await expect(box).toHaveValue('My landlord kept my deposit')
  expect(uploads).toBe(1)
  await expect(page.getByRole('button', { name: 'Send message' })).toBeEnabled()
})
