"""
Resume parser — PDF → cleaned text → sections → evidence chunks with metadata.

Tolerates messy resumes: fuzzy header matching ("WHAT I KNOW" → skills),
mixed bullet styles, varied date formats, missing sections.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from rapidfuzz import fuzz, process

from config import (
    FUZZY_HEADER_CUTOFF,
    MIN_CHUNK_CHARS,
    RECENCY_DECAY_PER_YEAR,
    RECENCY_DEFAULT,
    RECENCY_MIN,
    SECTION_WEIGHT,
)
from pipeline.interfaces import EvidenceChunk, Resume
from pipeline.pdf_utils import (
    BULLET_CHARS,
    SUPPORTED_SUFFIXES,
    clean_text,
    extract_pdf_text,
    is_contact_line,
    looks_like_header,
    strip_bullet,
    strip_contacts,
)

SECTION_LABELS: dict[str, list[str]] = {
    "skills": ["skills", "technical skills", "technologies", "tech stack", "my tech stack",
               "competencies", "core competencies", "tools", "tools and technologies",
               "what i know", "expertise", "programming languages", "languages and tools",
               "technical proficiency", "technical expertise", "stack", "skill set",
               "key skills", "technical summary", "areas of expertise", "toolbox",
               "languages", "frameworks", "software skills", "it skills"],
    "experience": ["experience", "work experience", "employment", "employment history",
                   "professional experience", "work history", "career", "career history",
                   "internships", "internship", "internship experience", "professional journey",
                   "where i've worked", "positions held", "relevant experience", "roles"],
    "projects": ["projects", "personal projects", "key projects", "academic projects",
                 "portfolio", "work samples", "what i've built", "stuff i've built",
                 "things i built", "selected projects", "side projects", "project work",
                 "technical projects", "notable projects", "open source", "hackathons",
                 "hackathon projects", "capstone project", "mini projects", "major projects"],
    "education": ["education", "academic background", "qualifications", "degrees",
                  "academics", "academic qualifications", "educational background",
                  "education and training", "schooling", "academic history", "studies"],
    "certifications": ["certifications", "certificates", "courses", "training",
                       "achievements", "awards", "honors", "honours", "accomplishments",
                       "licenses", "online courses", "coursework", "relevant coursework",
                       "awards and achievements", "extracurricular", "extra curricular",
                       "activities", "publications", "volunteering", "volunteer experience",
                       "positions of responsibility", "leadership"],
    "summary": ["summary", "objective", "about", "profile", "about me", "career objective",
                "introduction", "professional summary", "overview", "bio", "who am i",
                "personal statement", "career summary", "highlights", "personal profile",
                "hobbies", "interests", "hobbies and interests", "personal details",
                "declaration", "references"],
}
_LABEL_TO_SECTION = {label: sec for sec, labels in SECTION_LABELS.items() for label in labels}
_ALL_LABELS = list(_LABEL_TO_SECTION)

ACTION_VERBS = {
    "built", "build", "developed", "develop", "designed", "design", "implemented", "implement",
    "created", "create", "deployed", "deploy", "optimized", "optimised", "led", "lead",
    "engineered", "architected", "integrated", "automated", "constructed", "delivered",
    "wrote", "established", "launched", "managed", "contributed", "maintained", "improved",
    "reduced", "increased", "mentored", "collaborated", "migrated", "refactored", "tested",
    "debugged", "shipped", "scaled", "trained", "analyzed", "analysed", "configured",
    "programmed", "coded", "prototyped", "researched", "presented", "won", "achieved",
    "handled", "worked on", "responsible for", "spearheaded", "streamlined", "resolved",
}
_VERB_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, ACTION_VERBS), key=len, reverse=True)) + r")\b", re.I)
_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")
_PRESENT_RE = re.compile(r"\b(present|current|currently|ongoing|till date|to date|now)\b", re.I)
_DATE_LINE_RE = re.compile(
    r"(\b(19[89]\d|20[0-4]\d)\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{2,4}|"
    r"\b\d{1,2}/\d{2,4}\b|present)", re.I)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z•\-–])")
_BULLET_START_RE = re.compile(r"^[" + re.escape(BULLET_CHARS) + r"]\s*")


def parse_resumes(folder_path: str | Path) -> list[Resume]:
    folder = Path(folder_path)
    files = sorted((p for p in folder.iterdir()
                    if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES),
                   key=lambda p: p.name.lower())

    # The same resume is often present twice (e.g. "X.pdf" and "X.docx").
    # Keep one copy per stem so a candidate is not ranked twice; prefer the
    # format that extracts most reliably.
    preference = {s: i for i, s in enumerate(SUPPORTED_SUFFIXES)}
    by_stem: dict[str, Path] = {}
    for f in files:
        key = f.stem.lower()
        cur = by_stem.get(key)
        if cur is None or preference[f.suffix.lower()] < preference[cur.suffix.lower()]:
            by_stem[key] = f
    files = sorted(by_stem.values(), key=lambda p: p.name.lower())

    resumes: list[Resume] = []
    seen_ids: set[str] = set()
    for f in files:
        try:
            resume = parse_single_resume(f)
        except Exception as exc:  # noqa: BLE001 — one bad PDF must not kill the batch
            print(f"[resume_parser] failed on {f.name}: {exc}")
            continue
        # Guarantee unique IDs (UI widget keys depend on them).
        base, cid, n = resume.candidate_id, resume.candidate_id, 2
        while cid in seen_ids:
            cid, n = f"{base}_{n}", n + 1
        resume.candidate_id = cid
        seen_ids.add(cid)
        resumes.append(resume)
    return resumes


def parse_single_resume(pdf_path: str | Path) -> Resume:
    path = Path(pdf_path)
    raw, quality = extract_pdf_text(path)
    text = clean_text(raw)
    return parse_resume_text(text, candidate_id=path.stem, extraction_quality=quality)


def parse_resume_text(text: str, candidate_id: str, extraction_quality: float = 1.0) -> Resume:
    lines = [l for l in text.split("\n") if l.strip()]
    display_name = _guess_name(lines)
    sectioned = _assign_sections(lines)
    chunks = _chunk(sectioned)
    full_text = strip_contacts(" ".join(l for l in lines)).lower()
    return Resume(
        candidate_id=candidate_id,
        full_text=full_text,
        chunks=chunks,
        extraction_quality=extraction_quality,
        display_name=display_name,
    )


# ── helpers ────────────────────────────────────────────────────────
def _guess_name(lines: list[str]) -> str:
    for line in lines[:4]:
        s = strip_bullet(line)
        if is_contact_line(s) or len(s) > 40 or _match_header(s):
            continue
        words = s.replace(",", " ").split()
        if 1 < len(words) <= 4 and all(w[:1].isalpha() for w in words) and not re.search(r"\d", s):
            return s.title() if s.isupper() else s
    return ""


def _match_header(line: str) -> str | None:
    """Return canonical section if the line is a recognisable section header."""
    s = strip_bullet(line).rstrip(":").strip()
    s_norm = re.sub(r"[^a-z' ]", " ", s.lower())
    s_norm = re.sub(r"\s+", " ", s_norm).strip()
    if not s_norm or len(s_norm.split()) > 5:
        return None
    if s_norm in _LABEL_TO_SECTION:
        return _LABEL_TO_SECTION[s_norm]
    if not looks_like_header(s):
        return None
    hit = process.extractOne(s_norm, _ALL_LABELS, scorer=fuzz.WRatio, score_cutoff=FUZZY_HEADER_CUTOFF)
    if hit:
        return _LABEL_TO_SECTION[hit[0]]
    # partial containment, e.g. "TECHNICAL SKILLS & TOOLS"
    for label in sorted(_ALL_LABELS, key=len, reverse=True):
        if len(label) >= 5 and re.search(rf"\b{re.escape(label)}\b", s_norm):
            return _LABEL_TO_SECTION[label]
    return None


def _assign_sections(lines: list[str]) -> list[tuple[str, str, float]]:
    """Return list of (section, line, recency_weight)."""
    out: list[tuple[str, str, float]] = []
    section = "other"
    recency = RECENCY_DEFAULT
    this_year = date.today().year
    for line in lines:
        # inline "Skills: Python, SQL"
        m = re.match(r"^([A-Za-z][A-Za-z &'’/-]{2,35}):\s*(.+)$", line)
        if m:
            sec = _match_header(m.group(1))
            if sec:
                section = sec
                line = m.group(2)
                if is_contact_line(line):
                    continue
                out.append((section, line, recency))
                continue
        sec = _match_header(line)
        if sec:
            section = sec
            recency = RECENCY_DEFAULT
            continue
        if is_contact_line(line):
            continue
        # update recency when a dated entry begins (experience / projects / education)
        if _DATE_LINE_RE.search(line):
            years = [int(y) for y in _YEAR_RE.findall(line)]
            if _PRESENT_RE.search(line):
                years.append(this_year)
            if years:
                latest = max(years)
                recency = max(RECENCY_MIN, 1.0 - RECENCY_DECAY_PER_YEAR * max(0, this_year - latest))
        out.append((section, line, recency))
    return out


def _chunk(sectioned: list[tuple[str, str, float]]) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    buffer: list[str] = []
    buf_meta: tuple[str, float] | None = None

    def flush() -> None:
        nonlocal buffer, buf_meta
        if buffer and buf_meta:
            text = " ".join(buffer).strip()
            sec, rec = buf_meta
            for piece in _split_sentences(text, sec):
                _append(chunks, piece, sec, rec)
        buffer, buf_meta = [], None

    for sec, line, rec in sectioned:
        is_bullet = bool(_BULLET_START_RE.match(line))
        content = strip_bullet(line)
        if sec == "skills":
            # skills lines are lists; keep each line as its own chunk
            flush()
            _append(chunks, content, sec, rec)
            continue
        if is_bullet or buf_meta is None or buf_meta[0] != sec or _DATE_LINE_RE.search(line):
            flush()
            buffer, buf_meta = [content], (sec, rec)
        else:
            # continuation of a PDF-wrapped line: previous line left open and this
            # one starts in lower case (a new bullet/sentence starts with a capital)
            prev = buffer[-1] if buffer else ""
            wrapped = (prev and not prev.endswith((".", ":", ";", "!", "?")) and len(prev) > 40
                       and (content[:1].islower() or prev.endswith((",", "-", " and", " or", " with", " of"))))
            if wrapped:
                buffer.append(content)
            else:
                flush()
                buffer, buf_meta = [content], (sec, rec)
    flush()
    return chunks


def _split_sentences(text: str, section: str) -> list[str]:
    if len(text) <= 220:
        return [text]
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [p for p in parts if p.strip()] or [text]


def _append(chunks: list[EvidenceChunk], text: str, section: str, recency: float) -> None:
    text = text.strip(" \t" + BULLET_CHARS).strip()
    if len(text) < MIN_CHUNK_CHARS:
        return
    chunks.append(EvidenceChunk(
        text=text,
        section=section,
        section_weight=SECTION_WEIGHT.get(section, SECTION_WEIGHT["other"]),
        has_action_verb=bool(_VERB_RE.search(text)),
        is_quantified=bool(re.search(r"\d", text)),
        recency_weight=recency,
    ))
