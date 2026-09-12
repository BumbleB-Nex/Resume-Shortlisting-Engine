"""
JD bias / narrow-phrasing detector — rule-based indicators only.
Flags never change the ranking; they are shown to the recruiter.
"""
from __future__ import annotations

import re

from pipeline.interfaces import Requirement
from pipeline.ontology import get_ontology

_EXCLUSIONARY = {
    "rockstar": "May discourage qualified candidates; prefer 'skilled' or 'strong'.",
    "ninja": "Informal, exclusionary jargon; prefer a plain skill description.",
    "wizard": "Informal, exclusionary jargon.",
    "guru": "Informal, exclusionary jargon.",
    "superhero": "Informal, exclusionary jargon.",
    "killer": "Aggressive phrasing.",
    "dominant": "Aggressive phrasing.",
    "aggressive": "Aggressive phrasing may deter some applicants.",
    "badass": "Informal, exclusionary jargon.",
    "young": "Age-related wording; describe the work, not the person.",
    "energetic": "Often read as an age proxy.",
    "digital native": "Often read as an age proxy.",
    "recent graduate": "Age proxy; consider 'early-career'.",
    "fresh graduate": "Age proxy; consider 'early-career'.",
    "native english": "Language-origin proxy; prefer 'fluent in English'.",
    "native speaker": "Language-origin proxy; prefer 'fluent'.",
    "he": "Gendered pronoun in a JD; prefer 'you' or 'they'.",
    "his": "Gendered pronoun in a JD; prefer 'your' or 'their'.",
    "she": "Gendered pronoun in a JD; prefer 'you' or 'they'.",
    "manpower": "Gendered term; prefer 'workforce'.",
    "guys": "Gendered term; prefer 'team'.",
    "cultural fit": "Vague and can mask affinity bias; prefer concrete behaviours.",
    "top-tier university": "Pedigree filter unrelated to ability.",
    "tier 1 college": "Pedigree filter unrelated to ability.",
    "iit": "Institution filter may exclude equally capable candidates.",
    "no gaps": "Career-gap filter may disadvantage caregivers and others.",
}
_YEARS_RE = re.compile(r"\b(\d+)\s*\+?\s*(?:years?|yrs?)\b(?:\s+of)?(?:\s+(?:hands[- ]on\s+|professional\s+|industry\s+)?experience)?(?:\s+(?:in|with)\s+([a-z0-9 .+#/-]{2,40}))?", re.I)
_VERSION_RE = re.compile(r"\b(react|python|node(?:\.js)?|django|angular|vue|java|typescript|next\.js)\s*v?(\d+(?:\.\d+)+)", re.I)
_ONLY_RE = re.compile(r"\b(only|exclusively|strictly)\s+([a-z0-9.+# ]{2,30})", re.I)


def detect_jd_bias(requirements: list[Requirement], jd_text: str) -> list[str]:
    flags: list[str] = []
    text = " " + re.sub(r"\s+", " ", jd_text.lower()) + " "
    ont = get_ontology()

    # 1. exclusionary language (whole-word match)
    for term, why in _EXCLUSIONARY.items():
        if re.search(rf"\b{re.escape(term)}\b", text):
            flags.append(f"Exclusionary/proxy wording: “{term}”. {why}")

    # 2. years-of-experience for an intern role
    for m in _YEARS_RE.finditer(jd_text):
        yrs = int(m.group(1))
        if yrs >= 1:
            phrase = m.group(0).strip()
            flags.append(f"Experience-year requirement “{phrase}” may be inappropriate for an "
                         f"internship / early-career role and can exclude capable candidates.")

    # 3. version-specific requirements
    for m in _VERSION_RE.finditer(jd_text):
        flags.append(f"Version-specific requirement “{m.group(0)}” may unnecessarily narrow the pool; "
                     f"consider stating the competency instead.")

    # 4. "only X" phrasing
    for m in _ONLY_RE.finditer(jd_text):
        flags.append(f"Restrictive phrasing “{m.group(0).strip()}” — consider whether equivalent "
                     f"technologies would satisfy the same responsibility.")

    # 5. single-vendor lock-in on must-haves where equivalents exist
    for req in requirements:
        if req.weight != "must_have" or req.category != "skill" or req.alternatives:
            continue
        canonical = ont.canonicalize(req.text)
        equivalents = [s for s, targets in ont.PARTIAL.items()
                       if canonical in targets and s not in ont.SOFT_SKILLS]
        if len(equivalents) >= 2 and canonical not in ("git", "javascript", "sql", "rest api", "html/css", "html", "css"):
            flags.append(f"Must-have “{req.label}” names one specific technology; equivalents such as "
                         f"{', '.join(e.title() for e in equivalents[:3])} may satisfy the same need. "
                         f"Consider “{req.label} or equivalent”.")

    # 6. very long must-have list
    must = [r for r in requirements if r.weight == "must_have" and r.category != "task"]
    if len(must) >= 10:
        flags.append(f"{len(must)} must-have skills is a long mandatory list for an intern role; "
                     f"research shows this disproportionately deters under-represented applicants. "
                     f"Consider moving some to 'preferred'.")

    return list(dict.fromkeys(flags))
