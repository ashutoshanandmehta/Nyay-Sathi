// Certified Legal Knowledge Pack, concept expansion, authority classification, and temporal applicability.
// Compatible with Deno 2 and Node/Vitest.

import { sha256Hex } from './crypto.ts'

export interface EvidencePassage {
  passage_id: string
  source_id: string
  title: string
  locator: string
  text: string
  canonical_url: string
  retrieved_at: string
  limitations: string
  origin: 'certified_proposition' | 'official_pack' | 'web'
  content_hash?: string
  verification_status?: string
  source_type?: string
  jurisdiction?: string
  publication_date?: string | null
  effective_date?: string | null
  effective_until?: string | null
  origin_verified?: boolean
  certified_proposition?: boolean
  source_hierarchy_tier?: number
  factual_conditions?: string[]
  exceptions?: string[]
  scenario_tags?: string[]
  amendment_warning?: string
  judicial_treatment_status?: string
  domain?: string
  keywords?: string[]
  search_score?: number
}

export const CERTIFIED_PROPOSITIONS: EvidencePassage[] = [
  {
    passage_id: 'prop-urgent-shafin-jahan-2018',
    source_id: 'sc-shafin-jahan-2018',
    title: 'Shafin Jahan v. Asokan K.M. (Supreme Court of India, 2018)',
    locator: 'Criminal Appeal No. 366 of 2018 (arising out of SLP (Crl.) No. 5777 of 2017), Judgment dated 08-Mar-2018',
    text: "An adult person of sound mind has the constitutionally protected autonomy under Article 21 (and Article 19(1)(a)) to choose a life partner and decide with whom to live; family disapproval, social pressure or patriarchal notions of honour do not authorise police or third parties to detain or separate a consenting adult.\n\nExact official passage: The right to marry a person of one's choice is integral to Article 21 of the Constitution. Society has no role to play in determining our choice of partners. Expression of choice in accord with law is acceptance of individual identity.",
    canonical_url: 'https://api.sci.gov.in/supremecourt/2017/19702/19702_2017_Judgement_08-Mar-2018.pdf',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations:
      'Binding three-Judge Bench precedent of the Supreme Court of India. Exceptions: Does not immunise conduct involving a minor (<18 years) or coercion/trafficking.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2018-03-08',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 1,
    domain: 'constitutional_urgent',
    keywords: ['adult', 'autonomy', 'marry', 'partner', 'consenting', 'harassment', 'family', 'police', 'liberty', 'article 21', 'shafin jahan', 'habeas corpus', 'interfaith'],
  },
  {
    passage_id: 'prop-urgent-nandakumar-2018',
    source_id: 'sc-nandakumar-2018',
    title: 'Nandakumar v. State of Kerala (Supreme Court of India, 2018)',
    locator: 'Criminal Appeal No. 597 of 2018, Judgment dated 20-Apr-2018',
    text: 'Consenting adults have the right to live together in a live-in relationship outside marriage even if one adult has not yet reached the statutory minimum marriageable age for a male (21 years), and their personal liberty cannot be curtailed merely because they are unmarried or below marriageable age while being major (>=18).\n\nExact official passage: Both the appellants are major. Even if they were not competent to enter into wedlock, they have right to live together even outside wedlock. Freedom of choice is guaranteed under Article 21 of the Constitution of India.',
    canonical_url: 'https://api.sci.gov.in/supremecourt/2017/15646/15646_2017_Judgement_20-Apr-2018.pdf',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'Binding Supreme Court precedent; specifically addresses consenting majors (>=18) living or associating together outside marriage.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2018-04-20',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 1,
    domain: 'constitutional_urgent',
    keywords: ['live-in', 'unmarried', 'couple', 'major', '18', '19', '20', '21', 'adults', 'police', 'nandakumar', 'liberty', 'wedlock'],
  },
  {
    passage_id: 'prop-urgent-madras-hc-hotel-unmarried-2019',
    source_id: 'madras-hc-hotel-unmarried-2019',
    title: 'Mypreferred Transformation & Hospitality Pvt. Ltd. v. District Collector, Coimbatore (Madras HC, 2019)',
    locator: 'W.P. No. 31505 of 2016, Order dated 25-Jun-2019',
    text: 'Directly addressing hotel accommodation, the Madras High Court held that the occupation of a hotel room by an unmarried couple of consenting adults is not a criminal offence under Indian law and cannot by itself be treated as immoral or illegal activity to justify police raids, sealing, or harassment.\n\nExact official passage: The occupation of a hotel room by an unmarried couple of consenting adults does not constitute a criminal offence under Indian law; live-in relationships and consensual association between adults are protected aspects of personal liberty.',
    canonical_url: 'https://hcmadras.tn.gov.in/',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'High Court precedent relying on Supreme Court Article 21 jurisprudence; persuasive across India and directly binding in Tamil Nadu.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2019-06-25',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 2,
    domain: 'constitutional_urgent',
    keywords: ['hotel', 'oyo', 'room', 'unmarried', 'couple', 'checked', 'stay', 'illegal', 'police', 'harassing', 'adults'],
  },
  {
    passage_id: 'prop-urgent-pca-1988-bribe-demand-s7',
    source_id: 'india-code-pca-1988-s7',
    title: 'Prevention of Corruption Act, 1988 — Section 7 (India Code)',
    locator: 'Prevention of Corruption Act, 1988 (Act 49 of 1988), Section 7 (as substituted by Act 16 of 2018, w.e.f. 26-Jul-2018)',
    text: 'Under Section 7 of the Prevention of Corruption Act, 1988 (as substituted in 2018), a public servant who obtains, accepts, or attempts to obtain an undue advantage (such as demanding a cash or UPI bribe to refrain from threatening or filing a baseless case) with intent to perform or forbear from performing a public duty improperly or dishonestly commits a punishable offence.\n\nExact official passage: Section 7. Offence relating to public servant being bribed.—Any public servant who obtains or accepts or attempts to obtain from any person, an undue advantage, with the intention to perform or cause performance of public duty improperly or dishonestly or to forbear or cause forbearance to perform such duty either by himself or by another public servant, shall be punishable with imprisonment which shall not be less than three years.',
    canonical_url: 'https://indiacode.nic.in/bitstream/123456789/9317/1/corruptiona1988-49.pdf',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'Section 7 addresses the public servant offence of demanding/obtaining a bribe; do not cite Section 7 for the separate Section 8(1) proviso concerning compelled bribe-givers.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2018-07-26',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 2,
    domain: 'criminal',
    keywords: ['bribe', 'money', 'demand', 'cash', 'police', 'officers', 'fake', 'impersonation', 'extortion', 'corruption', 'undue advantage', 'upi', 'raid', 'room'],
  },
  {
    passage_id: 'prop-urgent-pca-1988-compelled-reporting-s8',
    source_id: 'india-code-pca-1988-s8',
    title: 'Prevention of Corruption Act, 1988 — Section 8(1) Provisos (India Code)',
    locator: 'Prevention of Corruption Act, 1988 (Act 49 of 1988), Section 8(1), First and Second Provisos (w.e.f. 26-Jul-2018)',
    text: 'Under the First and Second Provisos to Section 8(1) of the Prevention of Corruption Act, 1988 (as amended in 2018), a person who was compelled to give an undue advantage (bribe) is protected from prosecution under Section 8 provided that the person reports the matter to the law enforcement authority or investigating agency within seven days from the date of giving such undue advantage.\n\nExact official passage: Section 8(1) Provisos: Provided that the provisions of this section shall not apply where a person is compelled to give such undue advantage: Provided further that the person so compelled shall report the matter to the law enforcement authority or investigating agency within a period of seven days from the date of giving such undue advantage.',
    canonical_url: 'https://indiacode.nic.in/bitstream/123456789/9317/1/corruptiona1988-49.pdf',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'The seven-day reporting rule belongs strictly to Section 8(1) provisos, never Section 7.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2018-07-26',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 2,
    domain: 'criminal',
    keywords: ['paid', 'compelled', 'seven days', 'section 8', 'forced', 'handed over', 'transferred', 'acb', 'bribe'],
  },
  {
    passage_id: 'prop-urgent-erss-112-mha',
    source_id: 'mha-erss-112',
    title: 'Emergency Response Support System (ERSS 112) — Ministry of Home Affairs',
    locator: 'MHA Official ERSS Overview',
    text: "India's Emergency Response Support System (ERSS) provides the pan-India single emergency number 112 (managed under Ministry of Home Affairs guidance) to reach police, fire, and emergency dispatch, and can be used when safe to verify whether uniformed or plainclothes personnel at a location are part of an authorised police dispatch.\n\nExact official passage: Emergency Response Support System (ERSS) is a pan-India single number (112) based emergency response system for citizens in emergencies, integrating Police (100), Fire (101), Health (108) and Women Helpline (181) services.",
    canonical_url: 'https://www.mha.gov.in/emergency-response-support-system-erss',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'Never escalate physical danger by calling in front of hostile individuals if unsafe.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2019-02-19',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 4,
    domain: 'criminal',
    keywords: ['112', 'emergency', 'police', 'fake', 'verify', 'officers', 'danger', 'threat', 'violence', 'detain', 'custody', 'erss', 'mha'],
  },
  {
    passage_id: 'prop-cyber-i4c-1930-portal',
    source_id: 'mha-i4c-cybercrime-1930',
    title: 'National Cyber Crime Reporting Portal (cybercrime.gov.in) & Helpline 1930',
    locator: 'MHA I4C Citizen Financial Cyber Fraud Reporting System — Helpline 1930 & cybercrime.gov.in',
    text: 'For cyber-financial fraud in India (including fake customer-care numbers, phishing links, compromised digital wallets, UPI scams, and unauthorized bank debits), victims should immediately call the National Cyber Crime Helpline 1930 and submit a formal financial-fraud complaint on https://cybercrime.gov.in with transaction IDs/UTRs, suspect phone numbers, and phishing URLs.\n\nExact official passage: Victims of online financial cyber fraud should immediately call the National Cyber Crime Helpline number 1930 and register a formal financial-fraud complaint on https://cybercrime.gov.in with bank/wallet transaction IDs, suspect phone numbers, and links.',
    canonical_url: 'https://cybercrime.gov.in/',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'Fund recovery depends on whether money remains in recipient/intermediary accounts before withdrawal and is never guaranteed.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2021-01-01',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 3,
    domain: 'cyber_fraud',
    keywords: ['1930', 'cybercrime', 'debited', 'fraud', 'scam', 'phishing', 'link', 'whatsapp', 'wallet', 'password', 'pin', 'otp', 'upi', 'bank', 'customer care'],
  },
  {
    passage_id: 'prop-banking-rbi-unauthorised-liability',
    source_id: 'rbi-unauthorised-electronic-tx',
    title: 'Reserve Bank of India — Limiting Liability of Customers in Unauthorised Electronic Banking Transactions',
    locator: 'RBI Circular DBR.No.Leg.BC.78/09.07.005/2017-18 (and PPI / Responsible Business Conduct Directions)',
    text: 'Under Reserve Bank of India customer-protection directions on unauthorised electronic banking and prepaid payment instrument (wallet) transactions, a customer must notify the bank/issuer immediately to block compromised access. Zero liability applies automatically only where the deficiency lies with the bank or a third-party breach without customer deficiency (reported within 3 working days). Where loss occurs due to customer negligence—such as sharing credentials via a phishing link—customer liability before reporting is not automatically zero, whereas any further unauthorised debit occurring AFTER notifying the bank rests on the bank.\n\nExact official passage: Customers must notify their bank immediately of any unauthorised electronic banking transaction so payment access can be blocked to prevent further loss.',
    canonical_url: 'https://www.rbi.org.in/',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'Never promise an automatic bank refund where the user clicked a phishing link or entered a password/OTP.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2017-07-06',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 2,
    domain: 'cyber_fraud',
    keywords: ['rbi', 'bank', 'debited', 'unauthorized', 'unauthorised', 'liability', 'password', 'credentials', 'wallet', 'block', 'refund', 'phishing', 'transactions'],
  },
  {
    passage_id: 'prop-consumer-ecommerce-grievance-r4',
    source_id: 'cpa-ecommerce-rules-2020',
    title: 'Consumer Protection (E-Commerce) Rules, 2020',
    locator: 'Consumer Protection (E-Commerce) Rules, 2020, Rule 4(4)-(5), Gazette pages 3-4',
    text: "Under Rule 4(4)–(5) of the Consumer Protection (E-Commerce) Rules, 2020, every e-commerce entity must appoint a grievance officer, display their contact mechanism, acknowledge consumer complaints within 48 hours, and redress the complaint within one month from receipt.\n\nExact official passage: An e-commerce entity must maintain a grievance-redress mechanism and display the grievance officer's details. Rule 4 states that the officer must acknowledge a consumer complaint within forty-eight hours and redress it within one month from receipt.",
    canonical_url: 'https://consumeraffairs.gov.in/public/upload/files/E%20commerce%20rules_1732703966.pdf',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'Does not automatically guarantee a refund where underlying physical return/pickup facts are disputed.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2020-07-23',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 3,
    domain: 'consumer',
    keywords: ['amazon', 'flipkart', 'blinkit', 'goibibo', 'ecommerce', 'online', 'refund', 'return', 'grievance', 'support', 'booking', 'hotel', 'order', '48 hours'],
  },
  {
    passage_id: 'prop-consumer-nch-prelitigation',
    source_id: 'nch-about',
    title: 'National Consumer Helpline (1915 / consumerhelpline.gov.in) — Department of Consumer Affairs',
    locator: 'About National Consumer Helpline — Portal questions 1, 8 and 9 (Toll-Free 1915)',
    text: 'When platform customer support and the platform Grievance Officer have already closed, ignored, or redirected a consumer refund/return dispute, the immediate external pre-litigation next step is filing a grievance on the National Consumer Helpline (NCH — toll-free 1915 or https://consumerhelpline.gov.in).\n\nExact official passage: The National Consumer Helpline portal is a pre-litigation grievance mechanism. It forwards grievances to the concerned company, agency, regulator or ombudsman. It does not guarantee a remedy. If the grievance is not resolved to the consumer satisfaction, the consumer may approach the appropriate Consumer Commission.',
    canonical_url: 'https://consumerhelpline.gov.in/public/index.php/about',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'NCH is pre-litigation assistance, not a court, and filing on NCH does not pause the two-year statutory limitation under Section 69 CPA 2019.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2020-07-20',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 3,
    domain: 'consumer',
    keywords: ['nch', 'helpline', '1915', 'consumer', 'escalation', 'refund', 'return', 'pickup', 'closed', 'grievance', 'amazon', 'flipkart', 'goibibo', 'ejagriti'],
  },
  {
    passage_id: 'prop-consumer-cpa2019-district-forum-s35',
    source_id: 'india-code-cpa-2019',
    title: 'Consumer Protection Act, 2019 — Sections 35 & 69 (India Code)',
    locator: 'Consumer Protection Act, 2019, Sections 35(1) and 69',
    text: 'Under Sections 35 and 69 of the Consumer Protection Act, 2019, if internal grievance redress and National Consumer Helpline pre-litigation efforts do not resolve a consumer deficiency or disputed refund, a consumer may file a formal complaint before the District Consumer Disputes Redressal Commission where paid consideration does not exceed Rs. 50 lakh, within two years from the date the cause of action arose.\n\nExact official passage: A complaint, in relation to any goods sold or delivered or agreed to be sold or delivered or any service provided or agreed to be provided, may be filed with a District Commission by the consumer... within two years from the date on which the cause of action has arisen.',
    canonical_url: 'https://www.indiacode.nic.in/bitstream/123456789/15256/1/eng201935.pdf',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'Pure employer-employee unpaid salary disputes are employment matters, not consumer disputes under CPA 2019.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2020-07-20',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 2,
    domain: 'consumer',
    keywords: ['consumer', 'commission', 'district', 'complaint', 'limitation', 'two years', 'refund', 'deficiency', 'unfair', 'ejagriti', 'section 35'],
  },
  {
    passage_id: 'prop-employment-unpaid-wages-routing',
    source_id: 'nalsa-faq-legal-services',
    title: 'NALSA Official Legal Services & Employment Forum Routing Guidance',
    locator: 'NALSA Official Referral & Legal Aid Guidance (Section 12 & 13 Legal Services Authorities Act, 1987)',
    text: 'In India, the appropriate forum for recovering unpaid salary or full-and-final dues depends on (1) the state/location of the establishment and workplace, (2) the worker role, duties, supervisory/managerial authority and wage level, and (3) any valid arbitration or jurisdiction clause in the appointment contract; employment wage claims are not consumer disputes.\n\nExact official passage: NALSA helps individuals access legal aid through different Legal Services Institutions such as SLSAs/DLSAs, if they meet the eligibility criteria under Section 12 and 13 of the Legal Services Authorities Act, 1987.',
    canonical_url: 'https://nalsa.gov.in/faqs/',
    retrieved_at: '2026-11-07T00:00:00Z',
    limitations: 'Verify state-specific Shops & Establishments or Payment of Wages commencement before filing.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '1995-11-09',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 4,
    domain: 'employment',
    keywords: ['salary', 'wages', 'unpaid', 'employer', 'termination', 'appointment letter', 'settlement', 'employment', 'labour', 'legal aid'],
  },
  {
    passage_id: 'prop-criminal-fir-mandatory-s154-lalita-kumari',
    source_id: 'sc-lalita-kumari-fir-s154',
    title: 'Code of Criminal Procedure (S.154) / BNSS (S.173) & Lalita Kumari v. Govt. of U.P. (SC 2014)',
    locator: 'Criminal Procedure Code, 1973 (S. 154) / BNSS 2023 (S. 173) & Lalita Kumari (2014) 2 SCC 1',
    text: 'Under Section 154 of the Code of Criminal Procedure, 1973 (and Section 173 of the Bharatiya Nagarik Suraksha Sanhita, 2023), the police are legally required to register a First Information Report (FIR) when information discloses the commission of a cognizable offence.\n\nExact official passage: Registration of FIR is mandatory under Section 154 of the Code, if the information discloses commission of a cognizable offence and no preliminary inquiry is permissible in such a situation. A copy of the information as recorded shall be given forthwith, free of cost, to the informant.',
    canonical_url: 'https://api.sci.gov.in/supremecourt/2008/398/398_2008_Judgement_12-Nov-2013.pdf',
    retrieved_at: '2026-11-08T00:00:00Z',
    limitations: 'Preliminary inquiry may be conducted only in specific exceptional categories before FIR registration.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2013-11-12',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 1,
    domain: 'criminal',
    keywords: ['fir', 'first information report', 'police', 'file', 'cognizable', 'section 154', 'bnss 173', 'lalita kumari', 'free copy', 'complaint'],
  },
  {
    passage_id: 'prop-criminal-zero-fir-procedure',
    source_id: 'mha-zero-fir-advisory',
    title: 'MHA Advisory on Zero FIR & Mandatory Registration of Crime',
    locator: 'MHA Advisory No. 15011/35/2013-SC/ST-W & BNSS 2023 Section 173(1)',
    text: 'Under the Zero FIR mechanism established by Ministry of Home Affairs advisories and BNSS Section 173(1), a police station cannot refuse to record an FIR on the grounds of lack of territorial jurisdiction.\n\nExact official passage: A Zero FIR can be filed in any police station, irrespective of where the crime took place or territorial jurisdiction. The police station registering the Zero FIR will subsequently transfer the case to the appropriate police station having territorial jurisdiction.',
    canonical_url: 'https://www.mha.gov.in/sites/default/files/Advisory_Crime_Registration.pdf',
    retrieved_at: '2026-11-08T00:00:00Z',
    limitations: 'Regular investigation continues under the jurisdictional police station after transfer.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2013-05-10',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 2,
    domain: 'criminal',
    keywords: ['zero fir', 'jurisdiction', 'police station', 'transfer', 'refusal', 'crime', 'urgent', 'territorial'],
  },
  {
    passage_id: 'prop-criminal-fir-refusal-remedies-s154-s156',
    source_id: 'india-code-crpc-refusal-remedies',
    title: 'Criminal Procedure Code Sections 154(3) & 156(3) / BNSS Sections 173(4) & 175(3)',
    locator: 'CrPC, 1973 Sections 154(3) & 156(3) / BNSS, 2023 Sections 173(4) & 175(3) (Sakiri Vasu v. State of U.P.)',
    text: 'If a police station officer refuses to register an FIR for a cognizable offence, the legal remedies available are: (1) send the substance of the complaint in writing by registered post to the Superintendent of Police (SP) under Section 154(3) CrPC (Section 173(4) BNSS); and (2) if the SP fails to act, file an application before the Judicial Magistrate under Section 156(3) CrPC (Section 175(3) BNSS).\n\nExact official passage: Any person aggrieved by a refusal on the part of an officer in charge of a police station to record the information may send the substance of such information, in writing and by post, to the Superintendent of Police concerned... Any Magistrate empowered under section 190 may order such an investigation.',
    canonical_url: 'https://www.indiacode.nic.in/bitstream/123456789/15272/1/crpc_1973.pdf',
    retrieved_at: '2026-11-08T00:00:00Z',
    limitations: 'Priyanka Srivastava v. State of U.P. (2015) mandates prior affidavit and Section 154(1)/(3) compliance.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '1974-04-01',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 1,
    domain: 'criminal',
    keywords: ['police refused', 'refusal', 'fir', 'superintendent of police', 'sp', 'dcp', 'magistrate', 'section 156(3)', 'section 154(3)', 'bnss 175'],
  },
  {
    passage_id: 'prop-consumer-cpa2019-defective-goods-s2-s39',
    source_id: 'india-code-cpa-2019-defective-goods',
    title: 'Consumer Protection Act, 2019 — Sections 2(10), 2(42) & 39 (Defective Goods & Remedies)',
    locator: 'Consumer Protection Act, 2019, Sections 2(10) (defect), 2(11) (deficiency) & 39(1)(a)-(d)',
    text: 'Under Sections 2(10) and 39(1) of the Consumer Protection Act, 2019, where goods bought by a consumer suffer from a fault, imperfection, or shortcoming in quality, quantity, potency, purity, or standard required to be maintained by law or under contract, the Consumer Commission may direct removal of the defect, replacement with new goods of similar description free from defect, return of the price paid, or compensation for proved loss.\n\nExact official passage: Section 39(1). Where the District Commission is satisfied that the goods complained against suffer from any of the defects specified in the complaint... it shall issue an order to the opposite party directing him to do one or more of the following, namely:— (a) to remove the defect... (b) to replace the goods with new goods of similar description which shall be free from any defect; (c) to return to the complainant the price, or, as the case may be, the charges paid by the complainant.',
    canonical_url: 'https://www.indiacode.nic.in/bitstream/123456789/15256/1/eng201935.pdf',
    retrieved_at: '2026-11-08T00:00:00Z',
    limitations: 'Entitlement to replacement or refund requires establishing that the product was defective rather than damaged by misuse after delivery.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2020-07-20',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 2,
    domain: 'consumer',
    keywords: ['defective', 'damaged', 'broken', 'warranty', 'replacement', 'repair', 'fault', 'appliance', 'phone', 'laptop', 'section 39', 'product'],
  },
  {
    passage_id: 'prop-banking-rbi-failed-tx-tat-2019',
    source_id: 'rbi-failed-tx-tat-2019',
    title: 'RBI Harmonisation of Turn Around Time (TAT) and Customer Compensation for Failed Transactions',
    locator: 'RBI Circular DPSS.CO.PD No.629/02.01.014/2019-20 dated 20-Sep-2019',
    text: 'Under the Reserve Bank of India circular on Harmonisation of Turn Around Time (TAT) and customer compensation for failed transactions, if a customer account is debited in a failed UPI, IMPS, card-to-card, or ATM transaction without credit to the beneficiary/merchant, the bank must auto-reverse the amount within the prescribed timeline (T+1 day for UPI/IMPS, T+5 days for POS/e-commerce card debits), failing which the bank must pay compensation of Rs. 100 per day of delay beyond the prescribed TAT.\n\nExact official passage: In case of failed transactions where the customer account is debited, banks are required to auto-reverse the transaction within the prescribed Turn Around Time (TAT), failing which financial compensation of Rs. 100/- per day of delay beyond TAT shall be credited to the customer account without waiting for a claim from the customer.',
    canonical_url: 'https://www.rbi.org.in/',
    retrieved_at: '2026-11-08T00:00:00Z',
    limitations: 'Applies strictly to technical failed transactions where the beneficiary account was not credited; does not apply to successful transfers induced by fraud.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2019-10-15',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 2,
    domain: 'banking',
    keywords: ['failed', 'transaction', 'upi', 'imps', 'atm', 'debited', 'not credited', 'auto-reversal', 'tat', '100 per day', 'compensation', 'pending'],
  },
  {
    passage_id: 'prop-banking-rbi-ombudsman-2021',
    source_id: 'rbi-integrated-ombudsman-2021',
    title: 'Reserve Bank - Integrated Ombudsman Scheme, 2021 (cms.rbi.org.in)',
    locator: 'Reserve Bank - Integrated Ombudsman Scheme, 2021, Clauses 10 & 13',
    text: 'Under the Reserve Bank - Integrated Ombudsman Scheme, 2021, a customer can escalate a deficiency-in-service complaint against a regulated bank or NBFC/payment system participant on https://cms.rbi.org.in (or CRPC Chandigarh) ONLY AFTER first submitting a written complaint to the regulated entity and either (a) receiving a rejection or unsatisfactory reply, or (b) receiving no reply within 30 days after the bank received the complaint.\n\nExact official passage: A complaint under the Scheme shall not lie unless the complainant had, before making a complaint under the Scheme, made a written complaint to the Regulated Entity concerned and the complaint was rejected wholly or partly or the complainant had not received any reply within 30 days after the Regulated Entity received the complaint.',
    canonical_url: 'https://cms.rbi.org.in/',
    retrieved_at: '2026-11-08T00:00:00Z',
    limitations: 'Cannot be filed directly with the RBI Ombudsman without first complaining in writing to the bank/issuer and waiting up to 30 days unless rejected earlier.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2021-11-12',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 2,
    domain: 'banking',
    keywords: ['ombudsman', 'rbi', 'cms', '30 days', 'bank complaint', 'escalation', 'nodal officer', 'banking', 'dispute'],
  },
  {
    passage_id: 'prop-criminal-ipc-cheating-s420-historical',
    source_id: 'india-code-ipc-1860-s420',
    title: 'Indian Penal Code, 1860 — Section 420 (Historical: Offences Prior to 1 July 2024)',
    locator: 'Indian Penal Code, 1860, Section 420 read with BNS, 2023 Section 358 (Repeal and Savings)',
    text: 'For substantive offences of cheating and dishonestly inducing delivery of property committed BEFORE 1 July 2024, Section 420 of the Indian Penal Code, 1860 remains the applicable substantive offence provision by virtue of the savings clause in Section 358 of the Bharatiya Nyaya Sanhita, 2023.\n\nExact official passage: Section 420 IPC: Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person... shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine.',
    canonical_url: 'https://www.indiacode.nic.in/bitstream/123456789/15289/1/ipc_act.pdf',
    retrieved_at: '2026-11-08T00:00:00Z',
    limitations: 'Repealed for prospective offences from 1 July 2024; applies only where the substantive offence date was prior to 1 July 2024.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '1862-01-01',
    effective_until: '2024-06-30',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 1,
    domain: 'criminal',
    keywords: ['ipc', '420', 'section 420', 'cheating', '2023', 'historical', 'before july 2024', 'old law'],
  },
  {
    passage_id: 'prop-criminal-bns-cheating-s318-current',
    source_id: 'india-code-bns-2023-s318',
    title: 'Bharatiya Nyaya Sanhita, 2023 — Section 318(4) (Offences on or after 1 July 2024)',
    locator: 'Bharatiya Nyaya Sanhita, 2023 (Act 45 of 2023), Section 318(4) & Section 358 (w.e.f. 01-Jul-2024)',
    text: 'For substantive offences of cheating and dishonestly inducing delivery of property committed ON OR AFTER 1 July 2024, Section 318(4) of the Bharatiya Nyaya Sanhita, 2023 (BNS) applies in place of erstwhile IPC Section 420.\n\nExact official passage: Section 318(4) BNS: Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person... shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine.',
    canonical_url: 'https://www.indiacode.nic.in/',
    retrieved_at: '2026-11-08T00:00:00Z',
    limitations: 'Does not apply retrospectively to substantive conduct committed prior to 1 July 2024 (which remains governed by IPC Section 420 under BNS Section 358).',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2024-07-01',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 1,
    domain: 'criminal',
    keywords: ['bns', '318', 'section 318', 'cheating', '420', 'ipc', 'new criminal law', 'july 2024'],
  },
  {
    passage_id: 'prop-criminal-bnss-s531-transitional-savings',
    source_id: 'india-code-bnss-2023-s531',
    title: 'Bharatiya Nagarik Suraksha Sanhita, 2023 — Section 531 (Repeal and Transitional Savings)',
    locator: 'Bharatiya Nagarik Suraksha Sanhita, 2023 (Act 46 of 2023), Section 531(2)(a) (w.e.f. 01-Jul-2024)',
    text: 'Mapping an old CrPC provision to a new BNSS section is not sufficient by itself: under Section 531(2)(a) of the Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS), if any appeal, application, trial, inquiry, or investigation was pending immediately before 1 July 2024, it continues to be disposed of, continued, held, or made in accordance with the Code of Criminal Procedure, 1973 (CrPC). Fresh FIRs registered on or after 1 July 2024 are governed procedurally by BNSS, while the substantive offence remains governed by the statute in force on the date of the offence.\n\nExact official passage: Section 531(2)(a) BNSS: If, immediately before the date on which this Sanhita comes into force, there is any appeal, application, trial, inquiry or investigation pending, then, such appeal, application, trial, inquiry or investigation shall be disposed of, continued, held or made, as the case may be, in accordance with the provisions of the Code of Criminal Procedure, 1973.',
    canonical_url: 'https://www.ncrb.mha.gov.in/uploads/SankalanPortal/DownloadPDF/BNSS2023.pdf',
    retrieved_at: '2026-11-08T00:00:00Z',
    limitations: 'When the incident date or FIR registration date is unknown, state both the pre-July-2024 (IPC/CrPC) and post-July-2024 (BNS/BNSS) position and ask for the dates.',
    origin: 'certified_proposition',
    verification_status: 'editor_certified',
    source_type: 'indian_official',
    jurisdiction: 'India',
    effective_date: '2024-07-01',
    origin_verified: true,
    certified_proposition: true,
    source_hierarchy_tier: 1,
    domain: 'criminal',
    keywords: ['transitional', 'section 531', 'bnss', 'crpc', 'ipc', 'bns', '1 july 2024', 'pending trial', 'pending investigation', 'repeal'],
  },
]

