"""
Semantic arm — local sentence-transformer retrieval of resume evidence.

For each JD requirement we embed the requirement (with its JD context) and
compare it against every evidence chunk of a resume:

    semantic_score = 0.7 × best_chunk_similarity
                   + 0.3 × mean(top-K chunk similarities)

Raw cosine values are linearly calibrated into 0..1 (BGE models keep even
unrelated pairs around 0.5). Chunk embeddings are cached to disk so 100+
resumes stay fast and the model is loaded exactly once.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from config import (
    CACHE_DIR,
    EMBEDDING_MODEL,
    EMBEDDING_QUERY_PREFIX,
    SEMANTIC_BEST_SHARE,
    SEMANTIC_CAL_MAX,
    SEMANTIC_CAL_MIN,
    SEMANTIC_SUPPORT_SHARE,
    SEMANTIC_SUPPORT_TOPK,
)
from pipeline.interfaces import Requirement, Resume

_MODEL = None


def get_model():
    """Load the sentence-transformer exactly once per process."""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(EMBEDDING_MODEL)
    return _MODEL


def _query_text(term: str, category: str) -> str:
    """Give bare skill names a little context so the query embedding is meaningful."""
    if category == "task":
        return term
    if category == "soft":
        return f"{term} skills"
    return f"hands-on experience with {term}"


def calibrate(cos: np.ndarray | float) -> np.ndarray | float:
    """Map raw cosine similarity into a 0..1 semantic score."""
    span = max(1e-6, SEMANTIC_CAL_MAX - SEMANTIC_CAL_MIN)
    return np.clip((cos - SEMANTIC_CAL_MIN) / span, 0.0, 1.0)


class SemanticMatcher:
    def __init__(self, resumes: list[Resume], cache_dir: Path = CACHE_DIR):
        self._model = get_model()
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._chunk_embeddings: dict[str, np.ndarray] = {}
        self._chunks = {r.candidate_id: r.chunks for r in resumes}
        self._req_cache: dict[str, np.ndarray] = {}
        for resume in resumes:
            self._chunk_embeddings[resume.candidate_id] = self._load_or_embed(resume)

    # ------------------------------------------------------------------
    def _load_or_embed(self, resume: Resume) -> np.ndarray:
        texts = [c.text for c in resume.chunks]
        if not texts:
            return np.zeros((0, self._model.get_sentence_embedding_dimension()), dtype=np.float32)
        digest = hashlib.md5(("\n".join(texts) + EMBEDDING_MODEL).encode("utf-8")).hexdigest()[:16]
        cache_file = self._cache_dir / f"{resume.candidate_id}_{digest}.npy"
        if cache_file.exists():
            embs = np.load(str(cache_file))
            if embs.shape[0] == len(texts):
                return embs
        embs = self._model.encode(texts, batch_size=64, normalize_embeddings=True,
                                  show_progress_bar=False).astype(np.float32)
        np.save(str(cache_file), embs)
        return embs

    def embed_requirement(self, requirement: Requirement) -> np.ndarray:
        """
        Requirement embedding = the atomic text; for tasks / long phrases we
        also embed the original JD sentence and keep whichever is closer to
        each chunk (done in `similarities`). Cached per requirement text.
        """
        key = "|".join(requirement.all_terms) + "||" + requirement.original_text
        if key not in self._req_cache:
            queries = [EMBEDDING_QUERY_PREFIX + _query_text(t, requirement.category)
                       for t in requirement.all_terms]
            orig = requirement.original_text.strip()
            if orig and orig.lower() != requirement.text and requirement.category == "task":
                queries.append(EMBEDDING_QUERY_PREFIX + orig)
            self._req_cache[key] = self._model.encode(
                queries, normalize_embeddings=True, show_progress_bar=False).astype(np.float32)
        return self._req_cache[key]

    def similarities(self, requirement: Requirement, candidate_id: str) -> np.ndarray:
        """Raw cosine similarity of the requirement against every chunk."""
        chunk_embs = self._chunk_embeddings[candidate_id]
        if chunk_embs.shape[0] == 0:
            return np.zeros(0, dtype=np.float32)
        q = self.embed_requirement(requirement)          # (n_queries, dim), normalised
        sims = chunk_embs @ q.T                           # (n_chunks, n_queries)
        return sims.max(axis=1)

    # ------------------------------------------------------------------
    def score(self, requirement: Requirement, candidate_id: str) -> tuple[float, np.ndarray]:
        """
        Returns (semantic_score, raw_sims).
        semantic_score blends the best chunk with the mean of the top-K chunks.
        """
        sims = self.similarities(requirement, candidate_id)
        if sims.size == 0:
            return 0.0, sims
        cal = calibrate(sims)
        top = np.sort(cal)[::-1][:SEMANTIC_SUPPORT_TOPK]
        score = SEMANTIC_BEST_SHARE * float(top[0]) + SEMANTIC_SUPPORT_SHARE * float(top.mean())
        return float(min(1.0, score)), sims

    def work_similarity(self, requirement: Requirement, candidate_id: str, sims: np.ndarray) -> float:
        """Calibrated best similarity restricted to projects/experience chunks."""
        chunks = self._chunks[candidate_id]
        idx = [i for i, c in enumerate(chunks) if c.section in ("projects", "experience")]
        if not idx or sims.size == 0:
            return 0.0
        return float(calibrate(sims[idx]).max())

    def invalidate_cache(self, candidate_id: str) -> None:
        for f in self._cache_dir.glob(f"{candidate_id}_*.npy"):
            f.unlink(missing_ok=True)
