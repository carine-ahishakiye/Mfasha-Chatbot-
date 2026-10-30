"""Request bodies of the JSON endpoints."""
from typing import Literal, Optional

from pydantic import BaseModel


class AskBody(BaseModel):
    question: str = ""


class SpeakBody(BaseModel):
    text: str = ""


class FeedbackBody(BaseModel):
    question: str = ""
    passage_id: Optional[str] = None
    vote: Literal["helpful", "not_helpful"]
