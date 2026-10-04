"""Step 8: LLM baseline. Same questions and definitions as Jev, asked to an LLM with structured JSON output.

    uv run scripts/6_llm_baseline.py            # call the LLM for every message, save a run file

The run file uses the same format as Jev runs, so the same harness reports it:

    uv run scripts/3_evaluate.py data/runs/<run>.json
    uv run scripts/4_calibration.py data/runs/<run>.json
    uv run scripts/5_routing.py data/runs/<run>.json
"""

import csv
import importlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent / "2_three_primitives"))  # folder name can't be imported as a package

from config import API_KEY_ENV, CATEGORY_LABELS, DATASET_BLOB, LLM_MAX_TOKENS, LLM_MODEL, LLM_URL, QUESTIONS, URGENCY_LEVELS  # noqa: E402

evaluate = importlib.import_module("3_evaluate")  # reuse the dataset freeze check and paths


class LLMAnswer(BaseModel):
    """What a well-formed LLM reply must look like. Anything else counts as malformed."""

    model_config = ConfigDict(extra="forbid")

    category: Literal[tuple(CATEGORY_LABELS)]  # type: ignore[valid-type]
    urgency: Literal[0, 1, 2]
    fraud_related: float = Field(ge=0, le=1)
    needs_human: float = Field(ge=0, le=1)


# Ranges are not put in the schema (provider support varies); pydantic enforces them instead.
# No `enum` on urgency: with an integer enum, gemini-2.5-flash via OpenRouter silently returned `{}`
# for every message (tested 2026-10-03). LLMAnswer still rejects anything but 0/1/2 as malformed.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORY_LABELS)},
        "urgency": {"type": "integer", "description": "0, 1 or 2, as defined in the instructions."},
        "fraud_related": {"type": "number", "description": "Probability from 0 to 1 that the answer is yes."},
        "needs_human": {"type": "number", "description": "Probability from 0 to 1 that the answer is yes."},
    },
    "required": ["category", "urgency", "fraud_related", "needs_human"],
    "additionalProperties": False,
}


def system_prompt() -> str:
    """Build the prompt from the same config wording Jev receives, so both get identical definitions."""
    category, urgency = QUESTIONS["category"], QUESTIONS["urgency"]
    lines = [
        "You triage customer support messages for a fintech app. Answer four questions about the user's message.",
        "Reply only with JSON matching the schema.",
        "",
        f"category: {category.instructions} Pick exactly one label:",
        *[f"- {label}: {description}" for label, description in category.criteria.items()],
        "",
        f"urgency: {urgency.instructions} Pick one level:",
        *[f"- {level}: {description}" for level, description in enumerate(urgency.criteria)],
    ]
    for name in ("fraud_related", "needs_human"):
        question = QUESTIONS[name]
        lines += [
            "",
            f"{name}: {question.instructions} Give the probability from 0 to 1 that the answer is yes.",
            f"- Yes: {question.criteria['true']}",
            f"- No: {question.criteria['false']}",
        ]
    return "\n".join(lines)


SYSTEM_PROMPT = system_prompt()


def to_jev_answers(answer: LLMAnswer) -> dict[str, Any]:
    """Store LLM answers in Jev's answer shape. The LLM gives one label, so it gets probability 1.0."""
    return {
        "category": {
            "type": "choice",
            "choice": answer.category,
            "confidence": 1.0,
            "probabilities": {label: 1.0 if label == answer.category else 0.0 for label in CATEGORY_LABELS},
        },
        "urgency": {
            "type": "score",
            "score": float(answer.urgency),
            "confidence": 1.0,
            "legend": {str(level): text for level, text in enumerate(URGENCY_LEVELS)},
            "probabilities": {str(level): 1.0 if level == answer.urgency else 0.0 for level in range(len(URGENCY_LEVELS))},
        },
        "fraud_related": {"type": "noul", "noul": answer.fraud_related},
        "needs_human": {"type": "noul", "noul": answer.needs_human},
    }


def ask(client: httpx.Client, message: str) -> httpx.Response:
    return client.post(
        LLM_URL,
        json={
            "model": LLM_MODEL,
            "temperature": 0,
            "max_tokens": LLM_MAX_TOKENS,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": message}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "triage", "strict": True, "schema": RESPONSE_SCHEMA}},
        },
    )


def run() -> Path:
    evaluate.check_dataset_frozen()
    load_dotenv()
    with evaluate.DATASET.open() as f:
        rows = list(csv.DictReader(f))

    started = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    headers = {"Authorization": f"Bearer {os.getenv(API_KEY_ENV)}"}
    with httpx.Client(headers=headers, timeout=60) as client:
        for row in rows:
            result: dict[str, Any] = {
                "id": row["id"],
                "message": row["message"],
                "tags": row["tags"],
                "expected": {
                    "category": row["category"],
                    "urgency": int(row["urgency"]),
                    "fraud_related": int(row["fraud_related"]),
                    "needs_human": int(row["needs_human"]),
                },
            }
            start = time.perf_counter()
            try:
                response = ask(client, row["message"])
            except httpx.HTTPError as error:
                result |= {"error_kind": "api", "error": f"{type(error).__name__}: {error}"}
            else:
                latency = round(time.perf_counter() - start, 3)
                if response.is_error:
                    result |= {"error_kind": "api", "error": f"HTTP {response.status_code}: {response.text[:200]}"}
                else:
                    data = response.json()
                    content = data["choices"][0]["message"].get("content") or ""
                    usage = data.get("usage", {})
                    result |= {
                        "latency_s": latency,
                        "model": data.get("model", LLM_MODEL),
                        "input_tokens": usage.get("prompt_tokens"),
                        "output_tokens": usage.get("completion_tokens"),
                        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                        "cost_usd": usage.get("cost"),
                        "reported_cost_usd": usage.get("cost"),
                        "finish_reason": data["choices"][0].get("finish_reason"),  # "length" = cut off by max_tokens
                        "raw_content": content,  # unprocessed model text
                    }
                    try:
                        result["answers"] = to_jev_answers(LLMAnswer.model_validate_json(content))
                    except ValidationError as error:
                        first = error.errors()[0]
                        where = ".".join(str(part) for part in first["loc"]) or "<root>"
                        result |= {"error_kind": "malformed", "error": f"malformed: {where}: {first['msg']}"}
            status = result.get("error", f"{result.get('latency_s', 0):.2f}s")
            print(f"{row['id']:>3}  {status}")
            if result.get("error_kind") == "malformed":
                print(f"     raw: {result['raw_content'][:200]!r}")  # show what the model actually sent
            results.append(result)

    record = {
        "triager": "llm",
        "run_at_utc": started.isoformat(timespec="seconds"),
        "requested_model": LLM_MODEL,
        "reported_models": sorted({r["model"] for r in results if "model" in r}),
        "dataset": {"path": "data/messages.csv", "git_blob": DATASET_BLOB},
        "cost_source": "OpenRouter usage.cost",
        "system_prompt": SYSTEM_PROMPT,
        "response_schema": RESPONSE_SCHEMA,
        "results": results,
    }
    evaluate.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = evaluate.RUNS_DIR / f"{started:%Y-%m-%dT%H%M%SZ}_{LLM_MODEL.replace('/', '_')}.json"
    path.write_text(json.dumps(record, indent=2))
    return path


if __name__ == "__main__":
    saved = run()
    evaluate.report(saved)
    print(f"\nSaved run: {saved}")
