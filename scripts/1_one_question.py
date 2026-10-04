"""Step 2: one hardcoded message, one noul question, print the raw response."""

import os
from dotenv import load_dotenv
from typesafe_sdk import Noul, RetryPolicy, TypeSafeClient

MODEL = "typesafe/jev-1.13"  # pinned version, never an alias

# Synthetic message: invented, no real customer data.
# MESSAGE = "I see a $249.99 charge from an electronics store I've never shopped at. I didn't make this purchase."
# MESSAGE = "How do I download last month's statement as a PDF?"
MESSAGE =  "There's a $12.00 charge I don't recognize. Maybe my partner used my card, not sure."

def main() -> None:
    load_dotenv(
        dotenv_path=".env"
    ) 

    with TypeSafeClient(api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api", retry=RetryPolicy(max_retries=0)) as client:
        response = client.system_one(
            state=MESSAGE,
            questions={
                "fraud_related": Noul(instructions="Does this message report suspected fraud or an unauthorized transaction?"),
            },
            model=MODEL,
        )
    # response.request_id raises when the header is missing (OpenRouter doesn't forward it)
    print("request id:", response.raw_http_response.headers.get("x-typesafe-request-id"))
    print(response.raw_http_response.text)


if __name__ == "__main__":
    main()
