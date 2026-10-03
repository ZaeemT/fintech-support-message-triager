"""Triage settings for the API: model, question wording, routing thresholds and keywords.

Copied from scripts/2_three_primitives/config.py, which is what the evaluation runs measured.
tests/test_triage_api.py fails if the two drift apart: change both together, then re-run the evaluation.
"""

from typesafe_sdk import Choice, Noul, Score

# Pinned via OpenRouter; responses report "typesafe/jev-1.13-20260917" (see docs/notes.md).
MODEL = "typesafe/jev-1.13"

MAX_MESSAGE_CHARS = 2000  # bounds cost per call; well inside Jev's 32k state limit

# Routing (step 7). Chosen from run 2026-10-03T125726Z on dataset v1; see docs/notes.md.
NEEDS_HUMAN_THRESHOLD = 0.20
FRAUD_ESCALATE_THRESHOLD = 0.25
CATEGORY_MIN_CONFIDENCE = 0.5
SHORT_MESSAGE_MAX_WORDS = 3
ESCALATE_KEYWORDS = [
    "fraud",
    "unauthorized",
    "unauthorised",
    "not authorize",
    "didn't make",
    "did not make",
    "never do this payment",
    "stolen",
    "hacked",
    "scam",
    "someone used",
    "someone took",
    "someone changed",
    "lost my card",
]

CATEGORY_LABELS: dict[str, str] = {
    "unauthorized_charge": "Customer reports a charge, transfer or withdrawal they did not make or approve, including charges after they cancelled.",
    "billing_question": "Fees, statements, refunds, or a charge the customer made but disputes (double charge, wrong amount).",
    "account_access": "Can't log in, locked out, password or 2FA reset, or login details changed by someone else.",
    "card_issue": "Problem with the card itself: lost, stolen, blocked, declined, damaged, not arrived, activation or PIN.",
    "other": "Anything else.",
}

URGENCY_LEVELS: list[str] = [
    "Low: no time pressure, nothing at risk.",
    "Medium: customer is blocked or money is in question, but there is no ongoing loss.",
    "High: money may be actively leaving or account control may be compromised; needs action today.",
]

QUESTIONS = {
    "category": Choice(
        instructions="What is this customer support message mainly about?",
        criteria=CATEGORY_LABELS,
    ),
    "urgency": Score(
        instructions="How urgently does this customer support message need a response?",
        criteria=URGENCY_LEVELS,
    ),
    "fraud_related": Noul(
        instructions="Does the customer suspect someone else used their account, card or money without permission?",
        criteria={
            "true": "The customer says or implies a third party made a transaction, accessed the account, or scammed them.",
            "false": (
                "The customer recognizes all activity; it is a billing error, a fee, or a general question. "
                "Also no: an attempt with no loss, exposure without misuse (e.g. a stolen card with no charges), or a weak hunch."
            ),
        },
    ),
    "needs_human": Noul(
        instructions="Should a human support agent handle this message rather than an automated reply?",
        criteria={
            "true": "A dispute, suspected fraud, a lockout, a distressed customer, or anything needing account investigation or judgment.",
            "false": "Fully answerable with standard help-center information.",
        },
    ),
}
