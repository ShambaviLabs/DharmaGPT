"""
scripts/scraper/valmiki_scraper.py

Scrapes https://www.valmikiramayan.net for all 7 Kandas.
Outputs one JSONL file per kanda under data/chunks/.
Each line = one chunk with text + rich metadata, ready for embedding.

Usage:
    pip install requests beautifulsoup4 tqdm
    python scripts/scraper/valmiki_scraper.py --kanda sundara
    python scripts/scraper/valmiki_scraper.py --kanda all
"""

import requests
import time
import json
import re
import argparse
from pathlib import Path
from bs4 import BeautifulSoup
from tqdm import tqdm

KANDA_CONFIG = {
    "bala":      {"slug": "bala",      "name": "Bala Kanda",      "sargas": 77,  "prefix": "bala"},
    "ayodhya":   {"slug": "ayodhya",   "name": "Ayodhya Kanda",   "sargas": 119, "prefix": "ayodhya"},
    "aranya":    {"slug": "aranya",    "name": "Aranya Kanda",    "sargas": 75,  "prefix": "aranya"},
    "kishkindha":{"slug": "kishkindha","name": "Kishkindha Kanda","sargas": 67,  "prefix": "kishkindha"},
    "sundara":   {"slug": "sundara",   "name": "Sundara Kanda",   "sargas": 68,  "prefix": "sundara"},
    "yuddha":    {"slug": "yuddha",    "name": "Yuddha Kanda",    "sargas": 128, "prefix": "yuddha"},
    "uttara":    {"slug": "uttara",    "name": "Uttara Kanda",    "sargas": 111, "prefix": "uttara"},
}

BASE_URL = "https://www.valmikiramayan.net/utf8/{kanda}/sarga{n}/{prefix}roman{n}.htm"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DharmaGPT-Scraper/1.0; open-source research)"}

CHARACTERS = [
    "Rama", "Sita", "Hanuman", "Lakshmana", "Ravana", "Vibhishana",
    "Sugriva", "Jambavan", "Angada", "Indrajit", "Mandodari", "Trijata",
    "Dasharatha", "Kausalya", "Bharata", "Vali", "Sampati", "Maricha",
]

THEMES = {
    "devotion":    ["devotion", "bhakti", "worship", "pray", "dedicate", "surrender"],
    "dharma":      ["dharma", "duty", "righteous", "virtue", "truth", "noble"],
    "courage":     ["courage", "brave", "fearless", "warrior", "strength", "valor"],
    "grief":       ["grief", "sorrow", "lament", "tears", "weep", "despair"],
    "wisdom":      ["wisdom", "wise", "knowledge", "intellect", "counsel", "discern"],
    "love":        ["love", "affection", "longing", "beloved", "dear", "tender"],
    "war":         ["battle", "war", "fight", "kill", "arrow", "weapon", "army"],
    "karma":       ["karma", "fate", "action", "result", "consequence", "destined"],
    "liberation":  ["moksha", "liberation", "free", "release", "attain", "eternal"],
    "sadhana":     ["sadhana", "penance", "tapas", "meditation", "yogi", "spiritual"],
}


def fetch_sarga(cfg: dict, n: int, retries: int = 3) -> str | None:
    url = BASE_URL.format(kanda=cfg["slug"], n=n, prefix=cfg["prefix"])
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
        except requests.RequestException:
            if attempt == retries - 1:
                return None
            time.sleep(2 ** attempt)
    return None


