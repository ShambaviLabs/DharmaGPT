# DharmaGPT TODO

Prioritized product backlog focused on business value.

## P0: Core Moat

1. Improve retrieval authenticity
   - Tighten chunk quality, metadata coverage, and citation fidelity.
   - Make sure answers are grounded in the source text every time.
   - Expand evaluation coverage for retrieval and citation precision.

2. Add stronger source provenance
   - Show exact source text, section, and verse/chapter references in the UI and API.
   - Make it obvious where each answer came from.
   - Add traceability for both text and audio sources.

3. Expand search and discovery
   - Support better verse, topic, character, and theme lookup.
   - Add filters for text type, kanda/parva, language, and source type.
   - Optimize for “find the exact passage” use cases.

## P1: Product Stickiness

4. Add user-facing workflows
   - Save answers, bookmark passages, and export citations.
   - Generate study notes, summaries, and lesson outlines.
   - Support compare-and-contrast views across translations.

5. Build personalization by mode and audience
   - Tune outputs for children, students, scholars, and general seekers.
   - Let users choose response style, depth, and language.
   - Remember user preferences across sessions.

6. Strengthen feedback loops
   - Add thumbs up/down, citation flags, and “report this answer” flows.
   - Capture what users searched for vs. what they actually needed.
   - Feed corrections back into corpus cleanup and retrieval tuning.

7. Improve multilingual access
   - Expand high-quality support for English, Hindi, Telugu, Tamil, and Sanskrit.
   - Keep sacred terms and proper nouns consistent across languages.
   - Make translated answers feel native, not machine-generated.

## P2: Distribution And Growth

8. Ship more surfaces
   - Provide embeddable widgets, public APIs, and bot integrations.
   - Consider WhatsApp, Telegram, and browser-based access.
   - Make it easy for institutions to adopt the product.

9. Add institutional and educator features
   - Create teacher, scholar, and admin views.
   - Support curated reading lists and lesson packs.
   - Add batch tools for classrooms, study groups, and temples.

10. Create a quality dashboard
    - Show retrieval quality, answer quality, and citation health.
    - Track pass rate over time by mode and corpus section.
    - Use the validation pipeline as a product KPI, not just a dev tool.

## P3: Long-Term Leverage

11. Fine-tune later, once the RAG loop is stable
    - Use successful prompts, corrections, and gold responses to train style and behavior.
    - Fine-tune for tone, citation discipline, and mode consistency.
    - Keep RAG as the source of truth and fine-tuning as a behavior layer.

12. Grow the corpus as a compounding asset
    - Add more texts, commentaries, and high-quality audio sources.
    - Standardize canonical metadata and dataset naming.
    - Treat corpus ownership and structure as part of the moat.

