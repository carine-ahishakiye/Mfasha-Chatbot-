"""Writes numbers, units and percentages as Kinyarwanda words so the voice can read them."""
import re

ONES = {1: "rimwe", 2: "kabiri", 3: "gatatu", 4: "kane", 5: "gatanu", 6: "gatandatu",
        7: "karindwi", 8: "umunani", 9: "icyenda", 10: "icumi"}
TENS = {2: "makumyabiri", 3: "mirongo itatu", 4: "mirongo ine", 5: "mirongo itanu",
        6: "mirongo itandatu", 7: "mirongo irindwi", 8: "mirongo inani", 9: "mirongo icyenda"}
HUNDREDS = {1: "ijana", 2: "magana abiri", 3: "magana atatu", 4: "magana ane", 5: "magana atanu",
            6: "magana atandatu", 7: "magana arindwi", 8: "magana inani", 9: "magana cyenda"}
THOUSAND_ONE = "igihumbi"
THOUSANDS = {2: "ibihumbi bibiri", 3: "ibihumbi bitatu", 4: "ibihumbi bine", 5: "ibihumbi bitanu",
             6: "ibihumbi bitandatu", 7: "ibihumbi birindwi", 8: "ibihumbi umunani",
             9: "ibihumbi icyenda", 10: "ibihumbi icumi"}
POINT, PERCENT, RANGE = "virigule", "ku ijana", "kugeza kuri"
UNITS = {"kg": "kilo", "g": "garama", "cm": "santimetero", "mm": "milimetero", "m": "metero",
         "ha": "hegitari", "ml": "mililitiro", "l": "litiro"}
NUM = r"\d+(?:[.,]\d+)?"


def _join_words(parts):
    out = parts[0]
    for p in parts[1:]:
        out += (" n'" if p[0] in "aeiou" else " na ") + p
    return out


def number_words(n: int) -> str:
    if n == 0:
        return "zeru"
    parts = []
    if n >= 1000:
        k, n = divmod(n, 1000)
        if k == 1:
            parts.append(THOUSAND_ONE)
        elif k in THOUSANDS:
            parts.append(THOUSANDS[k])
        else:
            parts.append("ibihumbi " + number_words(k))
    if n >= 100:
        h, n = divmod(n, 100)
        parts.append(HUNDREDS[h])
    if n >= 20:
        t, n = divmod(n, 10)
        parts.append(TENS[t])
    elif n >= 11:
        parts.append(ONES[10])
        n -= 10
    if n:
        parts.append(ONES[n])
    return _join_words(parts)


def read_number(s: str) -> str:
    s = s.replace(",", ".")
    if "." in s:
        whole, frac = s.split(".", 1)
        return f"{number_words(int(whole))} {POINT} " + " ".join(number_words(int(d)) for d in frac)
    return number_words(int(s)) if int(s) < 100000 else " ".join(number_words(int(d)) for d in s)


def speech_prep(text: str) -> str:
    t = text.replace("\u2019", "'")
    t = re.sub(rf"({NUM})\s*%", lambda m: read_number(m.group(1)) + " " + PERCENT, t)
    t = re.sub(rf"({NUM})\s*(kg|cm|mm|ml|ha|g|m|l)\b",
               lambda m: read_number(m.group(1)) + " " + UNITS[m.group(2)], t)
    t = re.sub(rf"{NUM}(?:-{NUM}){{2,}}", lambda m: m.group(0).replace("-", ", "), t)     # 17-17-17 one by one
    t = re.sub(rf"(?<![\d-])({NUM})-({NUM})(?![\d-])", lambda m: f"{m.group(1)} {RANGE} {m.group(2)}", t)  # 4-5 range
    t = re.sub(NUM, lambda m: read_number(m.group(0)), t)
    return re.sub(r"\s+", " ", t).strip()
