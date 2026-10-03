"""Step 3: triage one message with all four questions in a single request."""

import os

from dotenv import load_dotenv
from typesafe_sdk import ChoiceAnswer, NoulAnswer, RetryPolicy, ScoreAnswer, SystemOneResponse, TypeSafeClient

from config import API_KEY_ENV, BASE_URL, MODEL, QUESTIONS


class TriageResponse(SystemOneResponse):
    """Typed view of the response: the SDK copies each named answer into its field.

    A missing answer or wrong answer type raises TypeSafeAPIResponseValidationError.
    """

    category: ChoiceAnswer
    urgency: ScoreAnswer
    fraud_related: NoulAnswer
    needs_human: NoulAnswer


def make_client() -> TypeSafeClient:
    load_dotenv()
    # Retries off while learning, so errors show up instead of being retried silently.
    return TypeSafeClient(api_key=os.getenv(API_KEY_ENV), base_url=BASE_URL, retry=RetryPolicy(max_retries=0))


def triage(message: str, client: TypeSafeClient) -> TriageResponse:
    """Ask all four questions about one message in one request."""
    return client.system_one(state=message, questions=QUESTIONS, model=MODEL, response_model=TriageResponse)


def main() -> None:
    # Synthetic message: invented, no real customer data.
    message = "There's a $12.00 charge I don't recognize. Maybe my partner used my card, not sure."
    with make_client() as client:
        result = triage(message, client)

    print("raw:", result.raw_http_response.text)
    print()
    print("model:        ", result.model)
    print("category:     ", result.category.choice, f"(confidence {result.category.confidence})", result.category.probabilities)
    print("urgency:      ", result.urgency.score, f"(confidence {result.urgency.confidence})", result.urgency.probabilities)
    print("fraud_related:", result.fraud_related.noul)
    print("needs_human:  ", result.needs_human.noul)


if __name__ == "__main__":
    main()
