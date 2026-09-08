# Agent-Driven Income Ideas, Part 2: Businesses That Are Not About Code

Companion to [IDEAS.md](IDEAS.md). Part 1 sold code to people who buy code. This
part keeps the same engine (headless Claude pipelines, strict verification
gates, one human doing QA and sales) but points it at markets where the
customer never sees a repository: local businesses, publishers, sellers,
students, landlords, job seekers, and companies drowning in paperwork.

Same honest framing as part 1: after 6 months most solo attempts earn
0-500 EUR/month. Ranges assume 10-15 h/week, real distribution work, and
some luck. Anything above 2-3k EUR/month at month 6 is an outlier, not a plan.

Two things are different when the customer is not a developer:
- **The buyer cannot evaluate the pipeline, only the outcome.** Verification
  gates matter more, not less: one hallucinated phone number on a printed
  flyer ends the relationship.
- **Platforms now police AI output.** Amazon KDP, Etsy, and YouTube all
  require disclosure or originality since 2024-2026 and enforce it (see
  "Platform realities" at the end). Every idea below that touches a
  platform is designed to survive those rules, not to dodge them.

---

## Category 1: Services for French local businesses (fastest to first euro)

### 1. AI phone receptionist for artisans and clinics
- **What**: An always-on French-speaking voice agent that answers the calls a
  plumber, electrician, or physio misses while working, qualifies the request,
  books a slot in their calendar, and sends them a text summary. Sold as a
  monthly subscription (79-149 EUR) on top of a one-time setup (300-500 EUR).
  Built on an existing voice platform (Retell, Vapi, ElevenLabs agents),
  configured and monitored by your pipeline; you never write the telephony.
- **First step this week**: Configure one agent for a fictional plumber, call
  it yourself 20 times with messy real-life requests, then offer it free for
  a month to one artisan you personally know in exchange for a testimonial.
- **Startup cost**: 100-250 EUR (platform minutes, a French number, domain).
- **Realistic monthly revenue**: 300-2,500 EUR (5-20 subscribers at month 6;
  churn is low because the missed-call pain is constant).
- **Automation level**: 85% (the agent works alone; you review transcripts
  weekly and tune prompts).
- **Main risk**: Platform per-minute costs plus telephony eat margins on
  high-volume clients; price by call volume, not flat, above 300 calls/month.

### 2. Reviews and Google Business Profile management
- **What**: A retainer (49-99 EUR/month per location) where agents draft
  replies to every Google, Pages Jaunes, and TripAdvisor review in the
  owner's tone, post weekly profile updates with photos they send by
  WhatsApp, and flag fake or defamatory reviews for removal requests.
  Restaurants, garages, salons, dentists.
- **First step this week**: Pick 10 local businesses with unanswered reviews,
  draft the replies they should have posted, and send each owner the draft
  with a one-line offer.
- **Startup cost**: under 100 EUR.
- **Realistic monthly revenue**: 500-3,000 EUR (10-30 locations; multi-site
  owners pay for all sites at once).
- **Automation level**: 90% (drafting and posting are agent work; owner
  approves via a daily WhatsApp digest).
- **Main risk**: Google's own AI reply suggestions are free; the moat is the
  multi-platform watch and the human-sounding tone, which is thin.

### 3. Quote follow-up and unpaid-invoice chasing for TPEs
- **What**: The average French artisan loses sales because quotes are never
  followed up, and cash because invoices are chased late. An agent reads
  their quote/invoice exports (or their Pennylane/Tiime/Indy account), sends
  polite staged reminders by email and SMS in their name, and escalates to a
  formal "mise en demeure" template at the right legal delay. Priced per
  business (39-79 EUR/month) or as a percentage of recovered late payments.
- **First step this week**: Write the 4-step reminder sequence (J+3 quote
  nudge, J+15 invoice reminder, J+30 firm reminder, J+45 formal notice) and
  test it with one freelancer friend on their real backlog.
- **Startup cost**: under 100 EUR (SMS credits, email sending domain).
- **Realistic monthly revenue**: 400-2,000 EUR.
- **Automation level**: 90%.
- **Main risk**: Debt collection above a certain threshold is a regulated
  activity in France; stay on the "reminders in the client's name" side and
  never collect funds yourself.

