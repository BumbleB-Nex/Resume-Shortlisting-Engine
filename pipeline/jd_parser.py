"""
JD parser — turns a Job Description PDF into atomic, weighted Requirement
objects.

Strategy
  1. Regex / header-based structuring (primary, fully deterministic)
  2. Local Ollama fallback if step 1 finds too little
  3. Atomization of compound items ("REST APIs and SQL" → two requirements)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from config import (
    DERIVED_MUST_HAVE_MIN_SKILLS,
    DERIVED_TASK_MUST_HAVES,
    JD_MIN_REQUIREMENTS_BEFORE_FALLBACK,
    MAX_MUST_HAVE,
    MAX_PREFERRED,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SEC,
    OLLAMA_URL,
    REQ_IMPORTANCE,
)
from pipeline.interfaces import Requirement
from pipeline.ontology import get_ontology
from pipeline.pdf_utils import (
    clean_text,
    extract_pdf_text,
    is_bulleted,
    looks_like_header,
    strip_bullet,
)

# ── Section classification ────────────────────────────────────────
_MUST_HEADERS = [
    "requirements", "required skills", "required qualifications", "qualifications",
    "must have", "must-have", "essential skills", "essential", "minimum qualifications",
    "what we're looking for", "what we are looking for", "you have", "you should have",
    "technical requirements", "skills required", "required", "basic qualifications",
    "core skills", "key skills", "skills", "tech stack", "technical skills",
    "person specification", "knowledge and skills", "skills and experience",
    "skills & experience", "experience required", "candidate profile", "your profile",
    "who you are", "software", "tools", "technical competencies", "competencies",
    "knowledge skills and abilities", "knowledge skills & abilities", "skills and abilities",
    "skills abilities", "essential criteria", "essential requirements", "what you need",
    "what you'll need", "what you will need", "the ideal candidate", "ideal candidate",
    "requirements and qualifications", "qualifications and skills", "what we need",
    "required experience", "experience and skills", "knowledge and experience",
    "requirement", "qualification", "skill", "prerequisites", "prerequisite",
]
_PREF_HEADERS = [
    "preferred", "preferred skills", "preferred qualifications", "nice to have",
    "nice-to-have", "bonus", "bonus points", "good to have", "good-to-have",
    "desirable", "plus", "added advantage", "advantageous", "optional",
    "it would be great if", "brownie points", "stand out", "desired", "ideally",
    "extra credit", "even better if", "not required but", "what will make you stand out",
    "what would make you stand out", "additional skills", "other skills",
    "desirable criteria", "desired skills", "preferred experience", "nice to haves",
]
_RESP_HEADERS = [
    "responsibilities", "key responsibilities", "roles and responsibilities",
    "what you'll do", "what you will do", "your role", "the role", "duties",
    "day-to-day", "day to day", "you will", "job responsibilities", "what you'll be doing",
    "key accountabilities", "accountabilities", "main duties", "tasks", "scope of work",
    "what you'll work on", "deliverables", "description of work", "duties and responsibilities",
    "job duties", "essential functions", "essential duties", "primary responsibilities",
    "key duties", "role responsibilities", "responsible for", "job tasks",
    "tasks and responsibilities", "tasks & responsibilities", "responsibility", "duty",
]
_IGNORE_HEADERS = [
    "about us", "about the company", "about the role", "about", "company overview",
    "role overview", "benefits", "perks", "what we offer", "compensation", "stipend",
    "how to apply", "location", "duration", "application process", "equal opportunity",
    "why join us", "contact", "salary", "eligibility", "eligibility criteria",
    "who can apply", "overview", "job summary", "job description", "job title",
    "description", "key summary", "summary", "reports to", "department", "grade",
    "experience", "education", "our culture", "diversity", "disclaimer", "note",
    "working hours", "hours", "term", "contract", "start date", "closing date",
    # HR / government position-description boilerplate
    "ada checklist", "physical activity", "physical activities", "physical requirements",
    "physical demands", "working conditions", "work environment", "visual acuity",
    "cognitive/mental capabilities", "mental capabilities", "equal employment", "eeo",
    "license or certification", "licenses and certifications", "job purpose", "purpose",
    "position summary", "position description", "classification title", "working title",
    "employee number", "supervisor", "work schedule", "work hours", "primary purpose",
    "organizational unit", "position justification", "position number", "department/agency",
    "division", "section/unit", "training", "period", "employment agreement",
    "general availability", "emergency status", "appeals process", "resignation",
    "termination", "agreement renewal", "holiday shifts", "time-off requests",
    "outside employment", "our values", "mission", "vision", "recruitment process",
    "interview process", "next steps", "selection process", "travel requirements",
    "travel", "education and experience", "conduct history", "academic standing",
]
# a header that starts a line is recognised even when the line is long
# ("Knowledge, Skills, and Abilities Recommended in this Position") — only for
# distinctive multi-word labels so "Experience building web apps" stays content.
_MIN_PREFIX_LABEL_LEN = 15
# statements that describe the programme / candidate's journey, not a skill
_DERIVE_BLACKLIST_RE = re.compile(
    r"\b(apprenticeship|apprentice|training programme|training program|learning|"
    r"assessments? associated|working relationships?|relationships? with|"
    r"complete (?:all|the)|timescales|under supervision|develop an understanding|"
    r"gain (?:practical )?experience|probation\w*|attend\w*|onboarding|induction|"
    r"shadow(?:ing)?|mentor(?:ing|ed)?|wider organisation|wider organization|"
    r"escalating issues|escalate)\b", re.I)
# statements about the candidate's status rather than skills
_ELIGIBILITY_RE = re.compile(
    r"\b(pursuing|bachelor|master'?s?|degree|b\.?\s?tech|b\.?e\.?|m\.?\s?tech|mca|bca|"
    r"graduat\w*|availab\w*|start(?:ing)? date|cgpa|gpa|percentage|final[- ]year|"
    r"pre[- ]final|semester|university|college|full[- ]time|internship starting|"
    r"months? internship|hours per week|stipend|location|remote|relocat\w*|diploma|"
    r"institution|recogni[sz]ed|educated to|years? of (?:relevant |professional |working )?experience|"
    r"work(?:ing)? in shifts|shift(?:s| work)|salary|per annum|notice period)\b", re.I)
_NOISE_START_RE = re.compile(
    r"^(?:able to|ability to|be able to|to|preferably|ideally|including|as well as|on[- ]time|"
    r"in|with|for|of|both|either|also)\b\s*", re.I)
_VAGUE_RE = re.compile(
    r"\b(similar|related|other|another|equivalent|etc|relevant|any|comparable|alike|"
    r"more|various|modern|general)\b", re.I)
_EXAMPLE_SPLIT_RE = re.compile(
    r"\s*(?:\bsuch as\b|\blike\b|\bincluding\b|\be\.?g\.?,?|\bfor example\b|\bfor instance\b|\bespecially\b)\s*",
    re.I)

_MUST_INLINE = re.compile(
    r"\b(required|must[- ]have|must be|essential|mandatory|minimum|should have|need to have)\b", re.I)
_PREF_INLINE = re.compile(
    r"\b(preferred|nice[- ]to[- ]have|bonus|plus|good[- ]to[- ]have|advantageous|desirable|ideally|optional)\b", re.I)

# phrases that precede the actual skill in a requirement line
_LEAD_PHRASES = re.compile(
    r"^(?:(?:strong|solid|basic|good|working|hands[- ]on|prior|some|demonstrated|proven|excellent)\s+)?"
    r"(?:experience|exposure|familiarity|knowledge|understanding|proficiency|proficient|skilled|skills|"
    r"background|expertise|competence|comfort|comfortable|ability|interest|passion)\s*"
    r"(?:in|with|of|for|to|using|about|working with|building|developing)?\s*",
    re.I,
)
_TRAIL_NOISE = re.compile(
    r"\b(etc\.?|and more|or similar|or equivalent|is a plus|is preferred|is required|"
    r"preferred|required|\(.*?\))\s*$", re.I)

_PROTECTED = {"ci/cd", "html/css", "ui/ux", "tcp/ip", "c/c++", "a/b testing", "node.js",
              "next.js", "vue.js", "react.js", "express.js", "asp.net", ".net"}
_STOP_ATOMS = {"", "and", "or", "the", "a", "an", "etc", "e.g", "eg", "i.e", "such as",
               "including", "like", "more", "others", "other", "similar", "equivalent",
               "tools", "technologies", "frameworks", "languages", "skills", "concepts",
               "his", "her", "their", "his/her", "you", "your", "both", "all", "any", "key",
               "written", "oral", "verbal", "pro", "cc", "software", "packages", "solutions",
               "practice", "practices", "metrics", "results", "monitor", "manage", "evaluate them",
               "energy", "enthusiasm", "commitment", "dedication", "patience", "concentration",
               "members", "suppliers", "stakeholders", "departments", "channels", "role"}

_SPLIT_RE = re.compile(r"\s*(?:,|;|/|\band\b|\bor\b|&|\bas well as\b|\bplus\b)\s*", re.I)


# ── Public API ────────────────────────────────────────────────────
def parse_jd(pdf_path: str | Path) -> list[Requirement]:
    return parse_jd_meta(pdf_path)[0]


def parse_jd_text(text: str) -> list[Requirement]:
    """Parse already-extracted JD text (used by tests and the UI)."""
    return parse_jd_text_meta(text)[0]


def parse_jd_meta(pdf_path: str | Path) -> tuple[list[Requirement], dict]:
    """`parse_jd` plus a metadata dict (see `parse_jd_text_meta`)."""
    raw, _ = extract_pdf_text(pdf_path)
    return parse_jd_text_meta(clean_text(raw))


def parse_jd_text_meta(text: str) -> tuple[list[Requirement], dict]:
    """
    Parse JD text and return (requirements, meta). `meta` keys:
      explicit_must_have   must-haves found in an explicit requirements section
      derived_must_have    must-haves promoted from responsibilities / prose
      derived              True when the mandatory list had to be derived
      derived_terms        the promoted canonical terms
      notice               one-line human-readable note (or None)
      source               "regex" | "ollama"
    """
    global _LAST_META
    buckets = _regex_structure(text)
    source = "regex"
    total = sum(len(v) for v in buckets.values())
    if total < JD_MIN_REQUIREMENTS_BEFORE_FALLBACK:
        fallback = _ollama_structure(text)
        if fallback and sum(len(v) for v in fallback.values()) > total:
            buckets, source = fallback, "ollama"
    reqs = _build_requirements(buckets)
    explicit = sum(1 for r in reqs if r.weight == "must_have")
    meta: dict = {"explicit_must_have": explicit, "derived_must_have": 0, "derived": False,
                  "derived_terms": [], "notice": None, "source": source}
    if explicit == 0:
        derived = _derive_must_haves(reqs, buckets, text)
        if derived:
            meta.update(derived_must_have=len(derived), derived=True, derived_terms=derived)
            meta["notice"] = (f"no explicit requirements section; derived {len(derived)} "
                              f"must-haves from responsibilities")
            print(f"[jd_parser] {meta['notice']}")
        else:
            meta["notice"] = "no explicit requirements section and no core skills could be derived"
            print(f"[jd_parser] {meta['notice']}")
    _LAST_META = meta
    return reqs, meta


_LAST_META: dict = {}


def last_parse_meta() -> dict:
    """Metadata of the most recent `parse_jd*` call (empty before any parse)."""
    return dict(_LAST_META)


def jd_raw_text(pdf_path: str | Path) -> str:
    raw, _ = extract_pdf_text(pdf_path)
    return clean_text(raw)


# ── Step 1: regex structuring ─────────────────────────────────────
_LABELS: list[tuple[str, str, int]] = (
    [(l, "preferred", 0) for l in _PREF_HEADERS]
    + [(l, "responsibility", 1) for l in _RESP_HEADERS]
    + [(l, "must_have", 2) for l in _MUST_HEADERS]
    + [(l, "ignore", 3) for l in _IGNORE_HEADERS]
)


def _norm_header(line: str) -> str:
    h = strip_bullet(line).strip().rstrip(":").lower()
    h = re.sub(r"[^a-z0-9'’ /&+-]", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def _best_label(h: str) -> tuple[str, str] | None:
    """(label, kind) of the most specific header label contained in `h`."""
    hits = [(len(l), -prio, l, kind) for l, kind, prio in _LABELS if _label_in(l, h)]
    if not hits:
        return None
    _, _, label, kind = max(hits)
    return label, kind


def _label_in(label: str, h: str) -> bool:
    # whole-word containment: "term" must not match inside "terms" unless it is the same word
    return re.search(rf"(?<![a-z0-9]){re.escape(label)}(?![a-z0-9])", h) is not None


def _classify_header(line: str) -> str | None:
    h = _norm_header(line)
    if not h:
        return None
    if h.startswith(("about", "why ", "who we are", "our ")):
        return "ignore"
    if re.match(r"^\*+\s*=", line.strip()):          # "*= Required" footnote
        return "ignore"
    if _INTRO_HEADER_RE.search(line) and len(h.split()) <= 14:
        return "preferred" if _PREF_INLINE.search(line) else "must_have"
    best = _best_label(h)
    return best[1] if best else None


_PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]|\{[^}]*\}|<[^>]*>")
_INTRO_HEADER_RE = re.compile(
    r"(following (software|tools|technologies|skills|requirements)|well[- ]versed with|"
    r"proficient in the following|should have|must have|looking for|what you bring)\s*:?\s*$", re.I)
_SENTENCE_END = (".", "!", "?", ":", ";")
_OPEN_ENDINGS = (",", "(", "/", "&", " and", " or", " of", " with", " in", " to", " the", " a", " an",
                 " for", " on", " e.g.", " e.g", " eg", " including", " such as", " like", " using", " -", "–")


def _merge_wrapped_lines(text: str) -> list[str]:
    """
    Re-join PDF-wrapped lines into logical items. A line continues the
    previous one when the previous line is left "open" (no terminal
    punctuation and ends with a connector / comma / open paren) or when the
    current line starts in lower case and is not a bullet.
    """
    out: list[str] = []
    for raw in text.split("\n"):
        line = _PLACEHOLDER_RE.sub(" ", raw).strip()
        line = re.sub(r"\s{2,}", " ", line)
        if not line:
            continue
        if (out and not is_bulleted(line) and _header_kind(line) is None
                and _header_kind(out[-1]) is None and not looks_like_header(out[-1])):
            prev = out[-1]
            prev_l = prev.lower().rstrip()
            unbalanced = prev.count("(") > prev.count(")")
            abbrev_end = prev_l.endswith(("e.g.", "i.e.", "etc.", "eg.", "vs."))
            no_terminal = not prev_l.endswith(_SENTENCE_END) or abbrev_end
            # PDF wrap: previous line left open, or this line is clearly a tail fragment
            if unbalanced or line[:1].islower() or (no_terminal and (
                    prev_l.endswith(_OPEN_ENDINGS) or len(line.split()) <= 6 or len(prev) > 60)):
                out[-1] = prev + " " + line
                continue
        out.append(line)
    return out


_NUM_PREFIX_RE = re.compile(r"^\s*(?:\(?(?P<num>\d{1,2})[.)]|(?P<roman>[IVXivx]{1,4})[.)])\s+")
_TITLE_SMALL = {"and", "of", "the", "for", "to", "in", "on", "a", "an", "&", "or", "with", "at", "by"}


def _numbered_title(raw: str) -> str | None:
    """
    "II. Employment Agreement & Terms" / "1. Key Responsibilities" → "roman" | "digit"
    when the numbered remainder is a short Title-Case section title; else None.
    """
    m = _NUM_PREFIX_RE.match(raw)
    if not m:
        return None
    rest = raw[m.end():].strip().rstrip(":")
    words = rest.split()
    if not 1 <= len(words) <= 6 or re.search(r"[.;,]$|\d", rest):
        return None
    content = [w for w in words if re.search(r"[A-Za-z]", w)]
    if not content or not content[0][:1].isupper():
        return None
    if not all(w[:1].isupper() or w.lower() in _TITLE_SMALL for w in content):
        return None
    return "roman" if m.group("roman") else "digit"


def _header_kind(line: str) -> str | None:
    """
    Section kind if `line` is a header — either it *looks* like one
    (short / Title Case / colon / numbered section title) or it *is* one of
    the known labels ("Key responsibilities", "What will make you stand out",
    "Knowledge, Skills, and Abilities Recommended in this Position").
    """
    raw = line.strip()
    s = strip_bullet(raw).strip()
    if not s or len(s) > 80 or s.endswith((".", ",", ";")):
        return None
    if re.match(r"^\*+\s*=", raw):                      # "*= Required" footnote
        return "ignore"
    h = _norm_header(s)
    words = h.split()
    if not h or len(words) > 14:
        return None
    if _INTRO_HEADER_RE.search(s):                       # "…well-versed with the following software:"
        return "preferred" if _PREF_INLINE.search(s) else "must_have"
    if len(words) > 10:
        return None
    if h.startswith(("about", "why ", "who we are", "our ")) and len(words) <= 8:
        return "ignore"
    ont = get_ontology()
    numbered = _numbered_title(raw)
    best = _best_label(h)
    if best is None:
        # "II. Employment Agreement & Terms" — an unknown roman-numbered section resets context
        if numbered == "roman" and len(words) >= 2 and not ont.find_skills(s):
            return "ignore"
        return None
    label, kind = best
    coverage = len(label) / max(1, len(h))
    if coverage >= 0.6:
        return kind
    if s.endswith(":"):                                  # "The duties of the intern may include:"
        return kind
    # "Avid Compositing Software" names a tool — a header label is only incidental
    if ont.find_skills(s):
        return None
    if looks_like_header(s) or numbered is not None:
        return kind
    if h.startswith(label) and len(label) >= _MIN_PREFIX_LABEL_LEN:
        return kind
    return None


def _is_prose(content: str) -> bool:
    """Long multi-sentence paragraphs are context, not atomic requirements —
    unless they are really a comma list of known skills."""
    words = content.split()
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", content) if s.strip()]
    if not (len(words) > 28 or (len(sentences) >= 2 and len(words) > 18)):
        return False
    return len(get_ontology().find_skills(content)) < 3


def _regex_structure(text: str) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"must_have": [], "preferred": [], "responsibility": []}
    current: str | None = None
    for line in _merge_wrapped_lines(text):
        # inline "Header: content" on one line
        m = re.match(r"^([A-Za-z][A-Za-z '’/&-]{2,40}):\s*(.+)$", line)
        if m and _classify_header(m.group(1)):
            current = _classify_header(m.group(1))
            line = m.group(2).strip()
            if current in buckets and line:
                buckets[current].append(line)
            continue
        kind = _header_kind(line)
        if kind is not None:
            current = kind
            continue
        if looks_like_header(line):
            # a short Title-Case tool name inside a skills list ("Final Cut Pro") is content
            if current in ("must_have", "preferred") and (
                    get_ontology().find_skills(line) or _looks_like_tool(line)):
                buckets[current].append(strip_bullet(line))
                continue
            # unknown header — keep previous section unless clearly a new block
            if current is not None and len(line) < 25:
                current = None
                continue
        # "Candidate must be well-versed with the following software" → acts as a header
        if _INTRO_HEADER_RE.search(line) and len(line.split()) <= 14:
            current = "preferred" if _PREF_INLINE.search(line) else "must_have"
            continue
        content = strip_bullet(line)
        if len(content) < 3:
            continue
        # inline signal words override the section
        kind = current
        if _PREF_INLINE.search(content) and not _MUST_INLINE.search(content):
            kind = "preferred"
        elif _MUST_INLINE.search(content) and kind is None:
            kind = "must_have"
        if kind in ("must_have", "preferred") and _is_prose(content):
            kind = "responsibility"          # paragraph text → semantic context only
        if kind in buckets:
            buckets[kind].append(content)
    return buckets


# ── Derived must-haves (JD without a requirements section) ────────
def _derive_must_haves(reqs: list[Requirement], buckets: dict[str, list[str]], text: str) -> list[str]:
    """
    A JD that only lists responsibilities (plus "Job Purpose" prose) still
    implies mandatory skills. Run the ontology over the responsibility items
    and the remaining prose, rank concrete skills/tools by weighted frequency
    and first appearance, and promote up to MAX_MUST_HAVE of them. If fewer
    than DERIVED_MUST_HAVE_MIN_SKILLS are found, the most concrete
    responsibility items themselves become task must-haves. Mutates `reqs`
    and returns the promoted canonical terms.
    """
    ont = get_ontology()
    resp_items = [strip_bullet(i) for i in buckets.get("responsibility", [])]
    resp_set = set(resp_items)
    prose: list[str] = []
    for line in _merge_wrapped_lines(text):
        s = strip_bullet(line)
        if s in resp_set or _header_kind(line) is not None or len(s.split()) < 3:
            continue
        m = re.match(r"^([A-Za-z][A-Za-z '’/&-]{2,40}):\s*(.+)$", s)   # "Job Title: Cyber security apprentice"
        if m:
            s = m.group(2).strip()
        prose.append(s)

    scores: dict[str, float] = {}
    first_pos: dict[str, int] = {}
    origin: dict[str, str] = {}
    pos = 0
    for base_weight, lines in ((1.0, resp_items), (0.7, prose)):
        for line in lines:
            weight = base_weight
            if _ELIGIBILITY_RE.search(line) or _DERIVE_BLACKLIST_RE.search(line):
                weight *= 0.3                 # "complete the apprenticeship…" barely counts
            for skill in ont.find_skills(line):
                if ont.is_soft(skill) or skill in ont.UMBRELLA:
                    continue
                scores[skill] = scores.get(skill, 0.0) + weight
                first_pos.setdefault(skill, pos)
                origin.setdefault(skill, line)
            pos += 1

    existing = {r.text: r for r in reqs}
    covered = {a for r in reqs for a in r.alternatives}
    derived: list[str] = []
    for skill in sorted(scores, key=lambda s: (-scores[s], first_pos[s])):
        if len(derived) >= MAX_MUST_HAVE:
            break
        if skill in covered or skill in existing:
            continue                          # explicitly listed (e.g. under "Desirable") — respect the JD
        reqs.append(Requirement(
            text=skill, weight="must_have", category="skill",
            importance=REQ_IMPORTANCE["must_have"], original_text=origin[skill].strip(),
        ))
        derived.append(skill)

    if len(derived) < DERIVED_MUST_HAVE_MIN_SKILLS and DERIVED_TASK_MUST_HAVES > 0:
        derived += _promote_task_must_haves(reqs, ont, DERIVED_TASK_MUST_HAVES)

    order = {"must_have": 0, "preferred": 1, "responsibility": 2}
    reqs.sort(key=lambda r: order[r.weight])
    return derived


def _promote_task_must_haves(reqs: list[Requirement], ont, limit: int) -> list[str]:
    """Promote the most concrete responsibility items (domain nouns, no
    eligibility / training / relationship statements) to task must-haves."""
    candidates: list[tuple[float, int, Requirement]] = []
    for idx, r in enumerate(reqs):
        if r.weight != "responsibility" or r.category != "task":
            continue
        words = r.text.split()
        if not 4 <= len(words) <= 25:
            continue
        if (_ELIGIBILITY_RE.search(r.text) or _DERIVE_BLACKLIST_RE.search(r.text)
                or (_VAGUE_RE.search(r.text) and len(words) <= 6)):
            continue
        hits = ont.find_skills(r.text)
        concrete = [h for h in hits if not ont.is_soft(h)]
        # domain nouns: ontology hits, or capitalised tokens / acronyms in the original line
        proper = len(re.findall(r"\b[A-Z][A-Za-z0-9+#]{1,}\b", r.original_text[1:]))
        score = 2.0 * len(concrete) + 0.5 * min(proper, 4)
        if score <= 0:
            continue
        candidates.append((score, idx, r))
    candidates.sort(key=lambda c: (-c[0], c[1]))
    promoted: list[str] = []
    for _, _, r in candidates[:limit]:
        r.weight = "must_have"
        r.importance = REQ_IMPORTANCE["must_have"]
        promoted.append(r.text)
    return promoted


# ── Step 2: Ollama fallback (local only) ──────────────────────────
def _ollama_structure(text: str) -> dict[str, list[str]] | None:
    prompt = (
        "Extract requirements from this job description. Return ONLY valid JSON "
        "in exactly this format and nothing else:\n"
        '{"must_have": ["skill1", "skill2"], "preferred": ["skill3"], '
        '"responsibilities": ["task1"]}\n\nJob Description:\n' + text[:6000]
    )
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0}},
            timeout=OLLAMA_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        body = resp.json().get("response", "")
        start, end = body.find("{"), body.rfind("}")
        data = json.loads(body[start:end + 1])
        return {
            "must_have": [str(x) for x in data.get("must_have", [])],
            "preferred": [str(x) for x in data.get("preferred", [])],
            "responsibility": [str(x) for x in data.get("responsibilities", [])],
        }
    except Exception as exc:  # noqa: BLE001 — fallback must never crash the app
        print(f"[jd_parser] Ollama fallback unavailable: {exc}")
        return None


# ── Step 3: atomization + Requirement objects ─────────────────────
def _strip_lead(item: str) -> str:
    s = item.strip().strip(".;:")
    prev = None
    while prev != s:
        prev = s
        s = _LEAD_PHRASES.sub("", s, count=1).strip()
        s = re.sub(r"^(?:of|in|with|using|the|a|an)\s+", "", s, flags=re.I).strip()
    s = _TRAIL_NOISE.sub("", s).strip(" .;:,-")
    return s


Atom = tuple[str, list[str], str]          # (text, alternatives, category)

_FUNCTION_WORDS = {"a", "an", "the", "of", "for", "to", "in", "on", "at", "with", "and", "or",
                   "as", "by", "from", "into", "is", "are", "be", "that", "this", "very", "under"}
_GENERIC_WORDS = {
    "skills", "skill", "ability", "abilities", "knowledge", "experience", "understanding",
    "strong", "good", "excellent", "keen", "eye", "detail", "mind", "interest", "passion",
    "level", "high", "approach", "attitude", "work", "working", "team", "teams", "part",
    "well", "others", "ideas", "projects", "complete", "pressure", "deadlines", "key",
    "product", "results", "quality", "delivery", "role", "candidate", "required", "ensure",
}


def _looks_like_tool(original: str) -> bool:
    """
    Does this (original-cased) phrase look like a named technology/tool rather
    than a generic ability?  Proper nouns after the first word, acronyms,
    digits/dots/plus signs, or a single capitalised token all count.
    """
    s = original.strip(" .;:,-")
    words = s.split()
    if not words or len(words) > 5:
        return False
    if re.search(r"[0-9.+#/]", s) and not re.search(r"\b(\d+\+?\s*years?)\b", s, re.I):
        return True
    if any(w.isupper() and len(w) >= 2 for w in words):
        return True
    caps = [w for w in words[1:] if w[:1].isupper()]
    if caps:
        return True
    if len(words) == 1 and words[0][:1].isupper():
        return True
    return False


def _or_groups(segment: str, ont) -> list[list[str]]:
    """
    Split a segment on ',', ';', 'and' and keep 'X or Y' together so that
    "React or Vue, Node.js and Express" → [[react, vue], [node.js], [express]].
    """
    groups: list[list[str]] = []
    for piece in re.split(r"\s*(?:,|;|\band\b|&|\bas well as\b|\bplus\b)\s*", segment, flags=re.I):
        skills = ont.find_skills(piece)
        if not skills:
            continue
        if re.search(r"\bor\b|/", piece) and len(skills) > 1:
            groups.append(skills)
        else:
            groups += [[s] for s in skills]
    return groups


def _atomize(item: str) -> list[Atom]:
    """
    Turn one requirement line into atomic requirements.

    1. Strip lead phrases ("Experience with …").
    2. Drop eligibility statements (degree, availability…).
    3. Pull out soft skills (never mandatory).
    4. Extract known skills from the ontology; "X or Y" and "… such as A or B"
       become ONE requirement with alternatives.
    5. If no known skill is present, fall back to the cleaned phrase (tool/task),
       discarding vague fragments ("similar framework", "related field").
    """
    ont = get_ontology()
    core = _strip_lead(item)
    if not core:
        return []
    if _ELIGIBILITY_RE.search(core) and not ont.find_skills(core):
        return []

    atoms: list[Atom] = []
    soft = [s for s in ont.find_skills(core) if ont.is_soft(s)]
    for s in soft:
        atoms.append((s, [], "soft"))

    # split "head such as examples"
    parts = _EXAMPLE_SPLIT_RE.split(core, maxsplit=1)
    head, examples = parts[0], (parts[1] if len(parts) > 1 else "")
    # parentheticals behave like examples: "JavaScript (ES6+)", "SQL (PostgreSQL/MySQL)"
    for paren in re.findall(r"\(([^)]*)\)", head):
        examples = (examples + " , " + paren) if examples else paren
    head = re.sub(r"\([^)]*\)", " ", head)

    head_groups = [g for g in _or_groups(head, ont) if not all(ont.is_soft(s) for s in g)]
    example_skills = [s for s in ont.find_skills(examples) if not ont.is_soft(s)]

    # umbrella terms ("backend development") are redundant next to a concrete skill
    specific = [g for g in head_groups if g[0] not in ont.UMBRELLA]
    if specific:
        head_groups = specific
    # html + css on one line → html/css
    for pair, merged in ont.MERGE.items():
        heads = [g[0] for g in head_groups]
        if pair.issubset(heads):
            first = min(heads.index(p) for p in pair)
            head_groups = [g for g in head_groups if g[0] not in pair]
            head_groups.insert(first, [merged])

    if head_groups:
        for i, group in enumerate(head_groups):
            alts = list(dict.fromkeys(group[1:]))
            if i == len(head_groups) - 1:                    # examples qualify the last head skill
                alts += [s for s in example_skills if s not in alts and s != group[0]]
            atoms.append((group[0], alts, "skill"))
    elif example_skills:
        atoms.append((example_skills[0], example_skills[1:], "skill"))
    elif not soft:
        # no known skills — keep the cleaned phrase(s), classified by how they look
        text = re.sub(r"\(([^)]*)\)", r" , \1 , ", core)      # parenthetical examples become items
        for piece in re.split(r"\s*(?:,|;|\band\b|\bor\b|&|/|\be\.?g\.?\b|\bsuch as\b|\blike\b)\s*",
                              text, flags=re.I):
            orig = _strip_lead(piece).strip(" .;:-")
            orig = _NOISE_START_RE.sub("", orig).strip(" .;:-")
            p = ont.normalize(orig)
            words = p.split()
            if not p or p in _STOP_ATOMS or len(p) < 3 or len(words) > 12:
                continue
            if _VAGUE_RE.search(p) and len(words) <= 4:
                continue
            if all(w in _GENERIC_WORDS or w in _STOP_ATOMS or w in _FUNCTION_WORDS for w in words):
                continue                                  # "keen eye for detail", "high level"
            if _ELIGIBILITY_RE.search(p):
                continue
            if _looks_like_tool(orig):
                atoms.append((p, [], "tool"))            # "Snowflake", "Final Cut Pro", "Adobe Premiere Pro"
            elif 3 <= len(words) <= 8 and not all(w in _FUNCTION_WORDS or w in _GENERIC_WORDS for w in words):
                atoms.append((p, [], "task"))            # "translate ideas into complete projects"
            # unknown 1–2 word generic fragments ("establish", "budget") carry no signal — dropped
    return atoms


def _build_requirements(buckets: dict[str, list[str]]) -> list[Requirement]:
    ont = get_ontology()
    reqs: list[Requirement] = []
    seen: dict[str, Requirement] = {}
    for weight in ("must_have", "preferred", "responsibility"):
        for item in buckets.get(weight, []):
            if weight == "responsibility":
                text = ont.normalize(strip_bullet(item)).strip(" .")
                if len(text.split()) < 3 or len(text.split()) > 40:
                    continue
                atoms: list[Atom] = [(text, [], "task")]
            else:
                atoms = _atomize(item)
            for text, alts, category in atoms:
                if not text:
                    continue
                # only concrete skills / named tools can gate a candidate as must-haves;
                # soft skills and free-text abilities are scored as preferred
                req_weight = weight if category in ("skill", "tool") else (
                    "preferred" if weight != "responsibility" else weight)
                if text in seen:
                    # merge alternatives into the earlier (higher-priority) requirement
                    for a in alts:
                        if a not in seen[text].alternatives and a != seen[text].text:
                            seen[text].alternatives.append(a)
                    continue
                # a skill already covered as an alternative of an earlier requirement is skipped
                if any(text in r.alternatives for r in seen.values()):
                    continue
                req = Requirement(
                    text=text,
                    weight=req_weight,
                    category=category,
                    importance=REQ_IMPORTANCE[req_weight],
                    original_text=item.strip(),
                    alternatives=[a for a in alts if a not in seen],
                )
                seen[text] = req
                reqs.append(req)
    # cap the mandatory list: known ontology skills stay, overflow tools become preferred
    must = [r for r in reqs if r.weight == "must_have"]
    if len(must) > MAX_MUST_HAVE:
        must.sort(key=lambda r: (r.category != "skill", len(r.text)))
        for r in must[MAX_MUST_HAVE:]:
            r.weight = "preferred"
            r.importance = REQ_IMPORTANCE["preferred"]
    # cap the preferred list: ontology-known skills first, then named tools, then free text;
    # the overflow is kept as responsibility context rather than dropped
    pref = [r for r in reqs if r.weight == "preferred"]
    if len(pref) > MAX_PREFERRED:
        pref.sort(key=lambda r: (not ont.is_known_skill(r.text), r.category == "task",
                                 r.category == "soft", len(r.text)))
        for r in pref[MAX_PREFERRED:]:
            r.weight = "responsibility"
            r.importance = REQ_IMPORTANCE["responsibility"]
    order = {"must_have": 0, "preferred": 1, "responsibility": 2}
    reqs.sort(key=lambda r: order[r.weight])
    return reqs
