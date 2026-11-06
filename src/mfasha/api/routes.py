"""HTTP endpoints. Thin on purpose: validate, call the pipeline, log, shape the response."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile

from mfasha import __version__
from mfasha.auth import burn_time, check_pin, make_token, normalize_phone, read_token
from mfasha.api.schemas import AskResponse, ExpertReviewIn, FeedbackIn, HealthResponse, OfficerLoginIn, OfficerRegisterIn, TextQuestion
from mfasha.domain.models import PipelineResult
from mfasha.storage.repository import InteractionRepository

router = APIRouter()


#  dependencies 
def get_pipeline(request: Request):
    return request.app.state.pipeline


def get_repository(request: Request) -> InteractionRepository:
    return request.app.state.repository


def require_staff(request: Request, x_api_key: str = Header(default=""),
                  authorization: str = Header(default="")) -> dict:
    """Officer endpoints. Allowed: an officer signed in with phone + PIN (Bearer token), or the
    administrator API key. Returns {"role": "officer" | "admin", "name": ...}."""
    if authorization.lower().startswith("bearer "):
        data = read_token(request.app.state.secret, authorization[7:].strip())
        officer = request.app.state.repository.get_officer(data["phone"]) if data else None
        if officer is None or not officer["active"]:      # a deactivated officer loses access at once
            raise HTTPException(status_code=401, detail="sign in again")
        return {"role": "officer", "name": officer["name"], "phone": officer["phone"]}
    if x_api_key:
        expected = request.app.state.settings.api_key
        if not expected:
            raise HTTPException(status_code=503, detail="API-key access is disabled: set MFASHA_API_KEY")
        if not secrets.compare_digest(x_api_key.encode(), expected.encode()):   # constant-time comparison
            raise HTTPException(status_code=401, detail="invalid API key")
        return {"role": "admin", "name": "admin"}
    raise HTTPException(status_code=401, detail="sign in required")


def _to_response(result: PipelineResult, answer_id: int) -> AskResponse:
    return AskResponse(answer_id=answer_id, **result.to_dict())


def _components(request: Request) -> dict:
    return request.app.state.pipeline.describe()


# farmer endpoints
@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    kb = request.app.state.kb
    return HealthResponse(status="ok", version=__version__,
                          passages=len(kb) if kb else 0, reviewed_passages=kb.reviewed_count() if kb else 0,
                          components=_components(request))


@router.post("/ask/text", response_model=AskResponse)
def ask_text(body: TextQuestion, request: Request, pipeline=Depends(get_pipeline),
             repo: InteractionRepository = Depends(get_repository)):
    limit = request.app.state.settings.max_question_chars
    if len(body.question) > limit:
        raise HTTPException(status_code=422, detail=f"question is longer than {limit} characters")
    result = pipeline.ask_text(body.question)
    return _to_response(result, repo.log_interaction(result, "text", _components(request)))


@router.post("/ask/voice", response_model=AskResponse)
async def ask_voice(request: Request, audio: UploadFile = File(...),
                    pipeline=Depends(get_pipeline), repo: InteractionRepository = Depends(get_repository)):
    settings = request.app.state.settings
    data = await audio.read(settings.max_audio_bytes + 1)       # never read more than the limit allows
    if len(data) > settings.max_audio_bytes:
        raise HTTPException(status_code=413, detail="audio file is too large")
    result = pipeline.ask_audio(data, max_seconds=settings.max_audio_seconds)
    return _to_response(result, repo.log_interaction(result, "voice", _components(request)))


@router.post("/feedback", status_code=201)
def feedback(body: FeedbackIn, repo: InteractionRepository = Depends(get_repository)):
    if not repo.answer_exists(body.answer_id):
        raise HTTPException(status_code=404, detail="unknown answer_id")
    return {"feedback_id": repo.add_feedback(body.answer_id, body.rating, body.is_useful, body.comment)}


# officer and administrator endpoints
@router.post("/officer/register", status_code=201)
def officer_register(body: OfficerRegisterIn, request: Request,
                     repo: InteractionRepository = Depends(get_repository)):
    """An officer creates their own account. Only people who know the sign-up code can do it."""
    expected = request.app.state.settings.officer_signup_code
    if not expected:
        raise HTTPException(status_code=503, detail="sign-up is closed: set MFASHA_OFFICER_CODE")
    throttle = request.app.state.throttle
    who = "signup:" + (request.client.host if request.client else "unknown")
    wait = throttle.seconds_locked(who)
    if wait:
        raise HTTPException(status_code=429, detail=f"too many wrong codes, try again in {wait} seconds")
    if not secrets.compare_digest(body.code.strip().encode(), expected.encode()):
        throttle.record_failure(who)
        raise HTTPException(status_code=401, detail="wrong sign-up code")
    phone, name = normalize_phone(body.phone), body.name.strip()
    if phone is None or len(name) < 2:
        raise HTTPException(status_code=422, detail="check the name and the phone number")
    if not repo.create_officer(phone, name, body.pin):
        raise HTTPException(status_code=409, detail="this phone number already has an account")
    throttle.reset(who)
    return {"token": make_token(request.app.state.secret, phone, name), "name": name, "phone": phone}


@router.post("/officer/login")
def officer_login(body: OfficerLoginIn, request: Request,
                  repo: InteractionRepository = Depends(get_repository)):
    phone = normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=401, detail="wrong phone number or PIN")
    throttle = request.app.state.throttle
    wait = throttle.seconds_locked(phone)
    if wait:
        raise HTTPException(status_code=429, detail=f"too many wrong PINs, try again in {wait} seconds")
    officer = repo.get_officer(phone)
    if officer is None or not officer["active"]:
        burn_time()                                        # same delay as a wrong PIN
        throttle.record_failure(phone)
        raise HTTPException(status_code=401, detail="wrong phone number or PIN")
    if not check_pin(body.pin, officer["pin_salt"], officer["pin_hash"]):
        throttle.record_failure(phone)
        raise HTTPException(status_code=401, detail="wrong phone number or PIN")
    throttle.reset(phone)
    return {"token": make_token(request.app.state.secret, phone, officer["name"]),
            "name": officer["name"], "phone": phone}


@router.post("/officer/reviews", status_code=201)
def officer_review(body: ExpertReviewIn, actor: dict = Depends(require_staff),
                   repo: InteractionRepository = Depends(get_repository)):
    if not repo.answer_exists(body.answer_id):
        raise HTTPException(status_code=404, detail="unknown answer_id")
    data = body.model_dump()
    if actor["role"] == "officer":
        data["reviewer"] = actor["name"]                   # the name on file, not whatever the page sent
    return {"review_id": repo.add_expert_review(**data)}


@router.get("/admin/stats", dependencies=[Depends(require_staff)])
def stats(repo: InteractionRepository = Depends(get_repository)):
    return repo.stats()


@router.get("/officer/answers", dependencies=[Depends(require_staff)])
def officer_answers(unreviewed: bool = True, limit: int = 50,
                    repo: InteractionRepository = Depends(get_repository)):
    return repo.list_answers(unreviewed=unreviewed, limit=min(max(limit, 1), 200))


@router.get("/officer/answers/{answer_id}", dependencies=[Depends(require_staff)])
def officer_answer(answer_id: int, repo: InteractionRepository = Depends(get_repository)):
    row = repo.get_answer(answer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown answer_id")
    return row