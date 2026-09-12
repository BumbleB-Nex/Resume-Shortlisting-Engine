"""
Shared data structures — the single source of truth for every module.

Member 1 produces Requirement / EvidenceChunk / Resume.
Member 2 produces RequirementScore / CandidateResult.
Member 3 consumes everything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

Weight    = Literal["must_have", "preferred", "responsibility"]
Category  = Literal["skill", "tool", "task", "soft"]
Tag       = Literal["STRONG", "PRESENT", "WEAK", "MISSING"]
MatchType = Literal["EXACT", "ALIAS", "RELATED", "SEMANTIC", "NO_MATCH"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]

_SPECIAL = {
    "javascript": "JavaScript", "typescript": "TypeScript", "node.js": "Node.js",
    "next.js": "Next.js", "mongodb": "MongoDB", "postgresql": "PostgreSQL", "mysql": "MySQL",
    "graphql": "GraphQL", "github": "GitHub", "fastapi": "FastAPI", "nosql": "NoSQL",
    "vs code": "VS Code", "scikit-learn": "scikit-learn", "pytorch": "PyTorch",
    "tensorflow": "TensorFlow", "numpy": "NumPy", "ci/cd": "CI/CD", "html/css": "HTML/CSS",
    "rest api": "REST API", "oop": "OOP", "aws": "AWS", "gcp": "GCP", "sql": "SQL",
    "html": "HTML", "css": "CSS", "json": "JSON", "ui/ux": "UI/UX", "api": "API",
    "sqlite": "SQLite", "php": "PHP", "jwt": "JWT", "c++": "C++", "c#": "C#",
    "nosql databases": "NoSQL Databases", "websockets": "WebSockets", "redux": "Redux",
}


def pretty(term: str) -> str:
    if term in _SPECIAL:
        return _SPECIAL[term]
    return " ".join(_SPECIAL.get(w, w[:1].upper() + w[1:]) for w in term.split(" "))


@dataclass
class Requirement:
    text: str                      # normalized, atomic, e.g. "python"
    weight: Weight                 # must_have | preferred | responsibility
    category: Category             # skill | tool | task | soft
    importance: float              # 1.0 / 0.6 / 0.4
    original_text: str = ""        # raw JD line it came from
    alternatives: list[str] = field(default_factory=list)   # "sql" ← ["postgresql", "mysql"]

    @property
    def all_terms(self) -> list[str]:
        return [self.text, *self.alternatives]

    @property
    def label(self) -> str:
        if self.category == "task":
            return self.text[0].upper() + self.text[1:]
        base = pretty(self.text)
        if self.alternatives:
            base += " (" + " / ".join(pretty(a) for a in self.alternatives) + ")"
        return base


@dataclass
class EvidenceChunk:
    text: str                      # the sentence / bullet (original case)
    section: str                   # experience | projects | skills | education |
                                   # certifications | summary | other
    section_weight: float          # from config.SECTION_WEIGHT
    has_action_verb: bool
    is_quantified: bool
    recency_weight: float          # 1.0 most recent → 0.5 oldest, 0.8 unknown


@dataclass
class Resume:
    candidate_id: str              # filename stem, e.g. "Resume_07"
    full_text: str                 # cleaned, lowercased (BM25 corpus)
    chunks: list[EvidenceChunk] = field(default_factory=list)
    extraction_quality: float = 1.0   # 1.0 clean, 0.5 suspicious extraction
    display_name: str = ""         # best-effort name from first line

    @property
    def name(self) -> str:
        return self.display_name or self.candidate_id


@dataclass
class RequirementScore:
    requirement: Requirement
    keyword_score: float           # 0–1  (BM25 + ontology)
    semantic_score: float          # 0–1  (calibrated best-chunk similarity)
    evidence_score: float          # 0–1  (after stuffing penalty)
    req_score: float               # weighted combination 0–1
    tag: Tag
    match_type: MatchType
    best_chunk: Optional[EvidenceChunk] = None
    best_chunk_similarity: float = 0.0    # raw cosine of the evidence chunk
    is_stuffed: bool = False


@dataclass
class CandidateResult:
    candidate_id: str
    rank: int
    final_score: float             # 0–100
    base_score: float              # 0–1 before mandatory multiplier
    mandatory_ratio: float
    must_have_met: int
    must_have_total: int
    keyword_agg: float
    semantic_agg: float
    evidence_agg: float
    confidence: Confidence
    req_scores: list[RequirementScore] = field(default_factory=list)
    stuffing_flags: list[str] = field(default_factory=list)
    matched_required: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    display_name: str = ""

    @property
    def name(self) -> str:
        return self.display_name or self.candidate_id

    def score_for(self, req_text: str) -> Optional[RequirementScore]:
        for rs in self.req_scores:
            if rs.requirement.text == req_text:
                return rs
        return None
