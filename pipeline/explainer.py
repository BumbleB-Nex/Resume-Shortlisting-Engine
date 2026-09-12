"""
Explanation engine — deterministic, template-based, zero LLM calls.
Every sentence is filled from stored RequirementScore data.
"""
from __future__ import annotations

from pipeline.interfaces import CandidateResult, RequirementScore, pretty

_ICON = {"STRONG": "✓", "PRESENT": "~", "WEAK": "≈", "MISSING": "✗"}
_WEIGHT_TITLE = {
    "must_have": "MUST-HAVE REQUIREMENTS",
    "preferred": "PREFERRED REQUIREMENTS",
    "responsibility": "RESPONSIBILITIES",
}


def snippet(rs: RequirementScore, limit: int = 150) -> str:
    if rs.best_chunk is None:
        return ""
    t = rs.best_chunk.text.strip()
    return t if len(t) <= limit else t[:limit].rstrip() + "…"


def requirement_line(rs: RequirementScore) -> list[str]:
    req = rs.requirement
    icon = _ICON[rs.tag]
    lines = [f"  {icon} {req.label}  [{rs.tag} — {rs.req_score:.2f}]  [{rs.match_type}]"]
    if rs.tag == "MISSING":
        if rs.best_chunk is not None and rs.best_chunk_similarity > 0:
            lines.append(f"      Not found. Closest text ({rs.best_chunk.section}): \"{snippet(rs, 80)}\"")
        else:
            lines.append("      Required but not found in resume.")
    elif rs.tag == "WEAK":
        lines.append(f"      Partial evidence ({rs.best_chunk.section if rs.best_chunk else '—'}): \"{snippet(rs, 100)}\"")
        if rs.match_type == "SEMANTIC":
            lines.append("      ⚠ Weak evidence — semantic similarity only, no explicit mention.")
    else:
        if rs.best_chunk is not None:
            lines.append(f"      Evidence ({rs.best_chunk.section.title()}): \"{snippet(rs)}\"")
            lines.append(f"      keyword {rs.keyword_score:.2f} · semantic {rs.semantic_score:.2f} · "
                         f"evidence {rs.evidence_score:.2f} · similarity {rs.best_chunk_similarity:.2f}")
    if rs.is_stuffed:
        lines.append("      ⚠ Listed as a keyword but not demonstrated in projects/experience.")
    return lines


def generate_explanation(result: CandidateResult, total: int | None = None) -> str:
    bar = "═" * 56
    total_txt = f" of {total}" if total else ""
    out = [
        bar,
        f"RANK #{result.rank}{total_txt} — {result.name}",
        f"FINAL SCORE: {result.final_score:.1f}      CONFIDENCE: {result.confidence}",
        bar,
    ]
    for weight in ("must_have", "preferred", "responsibility"):
        group = [rs for rs in result.req_scores if rs.requirement.weight == weight]
        if not group:
            continue
        out += ["", _WEIGHT_TITLE[weight], "─" * len(_WEIGHT_TITLE[weight])]
        for rs in sorted(group, key=lambda r: -r.req_score):
            out += requirement_line(rs)
    out += [
        "",
        bar,
        "SCORE BREAKDOWN",
        f"  Mandatory coverage : {result.must_have_met}/{result.must_have_total} "
        f"({result.mandatory_ratio * 100:.0f}%)",
        f"  Semantic score     : {result.semantic_agg * 100:.1f}",
        f"  Keyword score      : {result.keyword_agg * 100:.1f}",
        f"  Evidence quality   : {result.evidence_agg * 100:.1f}",
        f"  Base score         : {result.base_score * 100:.1f}",
        f"  Final score        : {result.final_score:.1f}  "
        f"(= base × mandatory coverage)",
        bar,
    ]
    return "\n".join(out)


def short_summary(result: CandidateResult) -> str:
    """One-paragraph plain-English summary used on cards and in Q&A."""
    strong = [rs.requirement.label for rs in result.req_scores
              if rs.tag == "STRONG" and rs.requirement.weight != "responsibility"]
    present = [rs.requirement.label for rs in result.req_scores
               if rs.tag == "PRESENT" and rs.requirement.weight != "responsibility"]
    missing = [rs.requirement.label for rs in result.req_scores
               if rs.requirement.weight == "must_have" and rs.tag in ("WEAK", "MISSING")]
    parts = [f"{result.name} is ranked #{result.rank} with a score of {result.final_score:.1f}."]
    if strong:
        parts.append("Strong, evidence-backed matches: " + ", ".join(strong[:6]) + ".")
    if present:
        parts.append("Also present: " + ", ".join(present[:6]) + ".")
    if missing:
        parts.append("Missing must-have requirements: " + ", ".join(missing) + ".")
    else:
        parts.append("All must-have requirements are covered.")
    if result.stuffing_flags:
        parts.append("Listed without supporting project evidence: "
                     + ", ".join(pretty(f) for f in result.stuffing_flags) + ".")
    parts.append(f"Semantic relevance {result.semantic_agg * 100:.0f}, keyword relevance "
                 f"{result.keyword_agg * 100:.0f}, evidence quality {result.evidence_agg * 100:.0f}; "
                 f"confidence {result.confidence}.")
    return " ".join(parts)
