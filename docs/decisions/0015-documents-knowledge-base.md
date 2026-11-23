# ADR 0015: A documents knowledge base the AI flows can use

**Status:** accepted
**Date:** 2026-11-24

## Context

The team describes what InfoBeans sells in decks, PDFs, Word files and notes: case studies,
capability decks, proposals, pricing sheets. Until Phase 8 none of that reached the app. The AI
flows that judge and pitch our offerings (offering fit, the recommendation, area suggestions, Quick
Check) only knew a one-line catalogue description, so they could not say what an offering has
actually delivered.

Constraints:
- These files are our own material, but they arrive as uploads and can contain anything, including
  text that reads like an instruction to a model (G2).
- Some contain client names and commercial details, so where their text is sent matters (G1).
- Anything a model writes from them must be traceable to who wrote it and from what (G9), and
  must never be mistaken for evidence about a prospect.
- Spend must stay small and predictable on a free or low Gemini tier.

## Decision

1. **Keep the text, not the file.** An upload is held in a short-lived staging row only until the
   worker has read it (a failed read is purged after `DOCUMENTS_STAGING_RETENTION_HOURS`).
   Everything the file said is stored as pages (full text in reading order), passages (about 1,000
   characters, slide- and page-aware) and, when switched on, model descriptions of pictures,
   charts, unreadable tables and scanned pages, each recorded with its model, prompt version and
   cost. Re-indexing never needs the file; re-reading with a better parser needs a re-upload.
2. **Our own readers.** PDF with PyMuPDF (reading order, tables to Markdown, repeated headers and
   footers dropped, decorative images filtered), PowerPoint with python-pptx, Word with
   python-docx, Markdown and text by headings. The file type comes from its content, never its
   name; zip bombs, page and passage limits are refused with a reason. Ideas from the Expona
   extractor were reused; its code was not.
3. **Versions and history.** A new upload of a document is a new version; the old one keeps being
   used until the new one is read, then is kept for audit. Uploads, versions, re-reads, renames,
   deletes, hidden cards and re-summaries are kept in `document_audit`, which outlives the document.
4. **Search by meaning and by words, merged.** Passages get Gemini embeddings
   (`gemini-embedding-001`, 768 dimensions, the model recorded per row so a change re-embeds) in a
   separate background job, so a spent quota never stops a file being read. Search runs a pgvector
   cosine search and a Postgres full-text search and merges them by reciprocal rank fusion, over the
   current version of each document. Without a key, or when embedding fails, it searches by words
   and says so.
5. **Knowledge in the flows, never as evidence.** The four prompts that reason about our offerings
   get the best few matches, labelled `[K1]`, `[K2]`..., fenced as untrusted text, with the rule
   that they describe us and are never evidence about the company. What a model cites is stored
   with its answer (`knowledge_refs`) and shown as "From our documents". A fit, an area or a "yes"
   still needs evidence from the company's own research.
6. **Gemini only for anything from the documents (G1).** Prompts that carry passages go through
   `generate_with_knowledge`, which restricts the chain to Gemini and, if Gemini cannot answer,
   asks again without the passages. Summaries, cards and offering suggestions are written by a
   Gemini-only chain. `governance_checks/test_documents_reach_gemini_only.py` fails if a new path
   could send them elsewhere.
7. **Summaries and knowledge cards.** After reading, Gemini summarises each section and the whole
   document and draws knowledge cards: one short fact each (case study, capability, result, client,
   certification, partnership), tied to the passage it came from. Code keeps a card only when its
   quote is in that passage, every figure in it is in that passage, and a client name is written
   there. Cards are searched like passages and shown to the flows first. A wrong card is hidden by
   a person, never edited, so its words stay the model's own.
8. **Offering descriptions change only by approval.** A document tied to an offering may suggest a
   better description; it waits in the offering review with the facts it used and any figure those
   facts do not back. Approving changes the description only.
9. **Spend has caps.** Pictures: per-document cap and concurrency, off by default. Summaries: a cap
   on sections, cards per section and per document. Every call is metered in `api_usage`; a
   summary row carries what the document cost to summarise.
10. **Released in 8f.** Documents, meaning search and summaries are on by default and switch
    themselves off without a Gemini key; picture descriptions stay off by default.

Alternatives considered: a hosted vector database (Pinecone and similar) and a graph database
(Neo4j) were left for later, behind the `VectorStore` interface and the card entity columns, since
Postgres already holds the data and handles this size; keeping original files was rejected (more
to secure, nothing gained once the text is extracted); an OCR library was not added, since Gemini
vision reads scanned pages when allowed.

## Consequences

- Easier: the flows can cite what we have actually delivered, with a link to the slide; a wrong
  fact is one click to hide; everything a model wrote is traceable to a model, a prompt and a
  passage.
- Harder: a new prompt that wants document knowledge must use the Gemini-only path; prompt changes
  in `card_prompts.py` and `vision.py` need eval reports (`knowledge_cards`, `picture_description`).
- Our own documents are only as good as what is uploaded; nothing checks that a case study is
  still current.
- **Licence to confirm (open):** PyMuPDF is AGPL-3.0 or a commercial licence from Artifex. It is
  used on the assumption that InfoBeans' existing use (Expona) covers it. Get that confirmed in
  writing before the app is served to anyone outside InfoBeans; if it is not, replace
  `documents/parsers/pdf.py` (every reader returns the same `ParsedDocument` through
  `read_document`, so nothing else changes; pypdf and pdfplumber are permissively licensed) and
  re-read the PDFs.
- Revisit: a graph view of clients, industries and offerings once cards accumulate; a dedicated
  vector store if the library grows past what one Postgres serves comfortably (the 8f load test:
  4,000 passages and 1,000 cards answer in well under half a second); per-person access to
  documents once sign-in exists.
