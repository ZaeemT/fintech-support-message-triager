# Fintech Support Message Triager

A small API that reads a customer support message and decides what should happen to it: answer it automatically, put it in a review queue, or escalate it to a person now. It is built on **Jev**, TypeSafe AI's System One model, as a hands-on learning project.

> **Learning project.** All data is synthetic. It is not suitable for real fraud, compliance or credit decisions.

## The problem

A fintech support inbox mixes very different messages:

- "Someone took $480 out of my account last night."
- "How do I download last month's statement?"
- "locked out"

Some can be answered from the help center. Others involve money leaving an account right now. Triage has to get two kinds of error right:

- **Missing a risky message** (suspected fraud, an account takeover) means money is lost while it waits in a queue.
- **Escalating everything** buries the people who handle the real cases.

Messages are also messy: very short, sarcastic, written in non-native English, mentioning "fraud" without being about it, or covering two issues at once. Keyword rules alone miss most of this, and a model alone can fail or be wrong with no warning.

## The solution

Each message gets one request to Jev with four typed questions. Each answer comes back with probabilities, not just a label:

| Question | Type | Answer |
|---|---|---|
| `category` | choice | `unauthorized_charge`, `billing_question`, `account_access`, `card_issue` or `other`, with a probability per label |
| `urgency` | score | 0 low, 1 medium, 2 high, as a probability-weighted score |
| `fraud_related` | noul (yes/no) | probability the customer suspects someone else used their account, card or money |
| `needs_human` | noul (yes/no) | probability a person should handle it rather than an automated reply |

The answers then go through a **routing layer** that picks one action. Deterministic rules run first and work even when the model call fails:

1. **Backstop rules (no model needed):**
   - model call failed → `review`
   - fraud keywords such as "unauthorized", "stolen" or "hacked" → `escalate`
   - three words or fewer → `review`
2. **Model thresholds:**
   - `fraud_related` ≥ 0.25 → `escalate`
   - urgency most likely high → `escalate`
   - `needs_human` ≥ 0.20 → `review`
   - category confidence < 0.5 → `review`
3. Otherwise → `auto_handle`.

The most severe action wins, and every rule that fired is returned as a reason. The thresholds were chosen from an evaluation on 50 hand-labeled synthetic messages, set to catch every message that needed a person (see `docs/notes.md`). Exact label and question definitions are in `docs/definitions.md`.

## The triage API

`POST /v1/triage/`

Request:

```json
{ "message": "unknown charge $73" }
```

The message must be 1 to 2,000 characters after trimming whitespace; otherwise the API returns `422`.

Response (illustrative; answer values taken from an evaluation run of Jev 1.13):

```json
{
  "success": true,
  "message": "Message triaged",
  "data": {
    "action": "escalate",
    "reasons": ["very short (3 words)", "fraud_related 0.37 >= 0.25", "needs_human 0.9 >= 0.2"],
    "model_ok": true,
    "model_error": null,
    "model": "typesafe/jev-1.13-20260917",
    "answers": {
      "category": {
        "label": "unauthorized_charge",
        "confidence": 0.96,
        "probabilities": {"unauthorized_charge": 0.97, "billing_question": 0.03, "account_access": 0, "card_issue": 0, "other": 0}
      },
      "urgency": {"score": 1.15, "most_likely_level": 1, "confidence": 0.77, "probabilities": {"0": 0, "1": 0.85, "2": 0.15}},
      "fraud_related": 0.37,
      "needs_human": 0.9
    },
    "latency_ms": 364,
    "disclaimer": "Learning project. Not suitable for real fraud, compliance or credit decisions."
  },
  "status_code": 200
}
```

How it behaves:

- **If Jev fails** (timeout, rate limit, bad response), the API still answers with HTTP 200, `model_ok: false` and `answers: null`. The action then comes from the backstop rules only: `review`, or `escalate` on a fraud keyword. There are no retries and no made-up model values.
- **`model`** reports the model version that actually answered.
- **The message text is never logged.** Only the action, whether the model answered, and latency are.

## Run it locally

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), and an [OpenRouter](https://openrouter.ai) API key with some credit. Jev is reached through OpenRouter.

```bash
git clone <repository-url> fintech-support-message-triager
cd fintech-support-message-triager

uv sync                      # creates .venv and installs dependencies
cp .env.example .env         # then edit .env
```

In `.env`:

- Set `OPENROUTER_API_KEY` to your key. The app will not start without it.
- `MONGO_URI`, `DB_NAME` and `JWT_SECRET` must have values. They come from the FastAPI boilerplate this app is built on. The example values are fine, and the triage endpoint does not need a running MongoDB.

Never commit `.env`; it is already in `.gitignore`.

Start the server:

```bash
uv run fastapi dev app/main.py
```

Try it:

```bash
curl -X POST http://localhost:8000/v1/triage/ \
  -H 'Content-Type: application/json' \
  -d '{"message": "Someone used my card at a gas station 300 miles away."}'
```

Interactive API docs: <http://localhost:8000/docs>

Run the tests (no API calls, no database):

```bash
uv run pytest
```
