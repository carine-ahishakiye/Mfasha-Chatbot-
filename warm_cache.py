import os, hashlib
from pathlib import Path
import numpy as np, torch

for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.split("#")[0].strip()
    if "=" in line:
        k, v = line.split("=", 1); os.environ[k.strip()] = v.strip()

from mfasha.config import Settings
from mfasha.factory import build_knowledge_base
from sentence_transformers import SentenceTransformer

torch.set_num_threads(os.cpu_count())
s = Settings.from_env()
kb = build_knowledge_base(s)
texts = ["passage: " + p.text for p in kb.passages]
digest = hashlib.md5("\n".join(texts).encode("utf-8")).hexdigest()[:10]
cache = s.models_dir / "cache" / f"passages_{digest}.npy"
cache.parent.mkdir(parents=True, exist_ok=True)
part_dir = cache.parent / f"parts_{digest}"; part_dir.mkdir(exist_ok=True)

m = SentenceTransformer(str(s.models_dir / "kinya-e5-large" / "best"))
m.max_seq_length = 256
CH = 50
for i in range(0, len(texts), CH):
    f = part_dir / f"{i:05d}.npy"
    if f.exists():
        continue
    e = m.encode(texts[i:i+CH], batch_size=16, normalize_embeddings=True).astype(np.float32)
    np.save(f, e)
    print(f"{min(i+CH, len(texts))}/{len(texts)} done", flush=True)

parts = sorted(part_dir.glob("*.npy"))
np.save(cache, np.concatenate([np.load(p) for p in parts]))
print("saved", cache)