### 4. Public tender watch and first-draft responses for SMEs
- **What**: Small firms miss public contracts (BOAMP, marches-publics.gouv,
  regional portals) because monitoring and writing the "memoire technique"
  takes days. Agents watch the sources, score each tender against the
  client's profile, and produce a first draft of the technical response
  from the client's past bids. Subscription 149-299 EUR/month plus 500-1,500
  EUR per full response drafted.
- **First step this week**: Take one real published tender in a trade you
  understand, produce a draft response with your pipeline, and show it to
  one SME owner who bids on public work.
- **Startup cost**: 50-150 EUR.
- **Realistic monthly revenue**: 500-4,000 EUR (bid writing is genuinely
  valuable and priced accordingly).
- **Automation level**: 75% (watching and drafting are automated; the client
  must supply facts and sign).
- **Main risk**: A lost bid gets blamed on the draft; sell the watch and the
  time saved, never the win rate.

### 5. Grant and subsidy application service (France Num, BPI, regions, CPF)
- **What**: French SMEs leave money on the table because subsidy programs are
  fragmented and the forms are long. Agents maintain a database of active
  programs, match a company profile against them, and draft the applications.
  Fixed fee per file (400-900 EUR) or success fee (8-12% of grant obtained,
  where the program allows it).
- **First step this week**: Build the program database for one region and one
  sector (e.g. digitalisation aids for retail in your region) and run three
  real companies through the matcher by hand.
- **Startup cost**: under 100 EUR.
- **Realistic monthly revenue**: 500-3,000 EUR, lumpy.
- **Automation level**: 70% (matching and drafting are agent work; the
  supporting-documents chase is human).
- **Main risk**: Programs change quarterly; a stale database produces
  applications to closed programs, which is worse than nothing.

---

## Category 2: Publishing and media (own the asset, respect the rules)

### 6. Niche B2B newsletter with an agent research desk
- **What**: A weekly French-language newsletter in a niche where paying
  sponsors exist but coverage is thin (EU AI Act compliance for SMEs, edtech
  procurement, public-sector digital tenders, energy renovation aid). Agents
  do the daily source sweep, summaries, and fact tables; you write the
  opinion paragraph and pick the stories. Revenue from sponsorships (150-600
  EUR per slot at 2-5k subscribers) and a paid tier (5-9 EUR/month).
- **First step this week**: Pick the niche, set up the source sweep, and
  publish issue 1 to 50 people you know; do not buy a domain before issue 4.
- **Startup cost**: 50-150 EUR (sending platform, domain).
- **Realistic monthly revenue**: 0-1,500 EUR at month 6 (audience building
  is the whole job; sponsors appear around 2k engaged subscribers).
- **Automation level**: 80% for research, 0% for voice; the voice is the
  product.
- **Main risk**: Pure AI summaries are what everyone can generate for free
  now; without a point of view and insider sourcing, open rates die.

### 7. Original-curation video channel (not a template farm)
- **What**: A YouTube channel on a topic where you have real knowledge (how
  games are built, French edtech, tools for artisans), where agents do
  research, scripting drafts, chaptering, thumbnail A/B tests, and
  multilingual subtitles, and you provide the on-camera or voiced opinion.
  Revenue from ads, sponsors, and affiliate links.
- **First step this week**: Script and publish one 8-minute video with a
  clear thesis and your own voice, then measure retention before deciding
  anything.
- **Startup cost**: 100-300 EUR (mic, light).
- **Realistic monthly revenue**: 0-800 EUR at month 6; sponsors matter more
  than ad revenue below 50k monthly views.
- **Automation level**: 60%.
- **Main risk**: YouTube's July 2026 "inauthentic content" rule demonetizes
  templated, mass-produced, voice-over-on-stock channels and has already
  terminated large ones. Only original curation survives; volume is a
  liability, not a strategy.

### 8. Podcast localization: French versions of English shows
- **What**: Offer independent English-language podcasters a French edition:
  translated and adapted script, cloned-voice dubbing with their consent,
  show notes, and distribution setup. Paid per episode (60-150 EUR) or as a
  revenue share on the French feed's ads.
- **First step this week**: Dub one Creative Commons episode end to end,
  have two native speakers rate it, and pitch 10 mid-size shows (10k-100k
  downloads) with the sample.
- **Startup cost**: 50-150 EUR (TTS and dubbing credits).
- **Realistic monthly revenue**: 200-1,500 EUR.
- **Automation level**: 85%.
- **Main risk**: Voice-cloning consent and platform labeling rules; get
  written consent per host and label the feed as an AI-dubbed edition.

