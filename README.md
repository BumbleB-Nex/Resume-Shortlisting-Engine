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

.\.venv\Scripts\python.exe -m streamlit run app.py
# then upload a JD + resumes in the sidebar (e.g. data/jd/Sample_JD.pdf + data/resumes_demo/*)
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

## The UI (Streamlit)

Each session starts empty: the recruiter uploads **one job description** and **the candidate resumes** in the sidebar and clicks **Run shortlisting**. The files are written to a temporary folder for that session only, the ranking is computed from exactly those files, and **Reset** (or closing the app) discards everything — nothing is stored and no previous JD or resume set influences the result. (The on-disk embedding cache in `.cache/embeddings` is keyed by content hash and only affects speed, never scores.)

| Page | Purpose |
|---|---|
| **Shortlist** | Ranked table — score, must-have coverage, confidence, top matched skills, key gaps (sub-scores behind a toggle); CSV export; top-10 chart; JD / coverage / confidence cards |
| **Top 3** | One evidence card per candidate: matched & missing skills, match type per must-have (EXACT / ALIAS / RELATED / SEMANTIC / MISSING) with the exact resume sentence, plain-English explanation |
| **Candidate** | The same card for any candidate plus the full requirement table and a per-requirement score chart |
| **Compare** | Side-by-side A vs B with a generated "why A ranks above B" summary |
| **Ask** | Recruiter Q&A — *why X above Y*, *who has Docker*, *missing skills for Z*, *top 5* … |
| **JD & Settings** | Structured requirements, bias / narrow-phrasing indicators, and a What-if weight simulator that re-ranks instantly |

`data/` is sample material only — used by the CLI (`run_cli.py`) and handy for uploading manually in the UI (`data/jd/*.pdf`, `data/resumes_demo` = an 18-resume demo set, `data/resumes` = the full dummy set).

Presentation code lives in `ui/` (`theme.py` CSS + WebGL hero, `components.py` cards/chips, `charts.py`, `session.py` per-session upload handling); `app.py` is pages and orchestration only.

## Project layout

```
smart_shortlisting/
├── app.py                    Streamlit UI (pages / orchestration)
├── ui/                       Theme (CSS + WebGL hero), components, charts, per-session uploads
├── .streamlit/config.toml    Dark theme
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
    ├── jd/                   Sample job descriptions (CLI / manual upload)
    ├── resumes/              Full dummy resume set (CLI / manual upload)
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
- All thresholds and weights live in `config.py`; the JD & Settings page lets recruiters change the three signal weights live.

## Bias indicators

The JD & Settings page flags exclusionary or proxy wording ("rockstar", "young", "native speaker"), experience-year requirements for intern roles, version-specific or single-vendor must-haves, and overly long mandatory lists. Indicators are informational only and never change the ranking.
