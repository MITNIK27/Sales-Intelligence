## What and why


## AI changes (skip if this PR touches no prompt, model call, vendor or AI-written table)
Rules are in [docs/ai-governance.md](../docs/ai-governance.md).

- [ ] Run `pytest governance_checks` from `backend/` and it passes
- [ ] A changed prompt has its version constant bumped (cached answers are keyed on it)
- [ ] Web text put into a prompt is fenced as untrusted (G2)
- [ ] Nothing here lets the model approve its own work or send anything without review (G4)
- [ ] A new vendor says whether it may receive personal data (G1)
- [ ] A new AI-written table records `model_used` and `prompt_version` and is added to the G9 check
- [ ] Once evals exist: the report for the changed prompt or model is attached (G5)
