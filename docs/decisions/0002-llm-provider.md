# ADR 0002: LLM Provider for AI Recommendation Layer

**Status:** accepted
**Date:** 2026-08-31

## Context

The AI Recommendation Layer needs an LLM to turn an enriched prospect profile + product catalog
into what-to-pitch/why/how sales-prep intelligence. This is currently a PoC heading toward a real
product, so cost matters more than provider polish at this stage.

## Decision

Use the free-tier Google Gemini API by default, accessed through a thin client abstraction in
`ai_recommendation/` so the provider can be swapped (e.g. to Claude, OpenAI) once the product is
validated and budget/quality needs justify it.

## Consequences

- Zero LLM cost during PoC validation.
- Free-tier rate limits may constrain throughput/testing volume — acceptable at current scale.
- Swapping providers later only requires changing the client implementation behind the
  abstraction, not prompt/orchestration logic, provided prompts avoid provider-specific features.