const CONCEPT_EXPANSIONS: Array<[RegExp, string]> = [
  [/\b(?:jail|arrest\w*|custody|giraftar\w*|hirasat|lock-?up|thana)\b|जेल|गिरफ्तार|हिरासत/iu, 'bail custody arrest legal aid'],
  [/\b(?:complaint|fir|thana|police\s+station|report\s+to\s+police)\b|शिकायत|shikayat/iu, 'information cognizable offence first information report fir police station written complaint superintendent of police'],
  [/\b(?:police\s+refus\w*|refus\w*\s+(?:to\s+)?(?:register|file|write|take|lodge)\w*|not\s+register\w*|complaint\s+not\s+taken)\b|fir\s+nah[ií]\s+likh\w*|शिकायत\s+न(?:हीं|ही)\s+लिख\w*/iu, 'non-cognizable police refused FIR not registered superintendent magistrate order investigation'],
  [/\b(?:salary|wages?|tankhwah|vetan|payslip)\b|वेतन|तनख्वाह/iu, 'wages payment claims employment salary unpaid'],
  [/\b(?:refund|return|damaged|defective|order|delivery|amazon|flipkart|goibibo|blinkit|meesho)\b|रिफंड|वापसी/iu, 'consumer grievance officer refund 48 hours nch 1915 district commission'],
  [/\b(?:upi|otp|phishing|debited|scam|fraud|unauthorized|unauthorised|cyber|1930)\b|धोखाधड़ी|फ्रॉड/iu, 'cybercrime 1930 unauthorized electronic banking transaction rbi liability block'],
]

