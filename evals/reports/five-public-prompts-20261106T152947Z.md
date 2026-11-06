# Five public-account prompts: actual live responses

Sequential run. Five-call cap per prompt; no automatic reruns. Temporary private chats were removed. Model review is not legal validation.

## Run summary and limitations

- Actual live HTTP turns, sequential, no provider-output mocks; five independent temporary chats.
- One response passed automated review; four were withheld. No lawyer review was performed.
- 23 reported generation/search calls, within the authorized 25-call run cap, plus 3 embedding lookups (349 embedding tokens). No bulk vector rebuild.
- Reported generation/search token usage: 144,845 input; 23,339 output; 168,184 total. These figures are provider-reported where available, not a monetary billing statement.
- Four reported web tool calls. About 360.2 seconds in total across the five turns, excluding setup.
- Existing `.env` and ordinary chats were unchanged. Test databases/checkpoints/uploads were temporary and removed; safe public-account prompts and observable outputs remain in the raw JSONL.
- The five-call per-turn cap left no two-call revision reserve in some cases. Those failures were retained without automatic reruns.

Observed blockers: exact citation-label mismatches; answered/deferred metadata disagreeing with honest research limitations; useful factual drafting being withheld together with failed research tasks; missing case intake in several fact-rich prompts (persisted case version remained zero for Blinkit, Goibibo and Chennai); and unnecessary consumer-corpus retrieval risk outside the supported consumer workflow. These results establish current limitations, not successful end-to-end legal performance. No unverified generated candidate was substituted for the displayed response.

## 1. amazon-delivery

Status: failed_or_limited; HTTP 200; 73.731 seconds; 5 reported model calls.

Prompt:

I bought an induction cooktop from Amazon for ₹1,399. It was marked delivered, but I never received it. Support arranged a replacement, which was delayed and then marked undeliverable. They promised a refund but later refused it, citing previous missing-item claims. What evidence should I collect? Prepare a factual complaint summary and suggest the next practical step.

Actual response:

I saved your account, but I couldn’t verify the legal guidance for this turn, so I’ve withheld that part. You can still prepare the factual record: keep the order confirmation, invoice, payment record, and your correspondence together. Record what you ordered, what happened, and the resolution you want. These documents may support different parts of your account; none automatically proves the whole dispute.

## 2. blinkit-milk

Status: failed_or_limited; HTTP 200; 51.184 seconds; 4 reported model calls.

Prompt:

Milk delivered through Blinkit curdled when heated. This has happened three times. Support says replacements are unavailable and offers refunds, but ordering again costs another ₹72 in delivery and handling charges. Is the milk suitable to consume? Draft a short message asking them to address the repeated problem and additional charges.

Actual response:

I couldn’t verify a reliable answer within this turn’s limits. Your message is saved, and your existing case is unchanged. You can narrow the question or try again later.

## 3. goibibo-checkin

Status: failed_or_limited; HTTP 200; 60.418 seconds; 4 reported model calls.

Prompt:

We are both 18 and booked a hotel through Goibibo. The listing said guests aged 18 were allowed, but the hotel refused check-in, saying we needed to be 19. They told us to cancel and promised a refund, then rejected the cancellation. Later they claimed the minimum age was 21. Who should I approach, and what should my complaint say?

Actual response:

I couldn’t verify a reliable answer within this turn’s limits. Your message is saved, and your existing case is unchanged. You can narrow the question or try again later.

## 4. chennai-wages

Status: passed_automated_review; HTTP 200; 81.505 seconds; 5 reported model calls.

Prompt:

My mother worked at a restaurant in Chennai for several years. Her March salary and part of April’s wages remain unpaid. We repeatedly approached the police, but the employer kept promising payment without paying. We then contacted the CM Cell and were told the matter was forwarded to the Labour Department. What records should we prepare? Write a factual brief for a lawyer without making us restart the complaint.

Actual response:

