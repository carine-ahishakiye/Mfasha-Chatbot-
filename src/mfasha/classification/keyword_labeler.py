
from __future__ import annotations

import re

from mfasha.interfaces import Classifier

CATEGORIES = (
    "crop production", "crop pests and diseases", "livestock management", "animal health",
    "weather-related farming", "agricultural programmes", "markets and inputs", "general farming",
)
GENERAL = "general farming"

# Word stems matched anywhere in lower-cased text: Kinyarwanda prefixes change (indwara / ndwara).
_STEMS = {
    "animal": ["nkoko", "ngurube", "ntama", "nkwavu", "nzuki", r"(?<![a-z])ihene", r"(?<![a-z])inka\b",
               "inyana", "kimasa", r"(?<![a-z])amata\b", "tungo", "bworozi", "mworozi", "aborozi", "kworora"],
    "vaccine": ["nkingo", "rukingo", "kingira"],
    "health": ["ndwara", "nkingo", "rukingo", "kingira", "kuvura", "imiti", "burwayi", "rwara", "rwaye",
               "bimenyetso", "cyonnyi", "byonnyi", "udukoko", "agakoko", "kwandura", "zandura", "kurwanya"],
    "crop": ["hinz", "hinga", "mbuto", "ngemwe", "sarura", "fumbire", "bihingwa", "gihingwa", "mirima",
             "murima", "butaka", "bigori", "bishyimbo", "birayi", "muceri", "myumbati", "bitoki", "cyayi",
             "kawa", "soya", "ngano", "mboga", "nyanya", "macunga", "pome", "fenesi", "makadamiya",
             "avoka", "biti", "bijumba"],
    "weather": ["kirere", "mvura", "izuba", "teganyagihe", "mapfa", "bushyuhe", "mwuzure"],
    "programme": ["bwishingizi", "nkunganire", "minagri", r"\brab\b", "gahunda", r"\bleta\b", "koperative",
                  "nguzanyo", "kigega", "mushinga", "tegeko"],
    "market": ["soko", "giciro", "biciro", "kugurisha", "gucuruza", "bucuruzi", "nyongeramusaruro",
               r"kugura\b"],
}
_PATTERNS = {key: re.compile("|".join(stems)) for key, stems in _STEMS.items()}


class KeywordCategoryLabeler(Classifier):
    name = "keyword-labeler"

    def predict(self, text: str) -> str:
        low = text.lower()
        title = low.split(":", 1)[0] if ":" in low else " ".join(low.split()[:12])

        def in_title(key: str) -> int:
            return len(_PATTERNS[key].findall(title))

        def score(key: str) -> int:  # a hit in the title counts three times a hit in the body
            return 3 * in_title(key) + len(_PATTERNS[key].findall(low))

        if in_title("programme"):
            return "agricultural programmes"
        if in_title("weather"):
            return "weather-related farming"
        if in_title("market"):
            return "markets and inputs"

        animal, crop, health = score("animal"), score("crop"), score("health")
        if score("vaccine") > 0 or (animal > crop and animal > 0):
            return "animal health" if (health >= 3 or score("vaccine") > 0) else "livestock management"
        if health >= 3:
            return "crop pests and diseases"
        if crop > 0:
            return "crop production"
        return GENERAL
