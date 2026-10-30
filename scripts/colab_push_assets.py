
from pathlib import Path
from google.colab import drive, userdata
from huggingface_hub import HfApi

HF_USER = "YOUR_HF_USERNAME"
REPO = f"{HF_USER}/mfasha-assets"

drive.mount("/content/drive")
DRIVE = Path("/content/drive/MyDrive/Mfasha chatbot")
api = HfApi(token=userdata.get("HF_TOKEN"))
api.create_repo(REPO, repo_type="model", private=True, exist_ok=True)

# (path on Drive, path in the repo). The repo paths match the project folder on your PC
folders = [("models/kinya-e5-large/best", "models/kinya-e5-large/best")]
files = [
    ("models/mms-kin-adapter/best.pt",        "models/mms-kin-adapter/best.pt"),
    ("data/clean/passages.jsonl",             "data/clean/passages.jsonl"),
    ("results/emb/kinya_e5_passages.npy",     "results/emb/kinya_e5_passages.npy"),
]

for src, dst in folders:
    assert (DRIVE / src).is_dir(), f"missing folder {src}"
    api.upload_folder(repo_id=REPO, repo_type="model", folder_path=str(DRIVE / src), path_in_repo=dst)
    print("uploaded folder", dst)
for src, dst in files:
    assert (DRIVE / src).is_file(), f"missing file {src}"
    api.upload_file(repo_id=REPO, repo_type="model", path_or_fileobj=str(DRIVE / src), path_in_repo=dst)
    print("uploaded", dst)
print("done ->", f"https://huggingface.co/{REPO}")
