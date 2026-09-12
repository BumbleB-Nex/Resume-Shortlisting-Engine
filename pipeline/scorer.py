"""
Scorer — combines the keyword, semantic and evidence arms into
requirement-level and candidate-level scores.

Two phases, deliberately separated:

  build_match_state()  expensive: BM25 + embeddings + evidence selection.
                       Produces weight-independent RawMatch cells.
  score_state()        cheap: applies WEIGHTS, tags, mandatory multiplier,
                       confidence and ranking. The What-if Simulator only
                       reruns this phase.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from config import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    MANDATORY_FLOOR,
    REQ_WEIGHT,
    SEMANTIC_MATCH_MIN,
    TAG_PRESENT,
    TAG_STRONG,
    TAG_WEAK,
    WEIGHTS,
)
from pipeline.evidence import (
    apply_stuffing_penalty,
    evidence_score,
    is_keyword_stuffed,
    mentioned_in_work,
    select_evidence,
)
from pipeline.interfaces import (
    CandidateResult,
    EvidenceChunk,
    Requirement,
    RequirementScore,
    Resume,
)
from pipeline.keyword import KeywordMatcher
from pipeline.ontology import SkillOntology, get_ontology
from pipeline.ranker import rank_candidates
from pipeline.semantic import SemanticMatcher


# ── weight-independent cell ────────────────────────────────────────
@dataclass
class RawMatch:
    requirement: Requirement
    keyword_score: float
    bm25_norm: float
    ontology_score: float
    keyword_match_type: str          # EXACT | ALIAS | RELATED | NO_MATCH
    semantic_score: float            # calibrated 0..1
    best_chunk: EvidenceChunk | None
    best_chunk_similarity: float     # raw cosine
    chunk_relevance: float
    evidence_raw: float              # before stuffing penalty
    is_stuffed: bool

    @property
    def evidence_score(self) -> float:
        return apply_stuffing_penalty(self.evidence_raw, self.is_stuffed)


@dataclass
class MatchState:
    requirements: list[Requirement]
    resumes: list[Resume]
    cells: dict[str, list[RawMatch]] = field(default_factory=dict)   # candidate_id → per-requirement

    def resume(self, candidate_id: str) -> Resume:
        return next(r for r in self.resumes if r.candidate_id == candidate_id)


# ── phase 1: expensive matching ────────────────────────────────────
def build_match_state(
    requirements: list[Requirement],
    resumes: list[Resume],
    ontology: SkillOntology | None = None,
) -> MatchState:
    ontology = ontology or get_ontology()
    kw = KeywordMatcher(resumes, ontology)
    sem = SemanticMatcher(resumes)
    state = MatchState(requirements=requirements, resumes=resumes)

    for resume in resumes:
        cells: list[RawMatch] = []
        chunk_mentions = [ontology.find_forms(c.text) for c in resume.chunks]
        for req in requirements:
            keyword_score, kw_type, bm25_norm, ont_score = kw.score(req, resume)
            semantic_score, sims = sem.score(req, resume.candidate_id)
            chunk, raw_sim, relevance, _ = select_evidence(req, resume, sims, ontology, chunk_mentions)
            ev_raw = evidence_score(chunk, relevance)
            work_sim = sem.work_similarity(req, resume.candidate_id, sims)
            stuffed = req.category in ("skill", "tool") and is_keyword_stuffed(
                keyword_score, chunk, work_sim,
                work_mentioned=mentioned_in_work(req, resume, chunk_mentions, ontology))
            cells.append(RawMatch(
                requirement=req,
                keyword_score=keyword_score,
                bm25_norm=bm25_norm,
                ontology_score=ont_score,
                keyword_match_type=kw_type,
                semantic_score=semantic_score,
                best_chunk=chunk,
                best_chunk_similarity=raw_sim,
                chunk_relevance=relevance,
                evidence_raw=ev_raw,
                is_stuffed=stuffed,
            ))
        state.cells[resume.candidate_id] = cells
    return state


# ── phase 2: cheap scoring / ranking ───────────────────────────────
def _coverage_credit(req_score: float) -> float:
    """1.0 at/above PRESENT, 0.0 at/below WEAK's lower bound, linear between."""
    if req_score >= TAG_PRESENT:
        return 1.0
    if req_score <= TAG_WEAK:
        return 0.0
    return (req_score - TAG_WEAK) / (TAG_PRESENT - TAG_WEAK)


def _mandatory_multiplier(ratio: float) -> float:
    """Mandatory coverage as a multiplier with a small floor so zero-coverage
    candidates still order by relevance instead of all tying at 0."""
    return MANDATORY_FLOOR + (1.0 - MANDATORY_FLOOR) * ratio


