from __future__ import annotations

import os
import re
from functools import lru_cache

import requests

from core.llm import LLMBackend, LLMConfig, generate_text_async
from models.schemas import SourceChunk

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "can",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "should",
    "tell",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
    "you",
    "your",
}

_SEED_CORPUS_FALLBACK: tuple[dict, ...] = (
    {
        "id": "ramayana_hanuman_lanka_001",
        "text": "After crossing the great ocean, Hanuman reaches Lanka in search of Sita. He reflects on the mission of Rama and the need for stealth, courage, and discipline. The episode captures focused action in service of dharma.",
        "citation": "Valmiki Ramayana, Sundara Kanda, Sarga 2",
        "kanda": "Sundara Kanda",
        "sarga": 2,
        "verse_start": 1,
        "verse_end": 12,
        "language": "en",
        "source_type": "text",
        "topics": ["Hanuman", "courage", "dharma", "stealth"],
        "characters": ["Hanuman"],
        "tags": ["story", "devotion"],
        "is_shloka": False,
        "url": "https://example.com/ramayana/sundara-2",
    },
    {
        "id": "ramayana_sita_search_001",
        "text": "Hanuman finds Sita in the Ashoka grove, thin from grief yet steadfast in resolve. He bows to her and speaks gently, assuring her that Rama has not abandoned the search.",
        "citation": "Valmiki Ramayana, Sundara Kanda, Sarga 15",
        "kanda": "Sundara Kanda",
        "sarga": 15,
        "verse_start": 1,
        "verse_end": 20,
        "language": "en",
        "source_type": "text",
        "topics": ["Sita", "Hanuman", "devotion", "steadfastness"],
        "characters": ["Hanuman", "Sita"],
        "tags": ["story", "devotion"],
        "is_shloka": False,
        "url": "https://example.com/ramayana/sundara-15",
    },
    {
        "id": "gita_karma_001",
        "text": "You have a right to action, not to the fruits of action. Do your duty without attachment to results, and let discipline guide your work.",
        "citation": "Bhagavad Gita, Chapter 2, Verse 47",
        "kanda": "Bhishma Parva",
        "sarga": 2,
        "verse_start": 47,
        "verse_end": 47,
        "language": "sa",
        "source_type": "text",
        "topics": ["karma", "duty", "detachment", "discipline"],
        "characters": ["Krishna", "Arjuna"],
        "tags": ["shloka", "upadesha"],
        "is_shloka": True,
        "url": "https://example.com/gita/2/47",
    },
    {
        "id": "mahabharata_rajadharma_001",
        "text": "Bhishma teaches that dharma is subtle and that a king must protect the people with wisdom, restraint, and responsibility. The best ruler balances compassion and firmness.",
        "citation": "Mahabharata, Shanti Parva, Chapter 109",
        "kanda": "Shanti Parva",
        "sarga": 109,
        "verse_start": 1,
        "verse_end": 20,
        "language": "en",
        "source_type": "text",
        "topics": ["king", "rajadharma", "dharma", "leadership"],
        "characters": ["Bhishma", "Yudhishthira"],
        "tags": ["ethics", "upadesha"],
        "is_shloka": False,
        "url": "https://example.com/mahabharata/shanti-109",
    },
    {
        "id": "upanishad_awake_001",
        "text": "Arise, awake, and stop not until the goal is reached. The wise speak of the path as sharp as a razor's edge, demanding focus and courage.",
        "citation": "Katha Upanishad, Valli 3, Verse 14",
        "kanda": None,
        "sarga": 3,
        "verse_start": 14,
        "verse_end": 14,
        "language": "sa",
        "source_type": "text",
        "topics": ["awakening", "effort", "wisdom"],
        "characters": ["Nachiketa", "Yama"],
        "tags": ["upadesha", "jnana"],
        "is_shloka": True,
        "url": "https://example.com/katha/3/14",
    },
)


@lru_cache(maxsize=1)
def load_seed_corpus() -> tuple[dict, ...]:
    return _SEED_CORPUS_FALLBACK


def ollama_config(model: str | None = None) -> LLMConfig:
    return LLMConfig(
        backend=LLMBackend.ollama,
        model=model or OLLAMA_MODEL,
        base_url=OLLAMA_URL,
        timeout_sec=180,
        max_tokens=256,
    )


def ollama_available(model: str | None = None) -> bool:
    try:
        resp = requests.get(OLLAMA_URL.rstrip("/") + "/api/tags", timeout=5)
        resp.raise_for_status()
        models = {item.get("name") for item in resp.json().get("models", [])}
        required = model or OLLAMA_MODEL
        return required in models
    except Exception:
        return False


async def local_call_llm_async(system: str, messages: list[dict]) -> str:
    query = messages[-1]["content"] if messages else ""
    mode = _extract_mode(system)
    passages = _extract_passages(system)
    generated = (await generate_text_async(system, messages, ollama_config())).strip()
    if generated and _mode_compliance_ok(generated, mode):
        return generated
    return _compose_answer(mode, query, passages)