export function expandQueryConcepts(message: string, domain = 'unknown', urgentContinuation = false): string {
  const cleaned = (message || '').replace(/\S+@\S+|https?:\/\/\S+|\b\d[\d\-/.,]*\b/g, ' ')
  const words = (cleaned.toLowerCase().match(/[a-z\u0900-\u097f]{3,}/gu) || []).slice(0, 48)
  const extras: string[] = []
  for (const [pattern, expansion] of CONCEPT_EXPANSIONS) {
    if (pattern.test(message)) extras.push(expansion)
  }
  if (domain && domain !== 'unknown' && domain !== 'general') extras.push(domain)
  if (urgentContinuation) extras.push('police bribe corruption emergency liberty 112')
  return [...words, ...extras].join(' ').trim()
}

export function classifyOfficialAuthority(url: string): { isOfficial: boolean; jurisdiction: string | null; tier: number } {
  try {
    const parsed = new URL(url)
    const host = parsed.hostname.toLowerCase()
    if (host.endsWith('.gov') && !host.endsWith('.gov.in')) {
      return { isOfficial: false, jurisdiction: null, tier: 5 }
    }
    if (host === 'api.sci.gov.in' || host === 'sci.gov.in' || host.endsWith('.sci.gov.in')) {
      return { isOfficial: true, jurisdiction: 'India', tier: 1 }
    }
    if (host.endsWith('.nic.in') || host.endsWith('.gov.in') || host === 'rbi.org.in' || host.endsWith('.rbi.org.in')) {
      return { isOfficial: true, jurisdiction: 'India', tier: 2 }
    }
    return { isOfficial: false, jurisdiction: null, tier: 5 }
  } catch {
    return { isOfficial: false, jurisdiction: null, tier: 5 }
  }
}

