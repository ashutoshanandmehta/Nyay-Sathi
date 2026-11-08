import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { api } from '../api'
import Composer from './Composer'
import { AgentWorkflowPanel, CasePanel, KnowledgeBasePanel, Sources } from './Drawer'
import MessageView from './MessageView'
import Sidebar from './Sidebar'

describe('chat interface',()=>{
  it('keeps partial assistance readable and allows speech only for approved content',()=>{
    const speech=vi.fn();render(<MessageView message={{id:'partial',role:'assistant',content:'Here is your factual draft.',created_at:'',status:'complete',metadata:{publication_status:'partial',verification:{passed:false,publication_safe:true}}}} onSources={()=>{}} onSpeech={speech}/>);
    expect(screen.getByText('Here is your factual draft.')).toBeInTheDocument();expect(screen.getByRole('note')).toHaveTextContent('Some help is ready');fireEvent.click(screen.getByText('Listen'));expect(speech).toHaveBeenCalledOnce()
  })
  it('distinguishes unverified public research and unknown effective dates',()=>{render(<Sources sources={[{source_id:'w',passage_id:'wp',title:'Public procedure candidate',locator:'Public webpage',text:'Supporting excerpt',canonical_url:'https://example.edu/',retrieved_at:'2026-11-06',limitations:'Current applicability requires review',origin:'web',verification_status:'unverified_public_source',effective_date:null}]}/>);expect(screen.getByText('Public source · authority not verified')).toBeInTheDocument();expect(screen.getByText('Current applicability requires review')).toBeInTheDocument();expect(screen.getByText(/Effective date unknown/)).toBeInTheDocument();expect(screen.queryByText('Official website · web research')).toBeNull()})
  it('keeps New chat visible and exposes system information',()=>{const onNew=vi.fn(),onSelect=vi.fn(),onKnowledge=vi.fn(),onWorkflow=vi.fn();render(<Sidebar open items={[{id:'1',title:'Refund case',language:'en',created_at:'',updated_at:''}]} active="1" onNew={onNew} onSelect={onSelect} onClose={()=>{}} onKnowledge={onKnowledge} onWorkflow={onWorkflow}/>);fireEvent.click(screen.getByText('New chat'));expect(onNew).toHaveBeenCalled();fireEvent.click(screen.getByText('Refund case'));expect(onSelect).toHaveBeenCalledWith('1');fireEvent.click(screen.getByText('Knowledge Base'));expect(onKnowledge).toHaveBeenCalled();fireEvent.click(screen.getByText('Agent Workflow'));expect(onWorkflow).toHaveBeenCalled()})
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
