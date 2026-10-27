"""Asks the LLM on Groq to copy the sentences that answer the question."""
import time

import requests

from . import config

NO_ANSWER = "Mbabarira, nta makuru mfite kuri icyo kibazo."

SYSTEM = (
    "You are an agriculture assistant for Rwandan farmers. "
    "Read the passages and pick the sentences that answer the question. "
    "Copy them exactly as written, word for word, in Kinyarwanda. Do not rewrite, translate, "
    "summarise or add anything. Use at most three sentences. "
    f"If no passage answers the question, reply exactly: {NO_ANSWER}"
)


def ask_llm(question, hits, retries=4):
    """Returns the reply text, or None if Groq could not be reached or kept returning empty replies."""
    if not config.GROQ_API_KEY:
        print("llm error: GROQ_API_KEY is not set")
        return None
    context = "\n\n".join(f"[{i + 1}] {h.text}" for i, h in enumerate(hits))
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Passages:\n{context}\n\nQuestion: {question}"},
    ]
    for attempt in range(retries):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                json={"model": config.LLM_MODEL, "messages": messages,
                      "temperature": config.LLM_TEMPERATURE,
                      "max_tokens": 4096, "reasoning_effort": "low"},
                timeout=60,
            )
            if r.status_code == 429:                      # rate limit: wait and try again
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            choice = r.json()["choices"][0]
            text = (choice["message"].get("content") or "").strip()
            if not text or choice.get("finish_reason") == "length":
                time.sleep(1)
                continue
            return text
        except Exception as e:
            print("llm error:", str(e)[:150])
            time.sleep(2)
    return None
