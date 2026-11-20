import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api'
import type { Conversation, Detail } from './types'

afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()})

it('starts with a centered mic and common problems, then moves the mic into the thread composer and restores it for a new chat', async()=>{
  Object.defineProperty(HTMLElement.prototype,'scrollIntoView',{configurable:true,value:vi.fn()})
  const conversation:Conversation={id:'home',title:'New chat',language:'hi',created_at:'',updated_at:''}
  const detail:Detail={conversation,messages:[],summary:'',attachments:[],drafts:[],case_memory:{version:1,domain:'',facts:{},contradictions:[],unknowns:[],actions_completed:[],evidence:[]}}
  vi.spyOn(api,'bootstrap').mockResolvedValue({ai_configured:false,privacy_notice:'',disclaimer:''})
  vi.spyOn(api,'list').mockResolvedValue([conversation])
  vi.spyOn(api,'detail').mockResolvedValue(detail)
  const create=vi.spyOn(api,'create').mockResolvedValue({...conversation,id:'new'})
  let finish!:()=>void
  vi.spyOn(api,'streamTurn').mockImplementation(()=>new Promise<void>(resolve=>{finish=resolve}))
  const view=render(<App/> )
  const mic=()=>screen.getByRole('button',{name:'Hold to talk, or hold Space'})
  await waitFor(()=>expect(mic()).not.toBeDisabled())
  expect(mic().closest('.welcome-voice')).not.toBeNull()
  expect(view.container.querySelectorAll('.mic-button')).toHaveLength(1)
  expect(screen.getByRole('heading',{name:'कुछ आम परेशानियाँ'})).toBeInTheDocument()
  expect(screen.queryByText(/Add your own OpenAI/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'बैंक ने मेरे पैसे रोक रखे हैं'}))
  expect(mic().closest('.composer')).not.toBeNull()
  expect(screen.queryByRole('heading',{name:'कुछ आम परेशानियाँ'})).not.toBeInTheDocument()
  expect(view.container.querySelectorAll('.mic-button')).toHaveLength(1)
  await act(async()=>finish())
  fireEvent.click(screen.getAllByRole('button',{name:'New chat'})[0])
  await waitFor(()=>expect(create).toHaveBeenCalledWith('hi'))
  await waitFor(()=>expect(mic().closest('.welcome-voice')).not.toBeNull())
})
