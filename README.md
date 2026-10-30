# MFASHA: A Kinyarwanda Agriculture Chatbot with Text and Voice Support

BSc. in Software Engineering, African Leadership University (ALU)
Capstone project, September 2026

| | |
|---|---|
| **Student** | Carine Ahishakiye Yibukabayo |
| **Supervisor** | Hubert Apana |
| **Repository** | https://github.com/carine-ahishakiye/Mfasha-Chatbot- |
| **Walkthrough video** | `<ADD LINK HERE>` |
| **Technical report (PDF, max 5 pages)** | `<ADD LINK HERE>` |
| **Live demo (if deployed)** | `<ADD LINK HERE>` |

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Objectives](#3-objectives)
4. [Scope](#4-scope)
5. [System Pipeline](#5-system-pipeline)
6. [Data Sources](#6-data-sources)
7. [Technical Requirements](#7-technical-requirements)
8. [Installation and Running](#8-installation-and-running)
9. [Configuration](#9-configuration)
10. [API Endpoints](#10-api-endpoints)
11. [Testing and Evaluation](#11-testing-and-evaluation)
12. [Repository Structure](#12-repository-structure)
13. [Alignment with the Proposal](#13-alignment-with-the-proposal)
14. [Ethics and Intended Use](#14-ethics-and-intended-use)
15. [Deployment](#15-deployment)
16. [Walkthrough Video and Technical Report](#16-walkthrough-video-and-technical-report)
17. [References](#17-references)

---

## 1. Project Overview

Most rural households in Rwanda make their living from farming. The National Institute of Statistics of Rwanda (NISR, 2025) reports about 2.2 million agricultural households in 2024, which is 65.3% of all households, and 88.4% of those households named agriculture as their main livelihood. Many farmers still depend on extension officers, radio programmes and meetings, none of which can answer a question on the spot when a problem appears in the field.

**MFASHA** is a Kinyarwanda agriculture chatbot. A farmer types a question or records a voice message, and the system replies in written Kinyarwanda and can read the answer aloud. It is meant to sit alongside extension services and the Tunga call-centre service, not to replace them.

Key design decisions taken from the proposal:

- **Retrieval, not generation.** Answers are selected from a verified agricultural knowledge base. No model in the pipeline generates new agricultural advice, because machine-generated advice needs expert checking before it can be trusted (Ibrahim et al., 2024).
- **Referral instead of guessing.** If the best match is not confident enough, the system returns a referral message and advises the farmer to contact an agricultural officer.
- **Candidates against baselines.** Pretrained components are assessed against simpler baselines and adopted only if the evidence supports it.

## 2. Problem Statement

1. **Advice is not available when needed.** One extension officer may serve a large number of farmers, and digital tools are limited by weak network coverage, cost, low digital skills and a lack of suitable devices (Choruma et al., 2024; Mapiye et al., 2023).
2. **Few services support Kinyarwanda in both text and voice.** Kinyarwanda is a low-resource language for NLP, and it is not yet known which of the newly published Kinyarwanda resources perform well enough on agricultural questions and farmers' voice messages.
3. **Trust.** A chatbot built on unchecked information can give incomplete or wrong advice (Ibrahim et al., 2024).

## 3. Objectives

**Main objective:** to develop and evaluate a Kinyarwanda agriculture chatbot that gives farmers timely agricultural information through text and voice messages.

**Specific objectives**

1. Validate, by the end of week 3, whether the topics in the `kinya-ag-retrieval` dataset cover the agricultural information that farmers need most, through short discussions with up to 10 farmers and the three agricultural officers in Bumbogo Sector.
2. Design and develop, by the start of week 9, a web-based chatbot that accepts Kinyarwanda text and voice questions and replies in written and spoken Kinyarwanda. Each candidate pretrained model is compared with a simple baseline on held-out data and adopted only if it clearly outperforms its baseline.
3. Evaluate the prototype by the end of week 10 with about 30 farmers and three agricultural officers. Target: at least 70% of sampled answers rated correct or partially correct by officers.

## 4. Scope

**Geographical scope.** Selected farmers in Bumbogo Sector, Gasabo District, Kigali City. The project does not try to represent all farmers in Rwanda.

**Content scope**

- Crop production and basic farming practices
- Common crop pests and diseases
- Livestock care and management
- Basic animal health information
- Weather-related farming advice, where suitable information exists
- Government agricultural programmes and services
- Referrals to agricultural officers for questions that need professional attention
- Markets and agricultural inputs, where suitable information exists

MFASHA does not give medical, financial or legal advice and is not an emergency service. It is a web-based prototype for testing and evaluation, not a nationwide production platform. Training a new language, retrieval or speech model from scratch is outside the scope.

**Time scope.** About ten weeks (September to November 2026).

## 5. System Pipeline

The proposal defines an eight-stage pipeline. Stages are kept separate so each can be evaluated and replaced on its own.

```
 Voice question                         Typed question
      |                                       |
 1. Voice input (browser recording)           |
      |                                       |
 2. Speech-to-text ---------------------------+
                         |
              3. Text preprocessing
                         |
        4. Question understanding / classification
                         |
        5. Answer retrieval and ranking
                         |
        6. Verified answer (confidence threshold)
           else -> referral message
                         |
              7. Text-to-speech
                         |
              8. Spoken response
```

An answer is released only when it comes from the reviewed knowledge base and its score passes a confidence threshold set on validation data. Otherwise the farmer receives a referral message.

## 6. Data Sources

No primary data is collected from farmers for training. MFASHA builds on two public Kinyarwanda datasets published by C4IR-RW on Hugging Face:

| Dataset | Purpose |
|---|---|
| [`kinya-ag-retrieval`](https://huggingface.co/datasets/C4IR-RW/kinya-ag-retrieval) (C4IR-RW, 2026a) | Question-and-answer data for retrieval, evaluation of retrieval and ranking, and the candidate knowledge base |
| [`kinya-ag-tts`](https://huggingface.co/datasets/C4IR-RW/kinya-ag-tts) (C4IR-RW, 2026b) | Paired Kinyarwanda text and audio for spoken output and speech-to-text assessment |

Datasets are reviewed for relevance, accuracy and licence terms before use. Where topics are not covered well enough, approved agricultural documents may be added. Data is split roughly 70% training, 15% validation and 15% testing, and official splits are used where a dataset provides them. Duplicate or near-duplicate questions are kept in the same split to avoid leakage.

## 7. Technical Requirements

The versions below are the ones declared in this repository (`pyproject.toml`, `requirements.txt`, `requirements-dev.txt`).

### Software

| Requirement | Version |
|---|---|
| Python | 3.10 or newer |
| FastAPI | >= 0.110 |
| Uvicorn | >= 0.29 |
| Pydantic | >= 2.0 |
| PyTorch | latest compatible (`torch`, unpinned) |
| Hugging Face Transformers | >= 4.45 |
| Sentence-Transformers | >= 3.0 |
| huggingface_hub, numpy, scipy, librosa, soundfile, av, python-dotenv | see `requirements.txt` |
| *Development only:* pytest, httpx, pandas, jiwer | see `requirements-dev.txt` |

### Models used by the application (see `mfasha/config.py`)

| Component | Model |
|---|---|
| Speech-to-text | `facebook/mms-1b-all` with the Kinyarwanda (`kin`) adapter, fine-tuned adapter weights loaded from `models/mms-kin-adapter/best.pt` |
| Retrieval | `intfloat/multilingual-e5-large`, fine-tuned, loaded from `models/kinya-e5-large/best` |
| Text-to-speech | `facebook/mms-tts-kin` |

### Hardware and environment

- The first start downloads the trained files and the MMS model weights (the project documentation estimates about 6 GB in total), so a stable internet connection and enough free disk space are needed.
- A GPU is optional. The application picks up a GPU automatically if present. Without one, typed questions are quick but voice questions take noticeably longer.
- Experiments in the notebook were run on Google Colab.
- A modern browser with microphone access is needed to record voice questions.

## 8. Installation and Running

### 8.1 Clone the repository

```bash
git clone https://github.com/carine-ahishakiye/Mfasha-Chatbot-.git
cd Mfasha-Chatbot-
```

### 8.2 Create a virtual environment and install dependencies

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Use `requirements.txt` instead if you only want to run the app and not the tests or evaluation scripts.

### 8.3 Configure the environment

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Open `.env` and set:

- `HF_TOKEN`: a Hugging Face **Read** token
- `HF_ASSETS_REPO`: the private Hugging Face repo that holds the trained files (for example `YOUR_USER/mfasha-assets`). Only needed if the model files are not already in the project folders.

No commercial AI API key is needed, because the answer is the best retrieved passage.

> The trained model weights (`models/`) are not stored in Git. They are kept in a private Hugging Face repository and downloaded on first start. `scripts/colab_push_assets.py` is the script used to upload them from Colab (see `DEPLOY.md`). If you need access, contact the author.

### 8.4 Run the application

```bash
python app.py
```

Open http://127.0.0.1:7860. The page offers a typed-question tab and a voice-question tab. The port can be changed with the `PORT` environment variable.

## 9. Configuration

Set these in `.env` (see `.env.example` and `mfasha/config.py`).

| Variable | Purpose |
|---|---|
| `HF_TOKEN` | Read token for the repository that holds the trained files |
| `HF_ASSETS_REPO` | That repository, for example `YOUR_USER/mfasha-assets` |
| `REFERRAL_THRESHOLD` | Optional. Overrides `results/referral_threshold.json`. Questions whose best passage scores below it are referred (`0` = never refer) |
| `TOP_K` | Optional. Number of passages returned (default 5) |
| `MAX_AUDIO_SECONDS` | Optional. Longest accepted voice recording (default 30) |
| `TIER_MIN_SCORE`, `TIER_HIGH_MARGIN`, `TIER_MEDIUM_MARGIN` | Optional. Cutoffs for the confidence badge |
| `PORT` | Optional. Server port (default 7860) |

`results/referral_threshold.json` is read at start-up and must be committed. If it is missing, the threshold falls back to 0 and no question is ever referred.

## 10. API Endpoints

| Method and path | Purpose |
|---|---|
| `GET /` | Landing page |
| `GET /chat` | Chat interface |
| `GET /health` | Health check |
| `POST /api/ask` | Submit a typed question, returns the answer, confidence level, related passages and passage id |
| `POST /api/transcribe` | Submit audio recorded in the browser, returns the transcribed text |
| `POST /api/speak` | Submit text, returns spoken audio |
| `POST /api/feedback` | Store helpful / not-helpful feedback for an answer |

The server limits question length, upload size and request rate per visitor.

## 11. Testing and Evaluation

### 11.1 Commands

```bash
# Unit and endpoint tests (no model downloads needed)
python -m pytest tests

# Each model on its own, using the real files
python scripts/smoke_test.py

# Farming questions from unseen passages plus off-topic questions
python scripts/evaluate_answers.py

# Full evaluation, written to results/evaluation_report.md
python scripts/evaluate_system.py
```

### 11.2 Test files

| File | Covers |
|---|---|
| `tests/test_pipeline.py` | Answer / refer / empty logic of the pipeline |
| `tests/test_confidence.py` | Confidence level calculation |
| `tests/test_numbers_and_text.py` | Text cleaning and number-to-Kinyarwanda-words conversion |
| `tests/test_voice_and_audio.py` | Voice handling and audio utilities |
| `tests/test_api.py` | Web endpoints |
| `tests/test_ratelimit.py` | Per-visitor rate limiting |

### 11.3 Evaluation plan (from the proposal)

Testing happens at three levels.

1. **Component level**, each against its baseline on held-out data:
   - Retrieval and ranking: Recall@k, top-1 accuracy, MRR (nDCG if graded relevance is available), officer relevance ratings, retrieval time
   - Speech-to-text: Word Error Rate (WER), transcription quality, processing time
   - Text-to-speech: native-speaker ratings of clarity, naturalness (MOS-style) and pronunciation of agricultural terms, audio generation time
   - Question classification (as proposed): accuracy, precision, recall, macro F1
2. **System level:** interface, backend and models working together. Test cases include text questions, voice questions, empty inputs, unclear recordings, spelling variations and questions outside the knowledge base. Response time is measured per stage and end to end, and fallback behaviour is checked.
3. **Pilot evaluation** in Bumbogo Sector with about 30 adult farmers and three agricultural extension officers or experts (purposive sampling). Officers rate a sample of answers as correct, partially correct, incorrect, relevant, clear and safe. Usability and satisfaction are measured with ratings, task completion and a short Likert-scale questionnaire. Target: at least 70% of sampled answers rated correct or partially correct.

Results apply to the selected sample only and are not claimed to hold for all farmers in Rwanda. The project does not claim that MFASHA raises crop yields.

### 11.4 Where to find the measured results

Measured results are generated by the evaluation scripts and stored in `results/`:

- `results/evaluation_report.md`: full evaluation report generated by `scripts/evaluate_system.py`
- `results/retrieval_*.csv`, `results/asr_*.csv`: retrieval and speech-recognition comparisons
- `results/plots/`: result plots
- `results/referral_threshold.json`: the confidence threshold used by the app
- `results/passages_for_officer_review.xlsx`: passages prepared for officer review

The technical report (see Section 16) summarises these results.

## 12. Repository Structure

```
Mfasha-Chatbot-/
├── app.py                     # Application entry point (starts the FastAPI app)
├── mfasha/                    # Main Python package
│   ├── pipeline.py            # Answer / refer logic
│   ├── retriever.py           # Passage retrieval and ranking
│   ├── asr.py                 # Speech-to-text
│   ├── tts.py                 # Text-to-speech
│   ├── voice.py               # Voice question handling
│   ├── audio.py               # Audio utilities
│   ├── confidence.py          # Confidence level from retrieval scores
│   ├── text_utils.py          # Text cleaning
│   ├── kin_numbers.py         # Numbers and units written as Kinyarwanda words
│   ├── ratelimit.py           # Per-visitor rate limiting
│   ├── assets.py              # Downloads trained files on first start
│   ├── interfaces.py          # Component interfaces
│   ├── evaluation.py          # Evaluation helpers
│   ├── config.py              # Paths, model names and settings
│   └── web/                   # Web layer
│       ├── app.py, routes.py, schemas.py, services.py, messages.py
│       ├── templates/         # landing.html, chat.html
│       └── static/            # CSS and JavaScript for the interface
├── scripts/                   # smoke_test.py, evaluate_answers.py,
│                              # evaluate_system.py, colab_push_assets.py
├── tests/                     # pytest test suite
├── notebook/                  # mfasha_agri_bot.ipynb (experiments)
├── data/                      # Cleaned passages, queries and splits
├── results/                   # Evaluation outputs, plots, referral threshold
├── eval/                      # off_topic_rw.txt (off-topic questions)
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt       # Test and evaluation dependencies
├── pyproject.toml             # Package metadata and pytest settings
├── .env.example               # Environment variable template
├── DEPLOY.md                  # Deployment procedure
└── README.md
```

`models/` (trained weights) is excluded by `.gitignore` and downloaded on first start.

## 13. Alignment with the Proposal

The proposal treats KinyaBERT, kiny-colbert-free and kinya-flex-tts as **candidate** components that must be compared against baselines and may be adopted, replaced or dropped depending on measured results (Sections 3.5.1 and 3.8 of the proposal). The implementation in this repository reflects the components that were selected and built:

| Pipeline stage | Proposal candidates / baselines | Implemented in this repository |
|---|---|---|
| Speech-to-text | Openly available Kinyarwanda-capable speech models, assessed with WER | `facebook/mms-1b-all` with Kinyarwanda adapter |
| Retrieval and ranking | kiny-colbert-free vs TF-IDF and BM25 | Fine-tuned `intfloat/multilingual-e5-large`, with BM25 comparisons in `results/` |
| Verified answer and referral | Confidence threshold set on validation data | Implemented in `mfasha/pipeline.py`, threshold in `results/referral_threshold.json` |
| Text-to-speech | kinya-flex-tts vs alternative | `facebook/mms-tts-kin` |
| Question classification | KinyaBERT vs TF-IDF with Logistic Regression and SVM | Not a separate stage in the running app. Out-of-scope questions are handled by the referral threshold |
| User interface | Streamlit (proposal) | FastAPI-served web interface (HTML, CSS, JavaScript) |
| Database | PostgreSQL (proposal) | Feedback is stored in `results/feedback.jsonl` |

These differences are explained in the technical report.

## 14. Ethics and Intended Use

- Datasets and models are public resources, used according to their licence terms and credited to their sources.
- Participation in the validation discussions and the pilot is voluntary, participants are told the purpose beforehand and may withdraw without penalty, and permission is obtained before any voice is recorded.
- Names, telephone numbers and other identifying details are kept out of the machine-learning data, and pilot recordings are used only for evaluation.
- The system does not present uncertain information as confirmed advice. Questions that need professional judgement are referred to an agricultural officer.
- MFASHA is a support tool. It does not replace extension officers. For urgent animal health or crop emergencies, farmers should consult an agricultural extension officer or a veterinarian.

## 15. Deployment

See [`DEPLOY.md`](DEPLOY.md) for the full procedure: uploading the trained files to a private Hugging Face repository, running locally, evaluating, pushing to GitHub and deploying to a Hugging Face Space. It also lists common problems and their fixes.

## 16. Walkthrough Video and Technical Report

- **Walkthrough video:** `<ADD LINK HERE>`
- **Technical report (PDF, max 5 pages):** `<ADD LINK HERE>` covering scope alignment, technical functionality, testing approaches and results, and code quality practices.

> Make sure both links are set to be accessible to anyone with the link before submitting.

## 17. References

- C4IR-RW. (2026a, March 11). *Kinyarwanda agricultural retrieval dataset* [Dataset]. Hugging Face. https://huggingface.co/datasets/C4IR-RW/kinya-ag-retrieval
- C4IR-RW. (2026b, March 17). *Kinyarwanda agricultural text-to-speech dataset* [Dataset]. Hugging Face. https://huggingface.co/datasets/C4IR-RW/kinya-ag-tts
- Choruma, D. J., Dirwai, T. L., Mutenje, M. J., Mustafa, M., Chimonyo, V. G. P., Jacobs-Mata, I., & Mabhaudhi, T. (2024). Digitalisation in agriculture: A scoping review of technologies in practice, challenges, and opportunities for smallholder farmers in sub-Saharan Africa. *Journal of Agriculture and Food Research, 18*, Article 101286. https://doi.org/10.1016/j.jafr.2024.101286
- Digital Transformation Center Rwanda. (2026, June). *Tunga Agri-chatbot open source suite.* https://digicenter.rw/portfolio/tunga-agri-chatbot-open-source-suite
- Ibrahim, A., Senthilkumar, K., & Saito, K. (2024). Evaluating responses by ChatGPT to farmers' questions on irrigated lowland rice cultivation in Nigeria. *Scientific Reports, 14*, Article 3407. https://doi.org/10.1038/s41598-024-53916-1
- Mapiye, O., Makombe, G., Molotsi, A., Dzama, K., & Mapiye, C. (2023). Information and communication technologies (ICTs): The potential for enhancing the dissemination of agricultural information and services to smallholder farmers in sub-Saharan Africa. *Information Development, 39*(3), 638–658. https://doi.org/10.1177/02666669211064847
- National Institute of Statistics of Rwanda. (2025). *Agricultural household survey 2024 report.* https://www.statistics.gov.rw/sites/default/files/documents/2025-10/AHS%202024_Main%20report.pdf
- Nzeyimana, A., & Niyongabo Rubungo, A. (2022). KinyaBERT: A morphology-aware Kinyarwanda language model. *Proceedings of the 60th Annual Meeting of the ACL (Volume 1: Long Papers)*, 5347–5363. https://doi.org/10.18653/v1/2022.acl-long.367
- Singh, N., et al. (2024). Farmer.Chat: Scaling AI-powered agricultural services for smallholder farmers. arXiv. https://doi.org/10.48550/arXiv.2409.08916

Full reference list is in the project proposal.