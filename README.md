# Mfasha: A Kinyarwanda Agricultural Question-Answering Assistant

**Capstone project**

| | |
|---|---|
| Author | [Carine Ahishakiye Yibukabayo] |
| Programme | [Software Engineering] |
| Supervisor | [Hubert Apana] |
| Year | [2026] |

## Abstract

Smallholder farmers in Rwanda work mostly in Kinyarwanda, while most digital agricultural information is written in other languages or in a form that is hard to search by voice. Mfasha is a question-answering system that accepts a question in Kinyarwanda, typed or spoken, and returns a short answer in Kinyarwanda as text and as synthesised speech. The system combines four components: a fine-tuned speech recogniser, a fine-tuned multilingual passage retriever, a language model restricted to copying sentences from the retrieved passages, and a Kinyarwanda speech synthesiser. On passages never seen during training, the retriever reaches a recall at rank 1 of 0.866 and a recall at rank 10 of 0.994. Fine-tuning reduced the word error rate of speech recognition on a held-out speaker from 30.1% to 27.7%. The answer step refuses questions that the collection cannot answer and blocks any number that does not appear in the source passages. The system is delivered as a web application with a voice interface and is deployed as a public service.

## 1. Introduction

Reliable agricultural advice depends on specific facts: planting periods, doses, gestation times, insurance procedures. A general language model can produce fluent Kinyarwanda but may state these facts incorrectly, which is costly for a farmer who acts on them. This project therefore treats the task as retrieval followed by constrained answer extraction. Every answer is taken from a curated collection of agricultural passages, so each statement can be traced to a source. When the collection does not contain the answer, the system says so.

## 2. Objectives

1. Build a retrieval component that finds the passage answering a Kinyarwanda agricultural question, including for passages not seen in training.
2. Adapt an existing multilingual speech recogniser to Kinyarwanda agricultural speech.
3. Generate answers that stay within the retrieved text, refuse out-of-scope questions, and never introduce unsupported figures.
4. Provide spoken output in Kinyarwanda, including correct reading of numbers and units.
5. Deliver the result as a usable web application.

## 3. System overview

```
 spoken question                typed question
        |                              |
  speech recognition (MMS-1b-all + kin adapter, fine-tuned)
        |______________________________|
                       |
          passage retrieval (multilingual-e5-large, fine-tuned)
                       |
     answer selection (gpt-oss-120b, copy-only prompt)
                       |
        safeguards: refusal, number check, confidence level
                       |
         written answer  ->  speech synthesis (MMS-TTS Kinyarwanda)
```

## 4. Data

Two public corpora from the C4IR Rwanda Hugging Face organisation were used: `C4IR-RW/kinya-ag-retrieval` (agricultural passages with questions) and `C4IR-RW/kinya-ag-tts` (studio recordings with transcripts).

**Passage collection.** The collection holds 984 passages. 43 passages that consist of a heading only were removed, leaving 941.

**Retrieval splits.** The original split was re-organised so that generalisation to new passages could be measured separately from generalisation to new questions.

| Split | Questions | Passages | Description |
|---|---:|---:|---|
| train | 14,232 | 850 | model fitting |
| dev_seen | 1,394 | 697 | new questions, passages seen in training |
| test_seen | 1,394 | 697 | new questions, passages seen in training |
| dev_unseen | 1,299 | 60 | passages held out of training |
| test_unseen | 329 | 20 | passages held out of training |

No question appears in more than one split.

**Speech data.** Fine-tuning used 2,000 clips (2.4 hours) from three studio speakers and a 100-clip development set. Evaluation used 200 sentences (19 minutes) from a fourth speaker, `rw_ag_tts_male2`. None of the test sentences occurs in the training data.

## 5. Methodology

### 5.1 Retrieval

`intfloat/multilingual-e5-large` was fine-tuned on question and passage pairs. Each training example contains a question, its passage, and one hard negative: a passage that BM25 ranks highly for the question but that is not the answer. The loss is the multiple negatives ranking loss (cached implementation, scale 20), so the other passages in a batch also serve as negatives, and a batch sampler ensures that no two questions in a batch share a passage.

