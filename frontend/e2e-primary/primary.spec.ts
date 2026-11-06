import { expect, test } from '@playwright/test'

test('Strict Mode initializes one anonymous owner session without a startup race',async({page})=>{
  let bootstraps=0
  page.on('request',request=>{if(new URL(request.url()).pathname==='/api/bootstrap')bootstraps++})
  await page.goto('/')
  await expect(page.getByRole('textbox',{name:'Message',exact:true})).toBeEnabled()
  expect(bootstraps).toBe(1)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('textbox',{name:'Message',exact:true})).toBeEnabled()
  expect(bootstraps).toBe(2)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('primary runner preserves familiar UI, history and general-question isolation',async({page})=>{
  await page.goto('/')
  const box=page.getByRole('textbox',{name:'Message',exact:true})
  await expect(box).toBeEnabled()
  const cid=new URL(page.url()).pathname.split('/').at(-1)
  const before=await (await page.request.get(`/api/conversations/${cid}`)).json()
  await box.fill('Explain cognizable and non-cognizable offences under current Indian law.')
  await page.getByRole('button',{name:'Send message',exact:true}).click()
  await expect(page.getByRole('main').getByText(/AI configuration required:/)).toBeVisible()
  await page.reload()
  const after=await (await page.request.get(`/api/conversations/${cid}`)).json()
  expect(after.case_memory).toEqual(before.case_memory)
  expect(after.messages.at(-1).metadata.engine_version).toBe('primary-agent-v2.0')
  expect(after.messages.at(-1).metadata.metrics.provider_requests_reserved).toBe(0)
  await expect(box).toHaveValue('')
})

test('emergency guidance survives reload and is shown once',async({page})=>{
  await page.goto('/')
  const box=page.getByRole('textbox',{name:'Message',exact:true})
  await expect(box).toBeEnabled()
  await box.fill('Police entered our room in India and demand money now.')
  await page.getByRole('button',{name:'Send message',exact:true}).click()
  await expect(page.getByRole('main').getByText(/call 112/)).toHaveCount(1)
  await expect(page.getByRole('main').getByText(/AI configuration required:/)).toBeVisible()
  await page.reload()
  await expect(page.getByRole('main').getByText(/call 112/)).toHaveCount(1)
})

test('workflow drawer supports the new engine without hardcoded legacy nodes',async({page,isMobile})=>{
  await page.goto('/')
  await expect(page.getByRole('textbox',{name:'Message',exact:true})).toBeEnabled()
  if(isMobile)await page.getByLabel('Open chat history').click()
  await page.getByText('Agent Workflow',{exact:true}).click()
  await expect(page.getByText('Primary reasoning agent',{exact:true})).toBeVisible()
  await expect(page.getByText('Immediate safety guidance',{exact:true})).toBeVisible()
  await expect(page.getByText('Claim checks and adaptive review',{exact:true})).toBeVisible()
  await page.screenshot({path:`test-results/v2-workflow-${test.info().project.name}.png`})
})
