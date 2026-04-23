# DharmaGPT

> AI-powered wisdom from the Valmiki Ramayana, Mahabharata, Bhagavad Gita, Upanishads, and Puranas — built for Bharat, accessible to the world.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made in India](https://img.shields.io/badge/Made%20in-India-orange)](https://github.com/dharmagpt)
[![Powered by Sarvam AI](https://img.shields.io/badge/Audio-Sarvam%20AI-blue)](https://sarvam.ai)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## What is DharmaGPT?

DharmaGPT is an open-source, mobile-first AI application that makes the wisdom of Hindu sacred texts accessible through natural conversation. Ask life questions, hear factual story retellings, find verse references, and listen to Sanskrit chantings — all grounded in real source texts with citations.

**This is not a chatbot that makes things up.** Every answer is retrieved from indexed source texts (Valmiki Ramayana, Mahabharata, Bhagavad Gita, Upanishads, Puranas) and cited by kanda, parva, chapter, and verse.

---

## Features

| Feature | Description |
|---|---|
| **Life Guidance** | Ask dharmic questions, get wisdom grounded in actual verses |
| **Story Generation** | Factual retellings from source texts, chapter-accurate |
| **Children's Mode** | Age-appropriate stories with moral teachings |
| **Scholarly Lookup** | Search verses, themes, characters across all texts |
| **Audio Support** | Listen to Sanskrit chantings, search within pravachanams |
| **22 Indian Languages** | Powered by Sarvam AI's Saaras v3 for multilingual audio |

---

## Tech Stack

```
Mobile App      →  React Native (Expo)
Backend API     →  FastAPI (Python)
LLM             →  Claude (Anthropic) via API
Vector Search   →  Pinecone
Embeddings      →  OpenAI text-embedding-3-large
Audio STT/TTS   →  Sarvam AI (Saaras v3 + Bulbul v3)
Text Sources    →  valmikiramayan.net, TTD publications, sacred-texts.com
```

---

## Project Structure

```
dharmagpt/
├── backend/                  # FastAPI backend
│   ├── api/routes/           # API route handlers
│   ├── core/                 # RAG engine, retrieval, LLM
│   ├── pipelines/            # Data ingestion pipelines
│   ├── models/               # Pydantic models
│   └── utils/                # Helpers, logging
├── mobile/                   # React Native (Expo) app
│   ├── app/                  # Expo Router screens
│   └── src/
│       ├── components/       # Reusable UI components
│       ├── screens/          # Screen components
│       ├── services/         # API clients
│       ├── store/            # Zustand state
│       ├── hooks/            # Custom hooks
│       └── navigation/       # Nav config
├── scripts/
│   ├── scraper/              # valmikiramayan.net scraper
│   ├── audio/                # Sarvam audio pipeline
│   └── embed/                # Pinecone embedding pipeline
├── data/                     # Local data (gitignored)
├── docs/                     # Architecture, API docs
└── tests/                    # Backend + mobile tests
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 20+
- Expo CLI (`npm install -g expo-cli`)
- API keys: Anthropic, Pinecone, OpenAI (embeddings), Sarvam AI

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn api.main:app --reload --port 8000
```

### Mobile

```bash
cd mobile
npm install
cp .env.example .env   # set EXPO_PUBLIC_API_URL
npx expo start
```

### Ingest Data

```bash
# 1. Scrape valmikiramayan.net
python scripts/scraper/valmiki_scraper.py --kanda all --output data/chunks/

# 2. Process your audio files
python scripts/audio/audio_pipeline.py --input data/audio/ --batch

# 3. Embed and index everything
python scripts/embed/embed_and_index.py --input data/chunks/ --index dharma-gpt
```

---

## Contributing

We welcome contributions — especially:
- **Sanskrit scholars** to verify citations and translations
- **Developers** to extend the text corpus (Mahabharata, Puranas)
- **Audio contributors** to add pravachanam recordings
- **Language contributors** for regional language support

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Sources & Acknowledgements

- **Valmiki Ramayana** — [valmikiramayan.net](https://www.valmikiramayan.net/) (K. M. K. Murthy translation)
- **Sundara Kanda** — TTD Edition, trans. Smt. Krishna Kota (Tirumala Tirupati Devasthanams, 2013)
- **Mahabharata** — Kisari Mohan Ganguli translation (public domain)
- **Bhagavad Gita** — Multiple public domain translations
- **Upanishads** — Max Müller & Patrick Olivelle translations
- **Audio Processing** — [Sarvam AI](https://sarvam.ai) Saaras v3 (22 Indian languages)

---

## License

MIT — free to use, study, and extend. Attribution appreciated.

---

*Satyam Vada. Dharmam Chara. — Speak truth. Walk the path of dharma.*
