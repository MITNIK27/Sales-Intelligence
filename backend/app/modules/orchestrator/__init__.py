"""One-Prompt Pipeline Orchestration. The system's second genuine multi-step "agent" (after
`discovery_agent/`) — it decides what to run next based on each stage's actual outcome, chaining
the existing, independent `ingestion.market_discovery`, `qualification`, `role_relevance`, and
`draft` services into one automatic run instead of a chain of manually-triggered buttons. Owns
none of their logic itself, only the sequencing and per-stage skip/error reporting."""
