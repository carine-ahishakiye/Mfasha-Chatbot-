import sqlite3, os, sys

DB = "mfasha.db"
if not os.path.exists(DB):
    sys.exit("mfasha.db not found. Run this from the Mfasha-Chatbot- folder.")

c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)   # read-only: cannot change your data
q = lambda sql: c.execute(sql).fetchall()

def head(t): print("\n" + "=" * 60 + "\n" + t + "\n" + "=" * 60)

head("1. TABLES AND ROW COUNTS")
for (t,) in q("select name from sqlite_master where type='table' order by name"):
    print(f"{t:20} {q(f'select count(*) from [{t}]')[0][0]} rows")

head("2. PRIVACY CHECK: personal columns in the questions table")
cols = [r[1] for r in q("pragma table_info(questions)")]
print("questions columns:", cols)
bad = [x for x in cols if any(k in x.lower() for k in ("name", "phone", "user", "email", "device", "ip_", "_ip", "address"))]
print("PASS: no personal-identifier columns" if not bad else f"WARNING: check these columns: {bad}")

head("3. PRIVACY CHECK: do questions contain phone numbers or emails?")
hits = q("""select id, substr(question_text,1,80) from questions
            where question_text glob '*[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]*'
               or question_text like '%@%'""")
print(f"{len(hits)} question(s) may contain a phone number or email")
for h in hits[:10]: print("  ", h)

head("4. OFFICERS: are PINs hashed? (hash only shown shortened)")
for r in q("select id, name, substr(phone,1,4)||'******', active, substr(pin_salt,1,6)||'...', substr(pin_hash,1,10)||'...' from officers"):
    print("  ", r)
print("Column check:", [r[1] for r in q("pragma table_info(officers)")])

head("5. INPUT TYPES (text vs voice)")
for r in q("select input_type, count(*) from questions group by input_type"): print("  ", r)

head("6. AUDIO CHECK: does the database keep recordings?")
allcols = [(t, r[1]) for (t,) in q("select name from sqlite_master where type='table'") for r in q(f"pragma table_info([{t}])")]
audio = [x for x in allcols if any(k in x[1].lower() for k in ("audio", "wav", "blob", "recording", "file", "path"))]
print("Audio-like columns:", audio if audio else "NONE (no recording is stored in the database)")
found = []
for root, _, files in os.walk("."):
    if any(s in root for s in (".venv", ".git", "models", "node_modules")): continue
    found += [os.path.join(root, f) for f in files if f.lower().endswith((".wav", ".mp3", ".webm", ".ogg", ".m4a"))]
print(f"Audio files on disk (outside .venv/models): {len(found)}")
for f in found[:10]: print("  ", f)

head("7. REFERRAL SAFEGUARD")
for r in q("select status, coalesce(referral_reason,'-'), count(*) from answers group by 1,2"): print("  ", r)

head("8. OFFICER REVIEW EVIDENCE (expert_reviews)")
for r in q("select verdict, count(*), sum(is_safe), sum(is_relevant), sum(is_clear) from expert_reviews group by verdict"):
    print("  verdict, n, safe, relevant, clear:", r)
print("answers awaiting review:", q("select count(*) from answers where review_status is null or review_status='pending'")[0][0])

head("9. USER FEEDBACK")
for r in q("select count(*), round(avg(rating),2), sum(is_useful) from feedback"):
    print("  n, avg rating, useful:", r)

head("10. SAMPLE FARMER QUESTION (for the video)")
for r in q("select id, input_type, substr(question_text,1,70), submitted_at from questions order by id desc limit 3"): print("  ", r)