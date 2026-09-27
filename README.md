# Marsh Pitch Generator

AI-powered insurance marketing pitch generator that creates client-specific presentations grounded in policy documents, with built-in factual accuracy auditing.

## Architecture Overview

```
┌─────────────────────────────────┐
│  Target Company Input & Upload  │
│  (Modern Web UI on FastAPI)     │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐      ┌─────────────────────────────┐
│  /api/upload-policy (Dynamic)   │─────▶│  Policy Documents (PDFs)    │
│  parse_policy_docs (pdfplumber) │      │  Chunked by Section/Clause  │
└─────────────────────────────────┘      └──────────────┬──────────────┘
                                                        │
               ┌────────────────────────────────────────┘
               ▼
┌─────────────────────────────────┐
│  1. generateCompanyProfile      │  ──▶ Inferred demographics & exposures
│     (gemini-3.5-flash-lite)     │      with explicit assumption logs
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  2. generateMarketingPitch      │  ──▶ 3–5 slides grounded in policy chunks
│     (gemini-3.5-flash-lite)     │      with valid source_chunk_id tags
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  3. auditPitchContent           │  ──▶ Two-step audit: fast fuzzy string match
│     (rapidfuzz + Gemini verify) │      (rapidfuzz) + LLM escalation for edge cases
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐      ┌─────────────────────────────┐
│  On-Demand Exports (Lazy Click) │─────▶│  - PowerPoint Deck (.pptx)  │
│  - render_pptx                  │      │  - Compliance Report (.pdf) │
│  - render_audit_pdf             │      └─────────────────────────────┘
└─────────────────────────────────┘
```

## Modules

| Module | Purpose |
|--------|---------|
| `server.py` | High-performance FastAPI backend serving REST APIs, policy indexing, and the executive web studio |
| `static/index.html` & `static/app.js` | Modern web frontend (Tailwind CSS, Lucide icons, 3-step pipeline, interactive carousel, and clause inspector) |
| `parse_policy_docs.py` | Extracts text from policy PDFs using pdfplumber, chunks by section headings, caches to `chunks.json`, and supports dynamic PDF uploads |
| `generate_company_profile.py` | Fetches verified corporate facts from Wikipedia REST API; uses Gemini 3.5 Flash-Lite to infer healthcare risks with explicit assumptions |
| `generate_marketing_pitch.py` | Generates a 3–5 slide pitch with strict source traceability (`source_chunk_id`) |
| `audit_pitch_content.py` | Two-step audit: rapidfuzz first pass, then Gemini escalation with exponential backoff retry |
| `render_pptx.py` | Builds clean, consulting-grade Marsh McLennan presentation deck on demand |
| `render_audit_pdf.py` | Generates official multi-page Marsh Compliance & Audit Report PDF with full traceability matrix |
| `app.py` | Alternative Streamlit interface (also preserved) |


## Libraries Used

| Library | Version | Purpose |
|---------|---------|---------|
| `streamlit` | ≥1.35 | Web UI framework |
| `google-generativeai` | ≥0.8.0 | Gemini API client (LLM calls) |
| `pdfplumber` | ≥0.11 | PDF text extraction |
| `python-pptx` | ≥1.0 | PowerPoint file generation |
| `rapidfuzz` | ≥3.9 | Fuzzy string matching for audit |
| `python-dotenv` | ≥1.0 | Environment variable management |
| `jsonschema` | ≥4.0 | JSON response validation |

## Design Decisions

### 1. Heading-based chunking (not fixed-size)
Policy documents have natural section boundaries (Eligibility Criteria, Wait Periods, Plan Details, etc.). Heading-based chunking preserves semantic coherence within chunks, making source traceability more meaningful.

### 2. Fuzzy-match-first audit strategy
The audit pipeline uses a **two-step approach** to minimize API costs:
- **Step A (cheap):** rapidfuzz partial_ratio and token_sort_ratio between bullet text and source chunk text
- **Step B (LLM):** Only escalated when Step A score falls in the inconclusive band (30–59)
- Scores ≥60 auto-pass; scores <30 auto-fail; null source_chunk_ids auto-flagged as "untraceable"

This typically reduces LLM calls by 60–80% vs. auditing every claim with Gemini.

### 3. Full context window (no vector store)
All policy chunks (~41K chars total) fit comfortably within Gemini 3.8 Flash's context window. A vector store would add complexity without benefit at this scale.

### 4. Structured JSON output
Gemini is forced to return `application/json` with explicit schema instructions in the prompt. The response is validated programmatically and retried once on schema mismatch.

### 5. Explicit assumption tracking
The company profile prompt requires Gemini to flag any inferred field with `"assumed": true` and a justification. This prevents silent hallucination about the client company.

### 6. Audit thresholds (pending user review)
Current thresholds are **placeholders**:
- **Pass:** confidence_score ≥ 0.7 AND no "not_supported" claims
- **Fail:** any "not_supported" claim OR confidence_score < 0.4
- **Needs review:** everything else

These are marked with `# THRESHOLD LOGIC — awaiting user review` in the code.

## Setup & Running
 
 ```bash
 # 1. Install dependencies
 pip install -r requirements.txt
 
-# 2. Set your Gemini API key
-cp .env.example .env
-# Edit .env and add your key from https://aistudio.google.com/apikey
-
-# 3. Run the app
+# 2. Set your Gemini API key in .env
+# GEMINI_API_KEY=your_key_here
+
+# 3. Run the Modern Web Advisory Studio (FastAPI + Modern Web UI) - RECOMMENDED
+python server.py
+# Open http://localhost:8000 in your browser
+
+# (Optional) Run the legacy Streamlit interface
 streamlit run app.py
 ```

## File Structure

```
marsh-case-study/
├── app.py                          # Streamlit UI entry point
├── parse_policy_docs.py            # PDF parsing & chunking
├── generate_company_profile.py     # Company profile generation (Gemini)
├── generate_marketing_pitch.py     # Pitch generation (Gemini)
├── audit_pitch_content.py          # Factual accuracy audit
├── render_pptx.py                  # PowerPoint generation
├── requirements.txt                # Python dependencies
├── .env.example                    # API key template
├── .gitignore
├── policies/                       # Source policy PDFs
│   ├── ABHI_Product_Brochure.pdf
│   ├── Care_Health_Product_Brochure.pdf
│   ├── HDFC_Product_Brochure.pdf
│   └── Niva_Bupa_Product_Brochure.pdf
├── chunks.json                     # Cached parsed chunks (auto-generated)
├── agent-context/                  # Agent handoff logs
│   └── HANDOFF.md
└── README.md
```
