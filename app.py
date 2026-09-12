"""
Smart Shortlisting Engine — recruiter UI.

Run:  streamlit run app.py

Inputs are uploaded per session (JD + resumes) and processed in a temporary
folder; nothing is stored and no previous data set influences the ranking.
Pages: Shortlist · Top 3 · Candidate · Compare · Ask · JD & Settings.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config import WEIGHTS
from pipeline.bias_detector import detect_jd_bias
from pipeline.comparator import compare_candidates
from pipeline.interfaces import CandidateResult, pretty
from pipeline.qa_engine import answer_query
from pipeline.scorer import score_state
from ui.charts import requirement_bar_chart, score_bar_chart
from ui.components import (candidate_card, chips, empty_state, esc, eyebrow, kv, matched_skills,
                           missing_skills, must_have_text, requirement_table, short_list, stat_card)
from ui.session import SUPPORTED_TYPES, Session, remove_dir, run_from_uploads
from ui.theme import CONF_COLOR, hero_canvas, inject_css

st.set_page_config(page_title="Smart Shortlisting Engine", page_icon="🎯", layout="wide")
inject_css()

PAGES = ["Shortlist", "Top 3", "Candidate", "Compare", "Ask", "JD & Settings"]
PICKER_KEYS = ("detail_pick", "cmp_a", "cmp_b", "qa_input", "rank_filter", "show_breakdown")


# ── session helpers ────────────────────────────────────────────────
def clear_results() -> None:
    """Drop the current run (temp folder + derived widget state). Uploads are kept."""
    run: Session | None = st.session_state.pop("run", None)
    if run is not None:
        remove_dir(run.tmp_dir)
    for k in ("weights", *PICKER_KEYS):        # page widgets are not instantiated yet at this point
        st.session_state.pop(k, None)


def reset_all() -> None:
    clear_results()
    st.session_state["uploader_gen"] = st.session_state.get("uploader_gen", 0) + 1   # fresh, empty uploaders
    st.session_state["page"] = PAGES[0]


st.session_state.setdefault("uploader_gen", 0)
st.session_state.setdefault("run_error", None)

# ── sidebar: inputs only ───────────────────────────────────────────
with st.sidebar:
    eyebrow("Session inputs")
    gen = st.session_state["uploader_gen"]
    up_jd = st.file_uploader("Job description", type=SUPPORTED_TYPES, key=f"up_jd_{gen}")
    up_res = st.file_uploader("Resumes", type=SUPPORTED_TYPES, accept_multiple_files=True, key=f"up_res_{gen}")
    ready = up_jd is not None and bool(up_res)
    if not ready:
        missing = [x for x, ok in (("a job description", up_jd is not None), ("at least one resume", bool(up_res))) if not ok]
        st.caption("Still needed: " + " and ".join(missing) + ".")
    else:
        st.caption(f"{up_jd.name} · {len(up_res)} resume{'s' if len(up_res) != 1 else ''} selected")
    run_clicked = st.button("Run shortlisting", type="primary", disabled=not ready, width="stretch", key="btn_run")
    if st.button("Reset", width="stretch", key="btn_reset"):
        reset_all()
        st.rerun()
    run: Session | None = st.session_state.get("run")
    if run is not None:
        st.caption(f"Loaded: {run.jd_name} · {run.n_parsed} of {run.n_uploaded} resumes parsed · "
                   f"{len(run.requirements)} requirements · {run.elapsed:.1f}s")

# ── header + navigation bar ────────────────────────────────────────
hero_canvas(height=240)
if st.session_state.get("nav") not in PAGES:            # first run / stale value → before the widget renders
    st.session_state["nav"] = st.session_state.get("page", PAGES[0])
page = st.segmented_control("Navigate", PAGES, key="nav", required=True,
                            label_visibility="collapsed", width="stretch")
st.session_state["page"] = page or st.session_state.get("page", PAGES[0])
page = st.session_state["page"]
st.write("")

# ── run the pipeline on the current uploads ────────────────────────
if run_clicked and ready:
    clear_results()
    st.session_state["run_error"] = None
    try:
        with st.spinner("Parsing documents, embedding evidence chunks and scoring…"):
            st.session_state["run"] = run_from_uploads(up_jd, list(up_res))
    except Exception as exc:  # noqa: BLE001 — user-supplied files: report, don't crash the page
        st.session_state["run_error"] = f"{type(exc).__name__}: {exc}"
    st.rerun()

run = st.session_state.get("run")
if st.session_state.get("run_error"):
    st.error("The uploaded files could not be processed — " + st.session_state["run_error"])
if run is None:
    empty_state()
    st.stop()
if not run.state.resumes:
    st.error("None of the uploaded resumes could be parsed (no extractable text). Try PDF/DOCX files with selectable text.")
    st.stop()

requirements, state, jd_text = run.requirements, run.state, run.jd_text

# active weights (What-if simulator can override)
weights = st.session_state.get("weights", dict(WEIGHTS))
results = score_state(state, weights)
baseline_results = score_state(state, WEIGHTS)
baseline_rank = {r.candidate_id: r.rank for r in baseline_results}
by_id = {r.candidate_id: r for r in results}
names = [f"#{r.rank} {r.name}" for r in results]
name_to_id = {n: r.candidate_id for n, r in zip(names, results)}
total = len(results)
top = results[0]
n_must = sum(1 for r in requirements if r.weight == "must_have")
n_pref = sum(1 for r in requirements if r.weight == "preferred")
n_resp = sum(1 for r in requirements if r.weight == "responsibility")
custom_weights = any(abs(weights[k] - WEIGHTS[k]) > 1e-9 for k in WEIGHTS)

# Candidate pickers keep their value in session_state; after a re-run / weight change that
# label may no longer exist, so validate before the widgets render (never after).
for _key, _default in (("detail_pick", names[0]), ("cmp_a", names[0]), ("cmp_b", names[min(1, total - 1)])):
    if st.session_state.get(_key) not in names:
        st.session_state[_key] = _default


def results_frame(results: list[CandidateResult], breakdown: bool) -> pd.DataFrame:
    rows = []
    for r in results:
        miss_must, _ = missing_skills(r, 99)
        row = {
            "Rank": r.rank,
            "Candidate": r.name,
            "Score": round(r.final_score, 1),
            "Must-haves": must_have_text(r),
            "Confidence": r.confidence,
            "Top matched skills": short_list(matched_skills(r, 6), 3),
            "Key gaps": short_list(miss_must, 3),
        }
        if breakdown:
            row.update({"Semantic": round(r.semantic_agg * 100), "Keyword": round(r.keyword_agg * 100),
                        "Evidence": round(r.evidence_agg * 100), "File": r.candidate_id,
                        "Flags": ", ".join(pretty(f) for f in r.stuffing_flags)})
        rows.append(row)
    return pd.DataFrame(rows)


def context_strip(note: bool = False) -> None:
    st.caption(f"JD **{esc(run.jd_name)}** · {total} candidates · {n_must} must-haves · {n_pref} preferred · "
               f"{n_resp} responsibilities" + (" · **custom weights**" if custom_weights else ""))
    if note and n_must == 0:
        st.info("No explicit must-haves found in this JD — ranking uses preferred skills and responsibilities.")


# ── Page: Shortlist ────────────────────────────────────────────────
if page == "Shortlist":
    context_strip(note=True)
    main, side = st.columns([2, 1], gap="large")
    with main:
        f1, f2 = st.columns([2, 1], vertical_alignment="bottom")
        q = f1.text_input("Filter by name or file", "", key="rank_filter", persist_state="session", placeholder="Filter by name or file")
        breakdown = f2.toggle("Show score breakdown", key="show_breakdown", persist_state="session")
        df = results_frame(results, breakdown)
        if q:
            ids = pd.Series([r.candidate_id for r in results])
            mask = df["Candidate"].str.contains(q, case=False, regex=False) | ids.str.contains(q, case=False, regex=False)
            df = df[mask.values]

        def conf_style(v):
            return f"color: {CONF_COLOR.get(v, '#e8e6e1')}; font-weight: 600"

        st.dataframe(
            df.style.map(conf_style, subset=["Confidence"]),
            width="stretch", hide_index=True, height=min(620, 38 * len(df) + 40),
            column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
                           "Rank": st.column_config.NumberColumn("Rank", width="small")},
        )
        st.download_button("Download ranking CSV", results_frame(results, True).to_csv(index=False).encode("utf-8-sig"),
                           "ranking.csv", "text/csv", key="dl_csv")
        with st.container(border=True):
            eyebrow("Top 10 scores · colour = must-have coverage")
            st.plotly_chart(score_bar_chart(results, 10), width="stretch", key="shortlist_bar")
    with side:
        with st.container(border=True):
            eyebrow("Job description")
            st.markdown(f"**{esc(run.jd_name)}**")
            st.markdown(kv([("Must-have", str(n_must)), ("Preferred", str(n_pref)), ("Responsibilities", str(n_resp)),
                            ("Weights", f"sem {weights['semantic']:.0%} · kw {weights['keyword']:.0%} · ev {weights['evidence']:.0%}")]),
                        unsafe_allow_html=True)
        all_met = sum(1 for r in results if r.mandatory_ratio >= 0.999)
        if n_must:
            stat_card("Must-have coverage", f"{100 * sum(r.mandatory_ratio for r in results) / total:.0f}", unit="% avg",
                      sub=f"{all_met} of {total} candidates cover every must-have")
        else:
            stat_card("Must-have coverage", "—", sub="No explicit must-haves in this JD")
        hi = sum(1 for r in results if r.confidence == "HIGH")
        med = sum(1 for r in results if r.confidence == "MEDIUM")
        stat_card("Confidence", f"{hi}", unit="high",
                  sub=f"{med} medium · {total - hi - med} low — extraction quality × evidence strength")
        stat_card("Leader", f"{top.final_score:.1f}", unit=f"· {top.name}",
                  sub=(f"{must_have_text(top)} must-haves · " if n_must else "")
                      + f"average score {sum(r.final_score for r in results) / total:.1f}")

# ── Page: Top 3 ────────────────────────────────────────────────────
if page == "Top 3":
    context_strip()
    podium = results[:3]
    candidate_card(podium[0], total, None, key="top1")
    if len(podium) > 1:
        cols = st.columns(len(podium) - 1, gap="medium")
        for col, r in zip(cols, podium[1:]):
            with col:
                candidate_card(r, total, top, key=f"top{r.rank}", compact=True)

# ── Page: Candidate ────────────────────────────────────────────────
if page == "Candidate":
    context_strip()
    pick = st.selectbox("Candidate", names, key="detail_pick", persist_state="session")
    r = by_id[name_to_id[pick]]
    candidate_card(r, total, top, key="detail")
    st.write("")
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        eyebrow("Every requirement")
        requirement_table(r, height=min(560, 38 * len(r.req_scores) + 40))
    with right:
        eyebrow("Requirement scores · colour = tag")
        st.plotly_chart(requirement_bar_chart(r), width="stretch", key="detail_reqbar")

# ── Page: Compare ──────────────────────────────────────────────────
if page == "Compare":
    context_strip()
    c1, c2 = st.columns(2, gap="large")
    a_pick = c1.selectbox("Candidate A", names, key="cmp_a", persist_state="session")
    b_pick = c2.selectbox("Candidate B", names, key="cmp_b", persist_state="session")
    a, b = by_id[name_to_id[a_pick]], by_id[name_to_id[b_pick]]
    if a.candidate_id == b.candidate_id:
        st.info("Pick two different candidates to compare.")
    cmp = compare_candidates(a, b)
    for col, cand, tag in ((c1, a, "A"), (c2, b, "B")):
        with col, st.container(border=True):
            eyebrow(f"{tag} · rank {cand.rank} of {total}")
            st.markdown(f"### {esc(cand.name)}")
            st.markdown(f'<div class="big-num">{cand.final_score:.1f}<small>/ 100</small></div>'
                        + kv([("Must-haves", must_have_text(cand)),
                              ("Semantic", f"{cand.semantic_agg*100:.0f}"), ("Keyword", f"{cand.keyword_agg*100:.0f}"),
                              ("Evidence", f"{cand.evidence_agg*100:.0f}"), ("Confidence", cand.confidence)]),
                        unsafe_allow_html=True)
            mm, mp = missing_skills(cand, 6)
            st.markdown('<p class="eyebrow" style="margin-top:.5rem">Matched</p>' + chips(matched_skills(cand, 8), "green", "none")
                        + '<p class="eyebrow" style="margin-top:.5rem">Missing must-haves</p>' + chips(mm, "red", "none"),
                        unsafe_allow_html=True)
    st.write("")
    with st.container(border=True):
        eyebrow("Why does the higher-ranked candidate win?")
        st.text(cmp["summary"])
    # "A: name" / "B: name" keeps the columns distinct even when both names match
    col_a, col_b = f"A: {a.name}", f"B: {b.name}"
    rows = [{"Requirement": t["requirement"], "Type": t["weight"].replace("_", "-"),
             col_a: f"{t['a_tag']} ({t['a_score']:.2f})", col_b: f"{t['b_tag']} ({t['b_score']:.2f})",
             "Δ (A−B)": t["diff"]} for t in cmp["table"]]
    cdf = pd.DataFrame(rows, columns=["Requirement", "Type", col_a, col_b, "Δ (A−B)"])

    def row_color(row):
        d = row["Δ (A−B)"]
        c = "rgba(34,197,94,.16)" if d > 0.1 else "rgba(239,68,68,.16)" if d < -0.1 else "transparent"
        return [f"background-color: {c}"] * len(row)

    eyebrow("Requirement by requirement · green = A stronger, red = B stronger")
    st.dataframe(cdf.style.apply(row_color, axis=1), width="stretch", hide_index=True,
                 height=min(560, 38 * len(cdf) + 40))

# ── Page: Ask ──────────────────────────────────────────────────────
if page == "Ask":
    context_strip()
    examples = [
        f"Why is {results[0].name} above {results[1].name}?" if total > 1 else "Explain rank 1",
        f"Explain {results[0].name}",
        f"Missing skills for {results[min(2, total - 1)].name}",
        "Who is ranked #3?",
        "Top 5 candidates",
    ]
    cols = st.columns(len(examples))
    for i, (col, ex) in enumerate(zip(cols, examples)):
        if col.button(ex, width="stretch", key=f"qa_ex_{i}"):
            st.session_state.qa_input = ex          # set widget state before the widget renders
    query = st.text_input("Ask a question", key="qa_input", persist_state="session",
                          placeholder="Why is A above B? · Who has Docker? · Missing skills for … · Top 5")
    st.caption("Deterministic answers built from the stored scoring data — no LLM involved.")
    if query:
        with st.container(border=True):
            st.text(answer_query(query, results))

# ── Page: JD & Settings ────────────────────────────────────────────
if page == "JD & Settings":
    context_strip()
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown("### Structured requirements")
        rdf = pd.DataFrame([{"Requirement": r.label if not r.alternatives else pretty(r.text), "Type": r.weight.replace("_", "-"),
                             "Alternatives": ", ".join(pretty(a) for a in r.alternatives) or "—",
                             "Category": r.category, "From": r.original_text[:80]} for r in requirements])
        if len(rdf):
            st.dataframe(rdf, width="stretch", hide_index=True, height=min(420, 38 * len(rdf) + 40))
        else:
            st.info("No requirements were extracted from this JD.")
        st.markdown("### Bias / narrow-phrasing indicators")
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
        st.markdown("### What-if weights")
        st.caption("Re-weight the three signals and watch the ranking update instantly (no re-embedding).")
        presets = {"Default": WEIGHTS, "Semantic": {"semantic": 0.65, "keyword": 0.15, "evidence": 0.20},
                   "Keyword": {"semantic": 0.20, "keyword": 0.60, "evidence": 0.20},
                   "Evidence": {"semantic": 0.30, "keyword": 0.20, "evidence": 0.50}}
        eyebrow("Presets")
        pcols = st.columns(len(presets))
        for i, (col, (label, w)) in enumerate(zip(pcols, presets.items())):
            if col.button(label, width="stretch", key=f"preset_{i}"):
                st.session_state.weights = dict(w)
                st.rerun()
        cur = st.session_state.get("weights", dict(WEIGHTS))
        s_w = st.slider("Semantic matching", 0, 100, int(round(cur["semantic"] * 100)), key="w_sem")
        k_w = st.slider("Keyword matching", 0, 100, int(round(cur["keyword"] * 100)), key="w_kw")
        e_w = st.slider("Evidence quality", 0, 100, int(round(cur["evidence"] * 100)), key="w_ev")
        tot = max(1, s_w + k_w + e_w)
        st.caption(f"Normalised: semantic {s_w/tot:.0%} · keyword {k_w/tot:.0%} · evidence {e_w/tot:.0%}"
                   + ("  — all zero: every score becomes 0" if s_w + k_w + e_w == 0 else ""))
        if st.button("Apply & re-rank", type="primary", width="stretch", key="btn_apply_w"):
            st.session_state.weights = {"semantic": s_w / tot, "keyword": k_w / tot, "evidence": e_w / tot}
            st.rerun()
        moves = []
        for r in results:
            old = baseline_rank[r.candidate_id]
            arrow = "↑" if r.rank < old else "↓" if r.rank > old else "="
            moves.append({"Rank": r.rank, "Δ vs default": f"{arrow}{abs(old - r.rank) if old != r.rank else ''}",
                          "Candidate": r.name, "Score": round(r.final_score, 1),
                          "Must-haves": must_have_text(r)})
        eyebrow("Ranking under the active weights")
        st.dataframe(pd.DataFrame(moves), width="stretch", hide_index=True, height=min(480, 38 * len(moves) + 40))
