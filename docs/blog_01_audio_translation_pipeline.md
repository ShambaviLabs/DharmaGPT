# Indic Audio Translation for Grounded Dharmic AI

> How I turned long-form pravachanam audio into a bilingual, human-correctable, retrieval-ready knowledge pipeline — and what it takes to validate that the AI actually uses it.

**Suggested tags:** AI, NLP, LLM, RAG, India, Translation, Open Source, Ethics, Indic Languages

---

If an AI system is expected to answer dharmic and ethical questions, it cannot be built as a pure prompt layer. It needs a strong data foundation: source traceability, retrieval structure, and a clean human review loop.

This post explains the current DharmaGPT pipeline that converts long Indic pravachanams (authentic audio discourses) into retrieval-ready bilingual chunks — with machine and manual translations stored side by side — and how we validate that the AI's responses are actually grounded in those sources.

---

## Why This Pipeline Exists

The long-term goal is an AI companion that can respond to ethical and dharmic queries with context and grounding. To get there, I needed a data system that is:

1. Stable on long recordings
2. Local-first for translation during iteration
3. Human-correctable without losing model output history
4. Structured for retrieval today and fine-tuning later
5. **Measurably grounded** — not just retrieval-connected, but scored for faithfulness

---

## The Full Model Stack

Every step in the pipeline uses a specific model. Here is the complete map:

| Step | Model | Provider | When it runs |
|---|---|---|---|
| **Transcribe** audio → text | `saaras:v3` | Sarvam AI | Data pipeline (offline, once) |
| **Translate** Telugu → English | `claude-sonnet-4` → `qwen2.5:7b` → `indictrans2` | Anthropic → Ollama → HuggingFace | Data pipeline (offline, once) |
| **Encode** text → vectors | `text-embedding-3-large` (3072d) | OpenAI | Ingest + every query |
| **Generate** RAG answer | `claude-sonnet-4-20250514` | Anthropic | Every query |
| **Judge primary** (relevance + context) | `sarvamai/sarvam-m` | Local OpenAI-compat at `:8000/v1` | Evaluation only |
| **Judge secondary** (faithfulness + citations) | `sarvamai/sarvam-30b` | Local OpenAI-compat at `:8000/v1` | Evaluation only |

The key design principle: **data pipeline models and query pipeline models are completely separate.** Transcription and translation happen once offline. Retrieval and generation happen at query time. Evaluation judges run as a separate audit loop.

---

## System Design Goals

The pipeline was built to:

1. Process long Telugu audio end to end
2. Respect STT duration constraints safely
3. Prefer local Ollama translation in auto mode
4. Preserve model and manual English in parallel
5. Scale from single-file tests to folder-level batch runs
6. **Score response quality without depending on cloud APIs for the judge**

---

## End-to-End Flow

```
Long audio file (pravachanam recording)
    ↓ split into 29-second chunks (ffmpeg)
    ↓ transcribe each chunk → Telugu text (Sarvam saaras:v3)
    ↓ translate Telugu → English (auto: Anthropic → Ollama → IndicTrans2)
    ↓ embed text (OpenAI text-embedding-3-large, 3072d)
    ↓ upsert to Pinecone
    
User query
    ↓ embed query (same model)
    ↓ retrieve top-5 chunks from Pinecone (cosine similarity, min score 0.35)
    ↓ generate answer (Claude claude-sonnet-4, max 6000 char context)
    ↓ score response (sarvam-m + sarvam-30b as LLM judges)
```

---

## Why 29-Second Chunking

Sarvam real-time STT has hard duration limits. Running at 29 seconds gives a deliberate buffer under the cap.

This gives three practical benefits:
1. Predictable API behavior
2. Better retry behavior at chunk level
3. Cleaner failure isolation

Each chunk becomes one JSONL record with a canonical filename:
```
<source>_<language>_transcript_partNN.jsonl
```

---

## Translation Layer: Three-Backend Fallback Chain

The translation abstraction tries backends in sequence:

```
1. Anthropic (claude-sonnet-4)  ← primary, highest quality
2. Ollama (qwen2.5:7b)          ← local fallback, no API cost
3. IndicTrans2 (ai4bharat/indictrans2-indic-en-dist-200M) ← offline fallback
4. skip                         ← explicit no-op
```

**Auto mode** tries them in this order. Each failure writes a `translation_fallback_reason` so you can audit what happened per record. In practice, building a 189-record corpus revealed this failure chain concretely: Anthropic failed for 71 records during one batch run (rate limit / no key), Ollama picked up 118 of them cleanly, and 71 needed a second pass after the environment was fixed.

Every translated record now stores both field names for compatibility:

```json
{
  "text_en_model": "Rama stood firm in dharma...",
  "text_en": "Rama stood firm in dharma...",
  "translation_mode": "auto",
  "translation_backend": "ollama",
  "translation_version": "qwen2.5:7b",
  "translation_fallback_reason": "failed:anthropic"
}
```

