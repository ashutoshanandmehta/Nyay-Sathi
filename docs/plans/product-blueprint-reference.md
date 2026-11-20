Complete Product Design & Technical Blueprint

Product: Nyay Saathi — AI-Powered Consumer Rights, Financial Fraud & Legal Assistance Platform
Primary market: India
Product stage: Proposed production upgrade
Core stack: React, FastAPI, LangGraph, PostgreSQL, hybrid legal RAG, Google Drive and Gmail integrations

1. Product Vision

Mission

Make everyday legal assistance accessible, understandable, affordable and actionable for ordinary Indians.

Nyay Saathi helps people understand their rights, organize evidence, prepare complaints and documents, and navigate official grievance channels without needing expensive legal assistance for every routine dispute.

Product promise

"Explain your problem in your own language. Understand your rights. Prepare your complaint. Take action."

Nyay Saathi is not intended to replace advocates, courts, regulators, police or government systems. It is an intelligent assistance layer that simplifies the process of using those systems.

Core product principles

Problem-first, not law-first: Users describe what happened instead of searching for legal sections.

Action-oriented: Every eligible query should produce clear next steps rather than just legal information.

Source-grounded: Legal claims must be supported by traceable, applicable sources.

Historically accurate: Recognize older laws and explain their relationship to current laws.

Privacy-conscious: User documents remain in the user's own Google Drive.

User-controlled: External actions require the appropriate authorization or confirmation.

Multilingual: Hindi, English and Hinglish first, with additional Indian languages later.

Urgency-aware: Active financial fraud must receive immediate protective guidance.

Continuity: Every case has its own history, evidence, communications and status.

Accessible: Optimize the experience for people with limited legal or technical knowledge.

2. Target Users

Primary users

Indian consumers facing refund, delivery or service disputes

Victims of UPI, bank-account, card or online financial fraud

People needing assistance with grievance letters or complaints

Individuals unfamiliar with consumer forums, banking regulators or cybercrime procedures

People whose dispute value makes conventional legal representation uneconomical

Secondary users

Employees facing unpaid salary or employment disputes

Tenants facing deposit or lease disputes

Citizens needing RTI or public-service grievance assistance

People seeking preliminary help with common criminal-law procedures

Users requiring simple personal document drafts

Primary pain points

Discovery: The consumer does not know the applicable law or their rights.

Understanding: Official laws and procedures are written in difficult language.

Documentation: Evidence is scattered across devices, messages and emails.

Action: The correct authority, contact details and filing procedure are unclear.

Cost: Formal legal representation may be disproportionate to the dispute.

Continuity: Users lose track of previous complaints, reference numbers and responses.

Nyay Saathi addresses these six problems in one workflow.

3. Product Scope and Prioritization

Priority

Legal domain

Supported problems

P0

Consumer protection

Refunds, defective goods, warranties, misleading claims, e-commerce, delivery and service complaints

P0

Financial fraud

UPI scams, unauthorized debits, card fraud, phishing, OTP theft, fake customer support

P0

Banking and payments

Failed transfers, disputed charges, banking grievances, relevant RBI protections

P0

Complaint preparation

Evidence collection, legal explanation, grievance drafting, complaint routing

P0

Digital action integrations

Gmail, user-owned Drive, official portal links, phone and WhatsApp links

P1

Investment fraud

Fake broker apps, fraudulent advisers, investment scams, securities-market grievance routes

P1

Cybercrime and online abuse

Online impersonation, fake profiles, harassment and cybercrime reporting

P1

Criminal-law assistance

Relevant provisions, FIR procedures, historical IPC/CrPC and current BNS/BNSS

P1

Travel and hospitality

Airline cancellations, denied hotel bookings, service and refund disputes

P1

Employment

Salary disputes, notice periods, offer letters, applicable employment provisions

P1

Rent and property

Rental agreements, deposit claims, contractual clauses, relevant state laws

P1

RTI and civic procedures

RTI drafting, public authority routing, government grievance processes

P1

Personal document drafts

Authorization letters, applications, notices and preliminary agreements

P2

Advanced legal research

Case law, precedent analysis and complex disputes requiring professional review

