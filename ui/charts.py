"""Plotly chart builders (presentation only)."""
from __future__ import annotations

import plotly.graph_objects as go

from pipeline.interfaces import CandidateResult
from ui.theme import ACCENT, MUTED, TAG_COLOR, style_fig


def coverage_color(ratio: float) -> str:
    return "#4ade80" if ratio >= 0.999 else "#fbbf24" if ratio >= 0.5 else "#f87171"


def score_bar_chart(results: list[CandidateResult], top_n: int = 10) -> go.Figure:
    ordered = sorted(results[:top_n], key=lambda r: r.final_score)
    fig = go.Figure(go.Bar(
        x=[r.final_score for r in ordered],
        y=[f"#{r.rank}  {r.name}" for r in ordered],
        orientation="h",
        marker_color=[coverage_color(r.mandatory_ratio) for r in ordered],
        marker_line_width=0,
        text=[f"{r.final_score:.1f}" for r in ordered],
        textposition="outside",
        hovertext=[f"Must-haves {r.must_have_met}/{r.must_have_total} · sem {r.semantic_agg*100:.0f} · "
                   f"kw {r.keyword_agg*100:.0f} · ev {r.evidence_agg*100:.0f}" for r in ordered],
    ))
    fig.update_layout(height=max(220, 30 * len(ordered) + 40), bargap=0.35,
                      xaxis=dict(range=[0, 108], title=None, showgrid=True), yaxis=dict(title=None, showgrid=False))
    return style_fig(fig)


def breakdown_chart(r: CandidateResult, top: CandidateResult | None = None) -> go.Figure:
    cats = ["Semantic", "Keyword", "Evidence", "Must-haves"]
    vals = [r.semantic_agg * 100, r.keyword_agg * 100, r.evidence_agg * 100, r.mandatory_ratio * 100]
    fig = go.Figure()
    fig.add_bar(name=r.name, x=cats, y=vals, marker_color=ACCENT, marker_line_width=0,
                text=[f"{v:.0f}" for v in vals], textposition="outside")
    if top is not None and top.candidate_id != r.candidate_id:
        tv = [top.semantic_agg * 100, top.keyword_agg * 100, top.evidence_agg * 100, top.mandatory_ratio * 100]
        fig.add_bar(name=f"#1 {top.name}", x=cats, y=tv, marker_color="#5b6270", marker_line_width=0,
                    text=[f"{v:.0f}" for v in tv], textposition="outside")
    fig.update_layout(barmode="group", height=250, bargap=0.4, yaxis=dict(range=[0, 118], showgrid=True),
                      xaxis=dict(showgrid=False), legend=dict(orientation="h", y=1.12, x=0))
    return style_fig(fig)


def requirement_bar_chart(r: CandidateResult) -> go.Figure:
    """Sorted horizontal bars of per-requirement scores, coloured by tag."""
    rows = sorted(r.req_scores, key=lambda x: x.req_score)
    fig = go.Figure(go.Bar(
        x=[rs.req_score for rs in rows],
        y=[rs.requirement.label[:48] for rs in rows],
        orientation="h",
        marker_color=[TAG_COLOR[rs.tag] for rs in rows],
        marker_line_width=0,
        text=[f"{rs.req_score:.2f}" for rs in rows],
        textposition="outside",
        hovertext=[f"{rs.requirement.weight.replace('_', '-')} · {rs.match_type} · {rs.tag}" for rs in rows],
    ))
    fig.update_layout(height=max(240, 22 * len(rows) + 40), bargap=0.3,
                      xaxis=dict(range=[0, 1.12], showgrid=True, title=None),
                      yaxis=dict(title=None, showgrid=False, tickfont=dict(size=11, color=MUTED)))
    return style_fig(fig)
