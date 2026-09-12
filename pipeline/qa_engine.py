"""
Recruiter Q&A — regex intent detection + templated answers. No LLM.

Supported:
  "why is X above/over/higher than/better than Y"
  "compare X and/with/vs Y"
  "explain X" / "tell me about X" / "why did X rank ..."
  "who is ranked N" / "who is #N" / "rank N"
  "top N candidates"
  "missing skills for X" / "what is X missing"
  "who has SKILL" / "which candidates know SKILL"
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from pipeline.comparator import compare_candidates
from pipeline.explainer import generate_explanation, short_summary
from pipeline.interfaces import CandidateResult

HELP = (
    "I can answer questions like:\n"
    "• Why is Resume_07 above Resume_12?\n"
    "• Compare Aditya Joshi and Meera Pillai\n"
    "• Explain rank 1\n"
    "• Who is ranked #3?\n"
    "• Top 5 candidates\n"
    "• Missing skills for Resume_05\n"
    "• Who has Docker?"
)


def _resolve(name: str, results: list[CandidateResult]) -> CandidateResult | None:
    name = name.strip(" ?.,'\"").lower()
    if not name:
        return None
    m = re.match(r"^(?:rank|#|number|no\.?)\s*(\d+)$", name) or re.match(r"^(\d+)(?:st|nd|rd|th)?$", name)
    if m:
        idx = int(m.group(1))
        return next((r for r in results if r.rank == idx), None)
    choices = {}
    for r in results:
        choices[r.candidate_id.lower()] = r
        if r.display_name:
            choices[r.display_name.lower()] = r
    if name in choices:
        return choices[name]
    hit = process.extractOne(name, list(choices), scorer=fuzz.WRatio, score_cutoff=70)
    return choices[hit[0]] if hit else None


def answer_query(query: str, results: list[CandidateResult]) -> str:
    q = query.strip()
    if not q or not results:
        return HELP
    ql = q.lower()

    m = re.search(r"why\s+(?:is|was|does|did)\s+(.+?)\s+(?:ranked\s+)?(?:above|over|higher than|better than|ahead of|before)\s+(.+?)[?.]?$", ql)
    if m:
        a, b = _resolve(m.group(1), results), _resolve(m.group(2), results)
        if a and b:
            return compare_candidates(a, b)["summary"]

    m = re.search(r"compare\s+(.+?)\s+(?:and|with|vs\.?|versus|to)\s+(.+?)[?.]?$", ql)
    if m:
        a, b = _resolve(m.group(1), results), _resolve(m.group(2), results)
        if a and b:
            return compare_candidates(a, b)["summary"]

    m = re.search(r"top\s+(\d+)", ql)
    if m:
        n = max(1, min(int(m.group(1)), len(results)))
        lines = [f"Top {n} candidates:"]
        for r in results[:n]:
            lines.append(f"{r.rank}. {r.name} — {r.final_score:.1f} "
                         f"(mandatory {r.must_have_met}/{r.must_have_total}, {r.confidence} confidence)")
        return "\n".join(lines)

    m = re.search(r"(?:who|which candidate)\s+(?:is|was)\s+(?:ranked\s+|at\s+)?(?:#|number|no\.?|rank\s*)?\s*(\d+)", ql) \
        or re.search(r"^rank\s*#?\s*(\d+)\??$", ql)
    if m:
        r = _resolve(m.group(1), results)
        return short_summary(r) if r else f"No candidate at rank {m.group(1)}."

    m = re.search(r"(?:missing|lack|lacks|lacking|gaps?)\s+(?:skills?\s+)?(?:for|of|in)?\s*(.+?)[?.]?$", ql) \
        or re.search(r"what\s+(?:is|does)\s+(.+?)\s+(?:missing|lack)", ql)
    if m:
        r = _resolve(m.group(1), results)
        if r:
            missing = [rs.requirement.label for rs in r.req_scores
                       if rs.requirement.weight == "must_have" and rs.tag in ("WEAK", "MISSING")]
            pref = [rs.requirement.label for rs in r.req_scores
                    if rs.requirement.weight == "preferred" and rs.tag in ("WEAK", "MISSING")]
            out = [f"{r.name} (rank #{r.rank}):"]
            out.append("Missing must-haves: " + (", ".join(missing) if missing else "none"))
            if pref:
                out.append("Missing preferred: " + ", ".join(pref))
            return "\n".join(out)

    m = re.search(r"(?:who|which candidates?)\s+(?:has|have|know|knows|used|with)\s+(.+?)[?.]?$", ql)
    if m:
        skill = m.group(1).strip()
        hits = []
        for r in results:
            for rs in r.req_scores:
                if fuzz.ratio(rs.requirement.text, skill) >= 80 and rs.tag in ("STRONG", "PRESENT"):
                    hits.append(f"{r.rank}. {r.name} ({rs.tag}, {rs.match_type})")
                    break
        if hits:
            return f"Candidates demonstrating '{skill}':\n" + "\n".join(hits)
        return f"No candidate shows a strong or present match for '{skill}' (or it is not a JD requirement)."

    m = re.search(r"(?:explain|tell me about|details? (?:for|on|of)|summar(?:y|ise|ize)|why (?:did|is|was))\s+(.+?)(?:\s+rank(?:ed)?.*)?[?.]?$", ql)
    if m:
        r = _resolve(m.group(1), results)
        if r:
            return short_summary(r) + "\n\n" + generate_explanation(r, len(results))

    r = _resolve(ql, results)
    if r:
        return short_summary(r)
    return HELP
