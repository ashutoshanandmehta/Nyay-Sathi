import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { api } from '../api'
import AgentFlowWidget from './AgentFlowWidget'
import Composer from './Composer'
import DevSpacePanel from './DevSpacePanel'
import { AgentWorkflowPanel, CasePanel, KnowledgeBasePanel, Sources } from './Drawer'
import MessageView from './MessageView'
import PracticePanel from './PracticePanel'
import SettingsPanel from './SettingsPanel'
import Sidebar from './Sidebar'

describe('chat interface',()=>{
  it('keeps partial assistance readable and allows speech only for approved content',()=>{
    const speech=vi.fn();render(<MessageView message={{id:'partial',role:'assistant',content:'Here is your factual draft.',created_at:'',status:'complete',metadata:{publication_status:'partial',verification:{passed:false,publication_safe:true}}}} onSources={()=>{}} onSpeech={speech}/>);
    expect(screen.getByText('Here is your factual draft.')).toBeInTheDocument();expect(screen.getByRole('note')).toHaveTextContent('Some help is ready');fireEvent.click(screen.getByText('Listen'));expect(speech).toHaveBeenCalledOnce()
  })
  it('distinguishes unverified public research and unknown effective dates',()=>{render(<Sources sources={[{source_id:'w',passage_id:'wp',title:'Public procedure candidate',locator:'Public webpage',text:'Supporting excerpt',canonical_url:'https://example.edu/',retrieved_at:'2026-11-06',limitations:'Current applicability requires review',origin:'web',verification_status:'unverified_public_source',effective_date:null}]}/>);expect(screen.getByText('Public source · authority not verified')).toBeInTheDocument();expect(screen.getByText('Current applicability requires review')).toBeInTheDocument();expect(screen.getByText(/Effective date unknown/)).toBeInTheDocument();expect(screen.queryByText('Official website · web research')).toBeNull()})
  it('keeps New chat visible and exposes system information',()=>{const onNew=vi.fn(),onSelect=vi.fn(),onKnowledge=vi.fn(),onWorkflow=vi.fn();render(<Sidebar open items={[{id:'1',title:'Refund case',language:'en',created_at:'',updated_at:''}]} active="1" onNew={onNew} onSelect={onSelect} onClose={()=>{}} onKnowledge={onKnowledge} onWorkflow={onWorkflow} isStreaming={true} streamEvents={[{stage:'primary'}]}/>);fireEvent.click(screen.getByText('New chat'));expect(onNew).toHaveBeenCalled();fireEvent.click(screen.getByText('Refund case'));expect(onSelect).toHaveBeenCalledWith('1');const settingsBtn=screen.getByRole('button',{name:'Settings'});expect(settingsBtn).toBeInTheDocument();fireEvent.click(settingsBtn);expect(onKnowledge).toHaveBeenCalled();const workflowBtn=screen.getByRole('button',{name:'Workflow'});expect(workflowBtn).toBeInTheDocument();fireEvent.click(workflowBtn);expect(onWorkflow).toHaveBeenCalled()})
  it('clears immediately and restores a failed draft',async()=>{let finish!:(ok:boolean)=>void;const send=vi.fn(()=>new Promise<boolean>(resolve=>{finish=resolve}));render(<Composer disabled={false} onSend={send} onUpload={()=>{}}/>);const input=screen.getByLabelText('Message');fireEvent.change(input,{target:{value:'My refund is late'}});fireEvent.keyDown(input,{key:'Enter',shiftKey:false});expect(send).toHaveBeenCalledWith('My refund is late');expect(input).toHaveValue('');await act(async()=>finish(false));await waitFor(()=>expect(input).toHaveValue('My refund is late'))})
  it('renders markdown without unsafe raw HTML',()=>{render(<MessageView message={{id:'m',role:'assistant',content:'**Safe** <script>alert(1)</script>',created_at:'',status:'complete',metadata:{}}} onSources={()=>{}}/>);expect(screen.getByText('Safe')).toBeInTheDocument();expect(document.querySelector('script')).toBeNull()})
  it('opens inspectable official source content',()=>{render(<Sources sources={[{source_id:'s',passage_id:'p',title:'Consumer Protection Act 2019',locator:'Section 69',text:'Two years',canonical_url:'https://www.indiacode.nic.in/',retrieved_at:'2026-11-05',limitations:'Check applicability'}]}/>);expect(screen.getByText('Section 69')).toBeInTheDocument();expect(screen.getByText('Check applicability')).toBeInTheDocument()})
  it('shows friendly case facts and evidence without internal identifiers',()=>{render(<CasePanel detail={{conversation:{id:'c',title:'Case',language:'en',created_at:'',updated_at:''},messages:[],summary:'Domain: consumer. Facts: amount=8000 [user_allegation]',attachments:[{id:'a',filename:'invoice.pdf',mime_type:'application/pdf',extraction_status:'partial',extracted_text:''}],drafts:[],case_memory:{version:2,domain:'consumer',facts:{amount:{value:'8000',status:'user_allegation'}},contradictions:[{description:'Was 18000'}],unknowns:[],actions_completed:[],evidence:[]}}}/>);expect(screen.getAllByText('8000').length).toBeGreaterThan(0);expect(screen.getByText('Partial')).toBeInTheDocument();expect(screen.getByText('Was 18000')).toBeInTheDocument();expect(screen.queryByText(/user_allegation/)).toBeNull();expect(screen.queryByText(/private upload a/)).toBeNull()})
  it('shows layered knowledge and actual indexed source counts',()=>{render(<KnowledgeBasePanel data={{corpus_version:'abc',collection_name:'law',total_passages:24,vector_index_enabled:true,vector_passages:24,retrieval_pipeline:['BM25'],knowledge_id:'consumer-v1',knowledge_version:'1',last_checked:'2026-11-05',review_status:'pending_indian_lawyer_review',scope:'Consumer disputes',separation_rule:'Private evidence stays outside the shared index.',layers:[{id:'evidence',label:'Evidence playbooks',count:7,storage:'versioned playbook'}],intake_playbooks:[],evidence_playbooks:[],procedures:[],templates:[],selected_judgments:[],lawyer_preparation:{pack_sections:[],consultation_questions:[],source_ids:[]},referrals:[],storage_map:[{store:'SQLite private case workspace',content:'User facts'}],sources:[{source_id:'act',title:'Consumer Protection Act 2019',issuing_authority:'India Code',canonical_url:'https://www.indiacode.nic.in',source_type:'statute',jurisdiction:'India',retrieved_at:'2026-11-05',verification_status:'verified_official',known_limitations:'Selected passages',passage_count:6,vector_passage_count:6,locators:['Section 35']} ]}}/>);expect(screen.getByText('24 searchable passages')).toBeInTheDocument();expect(screen.getByText('Evidence playbooks')).toBeInTheDocument();fireEvent.click(screen.getByRole('tab',{name:'sources'}));expect(screen.getAllByText('Consumer Protection Act 2019').length).toBeGreaterThan(0);expect(screen.getByText('Section 35')).toBeInTheDocument()})
  it('shows workflow branches and decision rules',()=>{render(<AgentWorkflowPanel data={{name:'flow',version:'v2',nodes:['checks','context','triage','intake','research','respond','review','revise','verify','persist','withhold'].map(id=>({id,label:id,detail:`${id} detail`})),edges:[{from:'intake',to:'research',condition:'needs_retrieval'}],decisions:[{if:'law asked',then:'retrieve'}],limits:{model_calls_per_turn:4,retrieval_expansions:1,revision_attempts:1}}}/>);expect(screen.getByText('IF needs_retrieval?')).toBeInTheDocument();expect(screen.getByText('IF review passes?')).toBeInTheDocument();expect(screen.getByText('IF verification passes?')).toBeInTheDocument();expect(screen.getByText('law asked')).toBeInTheDocument()})
  it('renders streaming safety event as an alert card rather than a duplicate message bubble',async()=>{
    cleanup()
    Element.prototype.scrollIntoView=vi.fn()
    let finishStream!:()=>void
    const conv={id:'c-safe',title:'Emergency chat',language:'en' as const,created_at:'',updated_at:''}
    const baseDetail={conversation:conv,messages:[],safety_messages:[],case_memory:{version:0,domain:'unknown',facts:{},contradictions:[],unknowns:[],actions_completed:[],evidence:[]},summary:'',attachments:[],drafts:[]}
    vi.spyOn(api,'bootstrap').mockResolvedValue({ai_configured:true,privacy_notice:'',disclaimer:''})
    vi.spyOn(api,'list').mockResolvedValue([conv])
    let detailCalls=0
    vi.spyOn(api,'detail').mockImplementation(async()=>{
      detailCalls++
      if(detailCalls===1)return baseDetail
      return {...baseDetail,messages:[{id:'u1',role:'user',content:'Police entered room',created_at:'',status:'complete',metadata:{}},{id:'a1',role:'assistant',content:'Verified answer.',created_at:'',status:'complete',metadata:{safety_messages:[{type:'safety',content_id:'s1',text:'Call 112 if safe.',request_id:'req-fixed',sources:[]}],resolution_blocks:[{block_id:'b1',block_type:'direct_answer',title:'Direct answer',content:'Verified answer.',items:[],claim_ids:['c1'],source_ids:[],sources:[],grounding:'verified_legal_source'}]}}]}
    })
    vi.spyOn(api,'streamTurn').mockImplementation(async(_id,_text,_lang,reqId,_files,onProgress)=>{
      onProgress({stage:'safety',type:'safety',content_id:'s1',text:'Call 112 if safe.',request_id:reqId})
      onProgress({stage:'primary',status:'running'})
      await new Promise<void>(r=>{finishStream=r})
    })
    const origUUID=crypto.randomUUID
    vi.spyOn(crypto,'randomUUID').mockReturnValue('req-fixed' as `${string}-${string}-${string}-${string}-${string}`)
    try{
      const view=render(<App/>)
      const scoped=within(view.container)
      await waitFor(()=>expect(scoped.getByLabelText('Message')).not.toBeDisabled())
      const box=scoped.getByLabelText('Message')
      fireEvent.change(box,{target:{value:'Police entered room'}})
      fireEvent.keyDown(box,{key:'Enter',shiftKey:false})
      const alertCard=await scoped.findByRole('alert')
      expect(alertCard).toHaveTextContent('Immediate Protective Advisory')
      expect(alertCard).toHaveTextContent('Call 112 if safe.')
      await act(async()=>finishStream())
      await waitFor(()=>expect(scoped.getByText('Verified answer.')).toBeInTheDocument())
      expect(scoped.queryByText('Immediate Protective Advisory')).toBeNull()
      expect(scoped.getAllByText('Call 112 if safe.')).toHaveLength(1)
    }finally{
      crypto.randomUUID=origUUID
      vi.restoreAllMocks()
      cleanup()
    }
  })
})

