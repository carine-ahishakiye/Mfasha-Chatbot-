# From your PC to a public link

Total work: about 1 hour, plus upload and build time. Do the steps in order.

## What you need
- A Hugging Face account (huggingface.co) and a **Write** token (Settings > Access Tokens)
- Your Groq API key
- Git installed (`git --version` in PowerShell)

## Step 1. Move the trained files from Drive to Hugging Face (in Colab)
Your trained models are on Google Drive. Send them straight to a private Hugging Face repo from Colab, so the 2+ GB never goes through your own internet.

1. In Colab, open the left key icon, add a secret named `HF_TOKEN` (your Write token) and switch on Notebook access.
2. Open a new cell, paste `scripts/colab_push_assets.py`, change `HF_USER` to your username, run it.
3. It creates `YOUR_USER/mfasha-assets` (private) and uploads 4 things: the fine-tuned e5 folder, the ASR adapter `best.pt`, `passages.jsonl`, and the saved passage embeddings.

## Step 2. Put the project in your folder (PowerShell)
Copy everything from this zip into `C:\Users\PC\Desktop\Mfasha agri bot`, next to your `data`, `models`, `notebook` and `results` folders. Then:

```powershell
cd "C:\Users\PC\Desktop\Mfasha agri bot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest tests          # 13 tests should pass
```

Create your `.env` file from the example and fill in the three values:

```powershell
copy .env.example .env
notepad .env        # GROQ_API_KEY, HF_TOKEN (a Read token is enough), HF_ASSETS_REPO=YOUR_USER/mfasha-assets
```

## Step 3. Run it on your PC
```powershell
python app.py
```
The first run downloads the trained files into your `models`, `data` and `results` folders, plus about 4 GB of MMS weights. Then open the link it prints (http://127.0.0.1:7860). Test both tabs: **Andika** (type) and **Vuga** (speak).
Without a GPU the voice question takes a while to be understood. That is normal on CPU.

## Step 4. Measure the answer step properly (for your report)
Copy `data/clean/splits/test_unseen.csv` and `data/clean/queries.jsonl` from Drive into the same folders on your PC, then:
```powershell
python scripts/evaluate_answers.py --n-farming 80
```
It tests 80 unseen-passage farming questions and 18 off-topic ones, and writes `results/answer_eval.csv`. The summary gives refusal rate, wrongly refused rate, verbatim share and invented numbers. It also prints the best-passage score for farming vs off-topic questions. If the two groups do not overlap, set `MIN_RETRIEVAL_SCORE` in `.env` between them to refuse off-topic questions without calling the LLM at all.
Fill the `fluency_1to5` and `faithful_1to5` columns by hand for the report.

## Step 5. Deploy on a Hugging Face Space
1. huggingface.co > New > **Space**. Name: `mfasha`. SDK: **Gradio**. Hardware: **CPU basic (free)** to begin with.
2. In the Space: Settings > Variables and secrets:
   - Secret `GROQ_API_KEY` = your Groq key
   - Secret `HF_TOKEN` = a **Read** token (so the Space can fetch your private assets)
   - Variable `HF_ASSETS_REPO` = `YOUR_USER/mfasha-assets`
3. Push the code (big folders are excluded by `.gitignore`):
```powershell
git init -b main
git add .
git commit -m "Mfasha"
git remote add space https://huggingface.co/spaces/YOUR_USER/mfasha
git push --force space main
```
Git asks for a username and password: use your HF username and a **Write** token as the password.
4. Open the Space and watch the Logs tab. The first start downloads about 6 GB, so it takes several minutes. When you see `ready`, the public link works.

**Check before you share the link:** open `git status` and confirm no `models/`, `data/`, `results/` or `.env` files are staged.

## If it is too slow
The free CPU Space works, but speech recognition takes noticeably longer than typing. If the demo feels slow for your panel, change the Space hardware to a GPU in Settings (this is paid, and you can switch back to CPU after the demo). No code change is needed, the app uses the GPU automatically.

## Problems
| Message | Cause and fix |
|---|---|
| `These files are missing` | Step 1 not done, or `HF_ASSETS_REPO` / `HF_TOKEN` not set |
| `adapter file does not fit the model` | `best.pt` is not the file saved by the ASR training cell. Upload the right one |
| UI shows "Mbabarira, habaye ikibazo" | Usually a wrong or missing `GROQ_API_KEY`. Look at the Space logs for `llm error` |
| Space shows "Runtime error" at start | Open Logs. Most often out of memory: try the GPU hardware, or check the files in the assets repo |
| Every question refused | `MIN_RETRIEVAL_SCORE` is set too high. Set it to 0 |

## Before you present
- Ask a Kinyarwanda speaker to read the `UI` dictionary at the top of `app.py` and fix any wording. I wrote it, but a native reader should confirm it.
- Keep the Groq key out of the repo. It lives only in `.env` (local) and Space secrets.
