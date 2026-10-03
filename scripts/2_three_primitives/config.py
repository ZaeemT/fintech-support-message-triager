"""All settings in one place: model, endpoint, and the four triage questions.

Wording here is the main control surface. Keep it in sync with docs/definitions.md.
"""

from typesafe_sdk import Choice, Noul, Score

# Route: OpenRouter (unofficial). The response reported "typesafe/jev-1.13-20260917";
# whether this name stays on that build is still an open question (see docs/notes.md).
MODEL = "typesafe/jev-1.13"
BASE_URL = "https://openrouter.ai/api"
API_KEY_ENV = "OPENROUTER_API_KEY"
INPUT_PRICE_PER_MILLION_USD = 0.042  # jev-1.13.0, docs.typesafe.ai/models, 2026-10-03; output tokens free

# Evaluation: frozen dataset v1 (commit 7da39c6). `git hash-object data/messages.csv` must match.
DATASET_BLOB = "539405fa5999f6be063f750c5f81abbf307e7c11"
NOUL_THRESHOLDS = [0.3, 0.5, 0.7, 0.9]

CATEGORY_LABELS: dict[str, str] = {
    "unauthorized_charge": "Customer reports a charge, transfer or withdrawal they did not make or approve, including charges after they cancelled.",
    "billing_question": "Fees, statements, refunds, or a charge the customer made but disputes (double charge, wrong amount).",
    "account_access": "Can't log in, locked out, password or 2FA reset, or login details changed by someone else.",
    "card_issue": "Problem with the card itself: lost, stolen, blocked, declined, damaged, not arrived, activation or PIN.",
    "other": "Anything else.",
}

# Ordered low to high; position is the score level (0, 1, 2).
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