Launch recommendation: Build comprehensive workflows for consumer refunds, defective products and financial fraud first. Add other domains using the same legal-data architecture and case-management framework.

4. Complete User Experience

4.1 Onboarding

The user opens Nyay Saathi and sees three primary options:

Know My Rights — Ask a legal or regulatory question.

Resolve a Complaint — Understand a dispute and create an actionable complaint.

Report Financial Fraud — Get immediate protective and reporting instructions.

The user can also browse existing cases from a My Cases dashboard.

Google Drive and Gmail connections should be optional initially and requested at the moment they become useful. A basic legal question should not require access to personal accounts.

4.2 Conversation intake

The assistant accepts:

Typed messages

Hindi, English or Hinglish

Voice notes and voice-to-text input

PDFs, invoices and contracts

Screenshots and photographs

Relevant Gmail evidence, if authorized

The intake engine extracts:

Problem category

Relevant company or institution

Incident date

Transaction or dispute amount

Location and jurisdiction

Desired remedy

Actions already taken

Available evidence

Urgency and potential ongoing harm

It asks only the questions necessary to make the next decision.

4.3 Legal understanding

The agent identifies relevant central laws, state laws, financial regulations, consumer policies and complaint procedures.

It checks whether the information applies to the incident date and location, considers relevant exceptions, and distinguishes reliable evidence from unverified claims.

4.4 Resolution planning

The agent recommends an appropriate sequence, which may include:

Immediate protective steps

Contacting the company or bank

Sending a formal written complaint

Using a government helpline

Submitting a grievance to a sector regulator

Preparing consumer commission paperwork

Seeking professional legal assistance for complex cases

The sequence must depend on the issue. For example, a suspected ongoing bank fraud should not wait for a routine merchant complaint process.

4.5 Case creation

After the user chooses to maintain a case, Nyay Saathi creates a dedicated case folder in their connected Google Drive.

The agent can then store original evidence, drafts, user-approved communications and official acknowledgements in that folder.

4.6 Taking action

Depending on the recommended resolution, the user can:

Approve and send a Gmail complaint

Open the official WhatsApp grievance chatbot

Open the device's phone dialer

Open a government complaint portal

Download or open the complaint draft

Save newly received evidence

Continue the case later

External filing completion must be confirmed rather than assumed.

5. Google Drive — User-Owned Case Management

5.1 Storage model

Each user connects their Google Drive through Google OAuth.

Nyay Saathi creates a dedicated root folder:

My Drive / Nyay Saathi

Every legal case gets a separate subfolder, automatically created and managed by the agent.

Recommended structure:

My Drive/
└── Nyay Saathi/
    ├── CASE-001/
    │   ├── 01_Original_Evidence/
    │   ├── 02_Emails_And_Communications/
    │   ├── 03_Complaint_Drafts/
    │   ├── 04_Submitted_Complaints/
    │   ├── 05_Official_Responses/
    │   └── 06_Case_Manifest/
    │
    ├── CASE-002/
    │   ├── 01_Original_Evidence/
    │   ├── 02_Emails_And_Communications/
    │   ├── 03_Complaint_Drafts/
    │   ├── 04_Submitted_Complaints/
    │   ├── 05_Official_Responses/
    │   └── 06_Case_Manifest/
    │
    └── CASE-003/
        └── ...

Use opaque case IDs by default to avoid exposing sensitive case details through filenames.

5.2 Folder permissions

The user grants narrowly scoped Google Drive access using OAuth, initially favoring drive.file.

The application manages files created within its own workspace and files individually authorized by the user. The application backend must separately enforce workspace and case boundaries.

A Google Drive folder alone is not an OAuth security boundary.

5.3 Agent responsibilities

The Drive agent should:

Create the root folder on first connection

Reuse the existing root folder on subsequent sessions

Create a subfolder for each new case

Categorize uploaded evidence

Preserve original file contents

Generate descriptive metadata without changing evidence

Store complaint drafts and approved final documents

Save user-selected Gmail correspondence

Maintain a document manifest

Open the correct case folder on request

Detect missing, moved or deleted files

Avoid duplicate uploads where possible

The Drive agent must not independently share, permanently delete or disclose files to external recipients.

5.4 User privacy

