# Start-of-project questionnaire

Ask these, one group at a time, and write the answers into the governance doc. Each answer turns
controls on or off (see `controls.md` for the numbers).

## What the model sees
1. **Which providers and models?** Free tier or paid? Is any model chosen by a rolling alias such as
   `...-latest`? (An alias means the model, behaviour and price can change silently. Prefer a named
   model. -> G6, G8)
2. **Does any prompt contain personal data** (names, emails, phone numbers, free text a person
   typed)? Which providers are cleared to receive it, and who confirmed that? (-> G1)
3. **Does any prompt contain text from outside the system**: scraped pages, search snippets, emails,
   uploaded documents, other users' input? (-> G2, the most important question)

## What the model writes
4. **Is any output customer-facing** (an email, a message, a published page)? Who reviews it before
   it goes out? (-> G3, G4)
5. **Does any output become a stored fact** (a label, a score, a verdict, a summary others will rely
   on)? Can it be traced to the evidence it came from? (-> G3, G9)
6. **Can the model's output trigger an action** (send, delete, approve, spend, call another system)?
   If yes, a person must approve or code must limit it. (-> G4)

## How it is checked
7. **Is there any way to tell a better prompt or model from a worse one today?** Is there a set of
   real cases with answers a person decided? Who can supply labels? (-> G5)
8. **Who will change prompts and models**, and how often? (A team that changes them weekly needs the
   regression gate; a frozen prototype may not.)

## What it costs and how it fails
9. **What is the spend now and the worst plausible month?** Is there any limit? Who is told when it
   is exceeded? (-> G8, G10)
10. **What happens when the provider is down, slow or rate-limited?** Is there a fallback vendor, and
    is a failure ever shown to a user as if it were an answer? (-> G7)

## Where it runs
11. **Is anything interactive** (a person waiting on the answer)? Or is it all background work?
    (Streaming matters only for the first; batch pricing only for work that can wait a day.) (-> G10)
12. **Is there a test setup and a CI?** Where do the team's tests live and are they committed? Put
    the enforcement checks where they will be committed. (-> G6, G9)

## Turning answers into controls
| If the answer is... | Turn on |
|---|---|
| Q3 yes (outside text in prompts) | G2 first, always |
| Q2 yes (personal data) | G1 |
| Q4 or Q6 yes | G4, and G3 for the text |
| Q5 yes | G3, G9 |
| Q7 no (no way to measure) | G5, starting with injection and grounding cases that need no labels |
| Q9 "no limit" and paid | G8 ceiling and alerts |
| Prototype, nothing customer-facing, no outside text | G6 and G8 only, and say the rest is deliberately skipped |