### 9. Non-fiction workbooks and study guides on KDP, disclosed and niche
- **What**: Short, genuinely useful French-language workbooks (exam revision
  guides for BTS and CAP trades, procedure checklists for new artisans,
  local-history walking guides) generated with agents, verified against
  primary sources, disclosed as AI-generated per KDP rules, and printed on
  demand. 6-15 EUR per copy, 2-5 EUR margin.
- **First step this week**: Publish one 60-page workbook in a niche you can
  verify yourself, disclosed correctly, and watch 30 days of sales before
  producing another.
- **Startup cost**: 0-50 EUR (cover design; the ISBN is free via KDP).
- **Realistic monthly revenue**: 50-600 EUR from a catalog of 10-20 titles;
  most titles sell nothing, a few carry the catalog.
- **Automation level**: 85%.
- **Main risk**: KDP requires the AI-generated disclosure, limits uploads to
  3 titles per day, reviews image-heavy AI books in 3-7 days, and suspends
  accounts for undisclosed AI content; low-effort volume gets the whole
  account banned, not just the title.

### 10. Digital planners and templates on Etsy, disclosed
- **What**: Sell printable and Notion/Goodnotes planners for a specific
  audience (French self-employed under the micro-entreprise regime: URSSAF
  calendar, TVA thresholds, expense trackers) at 4-12 EUR. Agents generate
  variants and listing copy; you design the base template once.
- **First step this week**: Design one planner, list it with the required AI
  disclosure in title/description and the 2026 image tag, and run 5 EUR/day
  of Etsy ads for a week to read demand.
- **Startup cost**: 50-100 EUR (listing fees, ads).
- **Realistic monthly revenue**: 50-500 EUR.
- **Automation level**: 80%.
- **Main risk**: Etsy's Creativity Standards require disclosing AI
  involvement and tagging AI images; undisclosed listings get removed, and
  the category is saturated with identical planners.

---

## Category 3: Commerce and property (agents as back office)

### 11. Marketplace listing optimization for existing sellers
- **What**: Amazon, Cdiscount, and Etsy sellers with 50-500 SKUs have weak
  titles, thin bullet points, and untranslated listings. Agents rewrite
  listings from the product data and reviews, generate A+ content drafts,
  and translate into DE/ES/IT for EU marketplaces, all in bulk via the
  seller's export. Priced per SKU (3-8 EUR) or per catalog (500-2,500 EUR).
- **First step this week**: Take one public seller's 20 worst listings,
  rewrite them, and send the before/after as a PDF with a per-SKU price.
- **Startup cost**: under 100 EUR.
- **Realistic monthly revenue**: 500-3,000 EUR (catalog jobs are lumpy but
  large).
- **Automation level**: 90%.
- **Main risk**: Sellers measure you on conversion rate; if the rewrite does
  not move it in 30 days you do not get the second catalog.

### 12. Short-term rental co-hosting on messaging and pricing only
- **What**: Airbnb and Booking hosts with 2-10 listings hate the messaging
  and pricing chores, not the cleaning. Offer remote co-hosting limited to
  guest messaging (agents answer 90% of questions from a house manual),
  review writing, dynamic price suggestions, and calendar sync. 8-12% of
  bookings or a flat 60-120 EUR per listing per month.
- **First step this week**: Write the house-manual-to-agent template and
  offer to run messaging for one host you know for a free month.
- **Startup cost**: under 100 EUR.
- **Realistic monthly revenue**: 300-2,500 EUR (10-25 listings at month 6).
- **Automation level**: 85% (escalations for real incidents are human).
- **Main risk**: A wrong answer about check-in or a lockbox code costs a
  5-star review; keep a human on call for the check-in window.

### 13. Real estate listing packs for independent agents
- **What**: Independent French real estate agents (IAD, SAFTI, Capifrance
  networks) produce mediocre listings. Sell a per-listing pack (49-99 EUR):
  polished description in three tones, legally required mentions checked
  (DPE, copropriete fees, honoraires), photo enhancement and virtual
  decluttering with clear "retouched" labeling, and a social video cut.
- **First step this week**: Rebuild the pack for 5 live listings from one
  agent and hand them the result for free.
- **Startup cost**: 100-200 EUR (image tooling credits).
- **Realistic monthly revenue**: 400-2,500 EUR (agents list 2-6 properties a
  month and are used to paying per lead).
- **Automation level**: 85%.
- **Main risk**: Virtual staging that misrepresents a property is a legal and
  trust problem; label every retouched image and never alter structure.

