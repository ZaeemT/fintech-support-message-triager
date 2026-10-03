"""All settings in one place: model, endpoint, and the four triage questions.

Wording here is the main control surface. Keep it in sync with docs/definitions.md.
"""

from typesafe_sdk import Choice, Noul, Score

# Route: OpenRouter (unofficial). The response reported "typesafe/jev-1.13-20260917";
# whether this name stays on that build is still an open question (see docs/notes.md).
MODEL = "typesafe/jev-1.13"
BASE_URL = "https://openrouter.ai/api"
API_KEY_ENV = "OPENROUTER_API_KEY"

CATEGORY_LABELS: dict[str, str] = {
    "unauthorized_charge": "Customer reports a charge, transfer or withdrawal they say they did not make or approve.",
    "billing_question": "Fees, statements, refunds, or a charge the customer recognizes but disputes (double charge, wrong amount).",
    "account_access": "Can't log in, locked out, password or 2FA reset, or login details changed by someone else.",
    "feature_request": "Asks for a product capability or change that doesn't exist today.",
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
            "false": "The customer recognizes all activity; it is a billing error, a fee, or a general question.",
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
