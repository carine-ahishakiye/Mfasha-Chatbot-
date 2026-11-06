#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def newest(folder: Path, pattern: str) -> Path | None:
    files = sorted(folder.rglob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def copy(src: Path | None, dst: Path, label: str) -> None:
    if src is None or not src.exists():
        print(f"  skipped  {label} (not found)")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    print(f"  copied   {label} -> {dst.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive", type=Path, required=True, help="the 'Mfasha chatbot' folder")
    drive = parser.parse_args().drive
    if not drive.exists():
        raise SystemExit(f"folder not found: {drive}")

    processed, models = ROOT / "data" / "processed", ROOT / "models"
    copy(drive / "data" / "clean" / "passages.jsonl", processed / "passages.jsonl", "passages")
    copy(newest(drive, "category_labels_officer*.csv"), processed / "category_labels_officer.csv", "officer labels")
    copy(newest(drive, "officer_reviewed_passages*.csv"), processed / "officer_reviewed_passages.csv", "reviewed passages")
    copy(drive / "results" / "referral_threshold.json", models / "referral_threshold.json", "referral threshold")
    copy(next((p for p in (drive / "models" / "classifier_svm.joblib", drive / "models" / "classifier_lr.joblib") if p.exists()), None),
         models / "classifier.joblib", "classifier")
    copy(drive / "models" / "kinya-e5-large" / "best", models / "kinya-e5-large" / "best", "fine-tuned e5 retriever")
    copy(drive / "models" / "mms-kin-adapter", models / "mms-kin-adapter", "speech-to-text adapter")
    print("\nNow set in .env:\n  MFASHA_KNOWLEDGE_PATH=data/processed/passages.jsonl\n"
          "  MFASHA_REVIEWED_PATH=data/processed/officer_reviewed_passages.csv\n"
          "  MFASHA_LABELS_PATH=data/processed/category_labels_officer.csv\n"
          "  MFASHA_RETRIEVER=embedding   (after: pip install -r requirements-ml.txt)")


if __name__ == "__main__":
    main()