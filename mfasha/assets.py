from . import config


def missing_assets():
    return [p for p in config.REQUIRED_ASSETS if not p.exists()]


def ensure_assets():
    missing = missing_assets()
    if not missing:
        return
    if not config.HF_ASSETS_REPO:
        names = "\n  ".join(str(p.relative_to(config.ROOT)) for p in missing)
        raise FileNotFoundError(
            "These files are missing:\n  " + names +
            "\nCopy them from your Drive folder into this project, or set HF_ASSETS_REPO "
            "to the Hugging Face repo that holds them (see DEPLOY.md)."
        )
    from huggingface_hub import snapshot_download
    print(f"downloading assets from {config.HF_ASSETS_REPO} ...")
    snapshot_download(
        repo_id=config.HF_ASSETS_REPO, repo_type="model", token=config.HF_TOKEN,
        local_dir=str(config.ROOT),
        allow_patterns=["data/clean/passages.jsonl", "models/kinya-e5-large/best/*",
                        "models/mms-kin-adapter/best.pt", "results/emb/kinya_e5_passages.npy"],
    )
    still = missing_assets()
    if still:
        raise FileNotFoundError("Still missing after download: " + ", ".join(str(p) for p in still))