Original documents remain in the user's Google Drive. The app stores only necessary metadata, case state, authorization records and file references in its own database.

Temporary document extraction should use secure, limited-retention processing. Sensitive text must not enter unrestricted logs, analytics or the shared legal vector database.

Drive ownership does not itself guarantee that Google, the connected application or authorized AI processors cannot access the contents. The privacy notice must clearly explain processing, storage, retention and sharing.

5.5 Important fallback

If the user does not connect Google Drive, Nyay Saathi can still answer general legal questions and generate text drafts. Persistent evidence management should remain unavailable or use an explicitly disclosed alternative storage model—not silently switch to permanent server storage.

6. Gmail MCP — Complaint Communication Agent

6.1 Core capabilities

Nyay Saathi integrates Gmail so consumers can manage the written communication required for a complaint.

Supported actions:

Search user-authorized email for relevant receipts or support conversations.

Extract transaction dates, order references and previous complaint details.

Draft professional complaint emails.

Let the user review and modify the draft.

Send through the user's Gmail after explicit approval.

Retrieve relevant responses.

Prepare follow-up or escalation emails.

Save selected correspondence to the appropriate Google Drive case folder.

6.2 User confirmation

The agent must show the full:

Sender

Recipient

Subject

Email body

Attachments

before sending.

The send tool runs only after a valid user approval.

Sensitive documents must never be attached merely because they exist in the case folder.

6.3 Gmail technical design

Implement Google OAuth with incremental permissions.

Use the Gmail API behind a narrowly defined MCP tool adapter. The adapter should validate the user's identity, requested Gmail action and approval state.

Persist Gmail thread IDs and confirmed message IDs in the case database.

Do not automatically email a grievance officer address retrieved from an unverified website.

6.4 Gmail monitoring

A later release may support optional follow-up monitoring, with the user's explicit consent.

The agent could detect a relevant reply, summarize it, and suggest the next action.

It should not automatically send legal responses or escalate a dispute without user approval.

7. One-Tap Calls, WhatsApp and Grievance Portals

7.1 Action cards

When Nyay Saathi recommends an official grievance channel, it displays an interactive contact card with verified details.

Each card can contain:

Authority name

Complaint category

Verified phone number

Verified WhatsApp number, if available

Official grievance website

Requirements and eligibility

Last verification date

Appropriate action buttons

7.2 Phone integration

Use a tel: deep link to open the phone dialer.

The user decides whether to place the call.

Opening the dialer must not be recorded as a completed call.

7.3 WhatsApp integration

Use a verified https://wa.me/ deep link to open the official WhatsApp conversation.

The user sends messages using WhatsApp.

Nyay Saathi may prepare suggested complaint text, but the user should review it before sending.

The application must not claim that launching WhatsApp means a message was delivered or a grievance was registered.

7.4 Grievance portal links

Use official HTTPS links to open the appropriate website.

Where technically supported, the product can guide users through each required field and prepare documents for submission.

Automated filing requires an authorized integration and explicit user approval.

7.5 Contact verification

Phone numbers, WhatsApp links, email addresses and portal URLs must come from a structured, verified contact registry.

Every record should include:

Authority identifier

Contact type

Normalized destination

Official supporting URL

Jurisdiction and category

Verification timestamp

Current or retired status

The language model may recommend a contact type, but it must not freely invent its destination.

8. Legal Knowledge Base — Vector Database Upgrade

8.1 Core architectural principle

The knowledge platform must store more than document embeddings.

It needs four cooperating systems:

Legal document store: Authoritative source documents, provisions and versions.

Structured legal metadata: Jurisdiction, effective dates, amendments, repeals, exceptions and relationships.

Search infrastructure: Vector retrieval, keyword retrieval and exact section matching.

Procedure and action registry: Official complaints, contacts, evidence requirements and escalation conditions.

8.2 Knowledge domains

Create logical collections covering:

Central legislation

State legislation and local procedural rules

RBI, SEBI and other financial regulations

Consumer law and e-commerce rules

Criminal law and procedural law

Historical legislation and provision mappings

Government grievance procedures

Company complaint policies

Verified contact information

Legal drafting templates

Judicial interpretation, in a later phase

8.3 Source hierarchy

