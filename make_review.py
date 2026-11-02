import pandas as pd, json
df = pd.read_excel('results/review_sheet_all_passages.xlsx')
print(df['review_status'].value_counts(dropna=False))
ok = df[df['review_status'].astype(str).str.strip().str.lower() == 'correct']
ids = {json.loads(l)['pid'] for l in open('data/processed/passages.jsonl', encoding='utf-8') if l.strip()}
ok = ok[ok['pid'].astype(str).str.strip().isin(ids)]
out = pd.DataFrame({'pid': ok['pid'].astype(str).str.strip(), 'reviewer': ok['reviewer'], 'reviewed_on': ok['date']})
out.to_csv('data/processed/officer_reviewed_passages.csv', index=False)
print(len(out), 'correct passages saved; total passages in knowledge base:', len(ids))
