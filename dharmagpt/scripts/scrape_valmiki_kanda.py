"""
scrape_valmiki_kanda.py
=======================
Scrape Valmiki Ramayana kanda pages from valmikiramayan.net into
data/chunks/valmiki_ramayanam/<kanda>_chunks.jsonl using the existing raw schema.

Usage:
    python scripts/scrape_valmiki_kanda.py --kanda bala
    python scripts/scrape_valmiki_kanda.py --kanda aranya --overwrite
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
OUT_DIR = REPO_ROOT / "data" / "chunks" / "valmiki_ramayanam"

BASE_URL = "https://www.valmikiramayan.net/utf8"
USER_AGENT = "Mozilla/5.0 (compatible; DharmaGPT-Scraper/1.0)"

KANDA_MAP = {
    "bala": {"name": "Bala Kanda", "dir": "baala"},
    "ayodhya": {"name": "Ayodhya Kanda", "dir": "ayodhya"},
    "aranya": {"name": "Aranya Kanda", "dir": "aranya"},
    "kishkindha": {"name": "Kishkindha Kanda", "dir": "kish"},
    "sundara": {"name": "Sundara Kanda", "dir": "sundara"},
    "yuddha": {"name": "Yuddha Kanda", "dir": "yuddha"},
}


def _clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_segments(page_text: str) -> list[str]:
    """
    Extract coarse verse/commentary segments from page text.
    We split on "Verse Locator" and keep content-only chunks.
    """
    if "Verse Locator" not in page_text:
        return []

    parts = page_text.split("Verse Locator")
    segments: list[str] = []

    # Optional intro before first locator
    intro = _clean_text(parts[0])
    if intro and len(intro.split()) >= 20:
        segments.append(intro)

    for part in parts[1:]:
        candidate = _clean_text(part)
        if not candidate:
            continue
        if len(candidate.split()) < 18:
            continue
        segments.append(candidate)

    return segments


def _extract_paragraph_segments(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text, "lxml")
    paragraphs: list[str] = []

    # These classes are used by valmikiramayan prose pages.
    for p in soup.select("p.txt, p.tat"):
        cleaned = _clean_text(p.get_text(" ", strip=True))
        if cleaned and len(cleaned.split()) >= 12:
            paragraphs.append(cleaned)

    # Fallback for pages that don't expose expected classes.
    if not paragraphs:
        for p in soup.find_all("p"):
            cleaned = _clean_text(p.get_text(" ", strip=True))
            if cleaned and len(cleaned.split()) >= 12:
                paragraphs.append(cleaned)

    # Last fallback: coarse split by locator markers.
    if not paragraphs:
        raw = _clean_text(soup.get_text(" ", strip=True))
        paragraphs = _extract_segments(raw)

    return paragraphs


def _find_prose_href(index_html: str) -> str | None:
    soup = BeautifulSoup(index_html, "lxml")
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if href.lower().endswith("_prose.htm"):
            return href
    return None


def _fetch_sarga(session: requests.Session, kanda_dir: str, sarga: int, timeout: int) -> tuple[str | None, str | None]:
    index_url = f"{BASE_URL}/{kanda_dir}/sarga{sarga}/"
    resp = session.get(index_url, timeout=timeout)
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()

    prose_href = _find_prose_href(resp.text)
    if not prose_href:
        return None, None

    prose_url = index_url + prose_href
    prose_resp = session.get(prose_url, timeout=timeout)
    if prose_resp.status_code == 404:
        return None, None
    prose_resp.raise_for_status()

    return prose_resp.text, prose_url


def scrape_kanda(kanda_slug: str, timeout: int, sleep_sec: float) -> list[dict]:
    if kanda_slug not in KANDA_MAP:
        raise ValueError(f"Unsupported kanda '{kanda_slug}'. Supported: {', '.join(sorted(KANDA_MAP))}")

    display_name = KANDA_MAP[kanda_slug]["name"]
    kanda_dir = KANDA_MAP[kanda_slug]["dir"]
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    records: list[dict] = []
    consecutive_misses = 0
    sarga = 1

    while sarga <= 200:
        try:
            page_html, prose_url = _fetch_sarga(session, kanda_dir, sarga, timeout)
        except requests.RequestException as exc:
            print(f"  [warn] {kanda_slug} sarga {sarga}: request failed ({exc})")
            consecutive_misses += 1
            if consecutive_misses >= 6:
                break
            sarga += 1
            continue

        if not page_html:
            consecutive_misses += 1
            if consecutive_misses >= 6:
                break
            sarga += 1
            continue

        consecutive_misses = 0
        segments = _extract_paragraph_segments(page_html)
        if not segments:
            sarga += 1
            time.sleep(sleep_sec)
            continue

        for verse_index, segment in enumerate(segments, start=1):
            source_url = prose_url or f"{BASE_URL}/{kanda_dir}/sarga{sarga}/"
            record = {
                "id": f"{kanda_slug}_kanda_s{sarga:03d}_v{verse_index:03d}",
                "text": segment,
                "metadata": {
                    "source": "Valmiki Ramayana",
                    "source_url": "https://www.valmikiramayan.net",
                    "kanda": display_name,
                    "sarga": sarga,
                    "verse_index": verse_index,
                    "citation": f"Valmiki Ramayana, {display_name}, Sarga {sarga}, ~Verse {verse_index}",
                    "url": source_url,
                    "source_type": "text",
                    "characters": [],
                    "themes": [],
                    "word_count": len(segment.split()),
                    "char_count": len(segment),
                },
            }
            records.append(record)

        print(f"  [ok] {kanda_slug} sarga {sarga}: {len(segments)} chunks")
        sarga += 1
        time.sleep(sleep_sec)

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Valmiki Ramayana kanda into raw chunk JSONL")
    parser.add_argument("--kanda", required=True, choices=sorted(KANDA_MAP.keys()))
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output file if non-empty")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between sarga requests")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"{args.kanda}_chunks.jsonl"

    if out_file.exists() and out_file.stat().st_size > 0 and not args.overwrite:
        print(f"Skip: {out_file} is non-empty. Use --overwrite to replace.")
        return

    print(f"Scraping {args.kanda} kanda...")
    records = scrape_kanda(args.kanda, timeout=args.timeout, sleep_sec=args.sleep)
    if not records:
        raise RuntimeError(f"No records scraped for {args.kanda}")

    with out_file.open("w", encoding="utf-8") as f:
        for obj in records:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"Done: wrote {len(records)} records to {out_file}")


if __name__ == "__main__":
    main()