`text_en` is retained as a compatibility alias to `text_en_model` so existing retrieval and manual review tooling does not break.

---

## Recovering 71 Missing Translations

After the initial batch run, 71 out of 189 records had empty `text_en` fields. The failure reason was `failed:ollama:No module named 'torch'` — PyTorch was not installed in the Ollama environment during that run.

The recovery was a single Python call using the existing `process_file()` function from `translate_corpus.py`:

```python
from scripts.translate_corpus import process_file
from pathlib import Path

TRANSCRIPT_DIR = Path("knowledge/processed/audio_transcript/01_01_...")
for f in sorted(TRANSCRIPT_DIR.glob("*.jsonl")):
    result = process_file(f, max_workers=4, force=False)
    print(f"{f.name}: updated {result['updated']} records")
```

All 189 records now have translations. The stat before and after:

| | Before | After |
|---|---|---|
| Files with translation | 118 (63%) | 189 (100%) |
| Missing | 71 | 0 |
| Backend used for recovery | — | Ollama `qwen2.5:7b` |

---

## Human Translation as Parallel Data

The most important structural decision: manual translation does not replace model translation. Each output record keeps:

- `text_en_model` — machine-generated translation
- `text_en_manual` — human correction (written via the review API)
- `text_en` — compatibility alias pointing to model output

This improves the system in three ways:
1. Quality can be measured over time by comparing fields
2. Human edits remain auditable (audit log with reviewer ID and timestamp)
3. Model-vs-human pairs become supervised fine-tuning data later

---

## Response Validation: Did the AI Actually Use the Sources?

The hardest problem in RAG is not retrieval — it is knowing whether the generated answer is actually grounded in what was retrieved, or whether the model fabricated a plausible-sounding answer from training data.

We built a validation pipeline that scores every response across four dimensions:

| Metric | Weight | What it checks |
|---|---|---|
| **Faithfulness** | 35% | Are factual claims in the answer traceable to the retrieved passages? |
| **Answer relevance** | 30% | Does the answer directly address the query? |
| **Context utilization** | 20% | Did the answer use the retrieved passages or ignore them? |
| **Citation precision** | 15% | Are inline citations like `[Valmiki Ramayana, Sundara Kanda, Sarga 15]` accurate? |

**Overall score** = weighted sum. A response passes when score ≥ 0.65.

The judge makes two LLM calls per response:
- **Primary** (`sarvamai/sarvam-m`): answer relevance + context utilization
- **Secondary** (`sarvamai/sarvam-30b`): faithfulness + citation precision

Both judges are Sarvam models running via an OpenAI-compatible local API — no cloud calls for evaluation. For local development without a Sarvam server, both roles can be overridden with an Ollama model:

```python
from core.llm import LLMBackend, LLMConfig
from evaluation.response_scorer import validate_response

local_judge = LLMConfig(
    backend=LLMBackend.ollama,
    model="qwen2.5:7b",
    base_url="http://localhost:11434",
)
result = validate_response(query, response, judge_config=local_judge)
print(f"Score: {result.overall_score:.3f} — {'PASS' if result.passed else 'FAIL'}")
```

---

## The Section Diversity Metric

One retrieval quality metric is **section diversity**: how many distinct sections of the source text appear in the retrieved chunks. Rather than using the Ramayana-specific term `kanda`, the codebase uses `section_diversity` — a generic label that works across all Indic texts regardless of whether they call their divisions kanda (Ramayana), parva (Mahabharata), adhyaya (Upanishads), or skandha (Bhagavata Purana).

This is a small but intentional design choice: the retrieval schema must remain neutral across source types.

---

## Two-Tier Test Suite: Offline Unit + Offline Integration

All tests run without cloud API keys.

**Unit tests** (`tests/unit/`, 29 tests, < 5 seconds):
- Scorer math (weighted average, pass threshold)
- Mode compliance regex for all four query modes (guidance, story, children, scholar)
- Retrieval stats (mean, min, section diversity)
- MetricScore labels (good / fair / poor thresholds)
- Passage formatting for judge prompts
- `ValidationResult.to_dict()` output shape

**Integration tests** (`tests/integration/`):

The integration suite uses a seed corpus file (`knowledge/processed/seed_corpus.jsonl`) and a local Ollama model. No Pinecone, no OpenAI, no Anthropic — completely offline after `ollama pull qwen2.5:1.5b`.

The `local_pipeline.py` module provides:
- **Local retrieval**: keyword overlap scoring against the seed corpus (replaces Pinecone embed + query)
- **Local LLM**: Ollama `qwen2.5:1.5b` for answer generation (replaces Claude)
- **Mode compliance fallback**: if the local model's answer does not satisfy the format check, a deterministic template is composed from the top retrieved passage

Tests are auto-skipped if Ollama is unavailable — they never fail on missing services.

```bash
make test-unit          # < 5s, zero credentials
make test-integration   # ~60s, requires local Ollama
make test-all           # both
```

---

## Script Names Match What They Do

All data pipeline scripts were renamed so their purpose is immediately readable:

