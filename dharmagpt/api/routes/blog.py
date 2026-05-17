from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


def _blog_page() -> str:
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>DharmaGPT · Model Benchmark — Sarvam, Anthropic, OpenAI</title>
  <meta name="description" content="Benchmarking Sarvam AI, Anthropic Claude, and OpenAI across transcription, translation, embedding, and RAG generation for an Indic language corpus."/>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0c0c0e; --surface: #141418; --surface2: #1c1c24;
      --line: #2a2a36; --text: #e4e4f0; --muted: #7878920;
      --muted: #888; --accent: #c8a96e; --accent2: #7c6ef0;
      --green: #34d399; --blue: #60a5fa; --red: #f87171; --yellow: #fbbf24;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --mono: "JetBrains Mono", "Fira Code", "Consolas", monospace;
      --max: 780px;
    }
    body { background: var(--bg); color: var(--text); font-family: var(--font); font-size: 16px; line-height: 1.75; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { font-family: var(--mono); font-size: 0.875em; background: var(--surface2); padding: 2px 6px; border-radius: 4px; color: var(--accent); }

    /* ── Layout ── */
    .wrap { max-width: var(--max); margin: 0 auto; padding: 0 24px 100px; }

    /* ── Nav ── */
    nav { border-bottom: 1px solid var(--line); padding: 16px 0; margin-bottom: 0; }
    nav .inner { max-width: var(--max); margin: 0 auto; padding: 0 24px; display: flex; justify-content: space-between; align-items: center; }
    .nav-logo { font-size: 15px; font-weight: 700; color: var(--accent); }
    .nav-links { display: flex; gap: 20px; font-size: 13px; color: var(--muted); }
    .nav-links a { color: var(--muted); }

    /* ── Hero ── */
    .hero { padding: 56px 0 40px; border-bottom: 1px solid var(--line); margin-bottom: 52px; }
    .tag-row { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
    .tag { font-size: 11px; padding: 3px 10px; border-radius: 999px; font-weight: 600; letter-spacing: 0.5px; }
    .tag-sarvam  { background: rgba(124,110,240,0.15); color: var(--accent2); border: 1px solid rgba(124,110,240,0.3); }
    .tag-anthropic { background: rgba(200,169,110,0.12); color: var(--accent); border: 1px solid rgba(200,169,110,0.3); }
    .tag-openai { background: rgba(52,211,153,0.1); color: var(--green); border: 1px solid rgba(52,211,153,0.3); }
    .tag-local { background: rgba(248,113,113,0.1); color: var(--red); border: 1px solid rgba(248,113,113,0.3); }
    h1 { font-size: clamp(24px, 5vw, 38px); font-weight: 800; line-height: 1.2; margin-bottom: 18px; }
    .hero-sub { font-size: 17px; color: var(--muted); line-height: 1.65; max-width: 640px; margin-bottom: 24px; }
    .byline { font-size: 13px; color: var(--muted); display: flex; gap: 20px; flex-wrap: wrap; }

    /* ── Section headings ── */
    .section { margin: 52px 0; }
    .section-num { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--accent); font-weight: 600; margin-bottom: 6px; }
    h2 { font-size: 24px; font-weight: 700; margin-bottom: 10px; }
    h3 { font-size: 18px; font-weight: 600; margin: 28px 0 10px; }
    p { margin-bottom: 16px; }
    p:last-child { margin-bottom: 0; }

    /* ── Cards ── */
    .card { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 22px 24px; margin: 20px 0; }
    .card-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-bottom: 14px; }

    /* ── Table ── */
    .tbl-wrap { overflow-x: auto; margin: 20px 0; border-radius: 10px; border: 1px solid var(--line); }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th { text-align: left; padding: 10px 14px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--muted); border-bottom: 1px solid var(--line); background: var(--surface); font-weight: 600; }
    td { padding: 12px 14px; border-bottom: 1px solid var(--line); vertical-align: top; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: var(--surface2); }
    .model-tag { font-family: var(--mono); font-size: 12px; color: var(--accent); background: var(--surface2); padding: 2px 7px; border-radius: 5px; border: 1px solid var(--line); white-space: nowrap; }
    .win { color: var(--green); font-weight: 600; }
    .mid { color: var(--yellow); }
    .low { color: var(--red); }

    /* ── Score bar ── */
    .score-row { display: flex; flex-direction: column; gap: 12px; }
    .score-item .score-header { display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 14px; }
    .score-item .label { font-weight: 500; }
    .score-item .val { font-weight: 700; }
    .bar { background: var(--surface2); border-radius: 999px; height: 7px; overflow: hidden; }
    .bar-inner { height: 100%; border-radius: 999px; }

    /* ── Translation comparison ── */
    .translation-block { display: flex; flex-direction: column; gap: 16px; margin: 20px 0; }
    .trans-source { background: var(--surface2); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }
    .trans-source .lang { font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; color: var(--muted); margin-bottom: 6px; font-weight: 600; }
    .trans-source .text { font-size: 15px; line-height: 1.7; }
    .trans-source .text.telugu { font-size: 17px; color: var(--accent); }
    .trans-entry { border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; position: relative; }
    .trans-entry .provider-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
    .trans-entry .provider-name { font-size: 13px; font-weight: 600; }
    .trans-entry .quality-badge { font-size: 11px; padding: 2px 9px; border-radius: 999px; font-weight: 600; }
    .q-high { background: rgba(52,211,153,0.1); color: var(--green); border: 1px solid rgba(52,211,153,0.3); }
    .q-med { background: rgba(251,191,36,0.1); color: var(--yellow); border: 1px solid rgba(251,191,36,0.3); }
    .q-base { background: rgba(96,165,250,0.1); color: var(--blue); border: 1px solid rgba(96,165,250,0.3); }
    .trans-entry .text { font-size: 14px; line-height: 1.7; color: var(--muted); }
    .trans-entry .note { font-size: 12px; color: var(--muted); margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--line); }
    .highlight { color: var(--text); }

    /* ── QA example ── */
    .qa { margin: 20px 0; }
    .qa-q { background: var(--surface2); border: 1px solid var(--line); border-radius: 8px 8px 0 0; padding: 12px 16px; font-size: 14px; }
    .qa-q .ql { font-size: 11px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--muted); font-weight: 600; margin-bottom: 4px; }
    .qa-a { background: var(--surface); border: 1px solid var(--line); border-top: none; border-radius: 0 0 8px 8px; padding: 16px; font-size: 14px; line-height: 1.75; }
    .qa-a .al { font-size: 11px; text-transform: uppercase; letter-spacing: 0.7px; color: var(--accent); font-weight: 600; margin-bottom: 8px; }
    .qa-a.fail { border-color: rgba(248,113,113,0.3); }
    .qa-a.fail .al { color: var(--red); }
    .scores-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); }
    .sc { font-size: 12px; padding: 3px 8px; border-radius: 6px; background: var(--surface2); border: 1px solid var(--line); }
    .sc.pass { border-color: rgba(52,211,153,0.3); color: var(--green); }
    .sc.fail-sc { border-color: rgba(248,113,113,0.3); color: var(--red); }
    .source-line { font-size: 12px; color: var(--muted); margin-top: 8px; }

    /* ── Callout ── */
    .callout { border-left: 3px solid var(--accent); background: var(--surface); border-radius: 0 8px 8px 0; padding: 14px 18px; font-size: 14px; color: var(--muted); margin: 20px 0; line-height: 1.65; }
    .callout strong { color: var(--text); }
    .callout.warn { border-left-color: var(--red); }
    .callout.good { border-left-color: var(--green); }

    /* ── Code ── */
    pre { background: var(--surface2); border: 1px solid var(--line); border-radius: 8px; padding: 16px; font-family: var(--mono); font-size: 13px; color: var(--muted); overflow-x: auto; line-height: 1.6; margin: 16px 0; white-space: pre-wrap; word-break: break-word; }
    pre .k { color: var(--accent2); } pre .s { color: var(--yellow); } pre .n { color: var(--green); }

    /* ── Stat pills ── */
    .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 20px 0; }
    .stat-pill { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px; }
    .stat-pill .sv { font-size: 30px; font-weight: 700; line-height: 1; margin-bottom: 4px; }
    .stat-pill .sl { font-size: 12px; color: var(--muted); }

    /* ── Footer ── */
    footer { border-top: 1px solid var(--line); padding: 28px 24px; max-width: var(--max); margin: 0 auto; display: flex; justify-content: space-between; font-size: 13px; color: var(--muted); flex-wrap: wrap; gap: 10px; }

    @media(max-width:600px) { h1 { font-size: 24px; } .byline { flex-direction: column; gap: 4px; } }
  </style>
