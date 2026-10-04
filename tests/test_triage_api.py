"""Tests for POST /v1/triage. No API calls and no MongoDB: Jev is faked, the app lifespan never runs."""

import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# Settings require these; dummy values are enough because the lifespan (DB connect) is not run.
os.environ.setdefault("MONGO_URI", "mongodb://unused")
os.environ.setdefault("DB_NAME", "unused")
os.environ.setdefault("JWT_SECRET", "unused")

from fastapi.testclient import TestClient  # noqa: E402
from typesafe_sdk import TypeSafeError  # noqa: E402

from app.main import app  # noqa: E402
from app.modules.triage import config as app_config  # noqa: E402
from app.modules.triage.controller import get_triage_service  # noqa: E402
from app.modules.triage.model import TriageResult  # noqa: E402
from app.modules.triage.routing import route as app_route  # noqa: E402
from app.modules.triage.service import TriageService  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JEV_RUN = ROOT / "data" / "runs" / "2026-10-03T125726Z_typesafe_jev-1.13.json"


def fake_result(fraud: float = 0.02, human: float = 0.05) -> TriageResult:
    answers = {
        "category": {"type": "choice", "choice": "other", "confidence": 0.95, "probabilities": {"other": 0.96, "billing_question": 0.04}},
        "urgency": {"type": "score", "score": 0.1, "confidence": 0.8, "legend": {"0": "low", "1": "medium", "2": "high"}, "probabilities": {"0": 0.9, "1": 0.1, "2": 0.0}},
        "fraud_related": {"type": "noul", "noul": fraud},
        "needs_human": {"type": "noul", "noul": human},
    }
    body = {"model": "fake-jev", "usage": {"input_tokens": 1, "output_tokens": 1}, "answers": answers} | answers
    return TriageResult.model_validate_json(json.dumps(body))


class FakeJev:
    """Stands in for AsyncTypeSafeClient: returns a fixed result or raises."""

    def __init__(self, result: TriageResult | None = None, error: Exception | None = None) -> None:
        self.result, self.error = result, error

    async def system_one(self, **kwargs: object) -> TriageResult:
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


@pytest.fixture
def client_with():
    """Returns a TestClient whose triage service uses the given fake Jev."""

    def make(fake: FakeJev) -> TestClient:
        app.dependency_overrides[get_triage_service] = lambda: TriageService(fake)  # type: ignore[arg-type]
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


QUIET = "How long does a refund take to appear on my statement?"


def test_low_risk_message_is_auto_handled(client_with):
    response = client_with(FakeJev(result=fake_result())).post("/v1/triage/", json={"message": QUIET})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["action"] == "auto_handle"
    assert data["model_ok"] is True
    assert data["model"] == "fake-jev"
    assert data["answers"]["category"]["label"] == "other"
    assert data["answers"]["urgency"]["most_likely_level"] == 0


def test_model_failure_still_answers_via_backstop(client_with):
    response = client_with(FakeJev(error=TypeSafeError("boom"))).post("/v1/triage/", json={"message": QUIET})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["action"] == "review"
    assert data["model_ok"] is False
    assert data["model_error"] == "TypeSafeError"
    assert data["answers"] is None


def test_model_failure_with_keyword_escalates(client_with):
    response = client_with(FakeJev(error=TypeSafeError("boom"))).post("/v1/triage/", json={"message": "My card was stolen and someone used it"})
    assert response.json()["data"]["action"] == "escalate"


def test_high_fraud_probability_escalates(client_with):
    response = client_with(FakeJev(result=fake_result(fraud=0.9))).post("/v1/triage/", json={"message": QUIET})
    assert response.json()["data"]["action"] == "escalate"


@pytest.mark.parametrize("message", ["", "   ", "x" * (app_config.MAX_MESSAGE_CHARS + 1)])
def test_invalid_message_is_rejected(client_with, message):
    response = client_with(FakeJev(result=fake_result())).post("/v1/triage/", json={"message": message})
    assert response.status_code == 422


def _load_scripts_config():
    path = ROOT / "scripts" / "2_three_primitives" / "config.py"
    spec = importlib.util.spec_from_file_location("scripts_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_app_config_matches_evaluated_config():
    """The API must ask exactly what the evaluation measured, with the same thresholds."""
    evaluated = _load_scripts_config()
    for name in ["MODEL", "NEEDS_HUMAN_THRESHOLD", "FRAUD_ESCALATE_THRESHOLD", "CATEGORY_MIN_CONFIDENCE", "SHORT_MESSAGE_MAX_WORDS", "ESCALATE_KEYWORDS"]:
        assert getattr(app_config, name) == getattr(evaluated, name), name
    assert {k: q.model_dump() for k, q in app_config.QUESTIONS.items()} == {k: q.model_dump() for k, q in evaluated.QUESTIONS.items()}


@pytest.mark.skipif(not JEV_RUN.exists(), reason="saved Jev run not present")
def test_app_routing_matches_evaluated_routing_on_saved_run():
    """Replay all 50 saved Jev answers through both route() copies: same action and reasons every time."""
    sys.path.insert(0, str(ROOT / "scripts"))
    scripts_routing = importlib.import_module("5_routing")
    for row in json.loads(JEV_RUN.read_text())["results"]:
        saved = scripts_routing.from_saved(row)
        app_result = TriageResult.model_validate_json(saved.model_dump_json()) if saved else None
        assert app_route(row["message"], app_result) == scripts_routing.route(row["message"], saved), row["id"]
