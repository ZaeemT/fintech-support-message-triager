"""Deterministic backstop + model thresholds -> auto_handle / review / escalate.

Same logic as scripts/5_routing.py (the version that was replayed and tested); keep them in sync.
"""

from typing import Literal

from .config import (
    CATEGORY_MIN_CONFIDENCE,
    ESCALATE_KEYWORDS,
    FRAUD_ESCALATE_THRESHOLD,
    NEEDS_HUMAN_THRESHOLD,
    SHORT_MESSAGE_MAX_WORDS,
)
from .model import TriageResult

Action = Literal["auto_handle", "review", "escalate"]
SEVERITY: dict[Action, int] = {"auto_handle": 0, "review": 1, "escalate": 2}


def route(message: str, result: TriageResult | None) -> tuple[Action, list[str]]:
    """Pick an action for one message. `result` is None when the Jev call failed."""
    fired: list[tuple[Action, str]] = []

    # 1. Deterministic backstop: does not trust or need the model.
    text = message.lower()
    if result is None:
        fired.append(("review", "model call failed"))
    if hits := [k for k in ESCALATE_KEYWORDS if k in text]:
        fired.append(("escalate", f"keyword: {', '.join(hits)}"))
    if len(message.split()) <= SHORT_MESSAGE_MAX_WORDS:
        fired.append(("review", f"very short ({len(message.split())} words)"))

    # 2. Model-based rules.
    if result is not None:
        if result.fraud_related.noul >= FRAUD_ESCALATE_THRESHOLD:
            fired.append(("escalate", f"fraud_related {result.fraud_related.noul} >= {FRAUD_ESCALATE_THRESHOLD}"))
        urgency_level = max(result.urgency.probabilities, key=lambda level: result.urgency.probabilities[level])
        if urgency_level == 2:
            fired.append(("escalate", f"urgency most likely high (score {result.urgency.score})"))
        if result.needs_human.noul >= NEEDS_HUMAN_THRESHOLD:
            fired.append(("review", f"needs_human {result.needs_human.noul} >= {NEEDS_HUMAN_THRESHOLD}"))
        if result.category.confidence < CATEGORY_MIN_CONFIDENCE:
            fired.append(("review", f"category confidence {result.category.confidence} < {CATEGORY_MIN_CONFIDENCE}"))

    if not fired:
        return "auto_handle", ["no rule fired"]
    action = max((a for a, _ in fired), key=lambda a: SEVERITY[a])
    return action, [reason for _, reason in fired]
