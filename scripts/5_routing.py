"""Step 7: route a triaged message to auto_handle / review / escalate.

    uv run scripts/5_routing.py data/runs/<run>.json   # replay a saved run through route(), no API calls

Deterministic rules run first and work even when Jev failed. Model-based rules come after.
The most severe action that fires wins; every rule that fired is returned as a reason.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent / "2_three_primitives"))  # folder name can't be imported as a package

from config import (  # noqa: E402
    CATEGORY_MIN_CONFIDENCE,
    ESCALATE_KEYWORDS,
    FRAUD_ESCALATE_THRESHOLD,
    NEEDS_HUMAN_THRESHOLD,
    SHORT_MESSAGE_MAX_WORDS,
)
from triager import TriageResponse  # noqa: E402

Action = Literal["auto_handle", "review", "escalate"]
SEVERITY: dict[Action, int] = {"auto_handle": 0, "review": 1, "escalate": 2}


def route(message: str, result: TriageResponse | None, use_rules: bool = True) -> tuple[Action, list[str]]:
    """Pick an action for one message. `result` is None when the Jev call failed."""
    fired: list[tuple[Action, str]] = []

    # 1. Deterministic backstop: does not trust or need the model.
    if use_rules:
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
    elif not use_rules:
        # Model-only mode has no fallback for failed calls; recorded so the comparison stays honest.
        fired.append(("auto_handle", "model call failed, no backstop"))

    if not fired:
        return "auto_handle", ["no rule fired"]
    action = max((a for a, _ in fired), key=lambda a: SEVERITY[a])
    return action, [reason for _, reason in fired]


def from_saved(result: dict[str, Any]) -> TriageResponse | None:
    """Rebuild the typed response from a saved run row (same JSON decoding the SDK uses)."""
    if "error" in result:
        return None
    body = {"model": result["model"], "usage": {"input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"]}}
    # The SDK lifts each named answer to a top-level field; do the same here.
    return TriageResponse.model_validate_json(json.dumps(body | {"answers": result["answers"]} | result["answers"]))


def replay(path: Path) -> None:
    record = json.loads(path.read_text())
    rows = record["results"]
    print(f"Run: {path.name}   model: {', '.join(record['reported_models'])}   dataset blob: {record['dataset']['git_blob'][:7]}")

    for use_rules in (False, True):
        decisions = [(r, *route(r["message"], from_saved(r), use_rules=use_rules)) for r in rows]
        counts = Counter(action for _, action, _ in decisions)
        # The dangerous error: a message that needed a person was auto-handled.
        unsafe = [(r, reasons) for r, action, reasons in decisions if action == "auto_handle" and (r["expected"]["needs_human"] or r["expected"]["fraud_related"])]
        # The costly error: a message that needed no person was sent to one.
        extra_work = [r for r, action, _ in decisions if action != "auto_handle" and not r["expected"]["needs_human"] and not r["expected"]["fraud_related"]]
        missed_fraud = [r for r, action, _ in decisions if r["expected"]["fraud_related"] and action != "escalate"]

        print(f"\n{'MODEL + RULES' if use_rules else 'MODEL ONLY'}")
        print(f"  auto_handle {counts['auto_handle']}   review {counts['review']}   escalate {counts['escalate']}")
        print(f"  unsafe auto-handles (needed a person): {len(unsafe)}")
        for r, reasons in unsafe:
            print(f"    id {r['id']:>2}  \"{r['message']}\"  ({'; '.join(reasons)})")
        print(f"  fraud cases not escalated: {len(missed_fraud)}  {[r['id'] for r in missed_fraud]}")
        print(f"  extra human work (needed no person): {len(extra_work)}  {[r['id'] for r in extra_work]}")

    print("\nDecisions with rules (id, action, reasons):")
    for r in rows:
        action, reasons = route(r["message"], from_saved(r))
        print(f"  {r['id']:>2}  {action:<11}  {'; '.join(reasons)}")


if __name__ == "__main__":
    replay(Path(sys.argv[1]))