### 14. Product photography and catalog imagery for small brands
- **What**: Small DTC brands and Etsy shops need consistent product imagery
  for every new color or season. Using generative image editing on the
  brand's own product shots (background, scene, model swaps), deliver
  campaign sets at 15-40 EUR per final image, with strict "the product itself
  is never regenerated" rules.
- **First step this week**: Take 3 product photos from a friend's shop,
  produce 10 scene variations each, and price the set.
- **Startup cost**: 50-150 EUR.
- **Realistic monthly revenue**: 300-2,000 EUR.
- **Automation level**: 80%.
- **Main risk**: Misrepresenting the product (wrong color, texture) triggers
  returns and chargebacks for the client; verification gates on the product
  pixels are the actual deliverable.

---

## Category 4: Education and careers (your Studi context is an edge)

### 15. Exam-prep question banks for French vocational diplomas
- **What**: BTS, CAP, and Titre Professionnel candidates lack practice
  material aligned to the official referentiels. Agents generate question
  banks with explanations from the public referentiel, verified against
  official annals by a subject reviewer, sold as an app or PDF packs (9-29
  EUR) or licensed to training centers (500-2,000 EUR per diploma per year).
- **First step this week**: Build 200 verified questions for one diploma
  module and put a free sample in a candidate Facebook or Discord group to
  measure pull.
- **Startup cost**: 100-200 EUR (reviewer time for the first bank).
- **Realistic monthly revenue**: 200-2,000 EUR; the B2B license is where it
  scales.
- **Automation level**: 80%.
- **Main risk**: Conflict of interest with your employer if the diplomas
  overlap Studi's catalog; check your contract and pick diplomas they do not
  offer, or pitch it internally instead.

### 16. Corporate micro-training from a company's own documents
- **What**: SMEs must train staff on their own procedures (safety, GDPR,
  onboarding) and never do it well. Agents turn the company's PDFs into a
  5-lesson micro-course with quizzes and a completion certificate, hosted on
  a simple LMS. 900-2,500 EUR per course plus 49 EUR/month hosting.
- **First step this week**: Turn one public safety procedure into a 5-lesson
  demo course and send it to 5 HR managers in your network.
- **Startup cost**: 100-200 EUR.
- **Realistic monthly revenue**: 500-4,000 EUR (course fees) plus stacking
  hosting fees.
- **Automation level**: 80%.
- **Main risk**: Qualiopi and OPCO funding do not apply to a solo non-certified
  provider; sell as internal documentation tooling, not certified training.

### 17. Job search concierge for career changers
- **What**: A fixed-price (150-300 EUR) package: tailored CV per application,
  cover letters, LinkedIn rewrite, interview question prep from the job ad,
  and a weekly shortlist of matching openings, run by agents with one human
  coaching call. You already have a CV-builder pipeline; the customer here
  is a non-tech career changer, not a developer.
- **First step this week**: Run 3 acquaintances in job search through the
  pipeline for free and collect what they would have paid.
- **Startup cost**: under 50 EUR.
- **Realistic monthly revenue**: 300-1,500 EUR (10 packages a month at month
  6 is a lot of outreach).
- **Automation level**: 75%.
- **Main risk**: Applicant tracking systems increasingly flag templated
  AI applications; tailoring depth is the product, and it must be real.

---

## Category 5: Data and back office for companies (boring, recurring)

### 18. Lead lists with verified enrichment for B2B sales teams
- **What**: Small B2B firms buy lists that are 40% stale. Agents build
  target lists from public registries (Sirene, LinkedIn public pages, trade
  directories), verify each contact against at least two sources, and
  deliver a scored, GDPR-annotated CSV. 0.80-2 EUR per verified lead or
  300-900 EUR per monthly list.
- **First step this week**: Build a 100-lead list for one niche (French
  independent opticians, for example), verify it manually, and sell it to
  one supplier in that niche.
- **Startup cost**: 50-150 EUR (data sources, verification APIs).
- **Realistic monthly revenue**: 500-3,000 EUR.
- **Automation level**: 85%.
- **Main risk**: GDPR: B2B prospecting on professional data is allowed under
  legitimate interest with opt-out, but scraping personal profiles at scale
  is not; document the legal basis on every list.

### 19. Meeting notes and follow-up desk for consultants and agencies
- **What**: Solo consultants record client calls but never send the follow-up.
  A service that ingests their recordings (Granola, Zoom, phone), produces
  the summary, decisions, action items, and a ready-to-send follow-up email
  in their voice, plus a monthly client-by-client history. 29-69 EUR/month
  per consultant.
