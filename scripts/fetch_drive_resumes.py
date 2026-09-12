"""
Download the dummy resumes from the shared Google Drive folder into
data/resumes/ (PDF + DOCX only; TXT/XML duplicates are skipped).

Run:  python scripts/fetch_drive_resumes.py [--folder FOLDER_ID] [--limit N]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import RESUMES_DIR  # noqa: E402

FOLDER_ID = "15UdJ7_R_mpBfLR-_sScTcFJIP8qkH5Pq"
_ENTRY_RE = re.compile(r'id="entry-([A-Za-z0-9_-]+)".*?flip-entry-title">([^<]+)<', re.S)


def list_folder(folder_id: str) -> list[tuple[str, str]]:
    url = f"https://drive.google.com/embeddedfolderview?id={folder_id}"
    html = requests.get(url, timeout=30).text
    return [(fid, name.strip()) for fid, name in _ENTRY_RE.findall(html)]


def download(file_id: str, dest: Path, session: requests.Session) -> bool:
    url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    for attempt in range(3):
        try:
            r = session.get(url, timeout=60)
            if r.status_code == 200 and not r.headers.get("content-type", "").startswith("text/html"):
                dest.write_bytes(r.content)
                return True
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default=FOLDER_ID)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(RESUMES_DIR))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    entries = [(fid, name) for fid, name in list_folder(args.folder)
               if name.lower().endswith((".pdf", ".docx"))]
    if args.limit:
        entries = entries[: args.limit]
    print(f"{len(entries)} PDF/DOCX files listed")

    ok = skipped = failed = 0
    with requests.Session() as s:
        for i, (fid, name) in enumerate(entries, 1):
            dest = out / name
            if dest.exists() and dest.stat().st_size > 0:
                skipped += 1
                continue
            good = download(fid, dest, s)
            ok += good
            failed += not good
            print(f"[{i}/{len(entries)}] {'ok ' if good else 'FAIL'} {name}")
    print(f"\ndone: {ok} downloaded, {skipped} already present, {failed} failed -> {out}")


if __name__ == "__main__":
    main()
