# Mfasha: a Kinyarwanda agricultural chatbot (text and voice)


## About the project

Most agricultural advice online is in English or French, and most language tools handle Kinyarwanda badly. I built a chatbot that takes a question in Kinyarwanda, typed or spoken, and returns the most relevant passage from an agricultural knowledge base. If nothing in the knowledge base matches well enough, it says so and suggests asking an extension officer.

The bot does not generate text. It only returns passages that already exist in the data. I chose this because a wrong dose or treatment in farming advice can cost a farmer a harvest, and a generated answer can be wrong in ways that are hard to spot.

The work has two parts that I built and tested separately: a retriever (fine-tuned embeddings plus BM25) and a speech recogniser (MMS-1B with its Kinyarwanda adapter fine-tuned on agricultural speech). Text-to-speech and a user interface are not built yet.

Main results on data the models never saw:

| | Before | After |
|---|---|---|
| Retrieval Recall@1 (329 test questions) | 0.486 (BM25) | 0.608 (hybrid) |
| Retrieval Recall@5 | 0.723 (BM25) | 0.891 (hybrid) |
| Speech word error rate (398 test clips) | 0.325 | 0.278 |
| Speech letter error rate | 0.070 | 0.057 |


## How it works

```
voice question -> speech recognition -+
                                      +-> hybrid retrieval -> confident enough? -> best passage + 2 alternatives
text question  ----------------------+     (Qdrant + BM25)            |
                                                                      +-> no: "no answer found" message
```

Voice questions are turned into text first, then both kinds of question go through the same search.

## Data

### Retrieval data

984 passages of agricultural text and 19,537 Kinyarwanda questions, each linked to its correct passage and to about 100 wrong ones. I split by passage so that no passage appears in more than one split.

| | Train | Dev | Test |
|---|---|---|---|
| Questions | 19,012 | 196 | 329 |
| Correct passages | 941 | 10 | 20 |

I checked that no question appears in two splits and that none of the 20 test passages was seen in training. Source of the data: [add name or link].

### Speech data

`C4IR-RW/kinya-ag-tts` on Hugging Face: 17,972 recordings of 5,240 sentences, read by four studio voices (two female, two male). Many sentences are read by several voices, so I split by sentence and not by clip.

| | Clips | Sentences | Hours |
|---|---|---|---|
| Train | 2,000 | 1,000 | 2.58 |
| Dev | 120 | 60 | 0.16 |
| Test | 398 | 200 | 0.55 |

No sentence is in both train and test. Two test clips (0.5%) match a training sentence once punctuation is ignored.

About 20% of the reference texts in this dataset contain brackets, slashes or foreign words, for example "( grlle à reine )" or "/SA". A speech model cannot write those, so they push the error rates up a little. I report scores with and without them below.

## Methods

### Retrieval

I started with two baselines: BM25, and the multilingual `paraphrase-multilingual-mpnet-base-v2` model without any training. The base model did badly on Kinyarwanda (Recall@1 of 0.10 on dev), and mixing it with BM25 made things worse.

I then fine-tuned the same model with `MultipleNegativesRankingLoss` on question, correct passage and wrong passage triplets. I used one random wrong passage per question, which gives 19,012 training examples. Batch size 32, learning rate 2e-5, fp16, on a free Colab T4. I used a no-duplicates batch sampler because many questions share a passage, and without it the same passage can be both a positive and a negative in one batch.

For the hybrid search I normalise the embedding score and the BM25 score and mix them 0.8 to 0.2. I picked that weight on dev.

306 of the 984 passages are longer than the model's 256-token limit, so I split long passages into 1,705 chunks of at most 247 tokens. The chunk embeddings are stored in Qdrant, and the search returns the best chunk for each passage.

If the top similarity score is below 0.485 the bot refuses to answer. I chose that threshold on dev. Answers also come with a confidence level (high, medium, low).

### Speech recognition

I used `facebook/mms-1b-all` with the Kinyarwanda adapter (`kin`). Only the adapter and output layer were trained, which is 2.33 million of 965 million weights (0.24%). Everything else stayed frozen. With only 2.6 hours of training audio and a free GPU, training the whole model was not realistic.

Training ran for 10 epochs, batch size 4, learning rate 2e-4, mixed precision, about 54 minutes. I picked the best epoch by dev word error rate and ran the test set once.

## Results

### Retrieval on the test set (329 questions, 20 unseen passages)

| Method | Recall@1 | Recall@5 | Recall@10 | MRR@10 |
|---|---|---|---|---|
| Base embeddings, no training | 0.036 | 0.097 | 0.140 | 0.063 |
| BM25 | 0.486 | 0.723 | 0.799 | 0.594 |
| Fine-tuned embeddings, 5 epochs | 0.562 | 0.796 | 0.848 | 0.667 |
| Hybrid (0.8 embeddings, 0.2 BM25) | 0.608 | 0.891 | 0.948 | 0.731 |

