# Deploying Mfasha

This is how I get the project from my laptop to a public link. It takes about an hour, plus waiting for uploads and the first build.

## What you need

- A Hugging Face account and a token with **Write** access (Settings > Access Tokens)
- Git (check with `git --version`)

## 1. Move the trained files to Hugging Face

The trained models live on Google Drive. I send them straight from Colab to a private Hugging Face repo, so the 2+ GB never goes through my own connection.

1. In Colab, click the key icon on the left, add a secret called `HF_TOKEN` with the Write token, and turn on notebook access.
2. Paste `scripts/colab_push_assets.py` into a new cell, set `HF_USER` to your username and run it.
3. It creates a private repo `YOUR_USER/mfasha-assets` and uploads four things: the fine-tuned e5 folder, the ASR adapter `best.pt`, `passages.jsonl`, and the saved passage embeddings.
4. Also copy `results/referral_threshold.json` from Drive into this project's `results/` folder and commit it. It is a few bytes, and the app reads it to decide when a question is referred instead of answered. Without it the threshold is 0 and no question is ever referred. Use the files from the same notebook run (see the note below).

The e5 model, `passages.jsonl`, the embeddings and the threshold must all come from the same notebook run. The embeddings only match the model that made them, and the threshold is worked out from that model's scores.

## 2. Set up the project locally

Put the project files in `C:\Users\PC\Desktop\Mfasha agri bot`, next to the `data`, `models`, `notebook` and `results` folders. Then in PowerShell:

```powershell
cd "C:\Users\PC\Desktop\Mfasha agri bot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest tests
```

All 13 tests should pass.

Next, create the `.env` file:

```powershell
copy .env.example .env
notepad .env
```

Fill in `HF_TOKEN` (a Read token is enough) and `HF_ASSETS_REPO=YOUR_USER/mfasha-assets`. No answer-generation key is needed: the answer is the best retrieved passage.

## 3. Run it on the PC

```powershell
python app.py
```

The first run downloads the trained files into `models`, `data` and `results`, plus about 4 GB of MMS weights, so be patient. Then open http://127.0.0.1:7860 and try both tabs: **Andika** (type) and **Vuga** (speak).

Without a GPU, voice questions take a long time to be understood. Typed questions are much quicker.

## 4. Measure the answers (for the report)

Copy `data/clean/splits/test_unseen.csv` and `data/clean/queries.jsonl` from Drive into the same folders here, then run:

```powershell
python scripts/evaluate_answers.py --n-farming 80
```

This asks 80 farming questions from unseen passages and 18 off-topic ones, and writes `results/answer_eval.csv`. The summary shows how many farming questions were answered, how often the answered passage was the right one, how often a good question was wrongly referred, and how many off-topic questions were referred. It also prints the best-passage score for farming vs off-topic questions.

If the off-topic scores sit well below the farming scores, the threshold separates them cleanly. To try a different threshold without retraining, set `REFERRAL_THRESHOLD` in `.env`. It overrides `results/referral_threshold.json`.

## 5. Push the code to GitHub

The GitHub repo is `Mfasha-Chatbot-`. The `.gitignore` keeps `.venv`, `models/` and `.env` out.

```powershell
git remote set-url origin https://github.com/carine-ahishakiye/Mfasha-Chatbot-.git
git add .
git commit -m "describe what changed"
git push
```

Run `git status --short` before committing and make sure no `models/` or `.env` files show up.

## 6. Deploy on a Hugging Face Space

1. On Hugging Face, go to New > **Space**. Name it `mfasha`, choose the **Gradio** SDK and **CPU basic (free)** hardware to start.
2. In the Space, open Settings > Variables and secrets and add:
   - secret `HF_TOKEN`: a **Read** token, so the Space can fetch the private assets
   - variable `HF_ASSETS_REPO`: `YOUR_USER/mfasha-assets`
3. Add the Space as a second remote and push. I use the name `space` so it doesn't clash with the GitHub remote:

```powershell
git remote add space https://huggingface.co/spaces/YOUR_USER/mfasha
git push --force space main
```

Git asks for a username and password. Use your Hugging Face username and a **Write** token as the password.

4. Make sure `README.md` starts with the Space config block (`title`, `sdk: gradio`, `app_file: app.py`). Hugging Face reads it to know how to run the app.
5. Open the Space and watch the Logs tab. The first start downloads about 6 GB, so it takes several minutes. When the log says `ready`, the public link works.

## If it's too slow

The free CPU Space works, but speech recognition is clearly slower than typing. If the demo feels sluggish, switch the Space to a GPU in Settings. It costs money, and you can switch back to CPU after the demo. No code change is needed, since the app picks up the GPU on its own.

## Problems I've hit

| Message | Cause and fix |
|---|---|
| `These files are missing` | Step 1 wasn't done, or `HF_ASSETS_REPO` / `HF_TOKEN` isn't set |
| `adapter file does not fit the model` | `best.pt` isn't the file saved by the ASR training cell. Upload the right one |
| "Mbabarira, habaye ikibazo" in the UI | A server error. Check the Logs tab for `ask error` |
| "Runtime error" when the Space starts | Open Logs. Most often it's out of memory, so try GPU hardware or check the assets repo |
| Every question is referred | The referral threshold is too high, or `results/referral_threshold.json` comes from a different model than the one loaded. Set `REFERRAL_THRESHOLD=0` to check, then re-run the notebook cell that saves it |
| Off-topic questions are answered | `results/referral_threshold.json` is missing, so the threshold is 0 |

## Before presenting

- Ask a Kinyarwanda speaker to read the `UI` dictionary at the top of `app.py` and correct any wording.
- Keep `.env` out of the repo. The `HF_TOKEN` only belongs in `.env` (local) and the Space secrets.