from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field

from .config import MAX_MESSAGE_CHARS
from .routing import Action


class TriageRequestDto(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_CHARS, description="Customer support message (synthetic data only)")]


class CategoryDto(BaseModel):
    label: str
    confidence: float
    probabilities: dict[str, float]


class UrgencyDto(BaseModel):
    score: Annotated[float, Field(description="Probability-weighted level: 0 low, 1 medium, 2 high")]
    most_likely_level: int
    confidence: float
    probabilities: dict[int, float]


class AnswersDto(BaseModel):
    category: CategoryDto
    urgency: UrgencyDto
    fraud_related: Annotated[float, Field(description="Probability the customer suspects third-party misuse")]
    needs_human: Annotated[float, Field(description="Probability a human should handle this")]


class TriageResultDto(BaseModel):
    action: Action
    reasons: list[str]
    model_ok: Annotated[bool, Field(description="False when Jev failed; the action then comes from the deterministic backstop only")]
    model_error: Optional[str] = None
    model: Optional[str] = None
    answers: Optional[AnswersDto] = None
    latency_ms: int
    disclaimer: str = "Learning project. Not suitable for real fraud, compliance or credit decisions."
