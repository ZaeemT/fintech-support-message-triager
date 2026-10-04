from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy
from app.core.config import get_settings

# Jev is reached through OpenRouter (unofficial route); see docs/notes.md, step 2.
JEV_BASE_URL = "https://openrouter.ai/api"


def create_jev_client() -> AsyncTypeSafeClient:
    """
    Create the async Jev client using the OpenRouter API key from settings.
    One client is created at startup and shared, so connections are reused.
    """
    settings = get_settings()

    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set in the environment variables.")

    # Retries off: a failed call goes to the deterministic backstop instead of being retried silently.
    return AsyncTypeSafeClient(api_key=settings.OPENROUTER_API_KEY, base_url=JEV_BASE_URL, retry=RetryPolicy(max_retries=0))
