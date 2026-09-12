"""
Command-line runner — rank resumes against a JD without the UI.

  python run_cli.py                       # uses data/jd + data/resumes
  python run_cli.py --jd path.pdf --resumes folder/ --top 3 --explain
"""
from __future__ import annotations

import argparse
import time

from config import JD_PATH, RESUMES_DIR
from pipeline.bias_detector import detect_jd_bias
from pipeline.explainer import generate_explanation
from pipeline.jd_parser import jd_raw_text, parse_jd_text
from pipeline.ontology import get_ontology
from pipeline.resume_parser import parse_resumes
from pipeline.scorer import run_pipeline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jd", default=str(JD_PATH))
    ap.add_argument("--resumes", default=str(RESUMES_DIR))
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--bias", action="store_true")
    args = ap.parse_args()

    t0 = time.perf_counter()
    jd_text = jd_raw_text(args.jd)
    requirements = parse_jd_text(jd_text)
    print(f"\nJD → {len(requirements)} requirements")
    for r in requirements:
        print(f"  [{r.weight:<14}] {r.text}")

    resumes = parse_resumes(args.resumes)
    print(f"\nParsed {len(resumes)} resumes "
          f"({sum(len(r.chunks) for r in resumes)} evidence chunks)")

    results = run_pipeline(requirements, resumes, get_ontology())
    print(f"\nScored in {time.perf_counter() - t0:.1f}s\n")
    print(f"{'Rank':>4}  {'Candidate':<32} {'Score':>6}  {'Mand':>5}  {'Sem':>4} {'Kw':>4} {'Ev':>4}  Conf    Flags")
    for r in results:
        flags = ",".join(r.stuffing_flags)[:30]
        print(f"{r.rank:>4}  {r.name[:32]:<32} {r.final_score:>6.1f}  "
              f"{r.must_have_met}/{r.must_have_total:<3}  {r.semantic_agg*100:>4.0f} {r.keyword_agg*100:>4.0f} "
              f"{r.evidence_agg*100:>4.0f}  {r.confidence:<6}  {flags}")

    if args.explain:
        for r in results[: args.top]:
            print("\n" + generate_explanation(r, len(results)))

    if args.bias:
        print("\nJD bias / narrow-phrasing indicators:")
        for f in detect_jd_bias(requirements, jd_text) or ["  none"]:
            print("  - " + f)


if __name__ == "__main__":
    main()