Prioritize official primary sources:

India Code

Gazette of India

State Gazettes and official state law portals

RBI publications and Master Directions

SEBI publications and circulars

Official government consumer and cybercrime portals

Authorized exchange, depository and payment-system publications

Government and judicial repositories

Commercial legal blogs may help discover relevant topics but should not replace primary legal authority.

8.4 Legal document ingestion

The ingestion pipeline should:

Discover official documents.

Retrieve source files and metadata.

Verify origin and document integrity.

Extract text, tables, headings and sections.

Identify dates, status and legal relationships.

Split documents along legal section boundaries.

Generate embeddings.

Insert or update structured provision records.

Preserve older versions.

Re-index only affected sections after amendments.

Original legal sources should be archived separately from processed text.

8.5 Retrieval pipeline

For a user query:

Identify domain, date, jurisdiction and statutory references.

Run exact citation matching where appropriate.

Run semantic and keyword search.

Fuse and deduplicate candidate results.

Check applicability and authority.

Rerank the eligible evidence.

Expand surrounding sections when exceptions or definitions matter.

Generate a grounded response.

Verify legal claims and citation identity.

Use approved real-time research if the evidence is inadequate.

Legal retrieval should not depend solely on cosine similarity.

8.6 CRAG integration

Use Corrective Retrieval-Augmented Generation to evaluate retrieved material before final generation.

The evaluator checks:

Relevance to the user's facts

Authority of the source

Correct law version

Jurisdiction

Completeness of the evidence

Presence of relevant exceptions

Whether the proposed remedy is supported

If retrieval is inadequate, the system can expand the search, fetch the missing version, consult another official source, or express uncertainty.

A CRAG score is not proof of legal correctness; it is one component of the verification system.

9. Historical Laws, Amendments and Jurisdiction

9.1 Historical-law recognition

The system must recognize references to older legislation.

Examples include:

IPC versus BNS

CrPC versus BNSS

Indian Evidence Act versus BSA

Superseded banking instructions

Amended consumer regulations

Previous state-level rules

When a user names an older law, Nyay Saathi retrieves the older text and verified corresponding newer provisions.

It then uses the event date and relevant transitional provisions to determine which framework may apply.

It should not tell users that an old provision is universally irrelevant merely because a newer law exists.

9.2 Legal versioning

Every provision should carry:

Canonical document and provision IDs

Jurisdiction

Publication date

Effective date

Expiry or repeal date, if applicable

Legal status

Source document hash

Amendment relationships

Previous and successor versions

Date last verified

Confidence and review status

Track uncertain effective dates explicitly rather than treating missing information as proof that a provision is currently enforceable.

9.3 National and state laws

The retrieval engine must filter by applicable jurisdiction.

State-specific coverage is particularly important for rent, property, employment, local administrative procedures and certain other regulated matters.

For every state-law answer, verify:

State and relevant locality

Type of dispute

Incident date

Applicable central legislation

Applicable state legislation

Relevant exceptions and conflicts

Authorized complaint or filing channel

Where central and state provisions may conflict, flag the issue for legal analysis rather than applying a simplistic rule that one automatically overrides the other.

10. Real-Time Web Retrieval and Continuous Updates

10.1 When live retrieval is needed

Trigger official web research when:

A regulator has potentially issued a new circular

The user asks for the latest rule

Existing indexed sources are stale

A relevant state notification is missing

A company grievance contact needs verification

A website's complaint procedure may have changed

Current legal sources disagree

The query falls outside indexed coverage

The agent should distinguish official current rules from drafts, press commentary and unverified interpretations.

10.2 Scheduled update pipeline

Monitor official sources at frequencies proportional to change risk.

Illustrative operational targets:

High-impact banking and market regulations: several checks daily

Central and state statutory publications: daily

Official complaint contacts and portals: daily or periodic verification

Lower-priority static explanations: weekly

On a change, identify the affected provisions, preserve previous versions, update metadata, refresh embeddings and invalidate affected cached answers.

High-impact legal changes should pass appropriate review before being marked verified.

11. Financial Fraud Emergency System

Financial fraud is not an ordinary complaint workflow.

11.1 High-priority detection

The first routing step should detect:

Active unauthorized debits

