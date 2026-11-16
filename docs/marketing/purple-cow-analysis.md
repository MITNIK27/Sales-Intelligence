# Purple Cow Analysis

_Written 2026-11-16 from the code and docs as of commit `0ba10bf`. Competitor and market statements
come from a web search the same day and are marked **[unverified]** where the source is a vendor or
blog. Verify before using any of them publicly._

## 1. The question

Does Sales Intelligence have a "purple cow" (Seth Godin, *Purple Cow*): something so unusual that
people remark on it and pass it on, not just a good product with good marketing?

**Short answer: it has the ingredients, not yet the cow.** Several behaviours are genuinely unusual
for this category, and they trace back to a single idea. But today they are spread across screens as
features, nobody has named the idea, and a few things a skeptical buyer will test first are not
built. Pitched as "AI prospecting that finds companies and writes emails", it is a brown cow: that
is what every tool in the category says.

### How we test for a purple cow
1. **Would a rep say it out loud to a colleague?** A remark-worthy sentence, not a feature list.
2. **Can you see it in the first minutes of a demo**, without being told?
3. **Does it cost something?** Godin's cows usually give something up (a limit, a refusal). A claim
   nobody could object to is not remarkable.
4. **Is it provable, not just claimed?** For this product it must be visible in the UI and in the
   code, because a trust claim that fails once is worse than none.
5. **Is it hard to copy by a bigger player in a quarter?**

## 2. The idea that holds it together

> **It shows its receipts, and it will tell you "I don't know".**

Every judgment the product makes is either backed by a quote you can check, or it says it could not
determine. The model proposes; code decides; a person approves. Nothing is sent.