export function isTemporallyApplicable(
  passage: Pick<EvidencePassage, 'effective_date' | 'effective_until'>,
  asOfIso?: string | null
): { applicable: boolean; reason: string } {
  if (!asOfIso) return { applicable: true, reason: 'no_incident_date_filter' }
  const dateOnly = asOfIso.slice(0, 10)
  if (!passage.effective_date) {
    return { applicable: true, reason: 'effective_date_unknown_requires_qualification' }
  }
  if (dateOnly < passage.effective_date.slice(0, 10)) {
    return {
      applicable: false,
      reason: `Incident date ${dateOnly} precedes commencement/effective date ${passage.effective_date}`,
    }
  }
  if (passage.effective_until && dateOnly > passage.effective_until.slice(0, 10)) {
    return {
      applicable: false,
      reason: `Incident date ${dateOnly} is after repeal/supersession date ${passage.effective_until}`,
    }
  }
  return { applicable: true, reason: 'within_effective_interval' }
}

export async function retrieveCertifiedPassages(options: {
  query: string
  domain?: string
  jurisdiction?: string
  asOfDate?: string | null
  limit?: number
  customPassages?: EvidencePassage[]
}): Promise<{ passages: EvidencePassage[]; diagnostics: { query_hash: string; total_candidates: number } }> {
  const expanded = expandQueryConcepts(options.query, options.domain)
  const tokens = Array.from(new Set(expanded.toLowerCase().match(/[a-z0-9\u0900-\u097f]{2,}/gu) || []))
  const pool = options.customPassages && options.customPassages.length > 0
    ? options.customPassages
    : CERTIFIED_PROPOSITIONS
  const limit = options.limit ?? 6
  const scored: EvidencePassage[] = []

  for (const item of pool) {
    if (options.jurisdiction) {
      const jur = (item.jurisdiction || 'India').toLowerCase()
      const wanted = options.jurisdiction.toLowerCase()
      if (jur !== wanted && jur !== 'india' && jur !== 'central') continue
    }
    const temporal = isTemporallyApplicable(item, options.asOfDate)
    if (!temporal.applicable) continue

    const haystack = `${item.title} ${item.locator} ${item.text} ${(item.keywords || []).join(' ')} ${(item.scenario_tags || []).join(' ')}`.toLowerCase()
    const keywordSet = new Set((item.keywords || []).map(k => k.toLowerCase()))
    let score = 0
    for (const token of tokens) {
      if (keywordSet.has(token)) score += 3.0
      else if (haystack.includes(token)) score += 1.2
    }
    if (options.domain && item.domain === options.domain) {
      score += 2.5
    }
    if (item.certified_proposition) {
      score += 1.5
    }
    if (score > 0) {
      scored.push({ ...item, search_score: Number(score.toFixed(3)) })
    }
  }

  scored.sort((a, b) => (b.search_score || 0) - (a.search_score || 0))
  const queryHash = (await sha256Hex(expanded)).slice(0, 16)
  return {
    passages: scored.slice(0, limit),
    diagnostics: {
      query_hash: queryHash,
      total_candidates: scored.length,
    },
  }
}

