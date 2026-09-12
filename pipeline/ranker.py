"""Ranking — max-heap ordering of pre-scored candidates (scales to 100+)."""
from __future__ import annotations

import heapq

from pipeline.interfaces import CandidateResult


def rank_candidates(scored: list[CandidateResult]) -> list[CandidateResult]:
    """
    Order candidates by final_score (desc) with deterministic tie-breaks:
    mandatory coverage, then evidence quality, then candidate id.
    heapq.nlargest gives O(n log k) — comfortably fast for 100+ resumes.
    """
    ranked = heapq.nlargest(
        len(scored),
        scored,
        key=lambda c: (round(c.final_score, 4), c.mandatory_ratio, c.evidence_agg, _neg_id(c.candidate_id)),
    )
    for i, cand in enumerate(ranked, start=1):
        cand.rank = i
    return ranked


def _neg_id(cid: str) -> tuple:
    # stable alphabetical tie-break inside nlargest (which wants "larger is better")
    return tuple(-ord(ch) for ch in cid)
