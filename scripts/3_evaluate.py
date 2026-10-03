"""Step 5: run every labeled message through the triager, save the run, report metrics.

    uv run scripts/3_evaluate.py                       # call Jev for all messages, save, report
    uv run scripts/3_evaluate.py data/runs/<run>.json  # re-report a saved run, no API calls
"""

import csv
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "2_three_primitives"))  # folder name can't be imported as a package

import typesafe_sdk  # noqa: E402
from config import DATASET_BLOB, INPUT_PRICE_PER_MILLION_USD, MODEL, NOUL_THRESHOLDS, QUESTIONS  # noqa: E402
from triager import make_client, triage  # noqa: E402

DATASET = ROOT / "data" / "messages.csv"
RUNS_DIR = ROOT / "data" / "runs"
NOUL_QUESTIONS = ["fraud_related", "needs_human"]


def check_dataset_frozen() -> None:
    blob = subprocess.run(["git", "hash-object", str(DATASET)], capture_output=True, text=True, check=True).stdout.strip()
    if blob != DATASET_BLOB:
        sys.exit(f"{DATASET} has changed (blob {blob}, expected {DATASET_BLOB}). Labels are frozen: make a new dataset version.")


def run() -> Path:
    """Call Jev once per message and save everything needed to recompute the report later."""
    check_dataset_frozen()
    with DATASET.open() as f:
        rows = list(csv.DictReader(f))

    started = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    with make_client() as client:
        for row in rows:
            # Labels and message are copied into the run, so the run file is self-contained.
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
                response = triage(row["message"], client)
            except typesafe_sdk.TypeSafeError as error:
                # Recorded and counted in the report, never retried or hidden.
                result["error"] = f"{type(error).__name__}: {error}"
                print(f"{row['id']:>3}  ERROR  {result['error']}")
                results.append(result)
                continue
            raw = response.raw_http_response.json()
            result |= {
                "latency_s": round(time.perf_counter() - start, 3),
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cost_usd": response.usage.input_tokens * INPUT_PRICE_PER_MILLION_USD / 1_000_000,
                "reported_cost_usd": raw["usage"].get("cost"),  # OpenRouter-only field
                "answers": raw["answers"],  # unprocessed, exactly as returned
            }
            print(f"{row['id']:>3}  {result['latency_s']:.2f}s")
            results.append(result)

    record = {
        "run_at_utc": started.isoformat(timespec="seconds"),
        "requested_model": MODEL,
        "reported_models": sorted({r["model"] for r in results if "model" in r}),
        "dataset": {"path": "data/messages.csv", "git_blob": DATASET_BLOB},
        "sdk_version": typesafe_sdk.__version__,
        "questions": {name: question.model_dump() for name, question in QUESTIONS.items()},
        "results": results,
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{started:%Y-%m-%dT%H%M%SZ}_{MODEL.replace('/', '_')}.json"
    path.write_text(json.dumps(record, indent=2))
    return path


def most_likely_level(score_answer: dict[str, Any]) -> int:
    probabilities: dict[str, float] = score_answer["probabilities"]
    return int(max(probabilities, key=lambda level: probabilities[level]))


def misses(result: dict[str, Any]) -> list[tuple[float, str, str, str]]:
    """Per question: (miss size, question, expected, got). Miss size = 1 - probability given to the true label."""
    answers, expected = result["answers"], result["expected"]
    category, urgency = answers["category"], answers["urgency"]
    out = [
        (1 - category["probabilities"].get(expected["category"], 0.0), "category", expected["category"], f"{category['choice']} ({category['probabilities'][category['choice']]})"),
        (1 - urgency["probabilities"].get(str(expected["urgency"]), 0.0), "urgency", str(expected["urgency"]), f"level {most_likely_level(urgency)} (score {urgency['score']})"),
    ]
    for name in NOUL_QUESTIONS:
        p = answers[name]["noul"]
        out.append((abs(expected[name] - p), name, str(expected[name]), str(p)))
    return out


def ratio(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:.2f}" if denominator else "n/a"


def report(path: Path) -> None:
    record = json.loads(path.read_text())
    results = record["results"]
    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    print(f"\nRun:      {path.name}")
    print(f"Date:     {record['run_at_utc']}")
    print(f"Triager:  {record.get('triager', 'jev')}")
    print(f"Model:    requested {record['requested_model']}, reported {', '.join(record['reported_models'])}")
    print(f"Dataset:  {record['dataset']['path']} @ blob {record['dataset']['git_blob'][:7]}")
    kinds = Counter(r.get("error_kind", "api") for r in failed)
    print(f"Messages: {len(ok)} ok, {len(failed)} failed  (malformed output {kinds['malformed']}, api errors {kinds['api']})")
    for r in failed:
        print(f"  id {r['id']}: {r['error']}")
    if not ok:
        return

    category_hits = sum(r["answers"]["category"]["choice"] == r["expected"]["category"] for r in ok)
    urgency_hits = sum(most_likely_level(r["answers"]["urgency"]) == r["expected"]["urgency"] for r in ok)
    print("\nAccuracy")
    print(f"  category: {ratio(category_hits, len(ok))}  ({category_hits}/{len(ok)})")
    print(f"  urgency:  {ratio(urgency_hits, len(ok))}  ({urgency_hits}/{len(ok)})  most likely level vs label")

    for name in NOUL_QUESTIONS:
        positives = sum(r["expected"][name] for r in ok)
        print(f"\n{name}  ({positives} labeled yes of {len(ok)})")
        print("  threshold  precision  recall   TP  FP  FN")
        for threshold in NOUL_THRESHOLDS:
            predicted = [(r["answers"][name]["noul"] >= threshold, r["expected"][name] == 1) for r in ok]
            tp = sum(p and e for p, e in predicted)
            fp = sum(p and not e for p, e in predicted)
            fn = sum(e and not p for p, e in predicted)
            print(f"  {threshold:>9}  {ratio(tp, tp + fp):>9}  {ratio(tp, tp + fn):>6}  {tp:>3} {fp:>3} {fn:>3}")

    latencies = [r["latency_s"] for r in ok]
    costs = [r["cost_usd"] for r in ok]
    reported = [r["reported_cost_usd"] for r in ok if r["reported_cost_usd"] is not None]
    print("\nLatency per message (s)")
    print(f"  median {statistics.median(latencies):.2f}   mean {statistics.mean(latencies):.2f}   max {max(latencies):.2f}")
    print("Cost")
    print(f"  per message {statistics.mean(costs):.8f} USD   total {sum(costs):.6f} USD   ({record.get('cost_source', 'tokens x price')})")
    if reported:
        print(f"  OpenRouter reported total {sum(reported):.6f} USD")
    print(f"  mean input tokens {statistics.mean(r['input_tokens'] for r in ok):.0f}   mean output tokens {statistics.mean(r['output_tokens'] for r in ok):.0f}")
    reasoning = [r["reasoning_tokens"] for r in ok if r.get("reasoning_tokens") is not None]
    if reasoning:
        print(f"  mean reasoning tokens {statistics.mean(reasoning):.0f} (billed as output)")

    worst = sorted(((miss, r, *rest) for r in ok for miss, *rest in misses(r)), key=lambda item: item[0], reverse=True)[:10]
    print("\n10 worst misses (miss = 1 - probability given to your label)")
    for miss, r, question, expected, got in worst:
        print(f"  {miss:.2f}  id {r['id']:>2}  {question:<13} expected {expected:<20} got {got}")
        print(f"        \"{r['message']}\"" + (f"  [{r['tags']}]" if r["tags"] else ""))


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else run()
    report(path)
    print(f"\nSaved run: {path}")


if __name__ == "__main__":
    main()