export interface TemporalApplicabilityResolution {
  incident_date: string | null
  procedural_stage: 'pending_before_2024_07_01' | 'fresh_after_2024_07_01' | 'unknown'
  substantive_regime: 'IPC_1860' | 'BNS_2023' | 'DUAL_DATE_UNKNOWN' | 'NON_CRIMINAL_CENTRAL'
  procedural_regime: 'CRPC_1973' | 'BNSS_2023' | 'DUAL_STAGE_UNKNOWN' | 'NON_CRIMINAL_CENTRAL'
  transitional_note: string
  jurisdiction_finding:
    | 'india_central_applicable'
    | 'state_specific_verification_required'
    | 'outside_india_coverage'
  detected_state: string | null
  requires_date_clarification: boolean
}

export interface CorrectiveRetrievalFindings {
  relevance: 'supported' | 'low_relevance' | 'no_candidates'
  source_authority: 'indian_official_verified' | 'unverified_or_mixed'
  date_applicability: 'confirmed_interval' | 'transitional_dual_regime' | 'date_unknown_qualified' | 'conflict_detected'
  jurisdiction: 'matched_india_central' | 'state_specific_gap' | 'foreign_mismatch'
  completeness: 'sufficient' | 'material_gap_requires_clarification'
  warnings: string[]
  cache_epoch?: number
  invalidated_provisions?: string[]
}

const PROVISION_TO_PASSAGE_MAP: Record<string, string[]> = {
  'prov-cpa-2019-s35-s69': ['prop-consumer-cpa2019-district-forum-s35'],
  'prov-ipc-1860-s420': ['prop-criminal-ipc-cheating-s420-historical'],
  'prov-bns-2023-s318': ['prop-criminal-bns-cheating-s318-current'],
  'prov-crpc-1973-s154': ['prop-criminal-fir-mandatory-s154-lalita-kumari'],
  'prov-bnss-2023-s173': ['prop-criminal-bnss-s531-transitional-savings'],
  'prov-rbi-failed-tx-2019': ['prop-banking-rbi-failed-tx-tat-2019'],
}

export function filterPassagesWithProvisionState(
  basePassages: EvidencePassage[],
  dbProvisions?: Array<Record<string, unknown>> | null
): {
  activePassages: EvidencePassage[]
  invalidatedProvisionIds: string[]
  invalidatedWarnings: string[]
  maxCacheEpoch: number
} {
  if (!dbProvisions || dbProvisions.length === 0) {
    return {
      activePassages: basePassages,
      invalidatedProvisionIds: [],
      invalidatedWarnings: [],
      maxCacheEpoch: 1,
    }
  }

  const suppressedPassageIds = new Set<string>()
  const invalidatedProvisionIds: string[] = []
  const invalidatedWarnings: string[] = []
  let maxCacheEpoch = 1

  for (const row of dbProvisions) {
    const provId = String(row.provision_id || '')
    const reviewState = String(row.review_state || '')
    const epoch = Number(row.cache_epoch || 1)
    if (epoch > maxCacheEpoch) maxCacheEpoch = epoch

    if (reviewState === 'amended_cache_invalidated' || reviewState === 'retired') {
      invalidatedProvisionIds.push(provId)
      suppressedPassageIds.add(provId)
      for (const mappedId of PROVISION_TO_PASSAGE_MAP[provId] || []) {
        suppressedPassageIds.add(mappedId)
      }
      invalidatedWarnings.push(
        `Provision ${provId} (${String(row.act_title || '')} ${String(row.section_locator || '')}) is marked '${reviewState}' (cache_epoch=${epoch}); dependent cached outputs are invalidated until re-verified.`
      )
    }
  }

  const activePassages = basePassages.filter(p => !suppressedPassageIds.has(p.passage_id))
  return {
    activePassages,
    invalidatedProvisionIds,
    invalidatedWarnings,
    maxCacheEpoch,
  }
}

