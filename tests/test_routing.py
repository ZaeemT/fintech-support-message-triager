"""Tests for route(): the safety-critical layer, so every rule gets a case. No API calls."""

import importlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
routing = importlib.import_module("5_routing")  # module name starts with a digit


def fake_result(fraud: float = 0.02, human: float = 0.05, urgency_high: float = 0.0, category_confidence: float = 0.95):
    """A typed TriageResponse with low-risk defaults; override one value per test."""
    answers = {
        "category": {"type": "choice", "choice": "other", "confidence": category_confidence, "probabilities": {"other": 0.96, "billing_question": 0.04}},
        "urgency": {"type": "score", "score": 0.1, "confidence": 0.8, "legend": {"0": "low", "1": "medium", "2": "high"},
                    "probabilities": {"0": 0.9 - urgency_high, "1": 0.1, "2": urgency_high}},
        "fraud_related": {"type": "noul", "noul": fraud},
        "needs_human": {"type": "noul", "noul": human},
    }
    body = {"model": "fake", "usage": {"input_tokens": 1, "output_tokens": 1}, "answers": answers} | answers
    return routing.TriageResponse.model_validate_json(json.dumps(body))


QUIET = "How long does a refund take to appear on my statement?"


def test_low_risk_message_is_auto_handled():
    assert routing.route(QUIET, fake_result())[0] == "auto_handle"


def test_failed_model_call_goes_to_review():
    action, reasons = routing.route(QUIET, None)
    assert action == "review"
    assert "model call failed" in reasons


def test_keyword_escalates_even_when_model_says_low_risk():
    action, reasons = routing.route("I think this is FRAUD, please check", fake_result())
    assert action == "escalate"
    assert any(r.startswith("keyword") for r in reasons)


def test_keyword_escalates_when_model_call_failed():
    assert routing.route("My card was stolen yesterday", None)[0] == "escalate"


def test_very_short_message_goes_to_review():
    assert routing.route("card declined", fake_result())[0] == "review"


def test_fraud_probability_at_threshold_escalates():
    assert routing.route(QUIET, fake_result(fraud=routing.FRAUD_ESCALATE_THRESHOLD))[0] == "escalate"


def test_high_urgency_escalates():
    assert routing.route(QUIET, fake_result(urgency_high=0.85))[0] == "escalate"


def test_needs_human_at_threshold_goes_to_review():
    assert routing.route(QUIET, fake_result(human=routing.NEEDS_HUMAN_THRESHOLD))[0] == "review"


def test_needs_human_just_below_threshold_is_auto_handled():
    assert routing.route(QUIET, fake_result(human=routing.NEEDS_HUMAN_THRESHOLD - 0.01))[0] == "auto_handle"


def test_low_category_confidence_goes_to_review():
    assert routing.route(QUIET, fake_result(category_confidence=0.3))[0] == "review"


def test_most_severe_action_wins_and_all_reasons_are_kept():
    action, reasons = routing.route(QUIET, fake_result(fraud=0.9, human=0.9))
    assert action == "escalate"
    assert len(reasons) == 2


def test_model_only_mode_ignores_keywords():
    assert routing.route("I think this is fraud, please check", fake_result(), use_rules=False)[0] == "auto_handle"