| Old name | New name | What it does |
|---|---|---|
| `auto_translate.py` | `translate_corpus.py` | Batch-translate corpus records to English |
| `batch_segment_and_transcribe.py` | `transcribe_audio_batch.py` | Split audio + transcribe each chunk via API |
| `ingest.py` | `ingest_to_pinecone.py` | Embed records and upsert to Pinecone |
| `normalize.py` | `normalize_raw_corpus.py` | Clean scraped raw JSONL → flat schema |

Run order for text corpus:
```
normalize_raw_corpus → translate_corpus → ingest_to_pinecone
```

For audio (requires API server running):
```
transcribe_audio_batch → (translate_corpus already handles new transcripts) → ingest_to_pinecone
```

---

## Batch Processing Across Full Audio Collections

Single-file scripts are useful for debugging. Corpus building needs orchestration. `transcribe_audio_batch.py` now:

1. Discovers supported audio files in a directory (mp3, wav, m4a, flac, opus, wma)
2. Splits each to 29-second clips via ffmpeg
3. Uploads each clip to the running transcription API with retry on transient errors
4. Skips clips that already have a transcript (unless `--overwrite`)
5. Emits a JSON batch manifest for run tracking

This makes long-running corpus builds resumable.

---

## Reliability Problems Solved

**Optional dependency coupling**
Local Ollama translation runs were failing because heavy IndicTrans2 dependencies were imported eagerly. Fixed by moving all IndicTrans2 imports inside the function that uses them — the module loads only when that backend is selected.

**Windows encoding failures**
Batch subprocess output failed with charmap errors on non-ASCII Telugu output. Fixed by configuring UTF-8-safe process I/O and explicit encoding on all file writes.

**Path and environment fragility**
Relative path assumptions made runs sensitive to launch directory. Fixed by standardising to repo-root path resolution (`Path(__file__).resolve().parents[N]`) in every script.

**Silent translation failures**
71 records had silently empty translations after a batch run. The `translation_fallback_reason` field — populated on every record including failures — made it straightforward to find and recover them in a single targeted re-run.

---

## Output Schema Snapshot

Each JSONL record includes:

```json
{
  "id": "01_01_sampoorna_ramayanam_..._part18",
  "text": "మీరు ఎందుకు నవ్వాలని...",
  "text_te": "మీరు ఎందుకు నవ్వాలని...",
  "text_en_model": "He said there is no difference between...",
  "text_en": "He said there is no difference between...",
  "text_en_manual": null,
  "language": "te",
  "source_type": "audio_transcript",
  "citation": "Audio transcription: Sampoorna Ramayanam part 1, chunk 19",
  "transcription_mode": "sarvam_stt",
  "transcription_version": "saaras:v3",
  "translation_mode": "auto",
  "translation_backend": "ollama",
  "translation_version": "qwen2.5:7b",
  "translation_fallback_reason": "failed:anthropic",
  "translation_attempted_backends": ["anthropic", "ollama"]
}
```

This schema supports retrieval today, manual review via the API, and fine-tuning dataset export later.

---

## Why This Matters for Dharmic AI

For dharmic and ethical AI, grounding is not optional. This pipeline provides:

1. **Source-aware retrieval** — every answer can be traced to a specific corpus record with a citation
2. **Human correction loops** — manual translations sit alongside model output without overwriting it
3. **Structured quality improvement** — the validation pipeline gives a numeric score to "how grounded is this answer"
4. **Training data pathways** — model-vs-human translation pairs and judge-scored QA pairs are future fine-tuning material

---

## For Potential Collaborators

If you are evaluating DharmaGPT as a collaborator, the current prototype already has:

1. Corpus creation pipeline from long audio
2. Local-first translation with three-backend fallback
3. Human-in-the-loop correction workflow
4. Retrieval-ready structured output with bilingual fields
5. LLM-as-judge validation pipeline with four scored dimensions
6. Offline test suite that runs without cloud credentials

What is still open and valuable to build together:

1. Larger corpus expansion across languages and source types
2. Product UX for review, guidance, and companion use cases
3. Governance framework for trusted source curation
4. Confidence-guided review prioritization (score low-confidence records first for human review)

---

## What I Am Building Next

1. Stronger IndicTrans2 local integration
2. Better reviewer UX for manual approvals
3. Fine-tuning dataset export from model-human translation pairs and validation-scored QA pairs
4. Expansion from audio-heavy ingestion to broader corpus types (Mahabharata, Upanishads, Puranas)
5. Continuous evaluation: run `run_evaluation.py` on a schedule and track score trends over time

---

## Closing

The core lesson is straightforward: if the mission is grounded dharmic AI, the data system has to be grounded first — and the AI's use of that data has to be measurable.

Model quality can evolve. Foundation choices and validation loops decide whether that evolution is trustworthy.

---

*Code is open source at [github.com/sahitya-pavurala/DharmaGPT](https://github.com/sahitya-pavurala/DharmaGPT)*