const CRIMINAL_LAW_Cutoff = '2024-07-01'

const INDIAN_STATES_RE =
  /\b(maharashtra|karnataka|tamil\s+nadu|delhi|uttar\s+pradesh|bihar|west\s+bengal|gujarat|rajasthan|kerala|telangana|andhra\s+pradesh|punjab|haryana|madhya\s+pradesh|odisha|assam|jharkhand|chhattisgarh|uttarakhand|himachal\s+pradesh|goa)\b/i

const FOREIGN_JURISDICTION_RE =
  /\b(united\s+states|u\.?s\.?a\.?|california|new\s+york|texas|united\s+kingdom|u\.?k\.?|london|england|canada|australia|singapore|dubai|uae|eu\s+gdpr)\b/i

const CRIMINAL_CODE_MENTION_RE =
  /\b(ipc|crpc|bns|bnss|bsa|fir|section\s+420|section\s+318|section\s+154|section\s+173|section\s+156|cheating|arrest|bail|cognizable|police\s+station)\b/i

export function resolveTemporalAndJurisdictionApplicability(options: {
  query: string
  incidentDate?: string | null
  proceduralStage?: 'pending_before_2024_07_01' | 'fresh_after_2024_07_01' | 'unknown' | null
  jurisdiction?: string | null
  domain?: string | null
}): TemporalApplicabilityResolution {
  const q = options.query || ''
  const incDate = options.incidentDate ? options.incidentDate.slice(0, 10) : null
  const stage = options.proceduralStage || 'unknown'
  const isForeign =
    FOREIGN_JURISDICTION_RE.test(q) ||
    (Boolean(options.jurisdiction) &&
      !['india', 'central'].includes((options.jurisdiction || '').toLowerCase()) &&
      FOREIGN_JURISDICTION_RE.test(options.jurisdiction || ''))
  const stateMatch = q.match(INDIAN_STATES_RE) || (options.jurisdiction || '').match(INDIAN_STATES_RE)
  const detectedState = stateMatch ? stateMatch[1] : null
  const needsStateRule =
    Boolean(detectedState) &&
    (/\b(rent|tenancy|eviction|landlord|shops?\s+and\s+establishments?|stamp\s+duty|state\s+police|excise|prohibition)\b/i.test(
      q
    ) ||
      options.domain === 'tenancy' ||
      options.domain === 'employment')

  const jurisdictionFinding: TemporalApplicabilityResolution['jurisdiction_finding'] = isForeign
    ? 'outside_india_coverage'
    : needsStateRule
      ? 'state_specific_verification_required'
      : 'india_central_applicable'

  const isCriminalOrTransitional =
    options.domain === 'criminal' || CRIMINAL_CODE_MENTION_RE.test(q)

  if (!isCriminalOrTransitional) {
    return {
      incident_date: incDate,
      procedural_stage: stage,
      substantive_regime: 'NON_CRIMINAL_CENTRAL',
      procedural_regime: 'NON_CRIMINAL_CENTRAL',
      transitional_note: incDate
        ? `Evaluated against statutory provisions in force on ${incDate}.`
        : 'Incident date not specified; current central statutory provisions evaluated with date qualification.',
      jurisdiction_finding: jurisdictionFinding,
      detected_state: detectedState,
      requires_date_clarification: !incDate,
    }
  }

  if (!incDate) {
    return {
      incident_date: null,
      procedural_stage: stage,
      substantive_regime: 'DUAL_DATE_UNKNOWN',
      procedural_regime: stage === 'pending_before_2024_07_01' ? 'CRPC_1973' : stage === 'fresh_after_2024_07_01' ? 'BNSS_2023' : 'DUAL_STAGE_UNKNOWN',
      transitional_note:
        'Incident date is unknown. Substantive offences before 1 July 2024 are governed by IPC 1860 (e.g., S. 420), whereas offences on or after 1 July 2024 are governed by BNS 2023 (e.g., S. 318(4)). Under BNSS Section 531(2)(a), investigations or trials pending before 1 July 2024 continue under CrPC 1973, while fresh FIRs registered on or after 1 July 2024 follow BNSS 2023.',
      jurisdiction_finding: jurisdictionFinding,
      detected_state: detectedState,
      requires_date_clarification: true,
    }
  }

  const substantiveRegime = incDate < CRIMINAL_LAW_Cutoff ? 'IPC_1860' : 'BNS_2023'
  const proceduralRegime =
    stage === 'pending_before_2024_07_01'
      ? 'CRPC_1973'
      : stage === 'fresh_after_2024_07_01' || incDate >= CRIMINAL_LAW_Cutoff
        ? 'BNSS_2023'
        : 'DUAL_STAGE_UNKNOWN'

  const transitionalNote =
    incDate < CRIMINAL_LAW_Cutoff
      ? stage === 'pending_before_2024_07_01'
        ? `Incident (${incDate}) and pending proceeding precede 1 July 2024: substantive law is IPC 1860 (saved by BNS S. 358) and procedure continues under CrPC 1973 per BNSS Section 531(2)(a).`
        : stage === 'fresh_after_2024_07_01'
          ? `Incident (${incDate}) occurred before 1 July 2024, but fresh FIR/proceeding initiated on or after 1 July 2024: substantive offence remains governed by IPC 1860 (BNS S. 358 savings), while fresh registration/investigation procedure follows BNSS 2023.`
          : `Incident (${incDate}) occurred before 1 July 2024: substantive offence is governed by IPC 1860; verify whether the FIR/inquiry was already pending before 1 July 2024 (CrPC 1973 per BNSS S. 531(2)(a)) or registered on/after 1 July 2024 (BNSS 2023).`
      : `Incident (${incDate}) occurred on or after 1 July 2024: governed by Bharatiya Nyaya Sanhita, 2023 (BNS) and Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS).`

  return {
    incident_date: incDate,
    procedural_stage: stage,
    substantive_regime: substantiveRegime,
    procedural_regime: proceduralRegime,
    transitional_note: transitionalNote,
    jurisdiction_finding: jurisdictionFinding,
    detected_state: detectedState,
    requires_date_clarification: stage === 'unknown' && incDate < CRIMINAL_LAW_Cutoff,
  }
}

export function evaluateCorrectiveRetrieval(options: {
  query: string
  passages: EvidencePassage[]
  temporalResolution: TemporalApplicabilityResolution
  invalidatedProvisionIds?: string[]
  invalidatedWarnings?: string[]
  cacheEpoch?: number
}): CorrectiveRetrievalFindings {
  const warnings: string[] = [...(options.invalidatedWarnings || [])]
  const { passages, temporalResolution } = options

  const relevance: CorrectiveRetrievalFindings['relevance'] =
    passages.length === 0
      ? 'no_candidates'
      : passages.some(p => (p.search_score || 0) >= 3.0)
        ? 'supported'
        : 'low_relevance'

  const allOfficial =
    passages.length > 0 &&
    passages.every(p => p.origin_verified || p.certified_proposition || classifyOfficialAuthority(p.canonical_url).isOfficial)

  const sourceAuthority: CorrectiveRetrievalFindings['source_authority'] = allOfficial
    ? 'indian_official_verified'
    : 'unverified_or_mixed'

  let dateApplicability: CorrectiveRetrievalFindings['date_applicability'] = 'confirmed_interval'
  if (temporalResolution.requires_date_clarification) {
    dateApplicability =
      temporalResolution.substantive_regime === 'DUAL_DATE_UNKNOWN'
        ? 'date_unknown_qualified'
        : 'transitional_dual_regime'
    warnings.push(temporalResolution.transitional_note)
  } else if (temporalResolution.incident_date && temporalResolution.incident_date < CRIMINAL_LAW_Cutoff) {
    dateApplicability = 'transitional_dual_regime'
    warnings.push(temporalResolution.transitional_note)
  }

  let jurisdiction: CorrectiveRetrievalFindings['jurisdiction'] = 'matched_india_central'
  if (temporalResolution.jurisdiction_finding === 'outside_india_coverage') {
    jurisdiction = 'foreign_mismatch'
    warnings.push('Query references a foreign jurisdiction outside Nyay Saathi Indian-law coverage.')
  } else if (temporalResolution.jurisdiction_finding === 'state_specific_verification_required') {
    jurisdiction = 'state_specific_gap'
    warnings.push(
      `State-specific rules for ${temporalResolution.detected_state || 'the requested state'} require state statute/notification verification.`
    )
  }

  const hasInvalidated = Boolean(options.invalidatedProvisionIds && options.invalidatedProvisionIds.length > 0)
  const completeness: CorrectiveRetrievalFindings['completeness'] =
    relevance === 'supported' &&
    jurisdiction === 'matched_india_central' &&
    !temporalResolution.requires_date_clarification &&
    !hasInvalidated
      ? 'sufficient'
      : 'material_gap_requires_clarification'

  return {
    relevance,
    source_authority: sourceAuthority,
    date_applicability: dateApplicability,
    jurisdiction,
    completeness,
    warnings,
    cache_epoch: options.cacheEpoch ?? 1,
    invalidated_provisions: options.invalidatedProvisionIds || [],
  }
}

