# MFASHA: Kinyarwanda agriculture chatbot (text and voice)

A farmer types a question or records a voice message in Kinyarwanda. MFASHA replies with a **verified,
officer-reviewed** answer in writing and, optionally, aloud. It never generates advice: it retrieves
reviewed passages and **refers the farmer to an agricultural officer** when it is not sure.

```
voice -> speech-to-text -> preprocessing -> classification -> retrieval -> referral policy -> answer -> text-to-speech
```

This repository turns the Colab notebook (`notebooks/mfasha_notebook.ipynb`) and the capstone proposal
(`docs/MFASHA_proposal.pdf`) into a deployable web application.

## Quick start (no GPU, no downloads)

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt && pip install -e .
cp .env.example .env
make run                                                  # http://localhost:8000   (API docs: /docs)
make test                                                 # 61 tests, about 1 second
```

The repository ships a **12-passage placeholder knowledge base** (`data/sample/`) so everything runs on day one.
It is NOT real agricultural content. Replace it with the real data as shown below.

## Using the real data and models from the notebook

1. In Colab, make sure Drive holds: `data/clean/passages.jsonl`, the officer's label and review CSVs,
   `results/referral_threshold.json`, `models/kinya-e5-large/best`, the classifier `.joblib`, the MMS adapter and TTS folder.
2. Download that **Mfasha chatbot** folder, then:
   ```bash
   python scripts/import_notebook_artifacts.py --drive "/path/to/Mfasha chatbot"
   pip install -r requirements-ml.txt
   ```
3. Edit `.env`:
   ```
   MFASHA_KNOWLEDGE_PATH=data/processed/passages.jsonl
   MFASHA_REVIEWED_PATH=data/processed/officer_reviewed_passages.csv
   MFASHA_LABELS_PATH=data/processed/category_labels_officer.csv
   MFASHA_RETRIEVER=embedding
   MFASHA_ENABLE_STT=true
   MFASHA_ENABLE_TTS=true
   ```
No data yet? `python scripts/prepare_data.py` downloads `kinya-ag-retrieval` and builds the files from scratch.

## Project layout

```
src/mfasha/
  domain/          data objects (Passage, PipelineResult, ReferralReason) and exceptions
  interfaces.py    abstract Retriever, Classifier, SpeechToText, TextToSpeech
  nlp/             text cleaning and tokenising
  retrieval/       BM25 (from scratch), TF-IDF, hybrid fusion, dense embeddings (e5)
  classification/  keyword labeller, TF-IDF + LR/SVM classifier
  referral/        referral rules (chain of responsibility) and threshold tuning
  knowledge/       knowledge base and loader (reviewed flags, officer labels)
  speech/          WAV helpers, MMS speech-to-text, MMS text-to-speech, "unavailable" null objects
  pipeline.py      the eight-stage pipeline, with per-stage timing
  factory.py       composition root: the only place that picks concrete classes
  storage/         SQLAlchemy tables and the repository (PostgreSQL or SQLite)
  api/             FastAPI app, routes, request/response schemas
frontend/          farmer web app (HTML, CSS, JS; records voice and converts it to WAV in the browser)
scripts/           prepare_data, train_classifier, evaluate_retrieval, benchmark, import_notebook_artifacts
tests/             unit/, integration/, performance/
docs/              ARCHITECTURE, TESTING, DEPLOYMENT, DEMO_SCRIPT
```

## API

| Method and path | Who | Purpose |
|---|---|---|
| `GET /api/health` | anyone | status, passage counts, active components |
| `POST /api/ask/text` | farmer | `{question, with_audio}` -> answer |
| `POST /api/ask/voice` | farmer | multipart WAV (`audio`, `with_audio`) -> answer + transcription |
| `POST /api/feedback` | farmer | rating 1-5 and useful yes/no for an answer |
| `POST /api/officer/reviews` | officer (`X-API-Key`) | correct / partially_correct / incorrect, plus relevant/clear/safe |
| `GET /api/admin/stats` | admin (`X-API-Key`) | referral rate, latency, ratings, officer-correct rate (objective 3: at least 70%) |

## Deploying

See `docs/DEPLOYMENT.md` (Docker, docker-compose with PostgreSQL, Hugging Face Spaces, Render).