Recent UPI scams

Account takeover

Exposed banking credentials

OTP/phishing attacks

Fake customer-support fraud

Investment fraud

Loan-app harassment and financial extortion

If funds or account access may still be at risk, the system displays verified protective guidance immediately.

11.2 Emergency assistance

For relevant financial cyberfraud cases:

Tell the user to contact their bank or payment provider through official channels immediately.

Show the national cybercrime helpline and reporting portal.

Explain what evidence to preserve.

Warn against giving more OTPs, PINs, passwords or remote-access permissions.

Help create a chronology and fraud complaint after urgent steps.

Explain bank complaint and eligible regulatory escalation routes.

Recovery cannot be guaranteed.

11.3 Liability analysis

The agent must distinguish:

Unauthorized electronic transactions

Transactions induced through deception

User-approved payments to fraudulent beneficiaries

Third-party system failures

Merchant or service disputes rather than fraud

It should retrieve the specific applicable RBI or other regulatory provisions before suggesting liability or reimbursement entitlement.

12. Complaint Dossier Engine

Every maintained case gets a structured dossier.

Dossier fields

Case ID

Case category

Parties involved

Chronological incident summary

Relevant dates

Disputed amount

User's desired remedy

Verified evidence inventory

Applicable legal sources

Existing communications

Suggested next steps

Official complaint references

Current case status

Follow-up and escalation history

Generated artifacts

The agent may produce:

Initial merchant complaint

Formal grievance email

Bank fraud report

Evidence checklist

Chronological statement of events

Consumer commission complaint draft

Follow-up letter

Authorization letter

RTI application

Basic agreement or notice

The product should identify drafts as preliminary where legal review or further verification is necessary.

Case status model

NEW → INTAKE → EVIDENCE_COLLECTION → DRAFT_READY → USER_APPROVED → ACTION_INITIATED → SUBMITTED/CONTACTED → AWAITING_RESPONSE → RESOLVED/ESCALATED/CLOSED

Record a submitted status only after independent confirmation. User-initiated contact and successful official filing are distinct events.

13. LangGraph Agent Architecture

The existing FastAPI and LangGraph architecture can be retained and upgraded.

13.1 Main agents and services

1. Interpreter / Triage Agent

Classifies the issue, extracts facts, determines urgency and routes to the right workflow.

2. Legal Research Agent

Searches the indexed corpus and approved official websites.

3. Corrective Retrieval Evaluator

Assesses retrieval quality and requests targeted corrections or additional evidence.

4. Legal Applicability Verifier

Checks dates, jurisdictions, historical mappings, authority and exceptions.

5. Resolution Planner

Determines recommended steps, evidence requirements and grievance channels.

6. Document Agent

Prepares drafts and case dossiers based on verified facts and user instructions.

7. Google Drive Agent

Manages case folders, evidence files and generated documents.

8. Gmail Agent

Searches authorized correspondence, prepares drafts, sends approved messages and retrieves replies.

9. Action/Contact Agent

Looks up verified phone numbers, WhatsApp destinations and official portals.

10. Safety and Approval Engine

Handles permissions, uncertainty, financial-fraud urgency, sensitive disclosures and confirmation before external actions.

These are logical roles. Not every role requires a separate LLM call. Deterministic code should handle file operations, access-control checks, exact statutory references and other predictable work.

13.2 Durable state

Use LangGraph checkpointing with PostgreSQL-backed persistence.

Store conversation state, case identity, workflow position and pending user approvals.

Use stable case IDs independently from conversation IDs, so the user can open the same case in a new chat.

13.3 Tool security

All Google or external-service actions must pass through authenticated backend adapters.

A retrieved document or email must never be able to instruct the assistant to send messages, disclose files, change recipients or override approvals.

Read operations, write operations and high-impact actions should have different authorization requirements.

14. Database and Infrastructure

Recommended production stack

Layer

Technology

Web interface

React / TypeScript

Backend

FastAPI

Agent orchestration

LangGraph

Primary relational database

PostgreSQL

Vector search

pgvector initially; Qdrant if warranted by scale

Keyword search

PostgreSQL full-text search, optionally OpenSearch

Embedding model

