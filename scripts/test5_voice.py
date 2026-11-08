import csv, io, json, math, os, random, struct, sys, time, uuid, wave
import urllib.request, urllib.error

BASE = "https://mfasha-chatbot.vercel.app/mfasha"
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_dir = os.path.join(root, "results", "system_testing")
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, "test5_voice.csv")


def make_wav(seconds, rate=16000, channels=1, width=2, kind="silence"):
    n = int(seconds * rate)
    if width == 1:
        data = bytes([128]) * (n * channels)
    elif kind == "silence":
        data = b"\x00\x00" * (n * channels)
    else:
        buf = bytearray()
        for i in range(n):
            if kind == "tone":
                v = int(8000 * math.sin(2 * math.pi * 440 * i / rate))
            else:
                v = random.randint(-400, 400)
            buf += struct.pack("<h", v) * channels
        data = bytes(buf)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(data)
    return bio.getvalue()


def post_audio(data, field="audio"):
    boundary = uuid.uuid4().hex
    head = ('--%s\r\nContent-Disposition: form-data; name="%s"; filename="clip.wav"\r\n'
            'Content-Type: audio/wav\r\n\r\n' % (boundary, field)).encode()
    body = head + data + ("\r\n--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(BASE + "/api/ask/voice", data=body, method="POST",
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    t0 = time.time()
    code, j, detail = 0, None, ""
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            code = r.status
            j = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            d = json.loads(e.read().decode("utf-8")).get("detail", "")
            detail = d if isinstance(d, str) else json.dumps(d)[:120]
        except Exception:
            detail = ""
    except Exception as e:
        code = -1
        detail = str(e)[:100]
    return code, j, detail, int((time.time() - t0) * 1000)


def health():
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


h = health()
if not h or h.get("status") != "ok":
    print("The app is not up right now. Wait until it is, then run this again.")
    sys.exit(1)
print("Speech component on the app: %s\n" % h.get("components", {}).get("stt"))

random.seed(1)
TESTS = [
    ("V01", "Valid WAV, 3 s of silence",             lambda: (make_wav(3), "audio"),                    200, True,  ""),
    ("V02", "Valid WAV, 2 s tone",                   lambda: (make_wav(2, kind="tone"), "audio"),       200, True,  ""),
    ("V03", "Valid WAV, 3 s low noise",              lambda: (make_wav(3, kind="noise"), "audio"),      200, True,  ""),
    ("V04", "Stereo 44.1 kHz WAV, 3 s",              lambda: (make_wav(3, 44100, 2), "audio"),          200, False, "tests the resampling path"),
    ("V05", "Valid WAV, 10 s (timing)",              lambda: (make_wav(10, kind="noise"), "audio"),     200, False, "speech-to-text time for 10 s"),
    ("V06", "Valid WAV, 29 s (timing, near limit)",  lambda: (make_wav(29, kind="noise"), "audio"),     200, False, "speech-to-text time for 29 s"),
    ("V07", "WAV of 31 s (over the 30 s limit)",     lambda: (make_wav(31), "audio"),                   422, False, ""),
    ("V08", "8-bit WAV",                             lambda: (make_wav(2, width=1), "audio"),           422, False, "only 16-bit is supported"),
    ("V09", "Not a WAV file (plain text)",           lambda: (b"this is not audio at all", "audio"),    422, False, ""),
    ("V10", "Empty file",                            lambda: (b"", "audio"),                            422, False, ""),
    ("V11", "WAV over 5 MB",                         lambda: (make_wav(165), "audio"),                  413, False, "the 413 may come from the app or from the Vercel proxy"),
    ("V12", "Request with no audio field",           lambda: (make_wav(2), "wrongfield"),               422, False, ""),
]

rows = []
for tid, name, build, exp, observe, note in TESTS:
    data, field = build()
    code, j, detail, ms = post_audio(data, field)
    res = "PASS" if code == exp else "FAIL"
    if observe and code == 200:
        res = "OBSERVE"
    status = j.get("status") if j else ""
    reason = j.get("referral_reason") if j else ""
    heard = (j.get("heard") or "")[:60] if j else ""
    stt_ms = (j.get("stage_ms") or {}).get("speech_to_text", "") if j else ""
    kb = len(data) // 1024
    rows.append({"ID": tid, "Test": name, "Expected": "HTTP %d" % exp, "HTTP": code, "Result": res,
                 "RoundTripMs": ms, "SttMs": stt_ms, "Status": status, "Reason": reason, "Heard": heard,
                 "SizeKB": kb, "Detail": detail, "Note": note})
    print("[%s] %s %-40s HTTP %s  %5d ms  stt %s ms  %s %s %s" % (res, tid, name, code, ms, stt_ms, status or "", reason or "", detail))

with open(out_file, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

p = sum(1 for r in rows if r["Result"] == "PASS")
f_ = sum(1 for r in rows if r["Result"] == "FAIL")
o = sum(1 for r in rows if r["Result"] == "OBSERVE")
print("\nSUMMARY: %d passed, %d failed, %d to judge by hand (of %d)" % (p, f_, o, len(rows)))
for r in rows:
    if r["Result"] == "FAIL":
        print("  FAIL %s %s: expected %s, got %s %s" % (r["ID"], r["Test"], r["Expected"], r["HTTP"], r["Detail"]))
print("Saved: %s" % out_file)