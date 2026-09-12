"""Reusable UI pieces: chips, stat cards, evidence lists, candidate cards, empty state."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from pipeline.explainer import generate_explanation, short_summary, snippet
from pipeline.interfaces import CandidateResult, RequirementScore, pretty
from ui.charts import breakdown_chart
from ui.theme import TAG_COLOR

_WEIGHT_ORDER = {"must_have": 0, "preferred": 1, "responsibility": 2}


# ── small html helpers ─────────────────────────────────────────────
def esc(s: str) -> str:
    return html.escape(str(s), quote=False)


def chips(items: list[str], kind: str = "grey", empty: str = "—") -> str:
    if not items:
        return f'<span class="chip chip-grey">{esc(empty)}</span>'
    return "".join(f'<span class="chip chip-{kind}">{esc(x)}</span>' for x in items)


def kv(pairs: list[tuple[str, str]]) -> str:
    return "".join(f'<div class="kv"><span>{esc(k)}</span><span>{esc(v)}</span></div>' for k, v in pairs)


def eyebrow(text: str) -> None:
    st.markdown(f'<p class="eyebrow">{esc(text)}</p>', unsafe_allow_html=True)


def stat_card(label: str, value: str, sub: str = "", unit: str = "") -> None:
    with st.container(border=True):
        st.markdown(f'<p class="eyebrow">{esc(label)}</p>'
                    f'<div class="big-num">{esc(value)}<small>{esc(unit)}</small></div>', unsafe_allow_html=True)
        if sub:
            st.caption(sub)


# ── derived candidate facts ────────────────────────────────────────
def must_have_text(r: CandidateResult) -> str:
    """'k/M' must-have coverage, or '—' when the JD has no explicit must-haves."""
    return f"{r.must_have_met}/{r.must_have_total}" if r.must_have_total else "—"


def match_label(rs: RequirementScore) -> str:
    return "MISSING" if rs.tag == "MISSING" else rs.match_type


def matched_skills(r: CandidateResult, limit: int = 10) -> list[str]:
    rows = [rs for rs in r.req_scores if rs.tag in ("STRONG", "PRESENT") and rs.requirement.weight != "responsibility"]
    rows.sort(key=lambda x: (_WEIGHT_ORDER[x.requirement.weight], -x.req_score))
    return [rs.requirement.label for rs in rows[:limit]]


def missing_skills(r: CandidateResult, limit: int = 8) -> tuple[list[str], list[str]]:
    """(missing must-haves, missing preferred) — WEAK counts as missing."""
    must = [rs.requirement.label for rs in r.req_scores
            if rs.requirement.weight == "must_have" and rs.tag in ("WEAK", "MISSING")]
    pref = [rs.requirement.label for rs in r.req_scores
            if rs.requirement.weight == "preferred" and rs.tag in ("WEAK", "MISSING")]
    return must[:limit], pref[:limit]


def short_list(items: list[str], n: int = 3) -> str:
    if not items:
        return "—"
    return ", ".join(items[:n]) + (f" +{len(items) - n}" if len(items) > n else "")


# ── evidence list ──────────────────────────────────────────────────
def evidence_html(r: CandidateResult, max_items: int | None = None) -> str:
    """One line per must-have (match type + tag) followed by the exact resume sentence used as evidence.
    JDs without must-haves fall back to the strongest requirements overall."""
    must = sorted((rs for rs in r.req_scores if rs.requirement.weight == "must_have"), key=lambda x: -x.req_score)
    rows = must or sorted(r.req_scores, key=lambda x: -x.req_score)[:6]
    if max_items:
        rows = rows[:max_items]
    out = []
    if not must and rows:
        out.append('<p class="eyebrow">No must-haves in this JD — strongest requirements shown</p>')
    for rs in rows:
        miss = rs.tag == "MISSING"
        cls = "mt miss" if miss else "mt"
        out.append(f'<div class="evi-head"><b>{esc(rs.requirement.label)}</b>'
                   f'<span class="{cls}">{match_label(rs)} · {rs.tag} · {rs.req_score:.2f}</span></div>')
        if not miss and rs.best_chunk is not None:
            out.append(f'<div class="evi">“{esc(snippet(rs, 220))}”'
                       f' <span style="font-style:normal;font-size:.72rem;opacity:.7">— {esc(rs.best_chunk.section)}</span></div>')
        else:
            out.append('<div class="evi" style="opacity:.6">No supporting evidence found in the resume.</div>')
        if rs.is_stuffed:
            out.append('<div class="evi" style="color:#fbbf24;font-style:normal;font-size:.8rem">'
                       'Listed as a keyword but not demonstrated in projects/experience — evidence halved.</div>')
    return "".join(out)


# ── candidate card ─────────────────────────────────────────────────
def candidate_card(r: CandidateResult, total: int, top: CandidateResult | None, key: str,
                   compact: bool = False) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([2.6, 1.1], vertical_alignment="top")
        with c1:
            eyebrow(f"Rank {r.rank} of {total}")
            st.markdown(f"### {esc(r.name)}")
            st.caption(f"{r.candidate_id} · confidence {r.confidence}")
        with c2:
            st.markdown(f'<div class="big-num">{r.final_score:.1f}<small>/ 100</small></div>'
                        + kv([("Must-haves", must_have_text(r)),
                              ("Semantic", f"{r.semantic_agg*100:.0f}"),
                              ("Keyword", f"{r.keyword_agg*100:.0f}"),
                              ("Evidence", f"{r.evidence_agg*100:.0f}")]), unsafe_allow_html=True)

        miss_must, miss_pref = missing_skills(r)
        st.markdown('<p class="eyebrow">Matched</p>' + chips(matched_skills(r, 8 if compact else 12), "green", "no strong matches")
                    + '<p class="eyebrow" style="margin-top:.6rem">Missing</p>'
                    + (chips(miss_must, "red") if miss_must else "")
                    + (chips(miss_pref, "grey") if miss_pref else "")
                    + ("" if (miss_must or miss_pref) else chips(
                        ["all must-haves covered" if r.must_have_total else "no gaps in preferred skills"], "gold")),
                    unsafe_allow_html=True)
        if r.stuffing_flags:
            st.markdown('<p class="eyebrow" style="margin-top:.6rem">Keyword-stuffing flags</p>'
                        + chips([pretty(f) for f in r.stuffing_flags], "gold"), unsafe_allow_html=True)

        st.markdown('<p class="eyebrow" style="margin-top:.8rem">Evidence</p>' + evidence_html(r, 6 if compact else None),
                    unsafe_allow_html=True)

        with st.expander("Plain-English explanation"):
            st.text(short_summary(r) + "\n\n" + generate_explanation(r, total))
        with st.expander("Score breakdown chart"):
            st.plotly_chart(breakdown_chart(r, top), width="stretch", key=f"{key}_bd")


# ── requirement table ──────────────────────────────────────────────
def requirement_table(r: CandidateResult, height: int | None = None) -> None:
    rows = [{
        "Requirement": rs.requirement.label,
        "Type": rs.requirement.weight.replace("_", "-"),
        "Match": match_label(rs),
        "Tag": rs.tag,
        "Score": round(rs.req_score, 2),
        "Sem": round(rs.semantic_score, 2),
        "Kw": round(rs.keyword_score, 2),
        "Ev": round(rs.evidence_score, 2),
        "Evidence from": rs.best_chunk.section if rs.best_chunk and rs.tag != "MISSING" else "—",
        "Flag": "stuffed" if rs.is_stuffed else "",
    } for rs in sorted(r.req_scores, key=lambda x: (_WEIGHT_ORDER[x.requirement.weight], -x.req_score))]
    if not rows:
        st.info("No requirements were extracted from this JD.")
        return
    df = pd.DataFrame(rows)

    def color_tag(v):
        return f"color: white; background-color: {TAG_COLOR.get(v, '#6b7280')}; font-weight: 600"

    st.dataframe(df.style.map(color_tag, subset=["Tag"]), width="stretch", hide_index=True, height=height)


# ── empty state ────────────────────────────────────────────────────
def empty_state() -> None:
    left, _ = st.columns([1.4, 1])
    with left:
        with st.container(border=True):
            eyebrow("Getting started")
            st.markdown("### Upload a job description and the candidate resumes")
            st.markdown(
                "1. **Job description** — one PDF, DOCX or TXT in the sidebar.\n"
                "2. **Resumes** — select all candidate files (PDF / DOCX / TXT; messy layouts are fine).\n"
                "3. Click **Run shortlisting**. Matching runs locally and takes about 15–30 s for 20–150 resumes."
            )
            st.caption("Files are processed in a temporary folder for this session only and are discarded on Reset "
                       "or when the app closes. Nothing is stored, and no previous JD or resume set influences the ranking.")
