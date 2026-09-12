"""Comparison engine — "Why is A ranked above B?" from stored scoring data."""
from __future__ import annotations

from pipeline.interfaces import CandidateResult, pretty

_DIFF_THRESHOLD = 0.15


def compare_candidates(a: CandidateResult, b: CandidateResult) -> dict:
    table = []
    for a_rs in a.req_scores:
        b_rs = b.score_for(a_rs.requirement.text)
        if b_rs is None:
            continue
        table.append({
            "requirement": a_rs.requirement.label,
            "weight": a_rs.requirement.weight,
            "a_tag": a_rs.tag, "b_tag": b_rs.tag,
            "a_score": a_rs.req_score, "b_score": b_rs.req_score,
            "a_match": a_rs.match_type, "b_match": b_rs.match_type,
            "a_stuffed": a_rs.is_stuffed, "b_stuffed": b_rs.is_stuffed,
            "diff": round(a_rs.req_score - b_rs.req_score, 3),
        })

    winner, loser = (a, b) if a.rank < b.rank else (b, a)
    reasons: list[str] = []

    mandatory_gap = (winner.must_have_met != loser.must_have_met
                     or abs(winner.mandatory_ratio - loser.mandatory_ratio) >= 0.05)
    if mandatory_gap:
        reasons.append(
            f"{winner.name} covers {winner.must_have_met}/{winner.must_have_total} mandatory "
            f"requirements ({winner.mandatory_ratio:.0%} coverage) vs "
            f"{loser.must_have_met}/{loser.must_have_total} ({loser.mandatory_ratio:.0%}) for {loser.name}. "
            f"Mandatory coverage multiplies the base score, so this is the primary factor.")
    else:
        reasons.append(
            f"Both cover {winner.must_have_met}/{winner.must_have_total} mandatory requirements, "
            f"so the difference comes from the strength of evidence below.")

    for comp, label in (("semantic_agg", "semantic relevance"),
                        ("keyword_agg", "keyword relevance"),
                        ("evidence_agg", "evidence quality")):
        d = getattr(winner, comp) - getattr(loser, comp)
        if abs(d) >= 0.08:
            who, other = (winner, loser) if d > 0 else (loser, winner)
            reasons.append(f"{who.name} has higher {label} "
                           f"({getattr(who, comp) * 100:.0f} vs {getattr(other, comp) * 100:.0f}).")

    for row in table:
        d = row["diff"] if winner is a else -row["diff"]
        if row["weight"] == "responsibility":
            continue
        if d >= _DIFF_THRESHOLD:
            reasons.append(f"{winner.name} shows stronger evidence for '{row['requirement']}' "
                           f"(+{d:.2f}).")
        elif d <= -_DIFF_THRESHOLD:
            reasons.append(f"{loser.name} is actually stronger on '{row['requirement']}' "
                           f"(+{-d:.2f}), but this does not outweigh the factors above.")

    for flag in winner.stuffing_flags:
        reasons.append(f"⚠ {winner.name} lists '{pretty(flag)}' without project/experience evidence.")
    for flag in loser.stuffing_flags:
        reasons.append(f"⚠ {loser.name} lists '{pretty(flag)}' without project/experience evidence, "
                       f"which reduced its evidence score.")

    only_w = [r["requirement"] for r in table
              if (r["a_tag"] if winner is a else r["b_tag"]) in ("STRONG", "PRESENT")
              and (r["b_tag"] if winner is a else r["a_tag"]) in ("WEAK", "MISSING")]
    only_l = [r["requirement"] for r in table
              if (r["b_tag"] if winner is a else r["a_tag"]) in ("STRONG", "PRESENT")
              and (r["a_tag"] if winner is a else r["b_tag"]) in ("WEAK", "MISSING")]
    if only_w:
        reasons.append(f"Only {winner.name} demonstrates: {', '.join(only_w[:6])}.")
    if only_l:
        reasons.append(f"Only {loser.name} demonstrates: {', '.join(only_l[:6])}.")

    if mandatory_gap and winner.mandatory_ratio > loser.mandatory_ratio:
        top_reason = "better mandatory-requirement coverage"
    elif winner.semantic_agg - loser.semantic_agg >= 0.05:
        top_reason = "stronger semantic relevance to the role"
    elif winner.evidence_agg - loser.evidence_agg >= 0.05:
        top_reason = "stronger project/experience evidence"
    else:
        top_reason = "a higher overall weighted match score"

    summary = "\n".join([
        f"{winner.name} (#{winner.rank}, {winner.final_score:.1f}) ranks above "
        f"{loser.name} (#{loser.rank}, {loser.final_score:.1f}).",
        "",
        *[f"• {r}" for r in reasons],
        "",
        f"Conclusion: {winner.name} ranks higher due to {top_reason}.",
    ])
    return {"table": table, "summary": summary, "winner": winner.candidate_id, "reasons": reasons}
