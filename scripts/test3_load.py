import csv, json, math, os, random, sys, threading, time, urllib.request, urllib.error
from collections import Counter

BASE = "https://mfasha-chatbot.vercel.app/mfasha"
LEVELS = [10, 25, 50, 100, 200]
DURATION = 30      # seconds each level runs
RAMP = 5           # seconds to start all users gradually
BUDGET_MS = 5000   # response time budget
TIMEOUT = 30       # a request slower than this counts as an error
QUESTIONS = ["Ni gute nahinga ibigori?", "Ibirayi bitera mu butaka bumeze bute?", "Ni gute nakora ubuhinzi bw'ibihumyo?",
             "Inkoko nzorora nte?", "Ni nde watwaye igikombe cy'isi cya 2022?", "Nakwirinda nte ibyonnyi mu bigori?",
             "Ni ryari nakingiza inka?", "Nabona nte nkunganire ku ifumbire?", "asdfgh", "Iteganyagihe ryamfasha iki mu buhinzi?"]

if len(sys.argv) > 1:
    LEVELS = [int(x) for x in sys.argv[1:]]

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_dir = os.path.join(root, "results", "system_testing")
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, "test3_load.csv")


def pct(vals, p):
    if not vals:
        return 0
    s = sorted(vals)
    i = max(0, int(math.ceil(p / 100.0 * len(s))) - 1)
    return s[i]


def user(deadline, results, lock, delay):
    time.sleep(delay)
    while time.time() < deadline:
        body = json.dumps({"question": random.choice(QUESTIONS)}).encode("utf-8")
        req = urllib.request.Request(BASE + "/api/ask/text", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        code = 0
        server = None
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                code = r.status
                server = json.loads(r.read().decode("utf-8")).get("latency_ms")
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:
            code = -1   # timeout or connection problem
        ms = (time.time() - t0) * 1000
        with lock:
            results.append((code, ms, server))
        time.sleep(random.uniform(1, 3))


def app_up():
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=15) as r:
            return json.loads(r.read().decode("utf-8")).get("status") == "ok"
    except Exception:
        return False


def run_level(n):
    results = []
    lock = threading.Lock()
    deadline = time.time() + RAMP + DURATION
    threads = []
    for i in range(n):
        th = threading.Thread(target=user, args=(deadline, results, lock, RAMP * i / float(n)))
        th.daemon = True
        th.start()
        threads.append(th)
    while time.time() < deadline:
        time.sleep(5)
        print("      ... %d requests so far" % len(results))
    for th in threads:
        th.join(timeout=TIMEOUT + 5)
    total = len(results)
    good = [r for r in results if r[0] == 200]
    lat = [r[1] for r in good]
    srv = [r[2] for r in good if r[2] is not None]
    errors = total - len(good)
    err_pct = round(100.0 * errors / total, 1) if total else 100.0
    p95 = int(pct(lat, 95))
    verdict = "PASS" if (total and p95 <= BUDGET_MS and err_pct < 1) else "FAIL"
    codes = Counter(str(r[0]) for r in results if r[0] != 200)
    return {"Users": n, "Requests": total, "Errors": errors, "ErrorPct": err_pct,
            "ReqPerSec": round(total / float(RAMP + DURATION), 1),
            "P50ms": int(pct(lat, 50)), "P95ms": p95, "P99ms": int(pct(lat, 99)), "MaxMs": int(pct(lat, 100)),
            "ServerP50ms": round(pct(srv, 50), 1), "ServerP95ms": round(pct(srv, 95), 1),
            "ErrorCodes": ";".join("%s x%d" % (k, v) for k, v in codes.items()), "Verdict": verdict}


def save(rows):
    with open(out_file, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if not app_up():
    print("The app is not up right now. Wait until it is, then run this again.")
    sys.exit(1)

print("LOAD TEST: levels %s, %d s each, think time 1-3 s per user\n" % (LEVELS, DURATION))
rows = []
last_pass = 0
first_fail = None
for n in LEVELS:
    print("== %d users ==" % n)
    r = run_level(n)
    rows.append(r)
    save(rows)
    print("   requests %d, errors %d (%.1f%%), req/s %.1f, p50 %d ms, p95 %d ms, max %d ms, server p95 %.0f ms -> %s" %
          (r["Requests"], r["Errors"], r["ErrorPct"], r["ReqPerSec"], r["P50ms"], r["P95ms"], r["MaxMs"], r["ServerP95ms"], r["Verdict"]))
    if r["ErrorCodes"]:
        print("   error codes: %s" % r["ErrorCodes"])
    if r["Verdict"] == "PASS":
        last_pass = n
    else:
        first_fail = n
        print("   Stopping: this level failed (p95 over %d ms or errors of 1%% or more)." % BUDGET_MS)
        break
    if n != LEVELS[-1]:
        time.sleep(10)

print("\n===== LOAD SUMMARY =====")
print("Highest level that passed: %s users" % (last_pass if last_pass else "none"))
print("First level that failed:   %s" % (("%d users" % first_fail) if first_fail else "none (all levels passed)"))
print("Pass rule: p95 <= %d ms and errors < 1%%" % BUDGET_MS)
print("Saved: %s" % out_file)