That is the opposite of the category's selling posture (more volume, more confidence, more
automation). It is also directly answerable to a real, current complaint: AI outbound tools that
invent facts about the prospect. Search results describe fabricated funding rounds, invented
shared connections and wrong-vertical emails, and say prospects notice when a quoted claim cannot be
found. Rates and churn figures in those sources are secondhand and **[unverified]**, but the problem
itself is widely discussed ([ABM.dev](https://dev.to/abmdev/ai-sdr-hallucination-pk5),
[AiSDR](https://aisdr.com/blog/ai-hallucination-trust.md),
[MapsLeads](https://www.mapsleads.co/blog/risks-of-ai-in-outbound)).

## 3. Audit of the candidates (what the code actually does)

| # | Behaviour | Where it lives | Remarkable? | Why |
|---|---|---|---|---|
| 1 | **Verbatim-quote evidence; unverifiable verdicts downgrade to "could not determine"** | `qualification/evidence.py`, `opportunity/evidence.py`, Quick Look snapshot checks | **Strong** | Costs something (shows more "don't know"), visible in the UI, enforced in code, rare as a stated rule. |
| 2 | **Model judges, code decides** (verdict, Priority Score, fit band, role priority computed in Python) | `qualification/ranking.py`, `opportunity/sufficiency.py`, `role_relevance` | Strong, but hard to *see* | The auditable score is a real differentiator, but a user only feels it through #1 and #8. |
| 3 | **"Check before sending"**: finished email scanned for invented figures and fake past-work claims | `draft/claims.py`, `DraftFlags.tsx` | **Strong, demoable** | Visible in 10 seconds. Tool that warns you about its own draft is unusual. Honest limit: a heuristic that can miss a claim. |
| 4 | **Never sends; a person decides** | `outreach/` (manual "Log as Sent"), ADR 0011 | Medium | Counter to the AI-SDR trend, but also just "not built yet" (no Gmail integration). Becomes a stance only if chosen on purpose. |
| 5 | **"Not a fit" with memory**: rejected companies leave every automatic step and are not revived by later searches; the reason and what discovery saw are logged | `review/`, `companies` dismissal, `skipped_dismissed` | Medium | Feels like a tool that learns your taste. Not yet a learner: the judge that uses the log (Phase 4b) is not built. |
| 6 | **Evidence-to-engagement map** with verified, inferred and unsupported links drawn differently and gaps shown as placeholders | `features/brief/graph/` | **Strong, demoable** | A picture of "what we know vs what we guess". Screenshot-worthy. |
| 7 | **Honest run screen**: real company names, real trail, "why wasn't this shown" for every company left out | `RunProgress`, `RunOutcome`, `run_results.py` | Medium | Respectful of the user, but looks like good UX unless framed. |
| 8 | **Priced in the open**: cost per call, task, run and company metered; the plan estimates about $0.03 to $0.05 per Quick Check brief | `modules/usage`, dashboard Cost panel | Medium | Unusual for a vendor to show cost-to-serve. Estimates only; the cost review on real runs is still to do. |
| 9 | **Sells *your* catalog**: offerings synced from your website with approval, one offering per email, a "Not a fit" for the pitch too | `offerings/`, drafting | Medium | Real, but "personalization" is every competitor's word. |
| 10 | **Governed AI**: evals, prompt versions, injection fencing, a reusable governance programme | `governance_checks/`, `evals/`, `ai-governance.md` | Strong for enterprise, invisible to a rep | A buyer-side trust story and an InfoBeans-credibility story (InfoBeans sells AI services). Not a cow for reps. |
| 11 | **Origin**: built by an engineer for a real rep's spreadsheet routine, with the rep's own rules ("everything factual, validated, flag it if you can't") as the spec | Meeting notes, assessment brief | Medium | A true, specific story; it explains #1 and #3 as a founder-level conviction, not a feature. |

**What is *not* a cow:** finding companies from plain language, enrichment, ranking, role
classification and drafting by email type. These are table stakes. Contact databases, volume,
sequencing and phone data are where the large vendors compete, and they are far ahead there.

## 4. Competitive context [unverified, from vendor and listicle sources]

The search results describe the large players repositioning around AI agents: Apollo as a
consolidated platform for enrichment, prospecting and sequencing; ZoomInfo as agent-ready data
(a "GTM.AI" layer exposed through MCP is reported); Clay as an enrichment workflow builder with web
research agents ([Apollo](https://www.apollo.io/insights/best-software-for-real-time-contact-enrichment),
[ZoomInfo](https://pipeline.zoominfo.com/sales/ai-gtm-tools),
[comparison](https://www.knowlee.ai/blog/ai-prospecting-tools-2026)). Contact-count and price
numbers conflict across those sources, so none are repeated here.

What this implies, if it holds on a closer look:
- The category competes on **data breadth and agent autonomy**. Nobody in those results leads with
  *provable, quote-level evidence per judgment*.
- A bigger player can bolt on "citations" quickly, so #1 alone is copyable. What is hard to copy is
  the whole stance: verdicts in code, "don't know" as a first-class answer, nothing sent without a
  person, and the habit of designing around it. That is a culture and architecture, not a feature.
- This product cannot win on data volume. It does not try to, and should say so.

## 5. Internal section: InfoBeans sales and leadership

**The audience** is a few reps, their managers and leadership. They do not compare against Apollo;
they compare against the spreadsheet and their own hours.

**The remark a rep makes:** "It showed me *why* it picked this company, with the line from their own
site, and it told me when it didn't know." Secondary: "It warned me my email had a number it
couldn't back up."

**Purple-cow moves for adoption**
- Lead the internal demo with one company: the verdict, the quote that backs it, the "could not
  determine" on a criterion, then "Check before sending". Do not lead with the pipeline.
- Show the time given back: one rep's spreadsheet day, replaced by one confirmation click and a
  worklist. Use real numbers from a timed comparison, not estimates. (Not measured yet.)
- Leadership angle: the dashboard shows funnel, cost per researched company and attention queue, and
  the governance programme is a proof point for InfoBeans' own AI-services credibility. That is a
  separate story from the rep's.
- Make "Not a fit" a ritual reps enjoy: each rejection is visibly remembered.

**Risks internally:** a tool that says "I don't know" can feel slower than a tool that always
answers; reps will compare the first week's output with their gut. Show the trade explicitly.

## 6. External section: the market

**Category framing options** (pick one before writing any copy):
1. *Prospecting you can audit.* Evidence-first sales research. Safest, most truthful.
2. *The AI sales researcher that admits what it doesn't know.* Stronger, more remarkable, rests on #1
   and #3.
3. *The anti-AI-SDR*: research and drafting with a human always sending. Sharp, but only true by
   choice, and it ignores Gmail integration as a roadmap item.

**Candidate positioning lines** (each needs the evidence in brackets to stay true)
- "Every call it makes comes with the quote that proves it." [#1, #2]
- "It will tell you when it doesn't know." [#1, tested by the "could not determine" rate]
- "Your email, checked against the facts before it leaves your hands." [#3, heuristic, say so]
- "Research you can show your manager." [#6, #10]
- "Built by a rep's routine, not a growth deck." [#11]

**Demo moments that make people remark** (build and rehearse these)
1. The quote that backs a verdict (hover or open to see the source text).
2. A "could not determine" shown proudly.
3. The "Check before sending" note catching an invented number.
4. The evidence map with solid, dashed and empty links.
5. "Why wasn't this shown?" next to every company left out.

**Who it is for first:** teams that sell expensive, considered services to a modest list of accounts
(InfoBeans' own motion: enterprise services), where one wrong fact in an email costs a deal. Not
high-volume SDR teams, where the volume tools win.

**What must be true before saying it publicly**
- Accuracy is measured against real labelled companies (the eval set is 37 cases and five tasks have
  no first report). A trust claim needs a number behind it.
- The "could not determine" rate is reported honestly: too high and the tool is useless, too low and
  the claim is empty. Neither is measured yet.
- Contact verification exists (today contacts are found, not verified), or the claim is scoped to
  company research and drafting only.
- Sign-in and tenant isolation (Phase 7) before any outside customer.
- The injection and fencing story is tested against hostile pages (planned in the evals).

## 7. Gaps that stop it being a cow today

| Gap | Why it matters | Fix |
|---|---|---|
| The idea has no name or single sentence | Nobody can repeat it | Choose a line from section 6 and use it everywhere |
| Name "Sales Intelligence" is generic | The opposite of a purple cow | Part of the branding step |
| Evidence is shown but not celebrated | The receipt is easy to miss | Make quote and "don't know" first-class in the UI |
| No contact verification | A skeptic's first test is a bounced email | Phase 5, or scope the claim |
| Accuracy and "don't know" rate unmeasured | The claim is unproven | Labelled-company eval; report the rate |
| No sending, no sign-in | Looks unfinished externally | Gmail send (ADR 0011), Phase 7 |
| Brand is InfoBeans' (`design-kit/`: cream, charcoal, crimson, Lexend, square corners) | A product with its own claim may want its own identity | Decide sub-brand versus product brand |
| Evals small; Groq blocked for personal data; free-tier caps | Limits what can be promised at scale | Governance open items in `ai-governance.md` |

## 8. Recommendation and open questions for branding

**Recommendation:** make the purple cow **"the research tool that shows its receipts and admits what
it doesn't know,"** prove it with two numbers (accuracy on labelled companies and the "could not
determine" rate) and five rehearsed demo moments, and let the name, visual identity and tone follow
from that. Do not compete on data or on volume.

Open questions for the branding step:
1. Is the first audience InfoBeans-internal adoption, or an external product? The line, the name and
   the proof required differ.
2. Product name and relationship to the InfoBeans brand: sub-brand of InfoBeans, or its own?
3. Tone: the truthful, careful voice suits the claim. Is it also the InfoBeans voice?
4. Is "a person always sends" a permanent stance or a phase? It is remarkable only if permanent.
5. Which of the three category framings in section 6?
6. Which numbers can be measured soon enough to support the line?

## Sources
Web search on 2026-11-16 (vendor and blog content, not independently verified):
[ABM.dev](https://dev.to/abmdev/ai-sdr-hallucination-pk5),
[AiSDR](https://aisdr.com/blog/ai-hallucination-trust.md),
[MapsLeads](https://www.mapsleads.co/blog/risks-of-ai-in-outbound),
[Apollo](https://www.apollo.io/insights/best-software-for-real-time-contact-enrichment),
[ZoomInfo](https://pipeline.zoominfo.com/sales/ai-gtm-tools),
[Knowlee comparison](https://www.knowlee.ai/blog/ai-prospecting-tools-2026), and book summaries of
*Purple Cow* (for example [YouExec](https://youexec.com/resources/purple-cow-by-seth-godin)).
Product facts: [`PROJECT_OVERVIEW.md`](../../PROJECT_OVERVIEW.md), [`ai-governance.md`](../ai-governance.md),
[`architecture.md`](../architecture.md).
