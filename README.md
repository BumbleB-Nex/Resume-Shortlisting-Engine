# Smart Shortlisting Engine

Rank resumes against a job description with **explainable, evidence-backed scores** — fully local, no external APIs.

Built for the InternLoom AI Hackathon problem statement *"Smart Shortlisting Engine — Rank Resumes Against a Job Description"*.

## What it does

1. **Parses the JD** into atomic, weighted requirements (must-have / preferred / responsibility), grouping alternatives such as `SQL (PostgreSQL / MySQL)` and demoting soft skills so they never block a candidate.
2. **Parses resumes** (PDF / DOCX / TXT) into evidence chunks tagged with section, action verbs, quantification and recency — tolerant of messy layouts and unusual section names.
3. **Scores every requirement × candidate** with three independent signals:
   - **Semantic** (50 %) — local `BAAI/bge-small-en-v1.5` sentence embeddings, calibrated cosine similarity between each requirement and the resume's evidence chunks.
   - **Keyword** (30 %) — BM25 over the resume corpus + a skill ontology with aliases (`JS → JavaScript`) and related-skill credit (`Vue → React`).
   - **Evidence** (20 %) — how strongly the skill is *demonstrated*: project/experience bullets with action verbs and numbers outrank a bare mention in a skills list. Keyword-stuffing is detected and penalised.
4. **Aggregates** into a candidate score: `final = (semantic·w₁ + keyword·w₂ + evidence·w₃) × mandatory-coverage × 100`.
5. **Explains** every rank with deterministic templates — matched / missing skills, the exact resume sentence used as evidence, match type (EXACT / ALIAS / RELATED / SEMANTIC), confidence — and answers recruiter questions such as *"Why is A above B?"*.

No LLM decides any score. A local Ollama model is used **only** as an optional fallback to structure an unusually formatted JD.

## Quick start

```powershell
# Windows (PowerShell)
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# put the JD in data/jd/ and resumes in data/resumes/ (or use the demo set), then:
.\.venv\Scripts\python.exe -m streamlit run app.py
```

```bash
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
streamlit run app.py
```

The embedding model (~130 MB) downloads once on first run and is cached by HuggingFace; everything afterwards runs offline.

### Command-line

```bash
python run_cli.py                                   # rank data/resumes against data/jd/Sample_JD.pdf
python run_cli.py --jd path/to/jd.pdf --resumes path/to/folder --explain --top 3 --bias
```

## The UI (Streamlit, 7 tabs)

| Tab | Purpose |
|---|---|
| **Dashboard** | Score distribution, mandatory coverage, top candidate |
| **Ranking** | Full sortable table with semantic / keyword / evidence sub-scores, confidence, stuffing flags; CSV export |
| **Top 3** | Detailed breakdown, matched & missing must-haves, evidence sentences |
| **Candidate** | Any candidate: radar chart, requirement table, plain-text explanation |
| **Compare** | Side-by-side A vs B with a generated "why A ranks above B" summary |
| **Ask** | Recruiter Q&A — *why X above Y*, *who has Docker*, *missing skills for Z*, *top 5* … |
| **JD & What-if** | Structured requirements, bias / narrow-phrasing indicators, and a live weight simulator that re-ranks instantly |

The sidebar lets you upload a new JD and resumes, or switch between resume folders (`data/resumes` = 176 dummy resumes, `data/resumes_demo` = an 18-resume demo set).

## Project layout

```
smart_shortlisting/
├── app.py                    Streamlit UI
├── run_cli.py                Terminal runner
├── config.py                 All tunable weights, thresholds and paths
├── requirements.txt
├── pipeline/
│   ├── interfaces.py         Shared dataclasses (Requirement, Resume, CandidateResult…)
│   ├── pdf_utils.py          PDF / DOCX / TXT extraction and cleaning
│   ├── jd_parser.py          JD → atomic weighted requirements (regex → Ollama fallback → ontology)
│   ├── resume_parser.py      Resume → sectioned evidence chunks
│   ├── ontology.py           Skill aliases, related skills, soft skills
│   ├── keyword.py            BM25 + ontology matching
│   ├── semantic.py           Local sentence-transformer matching with disk cache
│   ├── evidence.py           Evidence quality, keyword-stuffing detection
│   ├── scorer.py             Requirement/candidate aggregation (weight-independent match state)
│   ├── ranker.py             Heap-based ranking
│   ├── explainer.py          Deterministic explanations
│   ├── comparator.py         "Why A above B"
│   ├── qa_engine.py          Recruiter Q&A intents
│   └── bias_detector.py      JD bias / narrow-phrasing indicators
├── scripts/
│   ├── make_sample_jd.py     Generates data/jd/Sample_JD.pdf
│   └── fetch_drive_resumes.py  Downloads the dummy resume set
└── data/
    ├── jd/                   Job descriptions
    ├── resumes/              Full dummy resume set
    └── resumes_demo/         18-resume demo subset
```

## Scoring details

| Tag | req_score |
|---|---|
| STRONG | ≥ 0.75 |
| PRESENT | ≥ 0.45 |
| WEAK | ≥ 0.20 |
| MISSING | < 0.20 |

- Mandatory coverage gives full credit for PRESENT/STRONG must-haves, partial credit for WEAK, none for MISSING, and multiplies the base score (with a small floor so the tail stays ordered).
- Confidence = extraction quality × mean evidence of matched requirements (HIGH ≥ 0.70, MEDIUM ≥ 0.45).
- All thresholds and weights live in `config.py`; the What-if tab lets recruiters change the three signal weights live.

## Bias indicators

The JD tab flags exclusionary or proxy wording ("rockstar", "young", "native speaker"), experience-year requirements for intern roles, version-specific or single-vendor must-haves, and overly long mandatory lists. Indicators are informational only and never change the ranking.