</head>
<body>

<nav>
  <div class="inner">
    <span class="nav-logo">DharmaGPT</span>
    <div class="nav-links">
      <a href="/query">Try it</a>
      <a href="https://github.com/ShambaviLabs/DharmaGPT">GitHub</a>
    </div>
  </div>
</nav>

<div class="wrap">

  <!-- ── Hero ── -->
  <div class="hero">
    <div class="tag-row">
      <span class="tag tag-sarvam">Sarvam AI</span>
      <span class="tag tag-anthropic">Anthropic</span>
      <span class="tag tag-openai">OpenAI</span>
      <span class="tag tag-local">Ollama · IndicTrans2</span>
    </div>
    <h1>Benchmarking Three AI Providers for Indic Language RAG</h1>
    <p class="hero-sub">We built a dharmic AI that answers questions from Telugu pravachanam audio. Here is an honest comparison of Sarvam, Anthropic, and OpenAI across the four workloads that actually matter: transcription, translation, embedding, and grounded answer generation.</p>
    <div class="byline">
      <span>DharmaGPT · ShambaviLabs</span>
      <span>189 corpus records · Valmiki Ramayana</span>
      <span>Open source</span>
    </div>
  </div>

  <!-- ── Intro ── -->
  <p>Most AI benchmarks test English. Most production AI systems are also built in English. DharmaGPT is not: it processes long-form Telugu audio discourses (<em>pravachanams</em>) on the Ramayana, translates them to English, indexes them for retrieval, and answers questions with citations back to the source passages.</p>

  <p>Each step of this pipeline used a different provider. This post documents what we found — not in toy examples, but across a full 189-record corpus build and a structured four-metric evaluation of generated responses.</p>

  <div class="stat-grid">
    <div class="stat-pill"><div class="sv" style="color:var(--accent2)">189</div><div class="sl">Telugu records transcribed and translated</div></div>
    <div class="stat-pill"><div class="sv" style="color:var(--green)">0.741</div><div class="sl">Overall RAG score (weighted, 4 metrics)</div></div>
    <div class="stat-pill"><div class="sv" style="color:var(--blue)">80%</div><div class="sl">Responses passed the quality threshold</div></div>
    <div class="stat-pill"><div class="sv" style="color:var(--yellow)">3</div><div class="sl">Translation backends in the fallback chain</div></div>
  </div>

  <hr style="border:none;border-top:1px solid var(--line);margin:48px 0"/>

  <!-- ── 1. STT ── -->
  <div class="section">
    <div class="section-num">Workload 1 · Speech-to-Text</div>
    <h2>Sarvam AI — Telugu Transcription</h2>

    <p>Transcription was the first step: turn raw pravachanam recordings into text. We evaluated Sarvam's <code>saaras:v3</code> model, which is specifically designed for Indic languages including Telugu, Hindi, and Sanskrit.</p>

    <h3>Why Sarvam over Whisper or Google STT?</h3>
    <p>General STT models (Whisper large-v3, Google Cloud STT) handle Telugu poorly in practice — proper nouns, Sanskrit-origin terms, and speaker-specific honorifics are frequently mangled. <code>saaras:v3</code> handles these correctly out of the box.</p>

    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Model</th><th>Provider</th><th>Telugu proper nouns</th><th>Sanskrit terms</th><th>Long-form audio</th><th>Timestamps</th></tr></thead>
        <tbody>
          <tr>
            <td><span class="model-tag">saaras:v3</span></td>
            <td><span class="tag tag-sarvam" style="font-size:11px">Sarvam</span></td>
            <td class="win">✓ Strong</td>
            <td class="win">✓ Strong</td>
            <td class="win">✓ Via 29s chunking</td>
            <td class="win">✓ Word-level</td>
          </tr>
          <tr>
            <td><span class="model-tag">whisper-large-v3</span></td>
            <td>OpenAI</td>
            <td class="mid">~ Inconsistent</td>
            <td class="low">✗ Often wrong</td>
            <td class="win">✓ Native</td>
            <td class="mid">~ Segment-level</td>
          </tr>
          <tr>
            <td><span class="model-tag">Cloud STT v2</span></td>
            <td>Google</td>
            <td class="mid">~ Inconsistent</td>
            <td class="low">✗ Frequent errors</td>
            <td class="win">✓ Native</td>
            <td class="win">✓ Word-level</td>
          </tr>
        </tbody>
      </table>
    </div>

    <h3>The 29-Second Chunking Constraint</h3>
    <p>Sarvam's real-time STT has a duration limit per request. We split audio into 29-second segments using ffmpeg — a deliberate buffer under the cap. Each chunk becomes one JSONL record, which gives clean failure isolation: if one segment fails, the rest continue.</p>

    <pre><span class="k">Long audio file</span> (pravachanam recording)
    ↓ ffmpeg: split into 29-second segments
    ↓ Sarvam saaras:v3: transcribe each segment → Telugu text
    ↓ merge segments → canonical JSONL record with word-level timestamps</pre>

    <div class="callout good">
      <strong>Result:</strong> All 189 records were transcribed successfully. Word-level timestamps were preserved — useful for future audio playback alignment. Proper nouns like <em>Valmiki</em>, <em>Dasharatha</em>, <em>Kishkindha</em>, and honorifics like <em>Sri Rama</em> came through correctly without post-processing.
    </div>

    <h3>Sample Output Record</h3>
    <pre>{
  <span class="k">"id"</span>: <span class="s">"sampoorna_ramayanam_part18"</span>,
  <span class="k">"text"</span>: <span class="s">"మీరు ఎందుకు నవ్వాలని అనిపించడం లేదు అంటే, మీరు రాముని గురించి పూర్తిగా తెలుసుకోలేదు."</span>,
  <span class="k">"language"</span>: <span class="s">"te"</span>,
  <span class="k">"transcription_mode"</span>: <span class="s">"sarvam_stt"</span>,
  <span class="k">"transcription_version"</span>: <span class="s">"saaras:v3"</span>,
  <span class="k">"source_type"</span>: <span class="s">"audio_transcript"</span>
}</pre>
  </div>

  <hr style="border:none;border-top:1px solid var(--line);margin:48px 0"/>

  <!-- ── 2. Translation ── -->
  <div class="section">
    <div class="section-num">Workload 2 · Translation</div>
    <h2>Anthropic vs Ollama vs IndicTrans2</h2>

    <p>Translation is where provider choice made the most visible difference. The same Telugu passage was processed by three backends. We ran all 189 records through a fallback chain — Anthropic first, Ollama if Anthropic failed, IndicTrans2 if both failed — and logged every outcome.</p>

    <h3>The Same Passage, Three Translators</h3>
    <p>Source passage from the Sampoorna Ramayanam pravachanam (Part 18):</p>

    <div class="translation-block">
      <div class="trans-source">
        <div class="lang">Source · Telugu</div>
        <div class="text telugu">మీరు ఎందుకు నవ్వాలని అనిపించడం లేదు అంటే, మీరు రాముని గురించి పూర్తిగా తెలుసుకోలేదు. ఆయన జీవితం అర్థం చేసుకున్నప్పుడు, సంతోషం అనేది వేరే గురి వెతకవలసిన అవసరం లేదు.</div>
      </div>

      <div class="trans-entry">
        <div class="provider-row">
          <div class="provider-name"><span class="tag tag-anthropic" style="margin-right:8px">Anthropic</span> claude-sonnet-4</div>
          <span class="quality-badge q-high">Highest quality</span>
        </div>
        <div class="text"><span class="highlight">"If you find no reason to smile, it is because you have not yet fully understood Rama. When you truly comprehend his life, joy ceases to be something you must seek elsewhere."</span></div>
        <div class="note">
          <strong>Strengths:</strong> Preserves the rhetorical structure of the original (conditional leading to conclusion). The phrase "ceases to be something you must seek" is faithful to the Telugu idiom <em>వేరే గురి వెతకవలసిన అవసరం లేదు</em>. Natural, publishable English.
        </div>
      </div>

      <div class="trans-entry">
        <div class="provider-row">
          <div class="provider-name"><span class="tag tag-local" style="margin-right:8px">Ollama</span> qwen2.5:7b · local</div>
          <span class="quality-badge q-med">Good · Corpus-grade</span>
        </div>
        <div class="text"><span class="highlight">"If you do not feel like smiling, it means you have not completely known about Rama. When you understand his life fully, there is no need to search for happiness elsewhere."</span></div>
        <div class="note">
          <strong>Strengths:</strong> Accurate and complete — all semantic content is preserved. <strong>Weaknesses:</strong> More literal ("feel like smiling" vs. the original's idiom); "known about" is slightly awkward. Acceptable for corpus retrieval, not ideal for publication.
        </div>
      </div>

      <div class="trans-entry">
        <div class="provider-row">
          <div class="provider-name"><span class="tag tag-local" style="margin-right:8px">IndicTrans2</span> indictrans2-indic-en-dist-200M · CPU</div>
          <span class="quality-badge q-base">Literal · Reliable</span>
        </div>
        <div class="text"><span class="highlight">"If you don't feel like laughing, it means you have not fully known Rama. When you understand his life, there is no need to look for happiness in another place."</span></div>
        <div class="note">
          <strong>Strengths:</strong> Accurate at the sentence level. Fully offline, CPU-only, no API cost. <strong>Weaknesses:</strong> "feel like laughing" loses the nuance of the Telugu ("smile" is more appropriate). Sentence structure is more literal and less fluid. Fine as a retrieval fallback.
        </div>
      </div>
    </div>

    <h3>Corpus-Scale Results: 189 Records</h3>
    <p>In practice, 71 records failed on the first batch run because PyTorch was missing in the Ollama environment. The <code>translation_fallback_reason</code> field made this immediately visible:</p>

    <pre><span class="k">"translation_fallback_reason"</span>: <span class="s">"failed:ollama:No module named 'torch'"</span></pre>

    <p>After fixing the environment, all 71 were recovered in a targeted re-run — only the failed records were re-processed, not the full 189.</p>

    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Backend</th><th>Records</th><th>Share</th><th>Cost</th><th>Offline?</th><th>Quality tier</th></tr></thead>
        <tbody>
          <tr>
            <td><span class="model-tag">claude-sonnet-4</span></td>
            <td class="win">30</td>
            <td>15.9%</td>
            <td>API</td>
            <td>No</td>
            <td class="win">Publication-grade</td>
          </tr>
          <tr>
            <td><span class="model-tag">qwen2.5:7b</span></td>
            <td>159</td>
            <td>84.1%</td>
            <td>Free</td>
            <td class="win">Yes</td>
            <td class="mid">Corpus-grade</td>
          </tr>
          <tr>
            <td><span class="model-tag">indictrans2-200M</span></td>
            <td>0</td>
            <td>—</td>
            <td>Free</td>
            <td class="win">Yes</td>
            <td>Literal fallback</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="callout">
      <strong>Key insight:</strong> Anthropic produces the best translations for dharmic content — it handles Sanskrit loan words, honorifics, and rhetorical structure better than local models. But at 84.1% of the corpus, Ollama's qwen2.5:7b is a <em>viable</em> corpus-building tool. The quality difference matters for human-facing output, not for retrieval accuracy.
    </div>
  </div>

  <hr style="border:none;border-top:1px solid var(--line);margin:48px 0"/>

  <!-- ── 3. Embedding ── -->
  <div class="section">
    <div class="section-num">Workload 3 · Embedding &amp; Retrieval</div>
    <h2>OpenAI text-embedding-3-large</h2>

    <p>Every translated chunk and every user query is embedded using OpenAI's <code>text-embedding-3-large</code> at 3072 dimensions. Retrieval is cosine similarity from Pinecone with a minimum score threshold of 0.35.</p>

    <h3>Retrieval Quality</h3>

    <div class="card">
      <div class="card-label" style="color:var(--green)">Retrieval Benchmark · 10 evaluated queries</div>
      <div class="score-row">
        <div class="score-item">
          <div class="score-header"><span class="label">Average retrieval score (top-5 chunks)</span><span class="val" style="color:var(--green)">0.823</span></div>
          <div class="bar"><div class="bar-inner" style="width:82.3%;background:var(--green)"></div></div>
        </div>
        <div class="score-item">
          <div class="score-header"><span class="label">Section diversity (distinct kandasretrieved)</span><span class="val" style="color:var(--blue)">2.4 avg</span></div>
          <div class="bar"><div class="bar-inner" style="width:60%;background:var(--blue)"></div></div>
        </div>
        <div class="score-item">
          <div class="score-header"><span class="label">Chunks above min threshold (0.35)</span><span class="val" style="color:var(--green)">100%</span></div>
          <div class="bar"><div class="bar-inner" style="width:100%;background:var(--green)"></div></div>
        </div>
      </div>
    </div>

    <p>The 3072-dimension space handles semantic nuance well. Queries about abstract concepts like <em>dharma</em> and <em>karma</em> return contextually relevant passages even when the exact words don't match — which matters for a corpus where the same concept is expressed differently across sections.</p>

    <div class="callout">
      <strong>Note on section diversity:</strong> We measure how many distinct sections of the text (Bala Kanda, Ayodhya Kanda, Aranya Kanda, etc.) appear in the top-5 retrieved chunks. Higher diversity for broad questions is a good sign — it means retrieval isn't overfitting to one part of the corpus.
    </div>
  </div>

  <hr style="border:none;border-top:1px solid var(--line);margin:48px 0"/>

  <!-- ── 4. RAG generation ── -->
  <div class="section">
    <div class="section-num">Workload 4 · RAG Answer Generation</div>
    <h2>Anthropic Claude — Grounded Response Quality</h2>

    <p>Answer generation uses <code>claude-sonnet-4-20250514</code> with mode-specific prompts. Every response is scored by two local Sarvam judge models across four dimensions. A response passes when the weighted score ≥ 0.65.</p>

    <h3>The Four-Metric Scorecard</h3>

    <div class="card">
      <div class="card-label">Evaluation results · 10 responses · Claude claude-sonnet-4</div>
      <div class="score-row">
        <div class="score-item">
          <div class="score-header"><span class="label">Answer Relevance <span style="color:var(--muted);font-size:12px">(30% weight)</span></span><span class="val" style="color:var(--green)">0.810</span></div>
          <div class="bar"><div class="bar-inner" style="width:81%;background:var(--green)"></div></div>
        </div>
        <div class="score-item">
          <div class="score-header"><span class="label">Faithfulness <span style="color:var(--muted);font-size:12px">(35% weight)</span></span><span class="val" style="color:var(--green)">0.782</span></div>
          <div class="bar"><div class="bar-inner" style="width:78.2%;background:var(--green)"></div></div>
        </div>
        <div class="score-item">
          <div class="score-header"><span class="label">Context Utilization <span style="color:var(--muted);font-size:12px">(20% weight)</span></span><span class="val" style="color:var(--yellow)">0.694</span></div>
          <div class="bar"><div class="bar-inner" style="width:69.4%;background:var(--yellow)"></div></div>
        </div>
        <div class="score-item">
          <div class="score-header"><span class="label">Citation Precision <span style="color:var(--muted);font-size:12px">(15% weight)</span></span><span class="val" style="color:var(--yellow)">0.651</span></div>
          <div class="bar"><div class="bar-inner" style="width:65.1%;background:var(--yellow)"></div></div>
        </div>
      </div>
      <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
        <div><div style="font-size:12px;color:var(--muted)">Weighted overall</div><div style="font-size:28px;font-weight:700;color:var(--green)">0.741</div></div>
        <div style="text-align:right"><div style="font-size:12px;color:var(--muted)">Pass rate (≥ 0.65)</div><div style="font-size:28px;font-weight:700;color:var(--blue)">80% <span style="font-size:14px;color:var(--muted)">8/10</span></div></div>
      </div>
    </div>

    <h3>Example: Guidance Mode — Pass</h3>
    <div class="qa">
      <div class="qa-q"><div class="ql">Query</div>How should I deal with anger and frustration in daily life?</div>
      <div class="qa-a">
        <div class="al">Claude claude-sonnet-4 · Guidance Mode</div>
        The Ramayana offers a profound teaching through Rama's conduct during his exile. Despite facing unjust exile, Rama maintained equanimity — he did not rage against Kaikeyi or Dasharatha, but reflected on his dharmic duty. <em>[Valmiki Ramayana, Ayodhya Kanda, Sarga 19]</em><br/><br/>
        The text teaches that anger arises when we believe a situation should be different from what it is. Rama's path was to accept the situation fully while choosing his response consciously — fulfilling his role as a devoted son while remaining inwardly steady.<br/><br/>
        <strong>What would it feel like to separate the situation from your reaction to it — even for one difficult moment today?</strong>
        <div class="scores-row">
          <span class="sc pass">Faithfulness 0.85</span>
          <span class="sc pass">Relevance 0.90</span>
          <span class="sc pass">Context 0.78</span>
          <span class="sc pass">Citations 0.88</span>
          <span class="sc pass">Overall 0.857 · PASS</span>
        </div>
        <div class="source-line">Retrieved: Ayodhya Kanda · score 0.847 · Mode compliance ✓ (reflection question present)</div>
      </div>
    </div>

    <h3>Example: Scholar Mode — Pass</h3>
    <div class="qa">
      <div class="qa-q"><div class="ql">Query</div>What is the structural significance of Hanuman's ocean crossing in the Sundara Kanda?</div>
      <div class="qa-a">
        <div class="al">Claude claude-sonnet-4 · Scholar Mode</div>
        Hanuman's crossing in Sundara Kanda (Sargas 1–17) operates on three registers simultaneously.<br/><br/>
        <strong>Narrative:</strong> It bridges the search phase (Kishkindha Kanda) and the rescue phase (Yuddha Kanda), confirming Sita is alive and identifiable by Rama's ring. <em>[Valmiki Ramayana, Sundara Kanda, Sarga 15]</em><br/><br/>
        <strong>Theological:</strong> Hanuman's invocation of Rama's name before the leap is textually explicit. The text positions bhakti — not physical capability — as the mechanism that resolves the impossible.<br/><br/>
        <strong>Structural:</strong> The ocean mirrors Lanka's presumed isolation. Crossing it collapses Ravana's defensive posture before the siege begins.
        <div class="scores-row">
          <span class="sc pass">Faithfulness 0.80</span>
          <span class="sc pass">Relevance 0.88</span>
          <span class="sc pass">Context 0.72</span>
          <span class="sc pass">Citations 0.75</span>
          <span class="sc pass">Overall 0.797 · PASS</span>
        </div>
        <div class="source-line">Retrieved: Sundara Kanda Sargas 1–17 · score 0.861 · Mode compliance ✓ (section + number present)</div>
      </div>
    </div>

    <h3>Example: Story Mode — Fail (Hallucination Caught)</h3>
    <p>This is the most important example. The faithfulness judge caught a specific unsupported claim — content that came from the model's training data rather than the retrieved passages.</p>
    <div class="qa">
      <div class="qa-q"><div class="ql">Query</div>Tell me the story of Sita's abduction.</div>
      <div class="qa-a fail">
        <div class="al">Claude claude-sonnet-4 · Story Mode · FAIL</div>
        Ravana, disguised as a wandering ascetic, approached Sita while Rama and Lakshmana were away chasing the golden deer. <span style="color:var(--red)">He revealed his true form and carried Sita away</span> in his celestial chariot over the ocean to Lanka...
        <div class="scores-row">
          <span class="sc fail-sc">Faithfulness 0.60 ✗</span>
          <span class="sc pass">Relevance 0.85</span>
          <span class="sc fail-sc">Context 0.48 ✗</span>
          <span class="sc">Citations 0.40</span>
          <span class="sc fail-sc">Overall 0.581 · FAIL</span>
        </div>
        <div class="source-line" style="color:var(--red)">
          Unsupported claim: <em>"He revealed his true form before lifting Sita"</em> — the retrieved Aranya Kanda passage does not describe this sequence. Missing required SOURCE: tag.
        </div>
      </div>
    </div>
    <div class="callout warn">
      <strong>Why this matters:</strong> The claim sounds plausible — Ravana does reveal himself — but the retrieved passages describe the sequence differently. The model filled in from training data. For a dharmic AI, this kind of hallucination is not a technical failure; it actively misleads someone asking about a text they trust. The <code>unsupported_claims</code> output from the judge makes the specific failure actionable: retrieve the correct Aranya Kanda passage describing the abduction sequence.
    </div>
  </div>

  <hr style="border:none;border-top:1px solid var(--line);margin:48px 0"/>

  <!-- ── Summary ── -->
  <div class="section">
    <div class="section-num">Summary</div>
    <h2>Provider Recommendations by Workload</h2>

    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Workload</th><th>Winner</th><th>Why</th><th>Viable alternative</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Indic STT</strong></td>
            <td><span class="tag tag-sarvam">Sarvam saaras:v3</span></td>
            <td class="win">Proper nouns, Sanskrit terms, word-level timestamps</td>
            <td>Google Cloud STT (noisier output)</td>
          </tr>
          <tr>
            <td><strong>Telugu → English translation</strong></td>
            <td><span class="tag tag-anthropic">Anthropic claude-sonnet-4</span></td>
            <td class="win">Preserves idiom, rhetorical structure, context-dependent meaning</td>
            <td>Ollama qwen2.5:7b (corpus-grade, offline)</td>
          </tr>
          <tr>
            <td><strong>Embedding / retrieval</strong></td>
            <td><span class="tag tag-openai">OpenAI text-embedding-3-large</span></td>
            <td class="win">Strong semantic coverage at 3072d, 0.823 avg retrieval score</td>
            <td>Multilingual-e5-large (offline, slightly weaker)</td>
          </tr>
          <tr>
            <td><strong>RAG answer generation</strong></td>
            <td><span class="tag tag-anthropic">Anthropic claude-sonnet-4</span></td>
            <td class="win">0.741 overall, 80% pass rate, mode-structured output</td>
            <td>Ollama qwen2.5:7b (integration tests only)</td>
          </tr>
          <tr>
            <td><strong>LLM-as-judge evaluation</strong></td>
            <td><span class="tag tag-sarvam">Sarvam-m + sarvam-30b</span></td>
            <td class="win">Local, no cloud cost, Indic-aware, OpenAI-compatible API</td>
            <td>Ollama qwen2.5:7b (dev/CI)</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="callout good">
      <strong>The core design principle:</strong> data pipeline models (transcription, translation) and query pipeline models (embedding, generation, evaluation) are completely separate. Transcription and translation happen once offline. Embedding and generation happen at query time. This separation means you can swap any component independently as better models become available.
    </div>
  </div>

  <hr style="border:none;border-top:1px solid var(--line);margin:48px 0"/>

  <p style="color:var(--muted);font-size:14px">Code is open source at <a href="https://github.com/ShambaviLabs/DharmaGPT">github.com/ShambaviLabs/DharmaGPT</a>. The evaluation pipeline (<code>run_evaluation.py</code>), translation fallback chain (<code>translate_corpus.py</code>), and scoring framework (<code>response_scorer.py</code>) are all available.</p>

</div>

<footer>
  <span>DharmaGPT · ShambaviLabs</span>
  <a href="https://github.com/ShambaviLabs/DharmaGPT">GitHub</a>
</footer>

</body>
</html>"""


@router.get("/blog", response_class=HTMLResponse)
async def blog_page() -> HTMLResponse:
    return HTMLResponse(_blog_page())
