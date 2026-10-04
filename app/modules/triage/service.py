import logging
import time

from typesafe_sdk import AsyncTypeSafeClient, TypeSafeError

from ...core.responses import ServiceResponse
from .config import MODEL, QUESTIONS
from .dto import AnswersDto, CategoryDto, TriageResultDto, UrgencyDto
from .model import TriageResult
from .routing import route

logger = logging.getLogger(__name__)


class TriageService:
    def __init__(self, client: AsyncTypeSafeClient) -> None:
        self.client = client

    async def triage(self, message: str) -> ServiceResponse:
        start = time.perf_counter()
        result: TriageResult | None = None
        model_error: str | None = None
        try:
            result = await self.client.system_one(state=message, questions=QUESTIONS, model=MODEL, response_model=TriageResult)
        except TypeSafeError as error:
            # No retry, no hidden fallback value: route() sends the message to a human instead.
            model_error = type(error).__name__
            logger.warning("Jev call failed (%s); routing with deterministic backstop only", model_error)

        action, reasons = route(message, result)
        latency_ms = round((time.perf_counter() - start) * 1000)
        # Never log the message text: anything sent here is treated as sensitive.
        logger.info("triage action=%s model_ok=%s latency_ms=%d", action, result is not None, latency_ms)

        data = TriageResultDto(
            action=action,
            reasons=reasons,
            model_ok=result is not None,
            model_error=model_error,
            model=result.model if result else None,
            answers=self._answers(result) if result else None,
            latency_ms=latency_ms,
        )
        return ServiceResponse(success=True, message="Message triaged", data=data.model_dump())

    @staticmethod
    def _answers(result: TriageResult) -> AnswersDto:
        urgency = result.urgency.probabilities
        return AnswersDto(
            category=CategoryDto(label=result.category.choice, confidence=result.category.confidence, probabilities=result.category.probabilities),
            urgency=UrgencyDto(
                score=result.urgency.score,
                most_likely_level=max(urgency, key=lambda level: urgency[level]),
                confidence=result.urgency.confidence,
                probabilities=urgency,
            ),
            fraud_related=result.fraud_related.noul,
            needs_human=result.needs_human.noul,
        )