Training used a learning rate of 2e-5 with 10% warm-up, weight decay of 0.01, batch size 64, mixed precision, and up to 3 epochs. The word-embedding table was frozen to fit in GPU memory, so 304 M of 560 M parameters were updated. After every epoch the model was scored on the development sets, and the epoch with the best mean R@1 (epoch 2) was kept. Training would have stopped early after two epochs without improvement.

Passages are embedded once with the prefix `passage:` and questions at query time with the prefix `query:`. Retrieval is by cosine similarity. Lexical BM25 and reciprocal rank fusion of BM25 with the dense scores were evaluated as alternatives (Section 6.1).

### 5.2 Speech recognition

`facebook/mms-1b-all` with the Kinyarwanda language adapter was used as the starting point. The adapter and the output layer were fine-tuned (290 tensors) on the speech data described above. The epoch with the lowest development word error rate (epoch 3, 0.284) was kept.

### 5.3 Grounded answer generation

For each question, the five highest-ranked passages are given to `openai/gpt-oss-120b` through the Groq API with an instruction to copy, word for word, at most three sentences that answer the question, and to reply with a fixed refusal sentence if no passage answers it. The temperature is zero. Two checks run on the reply:

- **Number check.** Every number in the answer must occur as a whole number in the retrieved passages. If one does not, the answer is replaced by the opening sentences of the top passage and is marked as low confidence.
- **Refusal.** A reply equal to the refusal sentence is passed on unchanged and no source is shown.

A confidence level (high, medium, low) is derived from the margin between the best and the second-best retrieval score.

### 5.4 Speech synthesis

`facebook/mms-tts-kin` produces the speech. Before synthesis the answer is normalised: digits, decimals, percentages, ranges and units (for example kg, ha, cm) are written out as Kinyarwanda words, and the text is spoken clause by clause with short pauses at punctuation. A voice fine-tuned on a studio speaker was also trained and compared with the stock voice (Section 6.4).

## 6. Results

Metrics. R@k is the share of questions whose correct passage is among the top k results. MRR@10 is the mean reciprocal rank of the correct passage within the top 10. WER and CER are word and character error rates.

### 6.1 Retrieval method comparison (development sets)

| System | R@10 seen | R@10 unseen | MRR@10 seen | MRR@10 unseen |
|---|---:|---:|---:|---:|
| BM25 | 0.816 | 0.811 | 0.596 | 0.589 |
| multilingual-e5-large, no fine-tuning | 0.706 | 0.684 | 0.491 | 0.491 |
| BM25 fused with fine-tuned e5 (best weight) | 0.968 | 0.956 | 0.829 | 0.810 |
| **Fine-tuned e5 alone** | **0.994** | **0.980** | **0.946** | **0.893** |

Fine-tuning improved the dense retriever substantially, and fusion with BM25 did not improve on the fine-tuned model alone. The fine-tuned model is therefore used without BM25.

### 6.2 Retrieval on the test sets

| Test set | Questions | R@1 | R@5 | R@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| test_seen | 1,394 | 0.893 | 0.990 | 0.994 | 0.936 |
| test_unseen | 329 | 0.866 | 0.988 | 0.994 | 0.923 |

### 6.3 Speech recognition (held-out speaker, 200 sentences)

| Model | WER | CER |
|---|---:|---:|
| MMS-1b-all, Kinyarwanda adapter | 30.1% | 6.3% |
| After fine-tuning | 27.7% | n/a |

### 6.4 Speech synthesis

Synthesised speech was transcribed with the speech recogniser and compared with the input text (round-trip WER; lower is better).

| Voice | Round-trip WER |
|---|---:|
| Stock `mms-tts-kin` | 0.228 |
| Fine-tuned on 1.73 h of one speaker | 0.695 |

The stock voice is more intelligible and is the one used in the application.

### 6.5 Answer step 

On a first set of 6 agricultural questions and 3 off-topic questions, 94% of the answer sentences were copied word for word from the passages, one answer contained a number absent from its passages (caught by the number check), and all 3 off-topic questions were refused. A larger evaluation script is provided (Section 8.4).