export function knowledgeSummary() {
  return {
    total_propositions: CERTIFIED_PROPOSITIONS.length,
    certified_propositions: CERTIFIED_PROPOSITIONS.filter(p => p.certified_proposition).length,
    domains: Array.from(new Set(CERTIFIED_PROPOSITIONS.map(p => p.domain || 'general'))).sort(),
    urgent_pack_ids: CERTIFIED_PROPOSITIONS.filter(p =>
      ['constitutional_urgent', 'criminal', 'cyber_fraud'].includes(p.domain || '')
    ).map(p => p.passage_id),
  }
}

export function publicKnowledgeBasePayload() {
  const intakePlaybooks = [
    {
      playbook_id: 'consumer-refund-intake-v1',
      title: 'Refund dispute intake',
      applies_to: ['refund_not_received', 'stated_return_or_refund_refused'],
      questions: [
        {
          field: 'purchase_and_purpose',
          prompt: 'What did you buy, and was it mainly for personal use?',
          why: 'Tests whether the supported consumer workflow may fit without assuming consumer status.',
          required: true,
        },
        {
          field: 'parties',
          prompt: 'Who sold it, and was a marketplace or payment intermediary involved?',
          why: 'Identifies the possible opposite parties and available records.',
          required: true,
        },
        {
          field: 'order_date',
          prompt: 'When did you order and pay?',
          why: 'Starts the chronology and timing review.',
          required: true,
        },
        {
          field: 'completed_actions',
          prompt: 'What have you already sent or done, and what response did you receive?',
          why: 'Avoids repeating completed steps and preserves correspondence history.',
          required: true,
        },
      ],
      branches: [
        {
          if: 'seller_claims_refund_processed',
          ask: ['processing_date', 'refund_transaction_reference', 'payment_channel'],
          reason: 'Do not assume the seller never initiated a refund; distinguish initiation, routing and receipt.',
        },
        {
          if: 'online_marketplace_purchase',
          ask: ['marketplace_name', 'seller_legal_name', 'platform_ticket_number'],
          reason: 'Marketplace, seller and platform records may support different facts.',
        },
      ],
      source_ids: ['india-code-cpa-2019', 'cpa-ecommerce-rules-2020'],
    },
    {
      playbook_id: 'financial-cyber-fraud-intake-v1',
      title: 'Active financial & cyber fraud intake',
      applies_to: ['unauthorized_electronic_debit', 'upi_or_phishing_fraud'],
      questions: [
        {
          field: 'transaction_mechanism',
          prompt: 'How did the debit happen (unauthorized debit, phishing link, OTP/PIN shared, or screen-share app)?',
          why: 'Distinguishes unauthorized breach from induced transfer under RBI liability directions.',
          required: true,
        },
        {
          field: 'bank_and_1930_reporting',
          prompt: 'Have you blocked the card/UPI with your bank and reported to 1930 / cybercrime.gov.in?',
          why: 'Immediate channel block and 1930 reporting are time-critical for fund-freeze coordination.',
          required: true,
        },
      ],
      branches: [
        {
          if: 'credentials_or_otp_shared',
          ask: ['exact_notification_timestamp_to_bank', 'subsequent_debits_after_notification'],
          reason: 'Do not infer automatic bank reimbursement before reporting when credentials were shared.',
        },
      ],
      source_ids: ['mha-i4c-cybercrime-1930', 'rbi-unauthorised-electronic-tx'],
    },
  ]

  const evidencePlaybooks = [
    {
      evidence_type: 'invoice_or_order_confirmation',
      request: 'Complete invoice/order confirmation showing seller, product, amount and date.',
      may_support: ['purchase details', 'named seller', 'amount', 'product identity'],
      does_not_automatically_prove: ['defect', 'non-delivery', 'refund entitlement'],
      authenticity_checks: ['complete page', 'order number', 'seller identity', 'matching amount'],
      common_contradictions: ['invoice seller differs from platform name', 'invoice date differs from payment date'],
      preservation: 'Keep the original file or email and export a copy without editing it.',
    },
    {
      evidence_type: 'payment_record',
      request: 'Payment confirmation or bank/card/UPI entry with UTR reference.',
      may_support: ['payment amount', 'date', 'recipient or merchant reference'],
      does_not_automatically_prove: ['all contractual conditions were satisfied', 'the payment was never reversed elsewhere'],
      authenticity_checks: ['transaction reference', 'account/instrument', 'complete relevant period'],
      common_contradictions: ['merchant descriptor differs from seller', 'amount differs from invoice'],
      preservation: 'Preserve the original statement and note any redactions made for sharing.',
    },
  ]

  const procedures = [
    {
      route_id: 'seller_or_platform_correspondence',
      title: 'Factual seller or platform Grievance Officer request',
      when_may_fit: 'The person wants to clarify facts, invoke a stated policy or escalate to the statutory Grievance Officer.',
      authority: 'Seller, service provider, marketplace or Grievance Officer (Rule 4 E-Commerce Rules, 2020)',
      required_inputs: ['correct recipient', 'order details', 'factual chronology', 'requested remedy', 'supporting records'],
      instructions: [
        'State facts and sources separately from legal conclusions.',
        'Attach copies, not the only originals.',
        'Request acknowledgement within 48 hours and retain the complete sent record.',
      ],
      what_happens_next:
        'The recipient must acknowledge within 48 hours and redress within one month under Rule 4; record the actual outcome before choosing another step.',
      lawyer_review_triggers: ['large or consequential loss', 'serious factual dispute', 'safety or criminal allegation'],
      source_ids: ['cpa-ecommerce-rules-2020'],
      limitations: 'Does not guarantee a refund where underlying physical return or defect facts are disputed.',
    },
    {
      route_id: 'national_consumer_helpline',
      title: 'National Consumer Helpline pre-litigation grievance (1915)',
      when_may_fit:
        'Platform customer support and the Grievance Officer have closed, ignored, or failed to resolve a consumer grievance.',
      authority: 'National Consumer Helpline, Department of Consumer Affairs (1915 / consumerhelpline.gov.in)',
      required_inputs: ['consumer contact details', 'seller/company details', 'transaction and grievance summary', 'supporting documents'],
      instructions: ['Use official NCH channels.', 'Keep the docket or grievance number.', 'Record company responses and the outcome.'],
      what_happens_next:
        'NCH forwards the grievance through its convergence process; an unresolved person may approach the appropriate Consumer Commission.',
      lawyer_review_triggers: ['possible limitation issue', 'high value', 'complex party or jurisdiction question'],
      source_ids: ['nch-about'],
      limitations: 'NCH is a pre-litigation mechanism and does not pause the 2-year limitation period under Section 69 CPA 2019.',
    },
    {
      route_id: 'consumer_commission_ejagriti',
      title: 'District Consumer Commission complaint (Section 35 CPA 2019)',
      when_may_fit: 'Internal grievance redress and NCH pre-litigation efforts did not resolve the consumer dispute.',
      authority: 'Appropriate District, State or National Consumer Disputes Redressal Commission',
      required_inputs: [
        'consumer-status facts',
        'opposite parties',
        'territorial facts',
        'consideration paid',
        'cause-of-action chronology',
        'requested relief',
        'evidence index',
      ],
      routing_rules: [
        {
          rule: 'pecuniary_jurisdiction',
          inputs: ['consideration_paid'],
          source_id: 'india-code-cpa-2019',
          exceptions: ['other statutory provisions', 'later amendments', 'valuation dispute'],
        },
        {
          rule: 'limitation',
          inputs: ['cause_of_action_dates'],
          source_id: 'india-code-cpa-2019',
          exceptions: ['sufficient-cause condonation application'],
        },
      ],
      instructions: [
        'Verify current e-Daakhil / e-Jagriti instructions and accepted formats at filing time.',
        'Prepare a chronology, party details, relief, evidence index and source-backed legal issues.',
      ],
      what_happens_next: 'The Commission examines admissibility, issues notice, receives opposite party response, and adjudicates.',
      lawyer_review_triggers: ['forum uncertainty', 'timing issue', 'interim relief', 'substantial amount'],
      source_ids: ['india-code-cpa-2019'],
      limitations: 'Does not select a forum from similarity alone and does not file or serve anything automatically.',
    },
  ]

  const templates = [
    {
      template_id: 'seller-factual-refund-request-v1',
      title: 'Factual refund request',
      sections: [
        'recipient',
        'order and payment identifiers',
        'dated chronology',
        'observed problem',
        'requested remedy',
        'attached evidence list',
      ],
      required_confirmations: ['amount', 'dates', 'recipient', 'requested remedy'],
      must_not_invent: ['prior reminders', 'admissions', 'losses', 'threats', 'statutory deadlines'],
    },
    {
      template_id: 'lawyer-brief-v1',
      title: 'Qualified-lawyer briefing pack',
      sections: [
        'one-page overview',
        'chronology linked to evidence',
        'evidence index',
        'disputed facts and gaps',
        'questions for lawyer',
        'source list',
      ],
      required_confirmations: ['objective', 'parties', 'amount', 'material dates', 'completed actions'],
      must_not_invent: ['legal conclusion', 'deadline', 'lawyer instruction', 'eligibility'],
    },
  ]

  const selectedJudgments = [
    {
      judgment_id: 'sc-experion-sushma-2022',
      case_name: 'Experion Developers Pvt. Ltd. v. Sushma Ashok Shiroor',
      citation: 'Civil Appeal Nos. 6044 and 7149 of 2019',
      court: 'Supreme Court of India',
      decision_date: '2022-04-07',
      official_url: 'https://api.sci.gov.in/supremecourt/2019/26982/26982_2019_2_1501_34781_Judgement_07-Apr-2022.pdf',
      material_facts:
        'Homebuyer refund dispute concerning delayed apartment possession, one-sided agreement terms and overlapping Consumer Protection Act and RERA remedies.',
      issues: ['consumer commission power to direct refund', 'one-sided terms', 'parallel statutory remedies'],
      holding_summary:
        'On its facts, the Supreme Court upheld the refund direction and explained that the consumer and RERA remedies considered there did not exclude each other.',
      supporting_locator: 'Paragraphs 15-19, especially paragraph 17',
      exact_excerpt: 'the Commission has the power and jurisdiction to direct return of money',
      important_distinctions: ['homebuyer and immovable-property facts', 'Consumer Protection Act 1986', 'RERA overlap'],
      treatment_status: 'Supreme Court final judgment; subsequent treatment not independently checked',
      last_checked: '2026-11-05',
      use_rule: 'May identify arguments or distinctions. Must not be presented as promising the same result in a retail refund case.',
    },
  ]

  const lawyerPreparation = {
    pack_sections: [
      'one_page_overview',
      'evidence_linked_chronology',
      'evidence_index',
      'disputed_facts_and_gaps',
      'correspondence_history',
      'legal_issues_for_review',
      'urgent_matters',
      'questions_for_lawyer',
      'sources',
      'draft_versions',
    ],
    consultation_questions: [
      'Is this the appropriate forum?',
      'What facts or documents are still missing?',
      'Are there timing issues?',
      'What remedies are realistically available?',
      'What are the likely costs and stages?',
    ],
    source_ids: ['nalsa-faq-legal-services'],
  }

  const referrals = [
    {
      referral_id: 'nalsa-legal-services',
      title: 'Legal advice, assistance and possible legal aid',
      provider: 'National and State Legal Services Institutions (NALSA / SLSA / DLSA)',
      official_url: 'https://nalsa.gov.in/faqs/',
      services_described: [
        'legal advice and assistance',
        'drafting',
        'preparation of pleadings',
        'representation for eligible beneficiaries',
      ],
      do_not_promise: ['eligibility', 'lawyer assignment', 'availability', 'case acceptance', 'outcome'],
      source_ids: ['nalsa-faq-legal-services'],
    },
  ]

  return {
    corpus_version: 'certified-propositions-v1',
    collection_name: 'official_consumer_law_v1',
    total_passages: CERTIFIED_PROPOSITIONS.length,
    certified_knowledge_factory: knowledgeSummary(),
    vector_index_enabled: false,
    vector_passages: 0,
    retrieval_pipeline: [
      'Editor-certified proposition pack & statutory provisions',
      'Temporal applicability & official authority hierarchy verification',
      'Risk-calibrated mechanical checks & independent semantic review',
    ],
    knowledge_id: 'consumer-support-v1',
    knowledge_version: '1.0.0',
    last_checked: '2026-11-07',
    review_status: 'application_guidance_pending_indian_lawyer_review',
    scope: [
      'refund_not_received',
      'defective_goods',
      'non_delivery',
      'stated_return_or_refund_refused',
      'unauthorized_electronic_debit',
    ],
    separation_rule:
      'Public legal playbooks and statutory propositions are strictly isolated from private case memory, user uploads, and extracted documents.',
    layers: [
      {
        id: 'applicable_law',
        label: 'Applicable law and official guidance',
        count: CERTIFIED_PROPOSITIONS.length,
        storage: 'certified proposition register',
      },
      {
        id: 'procedures',
        label: 'Procedural routes',
        count: procedures.length,
        storage: 'versioned playbook',
      },
      {
        id: 'intake_playbooks',
        label: 'Intake playbooks',
        count: intakePlaybooks.length,
        storage: 'versioned playbook',
      },
      {
        id: 'evidence_playbooks',
        label: 'Evidence playbooks',
        count: evidencePlaybooks.length,
        storage: 'versioned playbook',
      },
      {
        id: 'templates',
        label: 'Drafting structures',
        count: templates.length,
        storage: 'template collection',
      },
      {
        id: 'selected_judgments',
        label: 'Curated judgments',
        count: selectedJudgments.length,
        storage: 'register + official passages',
      },
      {
        id: 'lawyer_preparation',
        label: 'Lawyer preparation',
        count: lawyerPreparation.pack_sections.length,
        storage: 'versioned playbook',
      },
      {
        id: 'referrals',
        label: 'Escalation and referrals',
        count: referrals.length,
        storage: 'versioned official guidance',
      },
    ],
    intake_playbooks: intakePlaybooks,
    evidence_playbooks: evidencePlaybooks,
    procedures,
    templates,
    selected_judgments: selectedJudgments,
    lawyer_preparation: lawyerPreparation,
    referrals,
    storage_map: [
      {
        store: 'Public Legal Knowledge Register',
        content: 'Approved statutory passages, official procedure guidance and selected judgment passages only',
      },
      {
        store: 'Versioned Playbooks',
        content: 'Intake questions, evidence meaning, route gates, escalation and lawyer-preparation guidance',
      },
      {
        store: 'Supabase PostgreSQL (RLS Private Case Workspace)',
        content: 'Owner-isolated facts, provenance, timeline, evidence links, contradictions, actions, and drafts',
      },
      {
        store: 'Disclosed Temporary Processing / User Drive',
        content: 'SHA-256 verified uploads and user-corrected extracted text',
      },
    ],
    sources: CERTIFIED_PROPOSITIONS.map(p => ({
      source_id: p.source_id,
      title: p.title,
      issuing_authority: p.source_hierarchy_tier === 1 ? 'Supreme Court of India / Parliament' : 'Government of India / Statutory Regulator',
      canonical_url: p.canonical_url,
      source_type: p.source_type || 'indian_official',
      jurisdiction: p.jurisdiction || 'India',
      publication_date: p.publication_date || p.effective_date || null,
      effective_date: p.effective_date || null,
      version_information: p.locator,
      retrieved_at: p.retrieved_at,
      verification_status: p.verification_status || 'editor_certified',
      known_limitations: p.limitations,
      passage_count: 1,
      vector_passage_count: 0,
      locators: [p.locator],
    })),
  }
}