- **First step this week**: Process one week of your own meetings with the
  pipeline and send the format to 10 consultants asking if they would pay.
- **Startup cost**: under 100 EUR.
- **Realistic monthly revenue**: 200-1,500 EUR.
- **Automation level**: 95%.
- **Main risk**: Otter, Fireflies, and Granola bundle this for the same price;
  the wedge is the per-client history and the follow-up email, which is thin.

### 20. Pre-accounting and receipt triage for micro-entrepreneurs
- **What**: French micro-entrepreneurs forward receipts and invoices to an
  email address; agents categorize, extract amounts and VAT, flag missing
  legal mentions, prepare the URSSAF declaration figures, and hand a clean
  export to their accountant. 19-39 EUR/month.
- **First step this week**: Process three months of one freelancer's inbox
  and compare your figures to what their accountant produced.
- **Startup cost**: under 100 EUR.
- **Realistic monthly revenue**: 300-2,000 EUR (needs 20-60 subscribers;
  churn is low once the habit is installed).
- **Automation level**: 90%.
- **Main risk**: You are not an expert-comptable and must not present the
  output as accounting; sell it as document preparation, and remember that
  Pennylane, Indy, and Tiime already do most of it at similar prices.

---

## Top 3 picks for this profile

1. **#1 AI phone receptionist for artisans** - the missed-call problem is
   universal, measurable, and constant; the tooling is a configuration job,
   and the French-speaking, local, trusted operator is the actual product.
   It is also the natural upsell base for #2 and #3.
2. **#4 Tender watch and bid drafting** - the only idea on this list where a
   single deliverable is worth 1,000 EUR or more to a small company, the
   demand is documented (every SME complains about it), and the pipeline is
   pure reading and writing with a strict verification gate, exactly what the
   RepoAtlas engine already does with code.
3. **#6 Niche newsletter** - the slowest, but the only one that builds an
   asset nobody can revoke, feeds sponsors, and becomes the distribution
   channel for every other service here (the failure mode of part 1 was
   "no audience"; this is the fix).

Common thread with part 1: start with a service to local or B2B buyers who
already spend money on the problem (weeks), let the pipeline become a
subscription (months), and treat any platform-dependent volume play (KDP,
Etsy, YouTube) as a side catalog with strict disclosure, never as the plan.

---

## Platform realities checked in September 2026

- **Amazon KDP**: AI-generated text, images, or translations must be
  disclosed via the "This title contains AI-generated content" checkbox;
  AI-assisted editing does not. Disclosure is not shown to buyers and does
  not affect ranking. Undisclosed AI content leads to blocked titles or
  account suspension; the 3-titles-per-day limit remains; image-heavy AI
  books take 3-7 business days to review.
- **Etsy**: AI-generated digital products are allowed with disclosure of AI
  involvement in title and description, and since 2026 an AI tag on
  generated or enhanced images; automated detection and member reports both
  lead to removals.
- **YouTube**: since July 15, 2026 the Partner Program rule "repetitious
  content" became "inauthentic content"; templated, mass-produced videos with
  no real author input are demonetized. Faceless channels stay eligible with
  original scripts and curation. In January 2026 YouTube terminated 16
  channels totaling 35 million subscribers under that policy.
- **Voice agents**: platform pricing sits around 0.05-0.12 USD per minute
  (Vapi, Retell, Synthflow), so a business with 1,000 minutes a month costs
  100-300 USD in platform fees plus telephony; agencies charge 500-2,000
  USD/month on top for configuration and monitoring, which is the margin
  idea #1 targets.

Sources:
- https://kdpbuilder.com/blog/kdp-ai-disclosure-rules
- https://publishing.co.uk/guides/kdp-ai-content-disclosure/
- https://www.promptlesspress.com/blog-etsy-ai-policy-2026-digital-products
- https://ngini.com/en-us/blog/etsy-ai-disclosure-policy-2026-explained
- https://arwriterai.com/en/blog/youtube-inauthentic-content-policy-ai-creators-2026/
- https://milx.app/en/news/why-youtube-just-suspended-thousands-of-ai-channels-and-how-to-protect-yours
- https://theaicall.com/blog/ai-voice-agent-pricing-in-2026-what-youll-really-pay
- https://www.cloudtalk.io/blog/best-ai-voice-agents/
