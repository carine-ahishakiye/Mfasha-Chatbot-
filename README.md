# Mfasha agri bot

A chatbot that answers farming questions in Kinyarwanda. You ask by typing or speaking, and it answers in text and in speech. Answers come from a set of agriculture passages (about 940 of them), and if the passages don't cover the question, it says so and doesn't guess.

This is a university project, and it is not finished. The notebook that trains and tests everything is done. The app around it is still being built.

## How it works

1. **Speech to text.** If you speak, `facebook/mms-1b-all` with its Kinyarwanda adapter turns the audio into text. I fine-tuned the adapter on studio recordings.
2. **Finding the passage.** `multilingual-e5-large`, fine-tuned on the question and passage pairs, finds the five best passages.
3. **The answer.** `gpt-oss-120b` (through Groq) is told to copy the sentences that answer the question, word for word. If the answer has a number that isn't in the passages, the answer is thrown away and the bot says it has no information. If nothing fits, it says so.
4. **Speech.** `facebook/mms-tts-kin` reads the answer. Numbers, units and percents are first written out as Kinyarwanda words.

## Results

All numbers come from the notebook. Everything was measured on studio recordings and on the dataset's own test split, so real phone audio will do worse. I haven't measured that yet.

| Part | Test | Result |
|---|---|---|
| Retrieval | R@1 / R@10 on 20 passages never seen in training | 0.866 / 0.994 |
| Retrieval | R@1 / R@10 on passages seen in training | 0.893 / 0.994 |
| Speech to text | Word error rate on a speaker the model never heard (200 clips) | 27.7% (30.1% before fine-tuning) |
| Speech to text | Character error rate, same clips | 5.8% (6.3% before) |
| Answers | Share copied word for word, 6 dev questions | 94% |
| Answers | Off-topic questions refused | 3 of 3 |
| Voice | Round-trip word error rate, stock voice | 0.228 |
| Voice | Round-trip word error rate, my fine-tuned voice | 0.695 |

The last two rows are why the app uses the stock voice. I fine-tuned the voice on 1.7 hours of one speaker and it came out clearly worse when the speech model listened to it. The training cells are still in the notebook.

## Folders

app/ the web app
src/ the Python code: retrieval, answers, speech
notebook/ the notebook with all training and tests
models/ fine-tuned retriever and speech adapter (not in git, too big)
data/ the passages and test files (not in git)
results/ score tables and plots from the notebook
docs/ notes
tests/ tests


## Setting it up

You need Python 3.11 or newer.
python -m venv .venv
.venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt


Copy `.env.example` to `.env` and fill in your own keys:

HF_TOKEN= 
GROQ_API_KEY= 


The models are too big for git. The fine-tuned retriever goes in `models/kinya-e5-large/best`, and the speech adapter (`best.pt`) goes in `models/mms-kin-adapter`. The passages go in `data/clean/passages.jsonl`. The other models download from Hugging Face the first time they are used.

The notebook was run on a free Colab T4. Training the retriever took about two hours and the speech adapter about 20 minutes.

## What doesn't work well yet

- The speech model gets about 1 word in 4 wrong, even on clean recordings. On phone audio in a noisy place, expect more.
- The Kinyarwanda number words are my own attempt. A native speaker hasn't checked them.
- No native speaker has rated how natural the voice sounds. I only measured how clearly the words come out.
- The bot only knows the passages it was given. It can't answer questions outside them, and it won't tell a farmer anything newer than that text.

## Licences and credits

- Data: [C4IR-RW/kinya-ag-retrieval](https://huggingface.co/datasets/C4IR-RW/kinya-ag-retrieval) and [C4IR-RW/kinya-ag-tts](https://huggingface.co/datasets/C4IR-RW/kinya-ag-tts).
- The MMS speech and voice models from Meta are released under CC-BY-NC 4.0, so this project is for research and demos only, not for commercial use.
- `multilingual-e5-large` is MIT licensed.
