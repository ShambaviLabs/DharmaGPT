import structlog
from pinecone import Pinecone
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from core.config import get_settings
from models.schemas import SourceChunk

log = structlog.get_logger()
settings = get_settings()

_pc: Pinecone | None = None
_openai: AsyncOpenAI | None = None


def get_pinecone() -> Pinecone:
    global _pc
    if _pc is None:
        _pc = Pinecone(api_key=settings.pinecone_api_key)
    return _pc


def get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai


def _source_text_from_metadata(meta: dict) -> str:
    """
    Choose the richest text available for retrieval context.

    Prefer the full stored chunk text, then any translated text, and only fall
    back to the preview when necessary.
    """
    base_text = (meta.get("text") or "").strip()
    translated_text = (meta.get("translated_text") or meta.get("text_en") or meta.get("text_en_model") or "").strip()
    preview = (meta.get("text_preview") or "").strip()
    language = (meta.get("language") or "").strip().lower()

    if base_text and translated_text and translated_text != base_text:
        if language and language != "en":
            return f"{base_text}\n\nEnglish translation:\n{translated_text}"
        if meta.get("source_type") == "audio":
            return f"{base_text}\n\nEnglish translation:\n{translated_text}"
        return base_text

    if base_text:
        return base_text
    if translated_text:
        return translated_text
    return preview


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def embed_query(text: str) -> list[float]:
    client = get_openai()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=[text],
    )
    return response.data[0].embedding


async def retrieve(
    query: str,
    top_k: int | None = None,
    filter_section: str | None = None,
    filter_source_type: str | None = None,
) -> list[SourceChunk]:
    """
    Embed query and retrieve top-k chunks from Pinecone.
    Returns SourceChunk list sorted by relevance score.
    """
    top_k = top_k or settings.rag_top_k
    vector = await embed_query(query)

    pc = get_pinecone()
    index = pc.Index(settings.pinecone_index_name)

    # Build metadata filter — "kanda" is the legacy Pinecone field name
    pf: dict = {}
    if filter_section:
        pf["kanda"] = {"$eq": filter_section}
    if filter_source_type:
        pf["source_type"] = {"$eq": filter_source_type}

    results = index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        filter=pf if pf else None,
    )

    chunks = []
    for match in results.matches:
        if match.score < settings.rag_min_score:
            continue
        meta = match.metadata or {}
        # "section"/"chapter"/"verse" are new names; fall back to legacy "kanda"/"sarga" keys
        section = meta.get("section") or meta.get("kanda") or None
        chapter_raw = meta.get("chapter") or meta.get("sarga")
        verse_raw = meta.get("verse")
        chunks.append(SourceChunk(
            text=_source_text_from_metadata(meta),
            citation=meta.get("citation", ""),
            section=section,
            chapter=int(chapter_raw) if chapter_raw is not None else None,
            verse=int(verse_raw) if verse_raw is not None else None,
            score=round(match.score, 4),
            source_type=meta.get("source_type", "text"),
            audio_timestamp=(
                f"{meta.get('start_time_sec', '')}s–{meta.get('end_time_sec', '')}s"
                if meta.get("source_type") == "audio" else None
            ),
            url=meta.get("url"),
        ))

    log.info("retrieval_done", query=query[:60], results=len(chunks))
    return chunks


def _full_citation(chunk: SourceChunk) -> str:
    """
    Return the richest possible citation string for a passage header.
    Appends chapter/verse to the stored citation if they aren't already present.
    """
    base = chunk.citation or ""
    extras: list[str] = []
    if chunk.chapter is not None and str(chunk.chapter) not in base:
        extras.append(f"Ch. {chunk.chapter}")
    if chunk.verse is not None and str(chunk.verse) not in base:
        extras.append(f"V. {chunk.verse}")
    if extras:
        return f"{base}, {', '.join(extras)}".strip(", ")
    return base


def format_context(chunks: list[SourceChunk], max_chars: int | None = None) -> str:
    """Format retrieved chunks into a context block for the LLM prompt."""
    max_chars = max_chars or settings.max_context_chars
    parts = []
    total = 0
    for i, chunk in enumerate(chunks, 1):
        src = f"[PASSAGE {i} — {_full_citation(chunk)}]"
        if chunk.source_type == "audio" and chunk.audio_timestamp:
            src += f" [Audio @ {chunk.audio_timestamp}]"
        block = f"{src}\n{chunk.text}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)
