"""
Per-session inputs — uploaded JD + resumes live in a temporary folder that is
deleted on Reset / re-run / interpreter exit. Nothing is written under data/.

The pipeline itself is untouched: this module only persists the uploads and
calls the existing parsers / matcher on exactly those files.
"""
from __future__ import annotations

import atexit
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from pipeline.interfaces import Requirement
from pipeline.jd_parser import jd_raw_text, parse_jd_text
from pipeline.ontology import get_ontology
from pipeline.resume_parser import parse_resumes
from pipeline.scorer import MatchState, build_match_state

SUPPORTED_TYPES = ["pdf", "docx", "txt"]


class UploadLike(Protocol):
    """Anything with a file name and a bytes buffer (st.UploadedFile, BytesIO, ...)."""
    name: str

    def getbuffer(self): ...


@dataclass
class Session:
    tmp_dir: Path
    jd_name: str
    jd_text: str
    requirements: list[Requirement]
    state: MatchState
    n_uploaded: int
    elapsed: float

    @property
    def n_parsed(self) -> int:
        return len(self.state.resumes)


_TMP_DIRS: set[str] = set()


def new_tmp_dir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="shortlist_"))
    _TMP_DIRS.add(str(d))
    return d


def remove_dir(path: Path | str | None) -> None:
    if not path:
        return
    shutil.rmtree(path, ignore_errors=True)
    _TMP_DIRS.discard(str(path))


def _cleanup_all() -> None:
    for d in list(_TMP_DIRS):
        shutil.rmtree(d, ignore_errors=True)


atexit.register(_cleanup_all)


def _safe_name(name: str, folder: Path) -> Path:
    base = Path(name).name or "file"
    target = folder / base
    n = 2
    while target.exists():                      # two uploads with the same file name
        target = folder / f"{Path(base).stem}_{n}{Path(base).suffix}"
        n += 1
    return target


def persist_uploads(jd_file: UploadLike, resume_files: Iterable[UploadLike], tmp_dir: Path) -> tuple[Path, Path]:
    """Write the uploads into <tmp_dir>/jd and <tmp_dir>/resumes; return (jd_path, resumes_dir)."""
    jd_dir, res_dir = tmp_dir / "jd", tmp_dir / "resumes"
    jd_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)
    jd_path = _safe_name(jd_file.name, jd_dir)
    jd_path.write_bytes(jd_file.getbuffer())
    for f in resume_files:
        _safe_name(f.name, res_dir).write_bytes(f.getbuffer())
    return jd_path, res_dir


def build_session(jd_path: Path, resumes_dir: Path, tmp_dir: Path, n_uploaded: int) -> Session:
    """Parse + match exactly the files in the temp folder (fresh BM25 corpus, fresh match state)."""
    t0 = time.perf_counter()
    jd_text = jd_raw_text(str(jd_path))
    requirements = parse_jd_text(jd_text)
    resumes = parse_resumes(resumes_dir)
    state = build_match_state(requirements, resumes, get_ontology())
    return Session(tmp_dir=tmp_dir, jd_name=jd_path.name, jd_text=jd_text, requirements=requirements,
                   state=state, n_uploaded=n_uploaded, elapsed=time.perf_counter() - t0)


def run_from_uploads(jd_file: UploadLike, resume_files: list[UploadLike]) -> Session:
    """Convenience: new temp dir → persist → build. Caller owns cleanup via remove_dir(session.tmp_dir)."""
    tmp = new_tmp_dir()
    try:
        jd_path, res_dir = persist_uploads(jd_file, resume_files, tmp)
        return build_session(jd_path, res_dir, tmp, len(resume_files))
    except Exception:
        remove_dir(tmp)
        raise
