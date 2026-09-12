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
    JD_MIN_REQUIREMENTS_BEFORE_FALLBACK,
    MAX_MUST_HAVE,
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
]
_PREF_HEADERS = [
    "preferred", "preferred skills", "preferred qualifications", "nice to have",
    "nice-to-have", "bonus", "bonus points", "good to have", "good-to-have",
    "desirable", "plus", "added advantage", "advantageous", "optional",
    "it would be great if", "brownie points", "stand out", "desired", "ideally",
    "extra credit", "even better if", "not required but", "what will make you stand out",
    "what would make you stand out", "additional skills", "other skills",
]
_RESP_HEADERS = [
    "responsibilities", "key responsibilities", "roles and responsibilities",
    "what you'll do", "what you will do", "your role", "the role", "duties",
    "day-to-day", "day to day", "you will", "job responsibilities", "what you'll be doing",
    "key accountabilities", "accountabilities", "main duties", "tasks", "scope of work",
    "what you'll work on", "deliverables",
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
]
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
    raw, _ = extract_pdf_text(pdf_path)
    text = clean_text(raw)
    return parse_jd_text(text)


def parse_jd_text(text: str) -> list[Requirement]:
    """Parse already-extracted JD text (used by tests and the UI)."""
    buckets = _regex_structure(text)
    total = sum(len(v) for v in buckets.values())
    if total < JD_MIN_REQUIREMENTS_BEFORE_FALLBACK:
        fallback = _ollama_structure(text)
        if fallback and sum(len(v) for v in fallback.values()) > total:
            buckets = fallback
    return _build_requirements(buckets)


def jd_raw_text(pdf_path: str | Path) -> str:
    raw, _ = extract_pdf_text(pdf_path)
    return clean_text(raw)


# ── Step 1: regex structuring ─────────────────────────────────────
def _classify_header(line: str) -> str | None:
    h = line.strip().rstrip(":").lower()
    h = re.sub(r"[^a-z0-9'’ /&-]", " ", h)
    h = re.sub(r"\s+", " ", h).strip()
    if not h:
        return None
    if h.startswith(("about", "why ", "who we are", "our ")):
        return "ignore"
    for label in _PREF_HEADERS:          # preferred before must (e.g. "preferred skills" vs "skills")
        if label in h:
            return "preferred"
    for label in _RESP_HEADERS:
        if label in h:
            return "responsibility"
    for label in _MUST_HEADERS:
        if label in h:
            return "must_have"
    for label in _IGNORE_HEADERS:
        if label in h:
            return "ignore"
    return None


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


def _header_kind(line: str) -> str | None:
    """
    Section kind if `line` is a header — either it *looks* like one
    (short / Title Case / colon) or it *is* one of the known labels
    ("Key responsibilities", "What will make you stand out").
    """
    s = strip_bullet(line).strip()
    if not s or len(s) > 60 or s.endswith((".", ",", ";")):
        return None
    h = re.sub(r"[^a-z0-9'’ /&-]", " ", s.lower())
    h = re.sub(r"\s+", " ", h).strip()
    if len(h.split()) > 8:
        return None
    kind = _classify_header(s)
    if kind is None:
        return None
    labels = _PREF_HEADERS + _RESP_HEADERS + _MUST_HEADERS + _IGNORE_HEADERS
    best = max((len(l) for l in labels if l in h), default=0)
    coverage = best / max(1, len(h))
    # "Avid Compositing Software" names a tool — a header label is only incidental
    if coverage < 0.6 and get_ontology().find_skills(s):
        return None
    if looks_like_header(s) or coverage >= 0.6:
        return kind
    return None


def _is_prose(content: str) -> bool:
    """Long multi-sentence paragraphs are context, not atomic requirements."""
    words = content.split()
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", content) if s.strip()]
    return len(words) > 28 or (len(sentences) >= 2 and len(words) > 18)


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
    order = {"must_have": 0, "preferred": 1, "responsibility": 2}
    reqs.sort(key=lambda r: order[r.weight])
    return reqs