On dev, Recall@1 went from 0.633 after 1 epoch to 0.668 after 2 and 0.735 after 5. BM25 scored 0.520 and the untrained model 0.102.

With chunking and Qdrant, dev scores were Recall@1 0.745, Recall@3 0.867 and Recall@5 0.908, at about 0.27 seconds per question on a CPU.

### Refusing and confidence (dev)

| Threshold | Real questions answered | Off-topic questions refused (of 8) |
|---|---|---|
| 0.400 | 100.0% | 1 |
| 0.450 | 98.5% | 3 |
| 0.485 (used) | 96.4% | 6 |
| 0.550 | 85.7% | 6 |
| 0.600 | 79.6% | 8 |

| Confidence | Questions | Best answer correct | Right answer in top 3 |
|---|---|---|---|
| below 0.6 | 40 | 30.0% | 57.5% |
| 0.6 to 0.7 | 35 | 57.1% | 85.7% |
| 0.7 to 0.8 | 47 | 87.2% | 93.6% |
| 0.8 and above | 74 | 98.6% | 98.6% |

When the bot is confident it is nearly always right. Low-confidence answers are shown together with the two alternative passages.

### Speech recognition on the test set (398 clips, 200 unseen sentences)

| Voice set | WER before | WER after | CER before | CER after |
|---|---|---|---|---|
| All | 0.325 | 0.278 | 0.070 | 0.057 |
| Female | 0.309 | 0.268 | 0.066 | 0.053 |
| Female 2 | 0.330 | 0.279 | 0.071 | 0.056 |
| Male | 0.337 | 0.289 | 0.076 | 0.064 |
| Male 2 | 0.324 | 0.277 | 0.068 | 0.055 |

On the 328 clips with clean reference text (no brackets, slashes or foreign letters), WER goes from 0.300 to 0.255 and CER from 0.055 to 0.044. I chose that subset after looking at the data, so I treat it as an extra analysis and not as the main result.

An earlier training run gave a test WER of 0.284, so results vary by about 0.005 between runs.

About three quarters of the remaining word errors are substitutions. Many of them are spelling variants or words joined or split differently ("ni ibi" against "n'ibi"). Part of the improvement therefore comes from learning the dataset's spelling habits and not only from better listening.

## Folder structure

```
Mfasha chatbot/
  src/chatbot.py                    the chatbot
  notebook/
    data_and_baselines.ipynb        data, splits, baselines
    finetune_retriever.ipynb        retriever training, hybrid, test results, figures
    chunking_and_chatbot_test.ipynb chunking, Qdrant, threshold, confidence
    speech.ipynb                    speech model training and evaluation
  models/
    kinya-retriever/                fine-tuned embedding model
    kinya-asr/mms_kin_adapter_finetuned.pt
  data/                             passages, questions, splits, chunks, embeddings
  results/                          tables and figures
  requirements.txt
  .env                              keys, not committed
```

## Setup

You need Python 3.10 or newer. Retrieval runs on a CPU. Training and fast speech recognition need a GPU (I used Google Colab).

```
git clone https://github.com/carine-ahishakiye/Mfasha-Chatbot-.git
cd "Mfasha chatbot"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Main libraries: sentence-transformers, qdrant-client, rank_bm25, transformers, torch, jiwer, librosa, pandas, numpy.

## Running it

Typed question:

```python
from src.chatbot import Chatbot

bot = Chatbot(
    model_dir="models/kinya-retriever",
    chunks_path="data/chunks.jsonl",
    emb_path="data/chunk_emb_e5.npy",
)

r = bot.ask("soya ihunikwa ahantu hameze gute ?")
print(r["answer"])
print(r["confidence"], r["tier"], r["passage_id"])
print(r["alternatives"])
```

Spoken question: open `notebook/speech.ipynb` in Colab with a GPU. It loads MMS-1B and the saved adapter. Then:

```python
use_adapter("finetuned")
heard, r = voice_ask(audio_16khz)
```

To repeat the experiments, run the notebooks in this order: data_and_baselines, finetune_retriever (GPU), chunking_and_chatbot_test, speech (GPU). The random seed is 42 everywhere.


## Notes on use

The bot retrieves existing advice and does not replace an extension officer. It refuses when it is unsure and points the user to one. The speech data is a public set of studio recordings, and I collected no personal data.

## Credits

- Speech data: C4IR Rwanda, `C4IR-RW/kinya-ag-tts`
- Speech model: Pratap et al. (2023), Scaling Speech Technology to 1,000+ Languages (Meta MMS)
- Embedding model: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`
- Libraries: Sentence-Transformers, Qdrant, rank_bm25, Hugging Face Transformers, jiwer
- Retrieval data: [add source]