def _tag(req_score: float) -> str:
    if req_score >= TAG_STRONG:
        return "STRONG"
    if req_score >= TAG_PRESENT:
        return "PRESENT"
    if req_score >= TAG_WEAK:
        return "WEAK"
    return "MISSING"


def _match_type(cell: RawMatch) -> str:
    if cell.keyword_match_type in ("EXACT", "ALIAS", "RELATED"):
        return cell.keyword_match_type
    if cell.semantic_score >= SEMANTIC_MATCH_MIN:
        return "SEMANTIC"
    return "NO_MATCH"


def normalize_weights(weights: dict | None) -> dict[str, float]:
    w = dict(WEIGHTS if weights is None else weights)
    total = sum(max(0.0, float(v)) for v in w.values()) or 1.0
    return {k: max(0.0, float(v)) / total for k, v in w.items()}


def score_state(state: MatchState, weights: dict | None = None) -> list[CandidateResult]:
    w = normalize_weights(weights)
    results: list[CandidateResult] = []

    for resume in state.resumes:
        cells = state.cells[resume.candidate_id]
        req_scores: list[RequirementScore] = []
        for cell in cells:
            ev = cell.evidence_score
            req_score = (w["keyword"] * cell.keyword_score
                         + w["semantic"] * cell.semantic_score
                         + w["evidence"] * ev)
            req_score = float(min(1.0, req_score))
            req_scores.append(RequirementScore(
                requirement=cell.requirement,
                keyword_score=round(cell.keyword_score, 4),
                semantic_score=round(cell.semantic_score, 4),
                evidence_score=round(ev, 4),
                req_score=round(req_score, 4),
                tag=_tag(req_score),
                match_type=_match_type(cell),
                best_chunk=cell.best_chunk,
                best_chunk_similarity=round(cell.best_chunk_similarity, 4),
                is_stuffed=cell.is_stuffed,
            ))

        total_w = sum(REQ_WEIGHT[rs.requirement.weight] for rs in req_scores) or 1.0
        agg = lambda attr: sum(REQ_WEIGHT[rs.requirement.weight] * getattr(rs, attr) for rs in req_scores) / total_w  # noqa: E731
        keyword_agg, semantic_agg, evidence_agg = agg("keyword_score"), agg("semantic_score"), agg("evidence_score")
        base = w["keyword"] * keyword_agg + w["semantic"] * semantic_agg + w["evidence"] * evidence_agg

        must = [rs for rs in req_scores if rs.requirement.weight == "must_have"]
        met = [rs for rs in must if rs.tag in ("STRONG", "PRESENT")]
        # smooth coverage: PRESENT/STRONG → 1, MISSING → 0, WEAK → linear in between
        mandatory_ratio = (sum(_coverage_credit(rs.req_score) for rs in must) / len(must)) if must else 1.0
        final = base * _mandatory_multiplier(mandatory_ratio) * 100

        matched = [rs for rs in req_scores if rs.tag in ("STRONG", "PRESENT")]
        conf_val = resume.extraction_quality * (mean(rs.evidence_score for rs in matched) if matched else 0.0)
        confidence = "HIGH" if conf_val >= CONFIDENCE_HIGH else "MEDIUM" if conf_val >= CONFIDENCE_MEDIUM else "LOW"

        results.append(CandidateResult(
            candidate_id=resume.candidate_id,
            rank=0,
            final_score=round(final, 2),
            base_score=round(base, 4),
            mandatory_ratio=round(mandatory_ratio, 4),
            must_have_met=len(met),
            must_have_total=len(must),
            keyword_agg=round(keyword_agg, 4),
            semantic_agg=round(semantic_agg, 4),
            evidence_agg=round(evidence_agg, 4),
            confidence=confidence,
            req_scores=req_scores,
            stuffing_flags=[rs.requirement.text for rs in req_scores if rs.is_stuffed],
            matched_required=[rs.requirement.text for rs in met],
            missing_required=[rs.requirement.text for rs in must if rs.tag in ("WEAK", "MISSING")],
            display_name=resume.display_name,
        ))
    return rank_candidates(results)


# ── public entry points ────────────────────────────────────────────
def run_pipeline(
    requirements: list[Requirement],
    resumes: list[Resume],
    ontology: SkillOntology | None = None,
    weights: dict | None = None,
) -> list[CandidateResult]:
    state = build_match_state(requirements, resumes, ontology)
    return score_state(state, weights)


def score_with_weights(state: MatchState, weights: dict) -> list[CandidateResult]:
    """Instant re-ranking for the What-if Simulator (no re-embedding)."""
    return score_state(state, weights)
