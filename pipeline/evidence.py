"""
Evidence arm — how strongly does the resume *demonstrate* a requirement?

  quality(chunk)  = section_weight × verb_factor × quant_factor × recency
  evidence_score  = quality(best_chunk) × relevance(best_chunk)

The evidence chunk is the strongest-quality chunk that actually mentions
the skill (or an alias / related tech). If nothing mentions it we fall back
to the most semantically similar chunk, weighted by its similarity.

Keyword stuffing: a skill that scores high on keywords but whose only
evidence lives in the Skills/Summary section — with nothing semantically
close in Projects/Experience — is flagged and its evidence halved.
"""
from __future__ import annotations

import numpy as np

from config import (
    EVIDENCE_NO_VERB,
    EVIDENCE_QUANT_BONUS,
    EVIDENCE_VERB_BONUS,
    STUFFING_KEYWORD_MIN,
    STUFFING_PENALTY,
    STUFFING_SEMANTIC_MAX,
    WORK_SECTIONS,
)
from pipeline.interfaces import EvidenceChunk, Requirement, Resume
from pipeline.ontology import SkillOntology
from pipeline.semantic import calibrate


def chunk_quality(chunk: EvidenceChunk) -> float:
    q = chunk.section_weight
    q *= EVIDENCE_VERB_BONUS if chunk.has_action_verb else EVIDENCE_NO_VERB
    q *= EVIDENCE_QUANT_BONUS if chunk.is_quantified else 1.0
    q *= chunk.recency_weight
    return float(min(1.0, q))


def select_evidence(
    requirement: Requirement,
    resume: Resume,
    sims: np.ndarray,
    ontology: SkillOntology,
    chunk_mentions: list[dict[str, set[str]]] | None = None,
) -> tuple[EvidenceChunk | None, float, float, str]:
    """
    Pick the evidence chunk for a requirement.
    `chunk_mentions[i]` is `ontology.find_forms(chunk_i.text)` (precomputed once
    per resume for speed). Returns (chunk, raw_similarity, relevance, chunk_match_type).
    """
    if not resume.chunks:
        return None, 0.0, 0.0, "NO_MATCH"
    sims = sims if sims.size == len(resume.chunks) else np.zeros(len(resume.chunks))
    if chunk_mentions is None:
        chunk_mentions = [ontology.find_forms(c.text) for c in resume.chunks]

    best_idx, best_key, best_rel, best_type = -1, -1.0, 0.0, "NO_MATCH"
    if requirement.category != "task":
        for i, chunk in enumerate(resume.chunks):
            rel, mtype = ontology.match_from_mentions(requirement.all_terms, chunk_mentions[i])
            if rel <= 0:
                continue
            key = rel * chunk_quality(chunk) + 0.05 * float(sims[i])
            if key > best_key:
                best_idx, best_key, best_rel, best_type = i, key, rel, mtype
    if best_idx >= 0:
        return resume.chunks[best_idx], float(sims[best_idx]), best_rel, best_type

    i = int(np.argmax(sims))
    return resume.chunks[i], float(sims[i]), float(calibrate(sims[i])), "SEMANTIC"


def evidence_score(chunk: EvidenceChunk | None, relevance: float) -> float:
    if chunk is None:
        return 0.0
    return float(min(1.0, chunk_quality(chunk) * relevance))


def mentioned_in_work(
    requirement: Requirement,
    resume: Resume,
    chunk_mentions: list[dict[str, set[str]]],
    ontology: SkillOntology,
) -> bool:
    """True if the skill (or a related skill) appears in any projects/experience chunk."""
    for chunk, mentions in zip(resume.chunks, chunk_mentions):
        if chunk.section in WORK_SECTIONS and ontology.match_from_mentions(requirement.all_terms, mentions)[0] > 0:
            return True
    return False


def is_keyword_stuffed(
    keyword_score: float,
    chunk: EvidenceChunk | None,
    work_similarity: float,
    work_mentioned: bool = False,
) -> bool:
    """
    Flag when the skill is lexically present but never demonstrated in work.
      1. keyword_score  > STUFFING_KEYWORD_MIN
      2. evidence chunk is NOT from projects/experience
      3. neither the skill nor a related one is mentioned in projects/experience
      4. best calibrated similarity vs projects/experience < STUFFING_SEMANTIC_MAX
    """
    if keyword_score <= STUFFING_KEYWORD_MIN:
        return False
    if chunk is None:
        return True
    if chunk.section in WORK_SECTIONS or work_mentioned:
        return False
    return work_similarity < STUFFING_SEMANTIC_MAX


def apply_stuffing_penalty(score: float, stuffed: bool) -> float:
    return score * STUFFING_PENALTY if stuffed else score