Multilingual model selected by Indian legal retrieval benchmarks

Reranking

Cross-encoder reranker

Shared legal documents

Versioned object storage

Private user evidence

User-owned Google Drive

Emails

Gmail API through MCP adapter

Background jobs

Celery or Dramatiq with Redis

Live research

Allowlisted official-source retrieval tools

Observability

Tracing, metrics, error monitoring and safe audit logs

Authentication

Secure application identity + Google OAuth

Secrets

Managed secret store and encrypted OAuth credentials

Primary tables

users

oauth_connections

cases

case_events

case_documents

drive_workspaces

legal_documents

legal_provisions

legal_versions

legal_relations

jurisdictions

source_registry

ingestion_jobs

official_contacts

complaint_procedures

drafts

action_approvals

external_actions

gmail_threads

evaluation_cases

PostgreSQL is the source of truth for structured data. The vector index is a derived search layer that can be rebuilt.

15. Privacy, Security and Trust

The application will process sensitive financial, identity and legal information, making security a fundamental product requirement.

Data boundaries

Shared legal knowledge: Public authoritative legal documents and carefully reviewed explanatory data.

Private case information: User-specific case metadata and permitted references.

Private evidence: Original documents in the user's Google Drive.

Temporary processing: Securely handled content used to answer questions or prepare documents.

Do not mix private evidence with the shared legal retrieval index.

Required protections

Per-user and per-case access authorization

Least-privilege OAuth

Encrypted communication and credentials

File-type and malware validation

No unnecessary bank account or identity data in logs

Sensitive-data minimization before external LLM calls

Explicit approval before disclosure or external action

Transparent retention and deletion policies

Safe credential revocation

Audit trails for sending, sharing and filing

No use of private case information for model training without separate valid authorization

Privacy and regulatory review before public launch

Important threat scenarios

Test prompt injection from malicious emails and PDFs, cross-user file access, forged grievance numbers, fake official websites, unauthorized email sending, duplicate messages after retries and unintended attachment disclosure.

The system should also prevent a fraudster from presenting a deceptive phone number as an official support contact.

16. Interface and Product Screens

Screen 1 — Home

Three prominent actions:

Know My Rights
Resolve a Complaint
Report Financial Fraud

Below them, show existing cases and their current statuses.

Screen 2 — Conversational Assistant

Main chat with voice input, file uploads, citation links, case-context controls and suggested next actions.

The assistant asks concise follow-up questions, preferably one or two at a time.

Screen 3 — My Cases

A case-management dashboard showing title, category, latest activity, status, documents, communications and next suggested action.

Each case opens its own detail view and Google Drive folder.

Screen 4 — Case Workspace

Organize into:

Overview

Evidence

Legal basis

Documents and drafts

Communications

Timeline

Actions and escalation

The case workspace should not require the user to leave the conversational interface for basic tasks.

Screen 5 — Email Review

Display recipients, subject, body and attachments.

The user can edit the message, approve the send or cancel.

Screen 6 — Verified Contact Actions

Show the relevant authority with tap-to-call, open-WhatsApp and open-portal actions where supported.

Screen 7 — Settings and Privacy

Google Drive connection, Gmail connection, permissions, data usage disclosures, case retention and disconnection controls.

17. Performance Strategy

Not every question needs a full multi-agent workflow.

Fast path

For familiar questions with sufficient indexed legal evidence, perform classification, hybrid retrieval, deterministic source checks and grounded generation.

Verified path

For state-specific cases or historical-law references, add jurisdiction and version-resolution steps.

Research path

For new regulations or ambiguous legal questions, fetch additional official sources and perform targeted verification.

Emergency path

For active financial fraud, return verified immediate action instructions before longer research.

Suggested performance objectives:

Workflow

Initial latency target

First urgent fraud instructions

Under 3 seconds

Common legal answer

Under 8 seconds p95

Complex verified legal answer

Under 20 seconds p95 where possible

Initial complaint draft

Under 30 seconds after required facts are available

Full case preparation

Approximately 1–3 minutes, excluding user interaction

These are engineering targets to validate, not promised product performance.

Use parallel retrieval, exact-match routing, caching, incremental source updates, controlled tool-call budgets and minimized LLM round trips.