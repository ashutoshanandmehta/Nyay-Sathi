import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import JourneyPanel from './JourneyPanel'
import type { Journey, RouteOption } from '../resolution'

afterEach(cleanup)

const route:RouteOption={route_id:'grievance',recipient_id:'blinkit',title:'Follow up with Blinkit',channel:'email',reason:'Use the existing ticket.',eligibility:{status:'insufficient_information',reasons:[],missing_inputs:['Current grievance recipient']},preparation:['Ticket reference'],instructions:['Check the official contact.'],source_urls:['https://blinkit.com/terms'],tradeoff:{filing_fee_inr:null,fee_basis:'No government filing involved.',effort:'low',effort_basis:'Application estimate',waiting_time:'Unknown',other_costs:[],uncertainty:['No guaranteed remedy.']}}
function fixture():Journey{return {events:[{id:'e',event_type:'ticket_closed',description:'They closed ticket TEST-100.',occurred_at:null,recorded_at:'2026-11-06',evidence_status:'user_reported',recipient:'blinkit',reference:'TEST-100',supersedes_id:null}],submissions:[],commitments:[],outcome:'closed_by_recipient_outcome_unknown',satisfaction:'unknown',severity:'ordinary',recommendations:[{id:'r',recommended_route_id:'grievance',case_version:2,stale:false,alternatives:[route],important_uncertainties:[],status:'proposed_not_submitted'}]}}
describe('resolution preparation',()=>{
  it('separates closed tickets, satisfaction, preparation estimates and eligibility',()=>{render(<JourneyPanel journey={fixture()} caseVersion={2}/>);expect(screen.getByText('Ticket closed — outcome not established')).toBeInTheDocument();expect(screen.getByText('Your satisfaction has not been established')).toBeInTheDocument();expect(screen.getByText(/Filing eligibility needs checking/)).toBeInTheDocument();fireEvent.click(screen.getByText('What to prepare and consider'));expect(screen.getByText('Current grievance recipient')).toBeInTheDocument();expect(screen.queryByText('closed_by_recipient_outcome_unknown')).toBeNull()})
  it('withholds outdated route details after case changes',()=>{render(<JourneyPanel journey={fixture()} caseVersion={3}/>);expect(screen.getByText(/case has changed/)).toBeInTheDocument();expect(screen.queryByText('Follow up with Blinkit')).toBeNull()})
})
