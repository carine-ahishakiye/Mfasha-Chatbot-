import csv, json, urllib.request, collections
rows = list(csv.DictReader(open("data/processed/questions_dev.csv", encoding="utf-8")))[:60]
reasons, scores, margins, ok = collections.Counter(), [], [], 0
for r in rows:
    req = urllib.request.Request("http://localhost:8000/api/ask/text",
        data=json.dumps({"question": r["question"][:500]}).encode(), headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req))
    reasons[d["status"] + " / " + str(d["referral_reason"])] += 1
    scores.append(d["retrieval_score"] or 0); margins.append(d["margin"] or 0)
    ok += d["passage_id"] == r["pid"]
print(reasons)
print("top-1 correct passage:", ok, "of", len(rows))
print("score  min/avg/max:", round(min(scores),3), round(sum(scores)/len(scores),3), round(max(scores),3))
print("margin min/avg/max:", round(min(margins),3), round(sum(margins)/len(margins),3), round(max(margins),3))
