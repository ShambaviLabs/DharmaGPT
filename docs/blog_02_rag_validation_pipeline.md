# Validating RAG Responses for Dharmic AI: Four Metrics, Two Local Judges, Zero Cloud Calls

> How to know whether your AI actually used the sources it retrieved — or just made something up that sounds right.

**Suggested tags:** AI, RAG, LLM, Evaluation, NLP, India, Open Source

---

The hardest problem in RAG is not retrieval. Retrieval is measurable — you can check cosine scores, count sources, filter by metadata. The hard problem is what happens after retrieval: did the language model actually *use* the passages it was given, or did it generate a confident-sounding answer from its training data while ignoring the retrieved context entirely?

For a dharmic AI, this matters acutely. A hallucinated verse reference or a fabricated character action is not just a technical failure — it actively misleads someone asking about source texts they trust.

This post explains the validation pipeline built for DharmaGPT.

---

## The Four Metrics

Every RAG response is scored across four dimensions:

### 1. Faithfulness (35% weight)
*Are the factual claims in the answer directly supported by the retrieved passages?*

A high-faithfulness answer only makes specific claims — about events, characters, teachings, verse contents — that appear in the retrieved context. Claims that come only from the model's training data are flagged as unsupported. This is the most important metric for a source-grounded system.

Score 1.0 means every specific claim traces back to a passage. Score 0.0 means the answer is pure hallucination relative to the retrieved context.

### 2. Answer Relevance (30% weight)
*Does the answer actually address the user's query?*

A retrieved context about Hanuman's journey is not useful if the question was about Rama's exile. This metric catches cases where the model produces a technically accurate passage summary that misses the question.

### 3. Context Utilization (20% weight)
*Did the answer draw from the retrieved passages, or ignore them?*

This is subtly different from faithfulness. A model can be faithful to the passages it *chose* to use while effectively ignoring most of the retrieved context. Context utilization measures how tightly the answer is built from the retrieved material versus drawn from general training knowledge.

### 4. Citation Precision (15% weight)
*Are the inline citations accurate and traceable?*

DharmaGPT's system prompts require inline citations in the format `[Valmiki Ramayana, Sundara Kanda, Sarga 15]`. Citation precision checks whether cited sources actually match the retrieved passages. A citation that names a real text but a wrong section, or a plausible-sounding but non-existent verse, scores poorly here.

---

## Overall Score and Pass Threshold

```
overall = 0.35 × faithfulness
        + 0.30 × answer_relevance
        + 0.20 × context_utilization
        + 0.15 × citation_precision
```

A response **passes** when `overall_score ≥ 0.65`. This maps roughly to "most specific claims are grounded, the answer is on-topic, and citations are mostly accurate."

The weights reflect the priority for a dharmic source-grounded system: faithfulness matters most, citation accuracy matters least (good citations are a sign of quality, missing them is not catastrophic if the answer is otherwise grounded).

---

## Two Judge Calls, Split by Concern

The judge is split into two separate LLM calls to keep each prompt focused:

**Primary judge** (`sarvamai/sarvam-m`):
- answer_relevance + context_utilization
- These are holistic reading comprehension tasks — a smaller, faster model handles them well

**Secondary judge** (`sarvamai/sarvam-30b`):
- faithfulness + citation_precision
- These require careful claim-by-claim comparison against source passages — a larger model is appropriate

Both judges run via an OpenAI-compatible local API (default: `localhost:8000/v1`). No cloud call is made for evaluation.

---

## The Judge Prompt Design

Each judge receives the query, the retrieved passages with their retrieval scores, and the system response. It returns structured JSON — no markdown, no explanation, just scores and reasoning strings.

**Primary prompt output:**
```json
{
  "answer_relevance": {
    "score": 0.9,
    "reasoning": "The answer directly addresses anger management through the lens of the Gita's teaching on equanimity."
  },
  "context_utilization": {
    "score": 0.75,
    "reasoning": "The answer draws from passages 1 and 3 but ignores passage 2 which is most relevant."
  }
}
```