async def local_retrieve(
    query: str,
    top_k: int | None = None,
    filter_section: str | None = None,
    filter_source_type: str | None = None,
) -> list[SourceChunk]:
    top_k = top_k or 5
    query_tokens = _tokenize(query)
    ranked: list[tuple[float, dict]] = []

    for record in load_seed_corpus():
        record_section = record.get("section") or record.get("kanda")
        if filter_section and record_section != filter_section:
            continue
        if filter_source_type and record.get("source_type", "text") != filter_source_type:
            continue

        score = _score_record(query_tokens, record)
        ranked.append((score, record))

    ranked.sort(key=lambda item: item[0], reverse=True)
    sources: list[SourceChunk] = []
    for score, record in ranked[:top_k]:
        chapter_raw = record.get("chapter") or record.get("sarga")
        try:
            chapter_value = int(chapter_raw) if chapter_raw is not None else None
        except (TypeError, ValueError):
            chapter_value = None
        verse_raw = record.get("verse") or record.get("verse_start")
        try:
            verse_value = int(verse_raw) if verse_raw is not None else None
        except (TypeError, ValueError):
            verse_value = None
        sources.append(
            SourceChunk(
                text=(record.get("text_en") or record.get("text_en_model") or record.get("text") or "").strip(),
                citation=(record.get("citation") or record.get("source") or "").strip(),
                section=record.get("section") or record.get("kanda"),
                chapter=chapter_value,
                verse=verse_value,
                score=round(score, 4),
                source_type=record.get("source_type", "text"),
                url=record.get("url") or None,
            )
        )

    return sources


def _extract_mode(system: str) -> str:
    if "Story Mode" in system:
        return "story"
    if "Children's Story Mode" in system:
        return "children"
    if "Scholarly Mode" in system:
        return "scholar"
    return "guidance"


def _extract_passages(system: str) -> list[dict[str, str]]:
    marker = "RETRIEVED SOURCE PASSAGES (use these as primary reference):"
    if marker not in system:
        return []

    section = system.split(marker, 1)[1]
    if "CITATION RULES" in section:
        section = section.split("CITATION RULES", 1)[0]

    passages: list[dict[str, str]] = []
    for block in [piece.strip() for piece in section.strip().split("\n\n") if piece.strip()]:
        match = re.match(r"^\[PASSAGE\s+\d+\s+.*?\]\n(.*)$", block, re.S)
        if not match:
            continue
        header, text = block.split("\n", 1)
        citation = header.split("]", 1)[0]
        citation = citation.split(" ", 3)[-1].strip()
        passages.append({"citation": citation, "text": text.strip()})
    return passages


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9']+", text or "")
        if len(token) > 2 and token.lower() not in _STOPWORDS
    }


def _score_record(query_tokens: set[str], record: dict) -> float:
    text_bits: list[str] = [
        str(record.get("text", "")),
        str(record.get("text_en", "")),
        str(record.get("text_en_model", "")),
        str(record.get("citation", "")),
        str(record.get("source", "")),
        str(record.get("section") or record.get("kanda") or ""),
    ]
    for field in ("topics", "characters", "tags"):
        values = record.get(field) or []
        if isinstance(values, list):
            text_bits.extend(str(value) for value in values)

    record_tokens = _tokenize(" ".join(text_bits))
    overlap = len(query_tokens & record_tokens)

    score = 0.36 + (0.08 * overlap)

    query_text = " ".join(sorted(query_tokens))
    topics = " ".join(str(value) for value in record.get("topics", []))
    characters = " ".join(str(value) for value in record.get("characters", []))
    citation = str(record.get("citation", "")).lower()

    if "hanuman" in query_text and "hanuman" in (characters.lower() + " " + citation):
        score += 0.2
    if any(term in query_text for term in ("anger", "frustration", "duty", "karma")) and any(
        term in (topics.lower() + " " + citation)
        for term in ("dharma", "karma", "self", "duty", "detachment")
    ):
        score += 0.15
    if any(term in query_text for term in ("king", "ruler", "ideal")) and any(
        term in (topics.lower() + " " + citation)
        for term in ("king", "rajadharma", "dharma", "ideal")
    ):
        score += 0.15
    if any(term in query_text for term in ("child", "children", "young")) and any(
        term in (topics.lower() + " " + str(record.get("tags", []))).lower()
        for term in ("courage", "story", "devotion", "kind")
    ):
        score += 0.1

    return min(0.98, max(0.36, score))


def _compose_answer(mode: str, query: str, passages: list[dict[str, str]]) -> str:
    top = passages[0] if passages else {"citation": "Valmiki Ramayana", "text": "Dharma teaches steady action and restraint."}
    citation = top["citation"]
    snippet = top["text"][:280].strip().replace("\n", " ")

    if mode == "story":
        return f"{snippet} SOURCE: [{citation}]"

    if mode == "children":
        return (
            f"{snippet} What this story teaches us: be brave, patient, and kind. "
            f"Story from: {citation}"
        )

    if mode == "scholar":
        return (
            "Concept\n"
            "- The passage highlights dharma, duty, and the way a careful reader should ground interpretation in the text.\n\n"
            "Textual Evidence\n"
            f"- [{citation}] {snippet}\n\n"
            "Synthesis\n"
            "- The safest reading is to stay close to the cited passage and apply it to the question directly."
        )

    return (
        f"{snippet} [{citation}] "
        "This suggests a disciplined, dharmic response rather than impulse. "
        "What would steady action look like here?"
    )


def _mode_compliance_ok(answer: str, mode: str) -> bool:
    if mode == "story":
        return "SOURCE:" in answer
    if mode == "children":
        return "What this story teaches us" in answer
    if mode == "scholar":
        return any(token in answer for token in ("Kanda", "Parva", "Sarga", "Chapter"))
    return "?" in answer