The police approaches and CM Cell referral are important history to preserve, so the lawyer’s brief should build on them rather than treat this as a new complaint.

### Records to prepare
- **Employment details:** your mother’s name, restaurant’s name and Chennai address, employer/manager details, approximate employment dates, duties, and any appointment letter, staff ID, job messages or other proof of work.
- **Wages outstanding:** the year for March and April, agreed salary or wage rate, days worked, payments received, and balance claimed. Gather any payslips, attendance records, bank statements or cash-payment records. A simple table separating March and April will help.
- **Payment promises:** any messages, emails or other records of promises to pay. For conversations without a written record, make a dated note of what is remembered, who spoke and any witnesses; distinguish recollection from documentary evidence.
- **Police history:** copies of complaints and acknowledgments, station names, reference numbers, dates of visits and any responses, if available.
- **CM Cell and Labour Department trail:** the CM Cell complaint, reference number, acknowledgment, and any message saying it was forwarded. Record who told you about the referral and when. Include any subsequent Labour Department communication, if received.

Keep originals unchanged and arrange copies chronologically. Missing records should be identified as gaps, not reconstructed as if they were original documents.

Employment-law research was restricted for this request, so I cannot verify the applicable Tamil Nadu procedure or legal time limits here. The checklist and brief below are factual preparation, not a conclusion about where you are eligible to file. Give the brief to the lawyer reviewing the existing matter. If no lawyer is yet involved, the existing Labour Department contact, if identified in your referral records, is an alternative place to request a status update—not to assume a fresh complaint is needed.

### Factual brief for a lawyer

**Subject: Unpaid wages — request to review existing police approaches and CM Cell referral**

My mother, [ADD NAME], worked at [ADD RESTAURANT NAME AND ADDRESS], Chennai, for several years. Her salary for March [ADD YEAR] and part of her wages for April [ADD YEAR] remain unpaid. Her agreed salary/wage rate was [ADD RATE OR MARK UNKNOWN]. The outstanding amount is [ADD AMOUNT OR MARK NOT YET CALCULATED].

We repeatedly approached the police about the unpaid wages. The employer repeatedly promised payment but has not paid the outstanding wages. The police stations approached, dates or approximate periods, and any complaint references are [ADD DETAILS OR MARK UNKNOWN]. These statements are based on our account; supporting records remain to be assembled.

We subsequently contacted the CM Cell and were told that the matter had been forwarded to the Labour Department. The CM Cell reference and date are [ADD DETAILS OR MARK UNKNOWN]. The source of the forwarding information and any subsequent communication are [ADD DETAILS OR MARK UNKNOWN]. We seek verification of the referral’s current status.

Please review the existing complaint history, identify any missing records, and advise on the appropriate next step without unnecessarily duplicating or restarting the complaint. The outcome my mother wants is [ADD DESIRED RESOLUTION].

We will provide whichever of the listed records are available and identify any gaps.

**Before sending:** add the names, restaurant details, wage years, amount or calculation, desired resolution, and available complaint/referral details. Mark anything genuinely unknown rather than guessing.

What resolution does your mother want the lawyer to pursue—payment of the outstanding wages only, or something else as well?

## 5. refund-fraud

Status: failed_or_limited; HTTP 200; 93.381 seconds; 5 reported model calls.

Prompt:

A damaged curd packet arrived in my Blinkit order. I searched online for customer care and called a number I found. Someone sent me a WhatsApp link to upload a photo, then asked me to check Google Pay. Afterwards, ₹98,000 was debited from my bank account. What should I prioritise now, and what evidence should I preserve?

Actual response:

I saved your account, but I couldn’t verify the legal guidance for this turn, so I’ve withheld that part. You can still prepare the factual record: keep the order confirmation, invoice, payment record, and your correspondence together. Record what you ordered, what happened, and the resolution you want. These documents may support different parts of your account; none automatically proves the whole dispute.
