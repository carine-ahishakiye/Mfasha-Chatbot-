from tests.conftest import IN_SCOPE_QUESTION, make_wav

KEY = {"X-API-Key": "test-key"}


def test_health(client, knowledge_base):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["components"]["retriever"]
    assert body["passages"] == len(knowledge_base)


def test_text_question_round_trip_and_feedback(client):
    r = client.post("/api/ask/text", json={"question": IN_SCOPE_QUESTION})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "answered"
    fb = client.post("/api/feedback", json={"answer_id": body["answer_id"], "rating": 5, "is_useful": True})
    assert fb.status_code == 201


def test_empty_and_oversized_questions_are_rejected(client):
    assert client.post("/api/ask/text", json={"question": ""}).status_code == 422
    assert client.post("/api/ask/text", json={"question": "a" * 501}).status_code == 422
    assert client.post("/api/ask/text", json={}).status_code == 422


def test_off_topic_question_returns_referral_message(client):
    body = client.post("/api/ask/text", json={"question": "Ni nde watwaye igikombe cy'isi cya 2022?"}).json()
    assert body["status"] == "referred" and "agoronome" in body["answer"]


def test_script_in_question_is_returned_as_data_not_executed(client):
    body = client.post("/api/ask/text", json={"question": "<script>alert(1)</script>"}).json()
    assert body["status"] == "referred"        # nothing relevant matched, and no crash


def test_voice_question(client):
    r = client.post("/api/ask/voice", files={"audio": ("q.wav", make_wav(), "audio/wav")})
    assert r.status_code == 200 and r.json()["heard"] == IN_SCOPE_QUESTION


def test_voice_with_invalid_audio_returns_422(client):
    r = client.post("/api/ask/voice", files={"audio": ("q.wav", b"not audio", "audio/wav")})
    assert r.status_code == 422 and r.json()["error"] == "invalid_audio"


def test_voice_too_large_returns_413(client, settings):
    client.app.state.settings = type(settings)(**{**settings.__dict__, "max_audio_bytes": 100})
    r = client.post("/api/ask/voice", files={"audio": ("q.wav", make_wav(1.0), "audio/wav")})
    assert r.status_code == 413


def test_voice_without_stt_returns_503(settings, knowledge_base):
    from fastapi.testclient import TestClient

    from mfasha.api import create_app
    with TestClient(create_app(settings=settings, knowledge_base=knowledge_base)) as c:
        r = c.post("/api/ask/voice", files={"audio": ("q.wav", make_wav(), "audio/wav")})
    assert r.status_code == 503 and r.json()["error"] == "service_unavailable"


def test_feedback_validation(client):
    assert client.post("/api/feedback", json={"answer_id": 999, "rating": 3, "is_useful": True}).status_code == 404
    assert client.post("/api/feedback", json={"answer_id": 1, "rating": 9, "is_useful": True}).status_code == 422