**Secondary prompt output:**
```json
{
  "faithfulness": {
    "score": 0.6,
    "unsupported_claims": ["Arjuna wept for three days before the battle"],
    "reasoning": "One specific duration claim is not present in any retrieved passage."
  },
  "citation_precision": {
    "score": 0.85,
    "invalid_citations": [],
    "reasoning": "All cited sections match retrieved passages."
  }
}
```

The `unsupported_claims` and `invalid_citations` arrays are directly actionable for debugging.

---

## Switching the Judge to a Local Ollama Model

The default judges are Sarvam models. For development without a Sarvam server, any Ollama model can be used as the judge by passing a config override:

```python
from core.llm import LLMBackend, LLMConfig
from evaluation.response_scorer import validate_response

local_judge = LLMConfig(
    backend=LLMBackend.ollama,
    model="qwen2.5:7b",     # or qwen2.5:3b for speed
    base_url="http://localhost:11434",
)
result = validate_response(query, response, judge_config=local_judge)
```

When `judge_config` is provided, it overrides both the primary and secondary judge. This makes the evaluation pipeline useful even without a Sarvam inference server.

---

## Rule-Based Metrics (Free, No LLM)

Two metrics are computed locally without any LLM call:

**Retrieval stats:**
- `score_mean` — average cosine similarity of the retrieved chunks
- `score_min` — minimum score (lowest-quality chunk retrieved)
- `source_count` — how many chunks were retrieved
- `section_diversity` — how many distinct text sections appear in the retrieved set (e.g., 3 different kandas for Ramayana, or parvas for Mahabharata)

**Mode compliance:**
Checks whether the answer follows the structural format required by the query mode:
- `guidance` → must contain a reflection question (ends with `?`)
- `story` → must contain `SOURCE:` tag near the end
- `children` → must contain a moral lesson phrase ("what this story teaches us")
- `scholar` → must reference a section and number ("Sundara Kanda 15", "Sarga 5", etc.)

---

## Running the Evaluation

```bash
# Run against 10 sample questions (all 4 modes)
cd dharmagpt && PYTHONPATH=. python scripts/run_evaluation.py

# Quick 3-question smoke test
python scripts/run_evaluation.py --limit 3

# Custom question set
python scripts/run_evaluation.py \
  --questions evaluation/sample_questions.jsonl \
  --output evaluation/reports/run.jsonl
```

Sample output:
```
==================================================
  Total evaluated:    10
  Passed (>= 0.65):   8  (80%)
  Mode compliance:    90%
──────────────────────────────────────────────────
  Overall score:          0.741
  Faithfulness (35%):     0.782
  Answer relevance (30%): 0.810
  Context utilization:    0.694
  Citation precision:     0.651
  Retrieval score (avg):  0.823
==================================================
```

Results are written as JSONL to `evaluation/reports/` with full per-question breakdowns including unsupported claims and invalid citations.

---

## The Section Diversity Metric

A note on terminology: the codebase uses `section_diversity` rather than `kanda_diversity` because the retrieval system covers multiple Indic texts. Kanda is Ramayana-specific. Mahabharata uses parva, Upanishads use adhyaya, Bhagavata Purana uses skandha. A metric that counted "unique kandas" would be meaningless for Mahabharata content. `section_diversity` is neutral across all source types.

---

## What This Validates — and What It Does Not

The validation pipeline checks whether the model used its retrieved context well. It does not check:

- Whether the retrieval itself was correct (that is a retrieval quality problem — covered by cosine scores and `section_diversity`)
- Whether the source texts themselves are accurate (that requires human scholarship review)
- Whether the answer is spiritually appropriate for the seeker's situation (that requires domain expert judgment)

The numeric scores are a quality signal, not a certificate of correctness. The `unsupported_claims` list from the faithfulness judge is the most directly useful output for catching specific hallucinations.

---

## Closing

Grounded AI requires measurable grounding. A retrieval system that can tell you what it retrieved is necessary but not sufficient — you also need to know whether the generation step actually used what was retrieved.

The four metrics here — faithfulness, relevance, context utilization, citation precision — give concrete, actionable numbers for that question. The split judge design keeps each evaluation concern focused. The local-model override makes the pipeline usable without a cloud evaluation API.

*Code is open source at [github.com/sahitya-pavurala/DharmaGPT](https://github.com/sahitya-pavurala/DharmaGPT)*