## 7. Implementation

**Stack.** Python, PyTorch, Hugging Face Transformers and Sentence-Transformers for the models, FastAPI for the server, and a single-page web interface served by the same application. Models are loaded once at start-up.

**Web interface.** Typed or spoken questions, a confidence badge on each answer, related passages, a button that reads the answer aloud, helpful and not-helpful feedback stored in `results/feedback.jsonl`, and conversation history kept in the visitor's browser. The page is the `PAGE` text at the bottom of `app.py`.

**Interface of the server.**

| Method and path | Input | Output |
|---|---|---|
| `POST /api/ask` | `{question}` | answer, confidence level, related passages, passage id |
| `POST /api/transcribe` | audio recorded in the browser | `{text}` |
| `POST /api/speak` | `{text}` | audio (WAV) |
| `POST /api/feedback` | `{question, passage_id, vote}` | `{ok}` |

The server limits question length and request rates per visitor.

## 8. Reproducibility and usage

### 8.1 Repository structure

```
app.py                  server and web page
mfasha/                 retrieval, answer generation, speech recognition and synthesis, pipeline
scripts/                evaluate_answers.py, smoke_test.py, colab_push_assets.py
tests/                  unit and endpoint tests
eval/off_topic_rw.txt   off-topic questions for the refusal test
notebook/               the experiments reported above (Google Colab, Tesla T4)
Dockerfile              container used for deployment
```

The trained weights, data and results (`models/`, `data/`, `results/`) are not stored in the repository. The trained files are kept in a private Hugging Face repository and downloaded on first start.

### 8.2 Installation and running

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

The application is then available at http://127.0.0.1:7860. The first start downloads about 6 GB of model files.

### 8.3 Configuration (`.env`)

| Name | Purpose |
|---|---|
| `GROQ_API_KEY` | key for the answer step |
| `HF_TOKEN` | read token for the repository that holds the trained files |
| `HF_ASSETS_REPO` | that repository, for example `carine01/mfasha-assets` |
| `MIN_RETRIEVAL_SCORE` | optional, refuse questions whose best passage scores below this value (0 = off) |
| `TIER_MIN_SCORE`, `TIER_HIGH_MARGIN`, `TIER_MEDIUM_MARGIN` | cutoffs for the confidence level |

### 8.4 Tests and evaluation

```
python -m pytest tests                 # logic and web endpoints, no model downloads
python scripts/smoke_test.py           # each model on its own, using the real files
python scripts/evaluate_answers.py     # unseen-passage farming questions and off-topic questions
```

`evaluate_answers.py` samples questions from the unseen-passage test split and reports retrieval hits, wrongly refused questions, the share of sentences copied verbatim, answers containing numbers absent from the passages, and the share of off-topic questions refused. Results are written to `results/answer_eval.csv`.

## 9. Deployment

The application is deployed as a Docker Space on Hugging Face. See `DEPLOY.md` for the procedure.

## 10. Intended use

Mfasha is designed to give farmers quick access to written agricultural guidance. For urgent animal health or crop emergencies, farmers should consult an agricultural extension officer or a veterinarian.

## Acknowledgements

The retrieval and speech data come from the C4IR Rwanda Kinyarwanda agriculture corpora. The speech models are released by Meta (MMS) and the retrieval model by the authors of multilingual-e5.

## References

1. Pratap, V., et al. (2023). Scaling Speech Technology to 1,000+ Languages. arXiv:2305.13516.
2. Wang, L., et al. (2024). Multilingual E5 Text Embeddings: A Technical Report. arXiv:2402.05672.
3. Kim, J., Kong, J., and Son, J. (2021). Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech. Proceedings of ICML.
4. Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. Advances in Neural Information Processing Systems.
5. Robertson, S., and Zaragoza, H. (2009). The Probabilistic Relevance Framework: BM25 and Beyond. Foundations and Trends in Information Retrieval.
6. Cormack, G., Clarke, C., and Buettcher, S. (2009). Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods. Proceedings of SIGIR.