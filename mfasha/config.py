"""All settings in one place. Anything can be overridden with an environment variable."""
import os
from pathlib import Path

try:  # optional: read a local .env file if python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent

# files the app needs. They mirror the project folder, and the Hugging Face assets repo uses the same paths
PASSAGES_PATH   = ROOT / "data" / "clean" / "passages.jsonl"
E5_DIR          = ROOT / "models" / "kinya-e5-large" / "best"
ASR_ADAPTER     = ROOT / "models" / "mms-kin-adapter" / "best.pt"
PASSAGE_EMB     = ROOT / "results" / "emb" / "kinya_e5_passages.npy"
REQUIRED_ASSETS = [PASSAGES_PATH, E5_DIR / "config.json", ASR_ADAPTER, PASSAGE_EMB]

# private Hugging Face model repo that holds the files above (needed on Spaces, optional locally)
HF_ASSETS_REPO = os.getenv("HF_ASSETS_REPO", "")
HF_TOKEN       = os.getenv("HF_TOKEN") or None

# retrieval
Q_PREFIX, P_PREFIX = "query: ", "passage: "
MAX_SEQ_LEN = 256
TOP_K = int(os.getenv("TOP_K", "5"))
# 0 = off. If you set it, questions whose best passage scores below it are refused without calling the LLM.
# run scripts/evaluate_answers.py to see the score gap between farming and off-topic questions first
MIN_RETRIEVAL_SCORE = float(os.getenv("MIN_RETRIEVAL_SCORE", "0"))

# answer generation (Groq)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_TEMPERATURE = 0.0

# speech to text
ASR_MODEL = "facebook/mms-1b-all"
ASR_LANG = "kin"
ASR_SR = 16000
MAX_AUDIO_SECONDS = int(os.getenv("MAX_AUDIO_SECONDS", "30"))

# text to speech: the stock voice won your round-trip test (0.228 vs 0.695 for the fine-tuned one)
TTS_MODEL = "facebook/mms-tts-kin"