def test_officer_and_admin_endpoints_need_the_api_key(client):
    answer_id = client.post("/api/ask/text", json={"question": IN_SCOPE_QUESTION}).json()["answer_id"]
    review = {"answer_id": answer_id, "reviewer": "Officer A", "verdict": "correct",
              "is_relevant": True, "is_clear": True, "is_safe": True}
    assert client.post("/api/officer/reviews", json=review).status_code == 401
    assert client.post("/api/officer/reviews", json=review, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/api/officer/reviews", json=review, headers=KEY).status_code == 201
    stats = client.get("/api/admin/stats", headers=KEY).json()
    assert stats["expert_reviews"] == 1 and stats["officer_correct_or_partial_rate"] == 1.0


def test_admin_disabled_without_configured_key(settings, knowledge_base, pipeline):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from mfasha.api import create_app
    app = create_app(settings=replace(settings, api_key=""), pipeline=pipeline, knowledge_base=knowledge_base)
    with TestClient(app) as c:
        assert c.get("/api/admin/stats", headers=KEY).status_code == 503


def test_frontend_is_served(client):
    r = client.get("/")                                  # welcome page: who are you?
    assert r.status_code == 200 and "Mfasha" in r.text
    assert 'href="chat.html"' in r.text and 'href="officer.html"' in r.text
    assert "Fungura konti" in client.get("/officer.html").text            # officer sign-up / sign-in page
    assert client.get("/chat.html").status_code == 200                    # farmer chat, no login

def test_officer_answer_queue_needs_key_and_lists_answers(client):
    answer_id = client.post("/api/ask/text", json={"question": IN_SCOPE_QUESTION}).json()["answer_id"]
    assert client.get("/api/officer/answers").status_code == 401
    rows = client.get("/api/officer/answers", headers=KEY).json()
    assert any(r["answer_id"] == answer_id for r in rows)
    one = client.get(f"/api/officer/answers/{answer_id}", headers=KEY)
    assert one.status_code == 200 and one.json()["answer_id"] == answer_id
    assert client.get("/api/officer/answers/99999", headers=KEY).status_code == 404


def _bearer(client, phone="0788123456", pin="4821"):
    r = client.post("/api/officer/login", json={"phone": phone, "pin": pin})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_officer_signs_in_with_phone_and_pin(client):
    client.app.state.repository.upsert_officer("0788123456", "Mukamana Jeanne", "4821")
    answer_id = client.post("/api/ask/text", json={"question": IN_SCOPE_QUESTION}).json()["answer_id"]

    assert client.post("/api/officer/login", json={"phone": "0788123456", "pin": "9999"}).status_code == 401
    assert client.post("/api/officer/login", json={"phone": "0700000000", "pin": "4821"}).status_code == 401
    assert client.post("/api/officer/login", json={"phone": "0788123456", "pin": "12"}).status_code == 422

    for phone in ("0788123456", "+250 788 123 456"):        # any way of writing the same number
        headers = _bearer(client, phone)
    assert client.get("/api/officer/answers").status_code == 401
    assert any(r["answer_id"] == answer_id for r in client.get("/api/officer/answers", headers=headers).json())
    assert client.get("/api/admin/stats", headers=headers).status_code == 200

    review = {"answer_id": answer_id, "reviewer": "Someone Else", "verdict": "correct",
              "is_relevant": True, "is_clear": True, "is_safe": True}
    assert client.post("/api/officer/reviews", json=review, headers=headers).status_code == 201
    from sqlalchemy import select

    from mfasha.storage.orm import ExpertReviewRow
    with client.app.state.repository._sessions() as s:
        assert s.scalar(select(ExpertReviewRow.reviewer)) == "Mukamana Jeanne"   # the name on file


def test_bad_or_forged_tokens_are_rejected(client):
    assert client.get("/api/officer/answers", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    client.app.state.repository.upsert_officer("0788123456", "Mukamana Jeanne", "4821")
    token = _bearer(client)["Authorization"]
    assert client.get("/api/officer/answers", headers={"Authorization": token + "x"}).status_code == 401


def test_deactivated_officer_loses_access_at_once(client):
    repo = client.app.state.repository
    repo.upsert_officer("0788123456", "Mukamana Jeanne", "4821")
    headers = _bearer(client)
    repo.set_officer_active("0788123456", False)
    assert client.get("/api/officer/answers", headers=headers).status_code == 401
    assert client.post("/api/officer/login", json={"phone": "0788123456", "pin": "4821"}).status_code == 401


def test_too_many_wrong_pins_locks_the_phone_number(client):
    client.app.state.repository.upsert_officer("0788123456", "Mukamana Jeanne", "4821")
    for _ in range(5):
        assert client.post("/api/officer/login", json={"phone": "0788123456", "pin": "0000"}).status_code == 401
    assert client.post("/api/officer/login", json={"phone": "0788123456", "pin": "0000"}).status_code == 429
    assert client.post("/api/officer/login", json={"phone": "0788123456", "pin": "4821"}).status_code == 429


def test_officer_creates_an_account_with_the_signup_code(client, settings):
    from dataclasses import replace
    client.app.state.settings = replace(settings, officer_signup_code="open-sesame")
    new = {"name": "Mukamana Jeanne", "phone": "0788 123 456", "pin": "4821", "code": "open-sesame"}

    assert client.post("/api/officer/register", json={**new, "code": "wrong"}).status_code == 401
    r = client.post("/api/officer/register", json=new)
    assert r.status_code == 201 and r.json()["phone"] == "0788123456"
    assert client.get("/api/officer/answers", headers={"Authorization": f"Bearer {r.json()['token']}"}).status_code == 200
    assert client.post("/api/officer/register", json=new).status_code == 409           # number already used
    assert _bearer(client)                                                              # and the PIN works to log in
    assert client.post("/api/officer/register", json={**new, "pin": "12"}).status_code == 422


def test_signup_is_closed_without_a_code_and_locks_after_wrong_codes(client, settings):
    from dataclasses import replace
    new = {"name": "Mukamana Jeanne", "phone": "0788123456", "pin": "4821", "code": "anything"}
    assert client.post("/api/officer/register", json=new).status_code == 503            # no code configured
    client.app.state.settings = replace(settings, officer_signup_code="open-sesame")
    for _ in range(5):
        assert client.post("/api/officer/register", json=new).status_code == 401
    assert client.post("/api/officer/register", json={**new, "code": "open-sesame"}).status_code == 429