def parse_sarga(html: str, kanda_name: str, sarga_num: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav"]):
        tag.decompose()

    raw = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    # Filter nav noise
    skip = {"copyright", "©", "previous", "next sarga", "piwik", "frame", "valmiki ramayana"}
    lines = [l for l in lines if not any(s in l.lower() for s in skip)]

    # Group into verse blocks by blank-line separation or double-danda
    chunks, buf = [], []
    verse_idx = 0
    for line in lines:
        buf.append(line)
        if "।।" in line or "॥" in line or (len(buf) >= 8 and line.endswith(".")):
            verse_idx += 1
            text = " ".join(buf).strip()
            if len(text) > 40:
                chunks.append(_build_chunk(text, kanda_name, sarga_num, verse_idx))
            buf = []

    if buf:
        text = " ".join(buf).strip()
        if len(text) > 40:
            verse_idx += 1
            chunks.append(_build_chunk(text, kanda_name, sarga_num, verse_idx))

    return chunks


def _build_chunk(text: str, kanda: str, sarga: int, verse_idx: int) -> dict:
    text_lower = text.lower()
    return {
        "id": f"{kanda.lower().replace(' ', '_')}_s{sarga:03d}_v{verse_idx:03d}",
        "text": text,
        "metadata": {
            "source": "Valmiki Ramayana",
            "source_url": "https://www.valmikiramayan.net",
            "kanda": kanda,
            "sarga": sarga,
            "verse_index": verse_idx,
            "citation": f"Valmiki Ramayana, {kanda}, Sarga {sarga}, ~Verse {verse_idx}",
            "url": f"https://www.valmikiramayan.net/utf8/{kanda.lower().split()[0]}/sarga{sarga}/",
            "source_type": "text",
            "characters": [c for c in CHARACTERS if c.lower() in text_lower],
            "themes": [t for t, words in THEMES.items() if any(w in text_lower for w in words)],
            "word_count": len(text.split()),
            "char_count": len(text),
        },
    }


def add_overlapping_windows(chunks: list[dict], window: int = 3) -> list[dict]:
    """Sliding window of 3 shlokas for better contextual recall."""
    extra = []
    for i in range(len(chunks) - window + 1):
        group = chunks[i : i + window]
        combined = "\n\n".join(c["text"] for c in group)
        base_meta = group[0]["metadata"].copy()
        last_meta = group[-1]["metadata"]
        base_meta.update({
            "verse_index": f"{group[0]['metadata']['verse_index']}-{last_meta['verse_index']}",
            "citation": f"Valmiki Ramayana, {base_meta['kanda']}, Sarga {base_meta['sarga']}, Verses ~{group[0]['metadata']['verse_index']}-{last_meta['verse_index']}",
            "is_window": True,
            "window_size": window,
            "characters": list({c for g in group for c in g["metadata"]["characters"]}),
            "themes": list({t for g in group for t in g["metadata"]["themes"]}),
            "word_count": sum(g["metadata"]["word_count"] for g in group),
        })
        extra.append({
            "id": f"{group[0]['id']}_w{i}",
            "text": combined,
            "metadata": base_meta,
        })
    return chunks + extra


def scrape_kanda(kanda_key: str, out_dir: Path, delay: float = 1.5) -> int:
    cfg = KANDA_CONFIG[kanda_key]
    out_path = out_dir / f"{kanda_key}_chunks.jsonl"
    all_chunks: list[dict] = []

    print(f"\n── {cfg['name']} ({cfg['sargas']} sargas) ──")
    for n in tqdm(range(1, cfg["sargas"] + 1)):
        html = fetch_sarga(cfg, n)
        if not html:
            continue
        raw = parse_sarga(html, cfg["name"], n)
        all_chunks.extend(add_overlapping_windows(raw))
        time.sleep(delay)

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")

    print(f"  → {len(all_chunks)} chunks saved to {out_path}")
    return len(all_chunks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--kanda", default="sundara", choices=list(KANDA_CONFIG) + ["all"])
    parser.add_argument("--out_dir", default="../../data/chunks")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    out = Path(args.out_dir)
    if args.kanda == "all":
        total = sum(scrape_kanda(k, out, args.delay) for k in KANDA_CONFIG)
        print(f"\nTotal: {total} chunks across all kandas")
    else:
        scrape_kanda(args.kanda, out, args.delay)
