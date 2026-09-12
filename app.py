"""
Smart Shortlisting Engine — recruiter UI.

Run:  streamlit run app.py
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from config import JD_DIR, RESUMES_DIR, WEIGHTS
from pipeline.bias_detector import detect_jd_bias
from pipeline.comparator import compare_candidates
from pipeline.explainer import generate_explanation, short_summary, snippet
from pipeline.interfaces import CandidateResult, Requirement, pretty
from pipeline.jd_parser import jd_raw_text, parse_jd_text
from pipeline.ontology import get_ontology
from pipeline.qa_engine import answer_query
from pipeline.resume_parser import parse_resumes
from pipeline.scorer import MatchState, build_match_state, score_state

st.set_page_config(page_title="Smart Shortlisting Engine", page_icon="🎯", layout="wide")

TAG_COLOR = {"STRONG": "#16a34a", "PRESENT": "#2563eb", "WEAK": "#f59e0b", "MISSING": "#dc2626"}
CONF_COLOR = {"HIGH": "#16a34a", "MEDIUM": "#f59e0b", "LOW": "#dc2626"}


# ── data loading (cached) ──────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_state(jd_path: str, resumes_dir: str, version: int) -> tuple[list[Requirement], MatchState, str, float]:
    t0 = time.perf_counter()
    jd_text = jd_raw_text(jd_path)
    requirements = parse_jd_text(jd_text)
    resumes = parse_resumes(resumes_dir)
    state = build_match_state(requirements, resumes, get_ontology())
    return requirements, state, jd_text, time.perf_counter() - t0


def mandatory_color(ratio: float) -> str:
    return "#16a34a" if ratio >= 0.999 else "#f59e0b" if ratio >= 0.5 else "#dc2626"


def mandatory_label(r: CandidateResult) -> str:
    icon = "✅" if r.mandatory_ratio >= 0.999 else "⚠️" if r.mandatory_ratio >= 0.5 else "❌"
    return f"{r.must_have_met}/{r.must_have_total} {icon}"


def results_frame(results: list[CandidateResult]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Rank": r.rank,
        "Candidate": r.name,
        "File": r.candidate_id,
        "Score": round(r.final_score, 1),
        "Mandatory": mandatory_label(r),
        "Semantic": round(r.semantic_agg * 100),
        "Keyword": round(r.keyword_agg * 100),
        "Evidence": round(r.evidence_agg * 100),
        "Confidence": r.confidence,
        "Stuffing": "⚠ " + ", ".join(pretty(f) for f in r.stuffing_flags) if r.stuffing_flags else "—",
    } for r in results])


def score_bar_chart(results: list[CandidateResult]) -> go.Figure:
    ordered = sorted(results, key=lambda r: r.final_score)
    fig = go.Figure(go.Bar(
        x=[r.final_score for r in ordered],
        y=[f"#{r.rank} {r.name}" for r in ordered],
        orientation="h",
        marker_color=[mandatory_color(r.mandatory_ratio) for r in ordered],
        text=[f"{r.final_score:.1f}" for r in ordered],
        textposition="outside",
        hovertext=[f"Mandatory {r.must_have_met}/{r.must_have_total} · sem {r.semantic_agg*100:.0f} · "
                   f"kw {r.keyword_agg*100:.0f} · ev {r.evidence_agg*100:.0f}" for r in ordered],
    ))
    fig.update_layout(height=max(320, 26 * len(results) + 80), margin=dict(l=10, r=40, t=10, b=10),
                      xaxis=dict(range=[0, 105], title="Final score"), yaxis=dict(title=None))
    return fig


def breakdown_chart(r: CandidateResult, top: CandidateResult | None = None) -> go.Figure:
    cats = ["Semantic", "Keyword", "Evidence", "Mandatory"]
    vals = [r.semantic_agg * 100, r.keyword_agg * 100, r.evidence_agg * 100, r.mandatory_ratio * 100]
    fig = go.Figure()
    fig.add_bar(name=r.name, x=cats, y=vals, marker_color="#2563eb", text=[f"{v:.0f}" for v in vals], textposition="outside")
    if top is not None and top.candidate_id != r.candidate_id:
        tv = [top.semantic_agg * 100, top.keyword_agg * 100, top.evidence_agg * 100, top.mandatory_ratio * 100]
        fig.add_bar(name=f"#1 {top.name}", x=cats, y=tv, marker_color="#94a3b8", text=[f"{v:.0f}" for v in tv], textposition="outside")
    fig.update_layout(barmode="group", height=280, yaxis=dict(range=[0, 115]), margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=1.1))
    return fig


def radar_chart(r: CandidateResult) -> go.Figure:
    conf_num = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}[r.confidence]
    cats = ["Semantic", "Keyword", "Evidence", "Mandatory", "Confidence"]
    vals = [r.semantic_agg, r.keyword_agg, r.evidence_agg, r.mandatory_ratio, conf_num]
    fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=cats + cats[:1], fill="toself", name=r.name))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 1], visible=True)), height=320,
                      margin=dict(l=30, r=30, t=20, b=20), showlegend=False)
    return fig


def requirement_table(r: CandidateResult) -> None:
    rows = []
    for rs in sorted(r.req_scores, key=lambda x: ({"must_have": 0, "preferred": 1, "responsibility": 2}[x.requirement.weight], -x.req_score)):
        rows.append({
            "Requirement": rs.requirement.label,
            "Type": rs.requirement.weight.replace("_", "-"),
            "Match": rs.match_type,
            "Tag": rs.tag,
            "Score": f"{rs.req_score:.2f}",
            "Sem": f"{rs.semantic_score:.2f}",
            "Kw": f"{rs.keyword_score:.2f}",
            "Ev": f"{rs.evidence_score:.2f}",
            "Source": rs.best_chunk.section if rs.best_chunk and rs.tag != "MISSING" else "—",
            "⚠": "stuffed" if rs.is_stuffed else "",
        })
    df = pd.DataFrame(rows)

    def color_tag(v):
        return f"color: white; background-color: {TAG_COLOR.get(v, '#6b7280')}; font-weight: 600"

    st.dataframe(df.style.map(color_tag, subset=["Tag"]), use_container_width=True, hide_index=True)


def evidence_panel(r: CandidateResult) -> None:
    for weight, title in (("must_have", "Must-have"), ("preferred", "Preferred"), ("responsibility", "Responsibilities")):
        group = [rs for rs in r.req_scores if rs.requirement.weight == weight]
        if not group:
            continue
        st.markdown(f"**{title}**")
        for rs in sorted(group, key=lambda x: -x.req_score):
            head = f"**{rs.requirement.label}** — {rs.tag} ({rs.req_score:.2f}) · {rs.match_type}"
            if rs.tag == "MISSING":
                st.error(f"✗ {head}: required but not found in the resume.")
            elif rs.tag == "WEAK":
                st.warning(f"≈ {head} — partial evidence ({rs.best_chunk.section if rs.best_chunk else '—'}): “{snippet(rs, 120)}”")
            else:
                st.info(f"{'✓' if rs.tag == 'STRONG' else '~'} {head}\n\n"
                        f"Evidence ({rs.best_chunk.section.title() if rs.best_chunk else '—'}): “{snippet(rs, 200)}”  \n"
                        f"semantic {rs.semantic_score:.2f} · keyword {rs.keyword_score:.2f} · evidence {rs.evidence_score:.2f} · cosine {rs.best_chunk_similarity:.2f}")
            if rs.is_stuffed:
                st.warning(f"⚠ '{rs.requirement.label}' is listed as a keyword but not demonstrated in projects/experience — evidence halved.")


# ── sidebar: data source ───────────────────────────────────────────
st.sidebar.title("🎯 Smart Shortlisting")
st.sidebar.caption("Local · API-free · evidence-backed ranking")

if "data_version" not in st.session_state:
    st.session_state.data_version = 0

with st.sidebar.expander("📂 Data", expanded=True):
    jd_files = sorted((p for p in JD_DIR.glob("*") if p.suffix.lower() in (".pdf", ".txt", ".docx")),
                      key=lambda p: p.stat().st_mtime, reverse=True)      # newest first
    jd_names = [p.name for p in jd_files] or ["(none found)"]
    if st.session_state.get("jd_choice") not in jd_names:
        st.session_state.jd_choice = jd_names[0]
    jd_choice = st.selectbox("Job description", jd_names, key="jd_choice")
    resume_dirs = sorted(p for p in config.DATA_DIR.iterdir() if p.is_dir() and p.name.startswith("resumes"))
    resume_dir_choice = st.selectbox("Resume folder", [p.name for p in resume_dirs] or ["resumes"],
                                     index=0)
    RESUMES_DIR = config.DATA_DIR / resume_dir_choice
    n_res = len([p for p in RESUMES_DIR.iterdir() if p.suffix.lower() in (".pdf", ".docx", ".txt")]) if RESUMES_DIR.exists() else 0
    st.write(f"Resumes in `data/{resume_dir_choice}/`: **{n_res}**")
    up_jd = st.file_uploader("Upload JD", type=["pdf", "txt", "docx"], key="up_jd")
    up_res = st.file_uploader("Upload resumes", type=["pdf", "docx", "txt"], accept_multiple_files=True, key="up_res")
    if st.button("Save uploads & re-run", use_container_width=True):
        JD_DIR.mkdir(parents=True, exist_ok=True)
        RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        if up_jd is not None:
            (JD_DIR / up_jd.name).write_bytes(up_jd.getbuffer())
            st.session_state.jd_choice = up_jd.name          # select the JD that was just uploaded
        for f in up_res or []:
            (RESUMES_DIR / f.name).write_bytes(f.getbuffer())
        st.session_state.data_version += 1
        load_state.clear()
        st.rerun()
    if st.button("Clear embedding cache", use_container_width=True):
        shutil.rmtree(config.CACHE_DIR, ignore_errors=True)
        load_state.clear()
        st.rerun()

if not jd_files:
    st.warning("Put the JD PDF in `data/jd/` and resumes in `data/resumes/` (or upload them in the sidebar).")
    st.stop()

jd_path = str(JD_DIR / jd_choice)
with st.spinner("Parsing documents, embedding evidence chunks and scoring…"):
    requirements, state, jd_text, elapsed = load_state(jd_path, str(RESUMES_DIR), st.session_state.data_version)

if not state.resumes:
    st.error("No resumes could be parsed from `data/resumes/`.")
    st.stop()

# active weights (What-if simulator can override)
weights = st.session_state.get("weights", dict(WEIGHTS))
results = score_state(state, weights)
baseline_results = score_state(state, WEIGHTS)
baseline_rank = {r.candidate_id: r.rank for r in baseline_results}
by_id = {r.candidate_id: r for r in results}
names = [f"#{r.rank} {r.name}" for r in results]
name_to_id = {n: r.candidate_id for n, r in zip(names, results)}
total = len(results)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Weights in use**  \nsemantic {weights['semantic']:.0%} · keyword {weights['keyword']:.0%} · evidence {weights['evidence']:.0%}")
st.sidebar.caption(f"Pipeline build: {elapsed:.1f}s · {total} resumes · {len(requirements)} requirements")

st.markdown(f"##### 📄 Active JD: `{jd_choice}` &nbsp;·&nbsp; 📁 `data/{resume_dir_choice}` ({total} resumes) "
            f"&nbsp;·&nbsp; {sum(1 for r in requirements if r.weight == 'must_have')} must-haves, "
            f"{sum(1 for r in requirements if r.weight == 'preferred')} preferred, "
            f"{sum(1 for r in requirements if r.weight == 'responsibility')} responsibilities")

tabs = st.tabs(["📊 Dashboard", "🏆 Ranking", "🥇 Top 3", "🔍 Candidate", "⚖️ Compare", "💬 Ask", "📄 JD & What-if"])

# ── Tab 1: Dashboard ───────────────────────────────────────────────
with tabs[0]:
    top = results[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Candidates", total)
    c2.metric(f"#1 · {top.name}", f"{top.final_score:.1f}", f"{top.must_have_met}/{top.must_have_total} must-haves")
    c3.metric("Average score", f"{sum(r.final_score for r in results) / total:.1f}")
    c4.metric("Avg mandatory coverage", f"{100 * sum(r.mandatory_ratio for r in results) / total:.0f}%")
    c5.metric("All must-haves met", sum(1 for r in results if r.mandatory_ratio >= 0.999))
    st.plotly_chart(score_bar_chart(results), use_container_width=True)
    st.caption("Bar colour = mandatory coverage (green all, orange ≥50%, red <50%). "
               "Score = (semantic·w₁ + keyword·w₂ + evidence·w₃) × mandatory coverage × 100.")

# ── Tab 2: Ranking table ───────────────────────────────────────────
with tabs[1]:
    df = results_frame(results)
    q = st.text_input("Filter by name / file", "")
    if q:
        df = df[df["Candidate"].str.contains(q, case=False) | df["File"].str.contains(q, case=False)]

    def conf_style(v):
        return f"color: {CONF_COLOR.get(v, '#000')}; font-weight: 600"

    st.dataframe(
        df.style.map(conf_style, subset=["Confidence"]),
        use_container_width=True, hide_index=True,
        column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f")},
    )
    st.download_button("⬇ Download ranking CSV", df.to_csv(index=False).encode(), "ranking.csv", "text/csv")

# ── Tab 3: Top 3 ───────────────────────────────────────────────────
with tabs[2]:
    for r in results[:3]:
        with st.expander(f"Rank #{r.rank} — {r.name}   ·   Score {r.final_score:.1f}   ·   {r.confidence} confidence",
                         expanded=(r.rank == 1)):
            st.write(short_summary(r))
            col_a, col_b = st.columns([1, 1])
            with col_a:
                st.plotly_chart(breakdown_chart(r), use_container_width=True, key=f"bd_{r.candidate_id}")
            with col_b:
                m_ok = ", ".join(pretty(x) for x in r.matched_required) or "—"
                m_no = ", ".join(pretty(x) for x in r.missing_required) or "none"
                st.markdown(f"**Matched must-haves:** {m_ok}")
                st.markdown(f"**Missing must-haves:** {m_no}")
                if r.stuffing_flags:
                    st.markdown("**Keyword-stuffing flags:** " + ", ".join(pretty(x) for x in r.stuffing_flags))
            requirement_table(r)
            evidence_panel(r)

# ── Tab 4: Candidate detail ────────────────────────────────────────
with tabs[3]:
    pick = st.selectbox("Candidate", names, key="detail_pick")
    r = by_id[name_to_id[pick]]
    st.subheader(f"{r.name} — ranked #{r.rank} of {total}")
    st.write(short_summary(r))
    c1, c2 = st.columns([1, 1])
    with c1:
        st.plotly_chart(breakdown_chart(r, results[0]), use_container_width=True, key="detail_bd")
    with c2:
        st.plotly_chart(radar_chart(r), use_container_width=True, key="detail_radar")
    requirement_table(r)
    evidence_panel(r)
    with st.expander("Plain-text explanation"):
        st.code(generate_explanation(r, total), language="text")

# ── Tab 5: Compare ─────────────────────────────────────────────────
with tabs[4]:
    c1, c2 = st.columns(2)
    a_pick = c1.selectbox("Candidate A", names, index=0, key="cmp_a")
    b_pick = c2.selectbox("Candidate B", names, index=min(1, total - 1), key="cmp_b")
    a, b = by_id[name_to_id[a_pick]], by_id[name_to_id[b_pick]]
    cmp = compare_candidates(a, b)
    m1, m2 = st.columns(2)
    for col, cand in ((m1, a), (m2, b)):
        col.metric(cand.name, f"{cand.final_score:.1f}", f"rank #{cand.rank}")
        col.write(f"Mandatory {cand.must_have_met}/{cand.must_have_total} · semantic {cand.semantic_agg*100:.0f} · "
                  f"keyword {cand.keyword_agg*100:.0f} · evidence {cand.evidence_agg*100:.0f} · {cand.confidence}")
    rows = [{"Requirement": t["requirement"], "Type": t["weight"].replace("_", "-"),
             f"{a.name}": f"{t['a_tag']} ({t['a_score']:.2f})", f"{b.name}": f"{t['b_tag']} ({t['b_score']:.2f})",
             "Δ (A−B)": t["diff"]} for t in cmp["table"]]
    cdf = pd.DataFrame(rows)

    def row_color(row):
        d = row["Δ (A−B)"]
        c = "#dcfce7" if d > 0.1 else "#fee2e2" if d < -0.1 else "#f1f5f9"
        return [f"background-color: {c}"] * len(row)

    st.dataframe(cdf.style.apply(row_color, axis=1), use_container_width=True, hide_index=True)
    st.markdown("**Why?**")
    st.code(cmp["summary"], language="text")

# ── Tab 6: Recruiter Q&A ───────────────────────────────────────────
with tabs[5]:
    st.caption("Deterministic answers built from the stored scoring data — no LLM involved.")
    examples = [
        f"Why is {results[0].name} above {results[1].name}?" if total > 1 else "Explain rank 1",
        f"Explain {results[0].name}",
        f"Missing skills for {results[min(2, total - 1)].name}",
        "Who is ranked #3?",
        "Top 5 candidates",
    ]
    cols = st.columns(len(examples))
    for col, ex in zip(cols, examples):
        if col.button(ex, use_container_width=True):
            st.session_state.qa_input = ex          # set widget state before the widget renders
    query = st.text_input("Ask a question", key="qa_input")
    if query:
        st.code(answer_query(query, results), language="text")

# ── Tab 7: JD analysis + What-if ───────────────────────────────────
with tabs[6]:
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Structured requirements")
        rdf = pd.DataFrame([{"Requirement": r.label, "Type": r.weight.replace("_", "-"),
                             "Category": r.category, "From": r.original_text[:70]} for r in requirements])
        st.dataframe(rdf, use_container_width=True, hide_index=True, height=360)
        st.subheader("Potential bias / narrow-phrasing indicators")
        flags = detect_jd_bias(requirements, jd_text)
        if flags:
            for f in flags:
                st.warning(f)
        else:
            st.success("No potential bias indicators found.")
        st.caption("Indicators only — they never change the ranking.")
        with st.expander("Raw JD text"):
            st.text(jd_text)
    with right:
        st.subheader("What-if ranking simulator")
        st.write("Re-weight the signals and watch the ranking update instantly (no re-embedding).")
        p1, p2, p3, p4 = st.columns(4)
        presets = {"Default": WEIGHTS, "Semantic-heavy": {"semantic": 0.65, "keyword": 0.15, "evidence": 0.20},
                   "Keyword-heavy": {"semantic": 0.20, "keyword": 0.60, "evidence": 0.20},
                   "Evidence-heavy": {"semantic": 0.30, "keyword": 0.20, "evidence": 0.50}}
        for col, (label, w) in zip((p1, p2, p3, p4), presets.items()):
            if col.button(label, use_container_width=True):
                st.session_state.weights = dict(w)
                st.rerun()
        cur = st.session_state.get("weights", dict(WEIGHTS))
        s_w = st.slider("Semantic matching", 0, 100, int(round(cur["semantic"] * 100)))
        k_w = st.slider("Keyword matching", 0, 100, int(round(cur["keyword"] * 100)))
        e_w = st.slider("Evidence quality", 0, 100, int(round(cur["evidence"] * 100)))
        tot = max(1, s_w + k_w + e_w)
        st.caption(f"Normalised → semantic {s_w/tot:.0%} · keyword {k_w/tot:.0%} · evidence {e_w/tot:.0%}")
        if st.button("Apply & re-rank", type="primary", use_container_width=True):
            st.session_state.weights = {"semantic": s_w / tot, "keyword": k_w / tot, "evidence": e_w / tot}
            st.rerun()
        moves = []
        for r in results:
            old = baseline_rank[r.candidate_id]
            arrow = "↑" if r.rank < old else "↓" if r.rank > old else "="
            moves.append({"Rank": r.rank, "Δ": f"{arrow}{abs(old - r.rank) if old != r.rank else ''}",
                          "Candidate": r.name, "Score": round(r.final_score, 1), "Mandatory": mandatory_label(r)})
        st.dataframe(pd.DataFrame(moves), use_container_width=True, hide_index=True, height=420)
