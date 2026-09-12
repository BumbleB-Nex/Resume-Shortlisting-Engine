"""
Central configuration for the Smart Shortlisting Engine.

Every tunable number in the system lives here so judges (and the
What-if Simulator) can see exactly which knobs exist.
"""
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR     = PROJECT_ROOT / "data"
JD_DIR       = DATA_DIR / "jd"
RESUMES_DIR  = DATA_DIR / "resumes"
CACHE_DIR    = PROJECT_ROOT / ".cache" / "embeddings"


def default_jd_path() -> Path:
    """First PDF found in data/jd/ (Sample_JD.pdf preferred)."""
    preferred = JD_DIR / "Sample_JD.pdf"
    if preferred.exists():
        return preferred
    pdfs = sorted(JD_DIR.glob("*.pdf"))
    return pdfs[0] if pdfs else preferred


JD_PATH = default_jd_path()

# ── Local embedding model (runs fully offline once cached) ─────────
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
# BGE models perform better on short queries with this instruction prefix.
EMBEDDING_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Raw cosine similarity from BGE sits in a narrow band (unrelated text
# still scores ~0.5). We linearly rescale raw cosine into 0..1 so the
# semantic score is spread out and thresholds below are meaningful.
#   calibrated = clip((cos - CAL_MIN) / (CAL_MAX - CAL_MIN), 0, 1)
SEMANTIC_CAL_MIN = 0.60   # measured: resumes NOT mentioning a skill peak at ~0.63 cosine
SEMANTIC_CAL_MAX = 0.80   # measured: strong evidence chunks reach ~0.75-0.83

# ── Ollama (LOCAL fallback for JD structuring only) ────────────────
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_TIMEOUT_SEC = 60
JD_MIN_REQUIREMENTS_BEFORE_FALLBACK = 3

# ── Scoring weights (default; What-if Simulator overrides live) ────
# Semantic matching is the primary signal (problem statement: a strong
# candidate rarely uses the JD's exact words). Keyword matching still
# genuinely contributes so explicit tool requirements are not diluted.
WEIGHTS = {
    "semantic": 0.50,   # local sentence-transformer similarity
    "keyword":  0.30,   # BM25 + ontology coverage
    "evidence": 0.20,   # section quality × action verb × quantified × recency
}

# Semantic score blends the single best evidence chunk with supporting
# chunks so a candidate with several relevant bullets beats one with a
# single lucky sentence.
SEMANTIC_BEST_SHARE    = 0.70   # weight of best chunk similarity
SEMANTIC_SUPPORT_SHARE = 0.30   # weight of mean(top-K chunk similarities)
SEMANTIC_SUPPORT_TOPK  = 3

# Requirement importance multipliers used in weighted aggregation
REQ_WEIGHT = {
    "must_have":      2.0,
    "preferred":      1.0,
    "responsibility": 0.5,
}

# final = base × (MANDATORY_FLOOR + (1 − MANDATORY_FLOOR) × mandatory_coverage) × 100
# 0.0 = hard gate (zero must-haves ⇒ score 0). A small floor keeps the tail ordered.
MANDATORY_FLOOR = 0.15

# Real-world JDs can list 20+ "required" items; beyond this many, the least
# specific ones are demoted to preferred so the mandatory gate stays meaningful.
MAX_MUST_HAVE = 12

# Long "nice-to-have" lists (or a mis-classified competency grid) are trimmed
# to this many preferred items; the overflow is kept as responsibility context.
MAX_PREFERRED = 25

# When a JD has no explicit requirements section (e.g. only "Key
# Responsibilities"), the core skills mentioned in the responsibilities /
# job-purpose prose are promoted to must-haves so the mandatory gate still
# reflects what the recruiter expects.
DERIVED_MUST_HAVE_MIN_SKILLS = 3   # below this, concrete responsibility items are promoted too
DERIVED_TASK_MUST_HAVES = 3        # how many responsibility items may become task must-haves

# Numeric importance stored on each Requirement
REQ_IMPORTANCE = {
    "must_have":      1.0,
    "preferred":      0.6,
    "responsibility": 0.4,
}

# ── Section evidence weights ───────────────────────────────────────
SECTION_WEIGHT = {
    "experience":     1.0,
    "projects":       1.0,
    "skills":         0.5,
    "certifications": 0.4,
    "education":      0.3,
    "summary":        0.3,
    "other":          0.2,
}
WORK_SECTIONS = ("experience", "projects")

# Evidence multipliers
EVIDENCE_VERB_BONUS     = 1.20
EVIDENCE_NO_VERB        = 0.80
EVIDENCE_QUANT_BONUS    = 1.10
RECENCY_DEFAULT         = 0.80
RECENCY_MIN             = 0.50
RECENCY_DECAY_PER_YEAR  = 0.10

# ── Keyword matching ───────────────────────────────────────────────
KEYWORD_BM25_SHARE     = 0.50   # keyword_score = 0.5*bm25 + 0.5*ontology
KEYWORD_ONTOLOGY_SHARE = 0.50
BM25_K1 = 1.5
BM25_B  = 0.75
ONTOLOGY_RELATED_CREDIT = 0.60

# ── Keyword stuffing detection ─────────────────────────────────────
STUFFING_KEYWORD_MIN  = 0.70   # keyword_score must exceed this
STUFFING_SEMANTIC_MAX = 0.35   # calibrated semantic vs work chunks below this
STUFFING_PENALTY      = 0.50   # evidence_score multiplier when flagged

# ── Requirement tag thresholds (on req_score) ──────────────────────
TAG_STRONG  = 0.75
TAG_PRESENT = 0.45
TAG_WEAK    = 0.20
# below TAG_WEAK → MISSING

# Semantic-only match is recognised as a match type above this score
SEMANTIC_MATCH_MIN = 0.45

# ── Confidence thresholds ──────────────────────────────────────────
# confidence_value = extraction_quality × mean(evidence_score of matched reqs)
CONFIDENCE_HIGH   = 0.70
CONFIDENCE_MEDIUM = 0.45

# ── Parsing ────────────────────────────────────────────────────────
MIN_CHUNK_CHARS = 8
FUZZY_HEADER_CUTOFF = 80
