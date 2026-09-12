"""
Keyword arm — BM25 lexical relevance + ontology skill coverage.

keyword_score(R, C) = 0.5 × BM25_normalized(R, C) + 0.5 × ontology_coverage(R, C)

BM25 is built over the whole resume corpus (proper IDF), queried with the
requirement text plus all its known alias forms, and normalised per
requirement by the maximum score across candidates.
"""
from __future__ import annotations

import re

import numpy as np
from rank_bm25 import BM25Okapi

from config import BM25_B, BM25_K1, KEYWORD_BM25_SHARE, KEYWORD_ONTOLOGY_SHARE
from pipeline.interfaces import Requirement, Resume
from pipeline.ontology import SkillOntology, get_ontology

_TOKEN_RE = re.compile(r"[a-z0-9+#]+(?:\.[a-z0-9]+)*")
_TASK_STOPWORDS = {
    "and", "or", "the", "a", "an", "of", "to", "in", "with", "for", "on", "by", "at", "as",
    "is", "are", "be", "from", "that", "this", "using", "into", "them", "their", "our", "your",
    "existing", "modern", "efficient", "good", "strong", "basic", "working", "well",
}


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class KeywordMatcher:
    def __init__(self, resumes: list[Resume], ontology: SkillOntology | None = None):
        self._ontology = ontology or get_ontology()
        self._ids = [r.candidate_id for r in resumes]
        self._index_of = {cid: i for i, cid in enumerate(self._ids)}
        self._resumes = {r.candidate_id: r for r in resumes}
        corpus = [tokenize(r.full_text) or ["_empty_"] for r in resumes]
        self._bm25 = BM25Okapi(corpus, k1=BM25_K1, b=BM25_B)
        self._bm25_cache: dict[str, np.ndarray] = {}
        # canonical skill → surface forms, once per resume
        self._mentions = {r.candidate_id: self._ontology.find_forms(r.full_text) for r in resumes}

    def mentions(self, candidate_id: str) -> dict[str, set[str]]:
        return self._mentions[candidate_id]

    # ------------------------------------------------------------------
    def _query_tokens(self, requirement: Requirement) -> list[str]:
        tokens: list[str] = []
        for term in requirement.all_terms:
            for form in self._ontology.get_all_forms(term):
                tokens += tokenize(form)
        if requirement.category == "task":
            tokens += [t for t in tokenize(requirement.text) if t not in _TASK_STOPWORDS]
        return list(dict.fromkeys(tokens)) or ["_none_"]

    def bm25_normalized(self, requirement: Requirement) -> np.ndarray:
        """Normalised BM25 vector (one entry per candidate) for a requirement."""
        key = requirement.text
        if key not in self._bm25_cache:
            scores = np.asarray(self._bm25.get_scores(self._query_tokens(requirement)), dtype=float)
            scores = np.clip(scores, 0.0, None)
            mx = scores.max() if scores.size else 0.0
            self._bm25_cache[key] = scores / mx if mx > 0 else scores
        return self._bm25_cache[key]

    def raw_bm25(self, requirement: Requirement, candidate_id: str) -> float:
        scores = self._bm25.get_scores(self._query_tokens(requirement))
        return float(scores[self._index_of[candidate_id]])

    # ------------------------------------------------------------------
    def score(self, requirement: Requirement, resume: Resume) -> tuple[float, str, float, float]:
        """
        Returns (keyword_score, match_type, bm25_norm, ontology_score).
        match_type ∈ EXACT | ALIAS | RELATED | NO_MATCH  (SEMANTIC decided later).
        """
        bm25_norm = float(self.bm25_normalized(requirement)[self._index_of[resume.candidate_id]])
        ont_score, match_type = self._ontology.match_from_mentions(
            requirement.all_terms, self._mentions[resume.candidate_id])
        if requirement.category == "task":
            # long task phrases rarely appear verbatim — rely on BM25 for the lexical arm
            keyword_score = bm25_norm if ont_score == 0 else max(bm25_norm, ont_score)
        else:
            keyword_score = KEYWORD_BM25_SHARE * bm25_norm + KEYWORD_ONTOLOGY_SHARE * ont_score
        return float(min(1.0, keyword_score)), match_type, bm25_norm, float(ont_score)
