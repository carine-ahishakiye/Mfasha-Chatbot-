
import json
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

# answering: the answer is the top retrieved passage, unchanged. No language model is involved.
# A question is referred instead when its best passage scores below the referral threshold.
# The notebook works the threshold out from the dev questions and saves it here:
REFERRAL_THRESHOLD_FILE = ROOT / "results" / "referral_threshold.json"
REFERRAL_MESSAGE = "Mbabarira, nta makuru mfite kuri icyo kibazo."


def _load_referral_threshold() -> float:
    """REFERRAL_THRESHOLD in the environment wins, then the file saved by the notebook, then 0 (never refer)."""
    env = os.getenv("REFERRAL_THRESHOLD")
    if env:
        return float(env)
    try:
        return float(json.loads(REFERRAL_THRESHOLD_FILE.read_text(encoding="utf-8-sig"))["threshold"])
    except (OSError, ValueError, KeyError):
        return 0.0


REFERRAL_THRESHOLD = _load_referral_threshold()

# speech to text
ASR_MODEL = "facebook/mms-1b-all"
ASR_LANG = "kin"
ASR_SR = 16000
MAX_AUDIO_SECONDS = int(os.getenv("MAX_AUDIO_SECONDS", "30"))

# text to speech: the stock voice won your round-trip test (0.228 vs 0.695 for the fine-tuned one)
TTS_MODEL = "facebook/mms-tts-kin"

# confidence badge: cutoffs on the gap between the best and the second-best passage score.
# scripts/evaluate_system.py (calibration part) prints the accuracy per gap bucket for tuning them
TIER_MIN_SCORE = float(os.getenv("TIER_MIN_SCORE", "0.60"))
TIER_HIGH_MARGIN = float(os.getenv("TIER_HIGH_MARGIN", "0.04"))
TIER_MEDIUM_MARGIN = float(os.getenv("TIER_MEDIUM_MARGIN", "0.015"))

# web server limits
MAX_QUESTION_CHARS = 500
MAX_SPOKEN_CHARS = 250            # longer answers are read only in part, to keep the wait short
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
VOICE_CACHE_SIZE = 32
FEEDBACK_FILE = ROOT / "results" / "feedback.jsonl"

