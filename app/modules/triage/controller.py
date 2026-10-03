from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request

from ...core.responses import ServiceResponse
from .dto import TriageRequestDto
from .service import TriageService

router = APIRouter()


def get_triage_service(request: Request) -> TriageService:
    """Dependency to get TriageService with the shared Jev client created at startup"""
    return TriageService(request.app.state.jev_client)


@router.post("/")
async def triage_message(body: Annotated[TriageRequestDto, Body()], triage_service: TriageService = Depends(get_triage_service)) -> ServiceResponse:
    return await triage_service.triage(body.message)