describe('numbered citations',()=>{
  const cited=[
    {source_id:'bnss',passage_id:'fir',title:'BNSS 2023',locator:'Section 173',text:'Information of a cognizable offence',canonical_url:'https://www.indiacode.nic.in/bnss.pdf',retrieved_at:'2026-11-07',limitations:'',citation_number:1},
    {source_id:'hc',passage_id:'hc-p',title:'Madras High Court',locator:'W.P. order',text:'Order text',canonical_url:'https://hcmadras.tn.gov.in/',retrieved_at:'2026-11-07',limitations:'',citation_number:2},
  ]
  const content='An FIR records a cognizable offence. [1](#cite-1)\n\nA court may be approached. [1](#cite-1)[2](#cite-2)'
  it('renders markers as numbered chips that open the matching source',()=>{
    cleanup()
    const onSources=vi.fn();render(<MessageView message={{id:'c',role:'assistant',content,created_at:'',status:'complete',metadata:{sources:cited}}} onSources={onSources}/>)
    expect(screen.getAllByRole('button',{name:'Source 1: BNSS 2023'})).toHaveLength(2)
    expect(screen.queryByText('#cite-1')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Source 2: Madras High Court'}))
    expect(onSources).toHaveBeenCalledWith(cited,2)
  })
  it('copies plain numbers with a numbered source list',async()=>{
    cleanup()
    const writeText=vi.fn().mockResolvedValue(undefined);Object.defineProperty(navigator,'clipboard',{value:{writeText},configurable:true})
    render(<MessageView message={{id:'c',role:'assistant',content,created_at:'',status:'complete',metadata:{sources:cited}}} onSources={()=>{}}/>)
    fireEvent.click(screen.getByRole('button',{name:/^Copy$/}))
    await waitFor(()=>expect(writeText).toHaveBeenCalled())
    const copied=writeText.mock.calls[0][0] as string
    expect(copied).toContain('offence. [1]\n\nA court may be approached. [1][2]')
    expect(copied).toContain('Sources:\n[1] BNSS 2023 — Section 173 — https://www.indiacode.nic.in/bnss.pdf\n[2] Madras High Court')
    expect(copied).not.toContain('#cite-')
  })
  it('keeps older messages with legacy source text readable',()=>{
    cleanup()
    render(<MessageView message={{id:'old',role:'assistant',content:'Old answer.\n\n[Source: CPA 2019 — Section 69]',created_at:'',status:'complete',metadata:{}}} onSources={()=>{}}/>)
    expect(screen.getByText('[Source: CPA 2019 — Section 69]')).toBeInTheDocument()
  })
  it('numbers source entries, highlights the focused one and labels site-root links',()=>{
    cleanup()
    const {container}=render(<Sources sources={cited} focus={2}/>)
    expect(screen.getByLabelText('Source 1')).toHaveTextContent('1')
    expect(container.querySelector('[data-citation="2"]')).toHaveClass('source-focused')
    expect(container.querySelector('[data-citation="1"]')).not.toHaveClass('source-focused')
    expect(screen.getByRole('link',{name:/Open source page/})).toHaveAttribute('href','https://www.indiacode.nic.in/bnss.pdf')
    expect(screen.getByRole('link',{name:/Website home page \(exact document not linked\)/})).toBeInTheDocument()
  })
})

describe('answer quality',()=>{
  it('shows safety guidance once even though the saved answer text repeats it',()=>{
    cleanup()
    const safety='If you are in immediate danger, prioritise your safety.'
    render(<MessageView message={{id:'s',role:'assistant',content:`${safety}\n\nAsk the police station where he is held.`,created_at:'',status:'complete',metadata:{safety_messages:[{type:'safety',content_id:'c1',text:safety,request_id:'r',sources:[]}]}}} onSources={()=>{}}/>)
    expect(screen.getAllByText(safety)).toHaveLength(1)
    expect(screen.getByRole('alert')).toHaveTextContent(safety)
    expect(screen.getByText('Ask the police station where he is held.')).toBeInTheDocument()
  })
  it('labels verbatim official pack sources as not lawyer-reviewed',()=>{
    cleanup()
    render(<Sources sources={[{source_id:'bnss',passage_id:'pack-bnss-2023-s47',title:'Bharatiya Nagarik Suraksha Sanhita, 2023',locator:'Section 47: Person arrested to be informed of grounds of arrest',text:'47. (1) Every police officer…',canonical_url:'https://www.ncrb.mha.gov.in/uploads/SankalanPortal/DownloadPDF/BNSS2023.pdf',retrieved_at:'2026-11-08',limitations:'Not reviewed by a lawyer.',origin:'official_pack',citation_number:1}]}/>)
    expect(screen.getByText('Official text, quoted exactly · not reviewed by a lawyer')).toBeInTheDocument()
  })
})

describe('roleplay arena',()=>{
  it('renders minimalist stakeholder selection, starts simulation, and sends turns',async()=>{
    cleanup()
    const mockSetup={
      case_title:'Liquor case · Bihar',
      case_synopsis:'From what you told us: “My brother was taking his car from Patna.”',
      stakeholders:['Police officer','Opposing lawyer'],
    }
    const mockStartRes={
      session_id:'sess-rp-1',
      stakeholder:'Police officer',
      case_title:mockSetup.case_title,
      case_synopsis:mockSetup.case_synopsis,
      opening_message:"I'm the officer at the station. What is your relation to the person, and what do you want to know?",
    }
    const mockChatRes={
      reply:'Do you have his FIR number or any arrest documents?',
      turn_index:1,
      in_character:true,
      notice:'Practise only with what really happened.',
    }

    vi.spyOn(api,'roleplaySetup').mockResolvedValue(mockSetup)
    vi.spyOn(api,'roleplayStart').mockResolvedValue(mockStartRes)
    vi.spyOn(api,'roleplayChatStream').mockImplementation(async(_cid,_sid,_msg,_lang,onDelta)=>{onDelta('Do you have his ');onDelta('FIR number or any arrest documents?');return mockChatRes})

    render(<PracticePanel caseId="c-test" setupDelayMs={20}/>)

    // Verify Reference 1 setup screen renders
    await waitFor(()=>expect(screen.getByText('Practice your conversation')).toBeInTheDocument())
    expect(screen.getByText('Liquor case · Bihar')).toBeInTheDocument()
    expect(screen.getByText('From what you told us: “My brother was taking his car from Patna.”')).toBeInTheDocument()
    expect(screen.getByText('Police officer')).toBeInTheDocument()
    expect(screen.getByText('Opposing lawyer')).toBeInTheDocument()

    // Click Start Practice
    fireEvent.click(screen.getByRole('button',{name:/Start Practice/}))

    // Verify Reference 2 active chat screen renders after short delay
    await waitFor(()=>expect(screen.getByText("I'm the officer at the station. What is your relation to the person, and what do you want to know?")).toBeInTheDocument())
    // The setup summary is reused, so starting needs no second extraction call.
    expect(api.roleplayStart).toHaveBeenCalledWith('c-test','Police officer',undefined,'en',mockSetup)
    expect(screen.getByText('Police officer')).toBeInTheDocument()
    expect(screen.getByText('End practice')).toBeInTheDocument()

    // Send user message
    const input=screen.getByLabelText('Type your response')
    fireEvent.change(input,{target:{value:'I want to know which court he was produced before.'}})
    fireEvent.submit(input.closest('form')!)

    await waitFor(()=>expect(screen.getByText('Do you have his FIR number or any arrest documents?')).toBeInTheDocument())
    expect(screen.getByText('Practise only with what really happened.')).toBeInTheDocument()
  })

  it('shows safety guidance in place of the character',async()=>{
    cleanup()
    const setup={case_title:'Arrest or police case',case_synopsis:'Tell us about your case in the chat first.',stakeholders:['Police officer']}
    vi.spyOn(api,'roleplaySetup').mockResolvedValue(setup)
    vi.spyOn(api,'roleplayStart').mockResolvedValue({session_id:'s2',stakeholder:'Police officer',case_title:setup.case_title,case_synopsis:setup.case_synopsis,opening_message:'Who are you?'})
    vi.spyOn(api,'roleplayChatStream').mockResolvedValue({reply:'Call 112 now if anyone is in danger.',turn_index:1,in_character:false,notice:'safety'})
    render(<PracticePanel caseId="c-safe" setupDelayMs={0}/>)
    await waitFor(()=>expect(screen.getByRole('button',{name:/Start Practice/})).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button',{name:/Start Practice/}))
    await waitFor(()=>expect(screen.getByText('Who are you?')).toBeInTheDocument())
    const input=screen.getByLabelText('Type your response')
    fireEvent.change(input,{target:{value:'They are beating him right now'}})
    fireEvent.submit(input.closest('form')!)
    await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('Call 112 now'))
    expect(screen.queryByText('safety')).not.toBeInTheDocument()
  })
})


const devspaceData={
  api_key:{configured:true,masked:'sk-proj…tnIA'},
  groups:[
    {title:'Models',fields:[{name:'OPENAI_CHAT_MODEL',value:'gpt-6-luna',type:'model' as const,options:['gpt-6-luna','gpt-4o'],restart_required:false}]},
    {title:'Agent caps',fields:[{name:'AGENT_MAX_REQUESTS',value:14,type:'integer' as const,min:1,max:24,restart_required:false},{name:'WEB_RESEARCH_ENABLED',value:true,type:'boolean' as const,restart_required:false}]},
  ],
  prompts:{primary:'You are Nyay Saathi',review:'Review',roleplay_setup:'Setup',roleplay_persona:'Persona',roleplay_reply:'Reply'},
  curl:{turn_stream:'curl turn',responses_api:'curl https://api.openai.com/v1/responses',roleplay_chat:'curl roleplay'},
}

describe('sidebar case actions',()=>{
  const conv=(id:string,title:string)=>({id,title,language:'en' as const,created_at:'',updated_at:''})

  it('renames a case inline and deletes from its menu',async()=>{
    cleanup();vi.restoreAllMocks()
    const onRename=vi.fn(),onDelete=vi.fn()
    render(<Sidebar open items={[conv('1','Refund case')]} active="1" onNew={()=>{}} onSelect={()=>{}} onClose={()=>{}} onKnowledge={()=>{}} onWorkflow={()=>{}} onRename={onRename} onDelete={onDelete}/>)
    fireEvent.click(screen.getByLabelText('Chat actions for Refund case'))
    expect(screen.getByRole('menuitem',{name:/Delete/})).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem',{name:/Rename/}))
    const input=screen.getByLabelText('Chat title')
    fireEvent.change(input,{target:{value:'Deposit dispute'}})
    fireEvent.keyDown(input,{key:'Enter'})
    expect(onRename).toHaveBeenCalledExactlyOnceWith('1','Deposit dispute')
    expect(screen.queryByLabelText('Chat title')).toBeNull()

    fireEvent.click(screen.getByLabelText('Chat actions for Refund case'))
    fireEvent.click(screen.getByRole('menuitem',{name:/Rename/}))
    fireEvent.keyDown(screen.getByLabelText('Chat title'),{key:'Escape'})
    expect(onRename).toHaveBeenCalledOnce()

    fireEvent.click(screen.getByLabelText('Chat actions for Refund case'))
    fireEvent.click(screen.getByRole('menuitem',{name:/Delete/}))
    expect(onDelete).toHaveBeenCalledWith('1')
  })

  it('clubs tools into bottom-left Settings and provides unified tabbed access',()=>{
    cleanup()
    const onSettings=vi.fn()
    render(<Sidebar open items={[]} onNew={()=>{}} onSelect={()=>{}} onClose={()=>{}} onKnowledge={()=>{}} onWorkflow={()=>{}} onSettings={onSettings}/>)
    const settingsBtn=screen.getByRole('button',{name:'Settings'})
    expect(settingsBtn).toBeInTheDocument()
    fireEvent.click(settingsBtn)
    expect(onSettings).toHaveBeenCalledWith('devspace')
  })

  it('renders Flowinggg showing one element at a time and disappears when idle',()=>{
    cleanup()
    const repairEvents = [
      {stage:'saving',status:'running'},
      {stage:'primary',status:'running',round:1},
      {stage:'review',status:'running'},
      {stage:'revision',status:'running',attempt:1}
    ]
    const {rerender} = render(<AgentFlowWidget isStreaming={true} events={repairEvents}/>)
    // Box title
    expect(screen.getByText('Flowinggg')).toBeInTheDocument()
    // Current active element
    expect(screen.getByText('Feedback Loop')).toBeInTheDocument()
    expect(screen.getByText('5/6')).toBeInTheDocument()
    // Other elements are not shown (only ONE element at a time)
    expect(screen.queryByText('Context & Intake')).toBeNull()
    expect(screen.queryByText('Primary Reasoning')).toBeNull()

    // When idle / not streaming, widget disappears
    cleanup()
    render(<AgentFlowWidget isStreaming={false} events={[]}/>)
    expect(screen.queryByText('Flowinggg')).toBeNull()
  })

  it('switches tabs smoothly in SettingsPanel',()=>{
    cleanup()
    const onLoadKnowledge = vi.fn()
    const onLoadWorkflow = vi.fn()
    render(
      <SettingsPanel
        initialTab="knowledge"
        knowledge={null}
        workflow={null}
        devspaceEnabled={true}
        onLoadKnowledge={onLoadKnowledge}
        onLoadWorkflow={onLoadWorkflow}
        onDevspaceSaved={()=>{}}
      />
    )
    const tabs = screen.getAllByRole('tab').map(t => t.textContent)
    expect(tabs).toEqual(['DevSpace', 'Agent Workflow', 'Knowledge Base'])
    expect(onLoadKnowledge).toHaveBeenCalled()
    const workflowTab = screen.getByRole('tab', {name: 'Agent Workflow'})
    fireEvent.click(workflowTab)
    expect(onLoadWorkflow).toHaveBeenCalled()
    const devspaceTab = screen.getByRole('tab', {name: 'DevSpace'})
    expect(devspaceTab).toBeInTheDocument()
  })

  it('deleting the open case opens the next one',async()=>{
    cleanup();vi.restoreAllMocks()
    Element.prototype.scrollIntoView=vi.fn()
    const cases=[conv('c1','First'),conv('c2','Second'),conv('c3','Third')]
    const detailFor=(id:string)=>({conversation:cases.find(c=>c.id===id)!,messages:[],safety_messages:[],case_memory:{version:0,domain:'unknown',facts:{},contradictions:[],unknowns:[],actions_completed:[],evidence:[]},summary:'',attachments:[],drafts:[]})
    let remaining=cases
    vi.spyOn(api,'bootstrap').mockResolvedValue({ai_configured:true,devspace_enabled:true,privacy_notice:'',disclaimer:''})
    vi.spyOn(api,'list').mockImplementation(async()=>remaining)
    const detail=vi.spyOn(api,'detail').mockImplementation(async id=>detailFor(id) as never)
    vi.spyOn(api,'remove').mockImplementation(async id=>{remaining=remaining.filter(c=>c.id!==id);return {}})
    vi.spyOn(window,'confirm').mockReturnValue(true)
    render(<App/>)
    await waitFor(()=>expect(detail).toHaveBeenCalledWith('c1'))
    fireEvent.click(screen.getByLabelText('Chat actions for First'))
    fireEvent.click(screen.getByRole('menuitem',{name:/Delete/}))
    await waitFor(()=>expect(detail).toHaveBeenLastCalledWith('c2'))
    expect(api.remove).toHaveBeenCalledWith('c1')
    expect(screen.queryByLabelText('Chat actions for First')).toBeNull()
  })
})

describe('DevSpace',()=>{
  it('toggles the key mask, saves only changed fields, and copies cURL',async()=>{
    cleanup();vi.restoreAllMocks()
    vi.spyOn(api,'devspace').mockResolvedValue(devspaceData)
    const save=vi.spyOn(api,'saveDevspace').mockResolvedValue({saved:['OPENAI_CHAT_MODEL'],restart_required:[],configured:true})
    const writeText=vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator,'clipboard',{value:{writeText},configurable:true})
    const onSaved=vi.fn()
    render(<DevSpacePanel onSaved={onSaved}/>)
    await waitFor(()=>expect(screen.getByText('Key active · sk-proj…tnIA')).toBeInTheDocument())

    const key=screen.getByLabelText('OpenAI API key')
    expect(key).toHaveAttribute('type','password')
    fireEvent.click(screen.getByLabelText('Show key'))
    expect(key).toHaveAttribute('type','text')

    fireEvent.change(screen.getByLabelText('OPENAI_CHAT_MODEL'),{target:{value:'gpt-4o'}})
    fireEvent.click(screen.getByRole('button',{name:'Save & Apply (1)'}))
    await waitFor(()=>expect(save).toHaveBeenCalledWith({OPENAI_CHAT_MODEL:'gpt-4o'},false))
    await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent('Saved and applied 1 setting.'))
    expect(onSaved).toHaveBeenCalledWith({saved:['OPENAI_CHAT_MODEL'],restart_required:[],configured:true})

    fireEvent.click(screen.getByRole('tab',{name:'Prompts & cURL'}))
    const block=screen.getByText('Direct OpenAI Responses call').closest('.ds-block') as HTMLElement
    fireEvent.click(within(block).getByRole('button',{name:/Copy/}))
    await waitFor(()=>expect(writeText).toHaveBeenCalledWith('curl https://api.openai.com/v1/responses'))
  })

  it('shows field errors returned by the server',async()=>{
    cleanup();vi.restoreAllMocks()
    vi.spyOn(api,'devspace').mockResolvedValue(devspaceData)
    vi.spyOn(api,'saveDevspace').mockRejectedValue(Object.assign(new Error('Some settings were not saved.'),{errors:{AGENT_MAX_REQUESTS:'Input should be less than or equal to 24'}}))
    render(<DevSpacePanel/>)
    await waitFor(()=>expect(screen.getByLabelText('AGENT_MAX_REQUESTS')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('AGENT_MAX_REQUESTS'),{target:{value:'99'}})
    fireEvent.click(screen.getByRole('button',{name:'Save & Apply (1)'}))
    await waitFor(()=>expect(screen.getByText('Input should be less than or equal to 24')).toBeInTheDocument())
    expect(screen.getByRole('status')).toHaveTextContent('Some settings were not saved.')
  })
})
