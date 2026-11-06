"""HTTP endpoints. Thin on purpose: validate, call the pipeline, log, shape the response."""
from __future__ import annotations

import base64
import secrets

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile

from mfasha import __version__
from mfasha.api.schemas import AskResponse, ExpertReviewIn, FeedbackIn, HealthResponse, TextQuestion
from mfasha.domain.models import PipelineResult
from mfasha.storage.repository import InteractionRepository

router = APIRouter()


#  dependencies 
def get_pipeline(request: Request):
    return request.app.state.pipeline


def get_repository(request: Request) -> InteractionRepository:
    return request.app.state.repository


def require_api_key(request: Request, x_api_key: str = Header(default="")) -> None:
    """Officer and administrator endpoints. Disabled completely when no key is configured."""
    expected = request.app.state.settings.api_key
    if not expected:
        raise HTTPException(status_code=503, detail="officer/admin endpoints are disabled: set MFASHA_API_KEY")
    if not secrets.compare_digest(x_api_key, expected):   # constant-time comparison
        raise HTTPException(status_code=401, detail="invalid API key")


def _to_response(result: PipelineResult, answer_id: int) -> AskResponse:
    data = result.to_dict(include_audio=True)
    audio = data.pop("audio", None)
    return AskResponse(answer_id=answer_id, audio_base64=base64.b64encode(audio).decode() if audio else None, **data)


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
    result = pipeline.ask_text(body.question, with_audio=body.with_audio)
    return _to_response(result, repo.log_interaction(result, "text", _components(request)))


@router.post("/ask/voice", response_model=AskResponse)
async def ask_voice(request: Request, audio: UploadFile = File(...), with_audio: bool = Form(False),
                    pipeline=Depends(get_pipeline), repo: InteractionRepository = Depends(get_repository)):
    settings = request.app.state.settings
    data = await audio.read(settings.max_audio_bytes + 1)       # never read more than the limit allows
    if len(data) > settings.max_audio_bytes:
        raise HTTPException(status_code=413, detail="audio file is too large")
    result = pipeline.ask_audio(data, with_audio=with_audio, max_seconds=settings.max_audio_seconds)
    return _to_response(result, repo.log_interaction(result, "voice", _components(request)))


@router.post("/feedback", status_code=201)
def feedback(body: FeedbackIn, repo: InteractionRepository = Depends(get_repository)):
    if not repo.answer_exists(body.answer_id):
        raise HTTPException(status_code=404, detail="unknown answer_id")
    return {"feedback_id": repo.add_feedback(body.answer_id, body.rating, body.is_useful, body.comment)}


# officer and administrator endpoints 
@router.post("/officer/reviews", status_code=201, dependencies=[Depends(require_api_key)])
def officer_review(body: ExpertReviewIn, repo: InteractionRepository = Depends(get_repository)):
    if not repo.answer_exists(body.answer_id):
        raise HTTPException(status_code=404, detail="unknown answer_id")
    return {"review_id": repo.add_expert_review(**body.model_dump())}


@router.get("/admin/stats", dependencies=[Depends(require_api_key)])
def stats(repo: InteractionRepository = Depends(get_repository)):
    return repo.stats()


@router.get("/officer/answers", dependencies=[Depends(require_api_key)])
def officer_answers(unreviewed: bool = True, limit: int = 50,
                    repo: InteractionRepository = Depends(get_repository)):
    return repo.list_answers(unreviewed=unreviewed, limit=min(max(limit, 1), 200))


@router.get("/officer/answers/{answer_id}", dependencies=[Depends(require_api_key)])
def officer_answer(answer_id: int, repo: InteractionRepository = Depends(get_repository)):
    row = repo.get_answer(answer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown answer_id")
    return row