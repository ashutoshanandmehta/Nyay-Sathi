import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import JourneyPanel from './JourneyPanel'
import MessageView from './MessageView'
import { CasePanel } from './Drawer'
import { api } from '../api'
import type { Journey, RouteOption } from '../resolution'

afterEach(cleanup)

const route:RouteOption={route_id:'grievance',recipient_id:'blinkit',title:'Follow up with Blinkit',channel:'email',reason:'Use the existing ticket.',eligibility:{status:'insufficient_information',reasons:[],missing_inputs:['Current grievance recipient']},preparation:['Ticket reference'],instructions:['Check the official contact.'],source_urls:['https://blinkit.com/terms'],tradeoff:{filing_fee_inr:null,fee_basis:'No government filing involved.',effort:'low',effort_basis:'Application estimate',waiting_time:'Unknown',other_costs:[],uncertainty:['No guaranteed remedy.']}}
function fixture():Journey{return {events:[{id:'e',event_type:'ticket_closed',description:'They closed ticket TEST-100.',occurred_at:null,recorded_at:'2026-11-06',evidence_status:'user_reported',recipient:'blinkit',reference:'TEST-100',supersedes_id:null}],submissions:[],commitments:[],outcome:'closed_by_recipient_outcome_unknown',satisfaction:'unknown',severity:'ordinary',recommendations:[{id:'r',recommended_route_id:'grievance',case_version:2,stale:false,alternatives:[route],important_uncertainties:[],status:'proposed_not_submitted'}]}}
describe('resolution preparation',()=>{
  it('separates closed tickets, satisfaction, preparation estimates and eligibility',()=>{render(<JourneyPanel journey={fixture()} caseVersion={2}/>);expect(screen.getByText('Ticket closed — outcome not established')).toBeInTheDocument();expect(screen.getByText('Your satisfaction has not been established')).toBeInTheDocument();expect(screen.getByText(/Filing eligibility needs checking/)).toBeInTheDocument();fireEvent.click(screen.getByText('What to prepare and consider'));expect(screen.getByText('Current grievance recipient')).toBeInTheDocument();expect(screen.queryByText('closed_by_recipient_outcome_unknown')).toBeNull()})
  it('withholds outdated route details after case changes',()=>{render(<JourneyPanel journey={fixture()} caseVersion={3}/>);expect(screen.getByText(/case has changed/)).toBeInTheDocument();expect(screen.queryByText('Follow up with Blinkit')).toBeNull()})
  it('renders natural markdown response with draft preparation and escalation action',()=>{
    const onOpenCase=vi.fn()
    render(<MessageView message={{
      id:'m-blocks',
      role:'assistant',
      content:'### Direct answer\n\nE-commerce entities must acknowledge grievances within 48 hours.\n\n### Immediate actions\n\n1. Save SMS\n2. Email Grievance Officer',
      created_at:'',
      status:'complete',
      metadata:{
        publication_status:'supported',
        resolution_blocks:[
          {block_id:'b1',block_type:'direct_answer',title:'Direct answer',content:'E-commerce entities must acknowledge grievances within 48 hours.',items:[],claim_ids:['c1'],source_ids:['prop-consumer-ecommerce-grievance-r4'],grounding:'verified_legal_source'},
          {block_id:'b2',block_type:'immediate_actions',title:'Immediate actions',content:'1. Save SMS\n2. Email Grievance Officer',items:['Save SMS','Email Grievance Officer'],claim_ids:['c2'],source_ids:[],grounding:'practical_precaution'},
          {block_id:'b3',block_type:'human_handoff',title:'When to involve a licensed advocate',content:'An escalation bundle is ready for review.',items:[],claim_ids:[],source_ids:[],grounding:'practical_precaution'},
          {block_id:'b4',block_type:'document',title:'Prepared grievance letter',content:'To Grievance Officer: refund request',items:[],claim_ids:[],source_ids:[],grounding:'practical_precaution',document_title:'Grievance Notice Draft'}
        ]
      }
    }} onSources={()=>{}} onOpenCase={onOpenCase}/>)
    expect(screen.getByText(/E-commerce entities must acknowledge grievances/)).toBeInTheDocument()
    expect(screen.getByText(/Save SMS/)).toBeInTheDocument()
    expect(screen.getByText('Copy prepared draft')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Open Lawyer Escalation Bundle in Your case'))
    expect(onOpenCase).toHaveBeenCalledOnce()
  })
  it('renders active resolution workspace sections for actions, submissions, escalation and privacy',()=>{
    render(<CasePanel detail={{
      conversation:{id:'c1',title:'Refund case',language:'en',created_at:'',updated_at:''},
      messages:[],
      summary:'',
      attachments:[],
      drafts:[],
      encryption:{envelope_encrypted:true,status:'active'},
      retention:{policy:'inactivity_1y',inactivity_retention_days:365,last_active_at:'',expires_at:'',days_remaining:365,user_deletable_anytime:true},
      case_memory:{version:1,domain:'consumer',facts:{},contradictions:[],unknowns:[],actions_completed:[],evidence:[]}
    }}/>)
    expect(screen.getByText(/Action tracker/)).toBeInTheDocument()
    expect(screen.getByText(/User-confirmed submission tracker/)).toBeInTheDocument()
    expect(screen.getByText(/Prepare Lawyer Escalation Bundle/)).toBeInTheDocument()
    expect(screen.getByText(/Privacy, retention & device transfer/)).toBeInTheDocument()
  })
  it('shows the escalation bundle content a lawyer needs, with downloads',async()=>{
    vi.spyOn(api,'escalationBundle').mockResolvedValue({bundle_version:'escalation-bundle-v2',generated_at:'',case_title:'Liquor case',domain:'criminal',case_version:2,escalation_recommended:true,
      escalation_reasons:['Criminal matter: personal liberty may be at stake (arrest, custody or bail).'],executive_summary:'',
      chronology:[{date:'2026-11-07',timestamp:'2026-11-07T10:00:00Z',kind:'reported_event',summary:'Police stopped the car near Biharsharif',status:'user_reported'}],stated_facts:['Vehicle owner: The client\'s father'],writing:'formal',
      facts_partition:{reported_and_consistent:[{key:'vehicle_owner',value:'Father',status:'user_allegation'}],uncertain_or_disputed:[],contradictions:[]},
      evidence_index:[],questions_for_counsel:['Whether bail is available for the recorded offence'],facts_to_establish:['Which police station registered the FIR'],not_confirmed:['Current charges are not confirmed.'],
      generated_drafts:[],source_backed_analysis:{findings:[],verified_sources:[{source_id:'s',title:'BNSS 2023',locator:'Section 480',canonical_url:'https://example.gov.in/bnss.pdf'}]},autonomy_notice:'No filing has been done for you.'})
    render(<CasePanel detail={{conversation:{id:'c9',title:'Liquor case',language:'en',created_at:'',updated_at:''},messages:[],summary:'',attachments:[],drafts:[],case_memory:{version:2,domain:'criminal',facts:{},contradictions:[],unknowns:[],actions_completed:[],evidence:[]}}}/>)
    fireEvent.click(screen.getByText(/Prepare Lawyer Escalation Bundle/))
    await waitFor(()=>expect(screen.getByText('A lawyer should look at this')).toBeInTheDocument())
    const card=within(document.querySelector('.bundle-card') as HTMLElement)
    for(const heading of ['Reasons for review','Chronology','Facts stated by the client','Questions for counsel','Facts to be established','Not yet verified by Nyay Saathi','Sources relied on'])expect(card.getByText(heading)).toBeInTheDocument()
    expect(card.getByText('Police stopped the car near Biharsharif')).toBeInTheDocument()
    expect(card.getByRole('link',{name:'BNSS 2023 · Section 480'})).toHaveAttribute('href','https://example.gov.in/bnss.pdf')
    const download=vi.spyOn(api,'downloadEscalationBundle').mockResolvedValue('nyay-saathi-lawyer-bundle.pdf')
    fireEvent.click(card.getByRole('button',{name:'PDF'}))
    await waitFor(()=>expect(card.getByRole('status')).toHaveTextContent('Downloaded nyay-saathi-lawyer-bundle.pdf'))
    expect(download).toHaveBeenCalledWith('c9','pdf')
    expect(card.queryByText('Evidence files')).toBeNull()
  })
})
