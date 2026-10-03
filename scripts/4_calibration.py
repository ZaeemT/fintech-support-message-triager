"""Step 6: calibration of the noul answers in a saved run (no API calls).

    uv run scripts/4_calibration.py data/runs/<run>.json

For each noul question: bucket the probabilities (0-0.1, 0.1-0.2, ...; lower bound inclusive),
compare the mean predicted probability with how often the label was actually yes,
and save a reliability diagram next to the run file.
"""

import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # write a PNG, no window
import matplotlib.pyplot as plt  # noqa: E402

NOUL_QUESTIONS = ["fraud_related", "needs_human"]
N_BUCKETS = 10

# Colors from the dataviz reference palette (light mode).
SURFACE, INK, INK_MUTED, GRID, SERIES = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"


def pairs(record: dict[str, Any], question: str) -> list[tuple[float, int]]:
    """(predicted probability, true label) for every successful message."""
    return [(r["answers"][question]["noul"], r["expected"][question]) for r in record["results"] if "error" not in r]


def buckets(data: list[tuple[float, int]]) -> list[dict[str, float]]:
    """Non-empty buckets with count, mean predicted probability and fraction actually yes."""
    grouped: list[list[tuple[float, int]]] = [[] for _ in range(N_BUCKETS)]
    for p, label in data:
        grouped[min(int(p * N_BUCKETS), N_BUCKETS - 1)].append((p, label))  # p = 1.0 goes in the top bucket
    return [
        {
            "low": i / N_BUCKETS,
            "n": len(items),
            "mean_predicted": sum(p for p, _ in items) / len(items),
            "fraction_yes": sum(label for _, label in items) / len(items),
        }
        for i, items in enumerate(grouped)
        if items
    ]


def brier(data: list[tuple[float, int]]) -> float:
    """Mean squared gap between probability and label. 0 is perfect; always saying 0.5 scores 0.25."""
    return sum((p - label) ** 2 for p, label in data) / len(data)


def print_table(question: str, data: list[tuple[float, int]]) -> None:
    base_rate = sum(label for _, label in data) / len(data)
    print(f"\n{question}  (n={len(data)}, base rate {base_rate:.2f}, Brier {brier(data):.3f})")
    print("  bucket      n   mean predicted   fraction yes   gap")
    for b in buckets(data):
        gap = b["fraction_yes"] - b["mean_predicted"]
        print(f"  {b['low']:.1f}-{b['low'] + 0.1:.1f}  {b['n']:>3}   {b['mean_predicted']:>14.2f}   {b['fraction_yes']:>12.2f}   {gap:+.2f}")


def plot(record: dict[str, Any], out: Path) -> None:
    fig, axes = plt.subplots(1, len(NOUL_QUESTIONS), figsize=(10, 5), facecolor=SURFACE)
    for ax, question in zip(axes, NOUL_QUESTIONS):
        data = pairs(record, question)
        bs = buckets(data)
        ax.set_facecolor(SURFACE)
        ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1, color=INK_MUTED, label="perfect calibration")
        ax.plot([b["mean_predicted"] for b in bs], [b["fraction_yes"] for b in bs], color=SERIES, linewidth=2, marker="o", markersize=7)
        for b in bs:
            ax.annotate(f"n={b['n']}", (b["mean_predicted"], b["fraction_yes"]), textcoords="offset points", xytext=(6, -12), fontsize=8, color=INK_MUTED)
        ax.set(xlim=(-0.02, 1.02), ylim=(-0.02, 1.02), aspect="equal")
        ax.set_title(f"{question}   (Brier {brier(data):.3f})", color=INK, fontsize=11, loc="left")
        ax.set_xlabel("mean predicted probability (per bucket)", color=INK_MUTED)
        ax.set_ylabel("fraction actually yes", color=INK_MUTED)
        ax.grid(color=GRID, linewidth=0.8)
        ax.tick_params(colors=INK_MUTED)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.legend(loc="upper left", frameon=False, fontsize=8, labelcolor=INK_MUTED)
    fig.suptitle(f"Reliability diagram: {record['reported_models'][0]}, run {record['run_at_utc'][:10]}", color=INK, x=0.06, ha="left")
    fig.tight_layout()
    fig.savefig(out, dpi=150, facecolor=SURFACE)


def main() -> None:
    path = Path(sys.argv[1])
    record = json.loads(path.read_text())
    print(f"Run: {path.name}   model: {', '.join(record['reported_models'])}   dataset blob: {record['dataset']['git_blob'][:7]}")
    for question in NOUL_QUESTIONS:
        print_table(question, pairs(record, question))
    out = path.with_name(path.stem + "_reliability.png")
    plot(record, out)
    print(f"\nSaved diagram: {out}")


if __name__ == "__main__":
    main()
