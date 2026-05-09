"""
Failure analysis plots:
  1. Failure-turn distribution by variant (violin + strip)
  2. Budget utilisation (moves used / turn_limit) for wins vs losses
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

from load_sessions import load_sessions, VARIANT_LABELS


def plot_failure_turn(df: pd.DataFrame, output: Path | None = None) -> None:
    """Box plot of move_count at end of session for losses."""
    lost = df[~df["won"]].copy()

    fig, ax = plt.subplots(figsize=(14, 5))

    if lost.empty:
        ax.text(0.5, 0.5, "No losses in dataset", ha="center", va="center", transform=ax.transAxes)
    else:
        variant_order = [v for v in VARIANT_LABELS if v in lost["variant_code"].unique()]
        lost["variant_label"] = pd.Categorical(
            lost["variant_label"],
            categories=[VARIANT_LABELS[v] for v in variant_order if v in lost["variant_code"].unique()],
            ordered=True,
        )
        sns.boxplot(data=lost, x="variant_label", y="move_count",
                    palette="Reds", hue="variant_label",
                    legend=False, ax=ax, linewidth=0.8, fliersize=4)
        sns.stripplot(data=lost, x="variant_label", y="move_count",
                      color="black", size=3, alpha=0.5, jitter=True, ax=ax, zorder=5)

    ax.set_xlabel("")
    ax.set_ylabel("Move count at failure", fontsize=11)
    ax.set_title("How Quickly the Model Failed (by Variant)", fontsize=13, fontweight="bold")
    ax.tick_params(axis="x", rotation=15, labelsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved: {output}")
    else:
        plt.show()
    plt.close(fig)


def plot_budget_utilisation(df: pd.DataFrame, output: Path | None = None) -> None:
    """KDE of budget used (move_count / turn_limit) by outcome."""
    fig, ax = plt.subplots(figsize=(7, 5))

    sub = df[df["turn_limit"] > 0].copy()
    if sub.empty:
        ax.text(0.5, 0.5, "No turn-limit data", ha="center", va="center", transform=ax.transAxes)
    else:
        sub["budget_pct"] = sub["budget_used"] * 100
        for outcome, color, ls in [("Win", "#2ecc71", "-"), ("Loss", "#e74c3c", "--")]:
            group = sub[sub["outcome"] == outcome]["budget_pct"].dropna()
            if group.empty:
                continue
            sns.kdeplot(data=group, ax=ax, label=outcome, color=color, linestyle=ls, linewidth=2)
        ax.axvline(100, color="gray", linewidth=0.8, linestyle=":", label="Turn limit")
        ax.set_xlim(0, None)

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax.set_xlabel("Budget used (% of turn limit)", fontsize=11)
    ax.set_ylabel("Density", fontsize=11)
    ax.set_title("Budget Utilisation: Wins vs Losses", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9, framealpha=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="both", linestyle="--", alpha=0.4)

    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved: {output}")
    else:
        plt.show()
    plt.close(fig)


def plot_failure_analysis(sessions_path: str, output_dir: Path | None = None) -> None:
    df = load_sessions(sessions_path)
    plot_failure_turn(df, output_dir / "failure_turn.png" if output_dir else None)
    plot_budget_utilisation(df, output_dir / "budget_utilisation.png" if output_dir else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Failure analysis plots")
    parser.add_argument("sessions", help="Path to session JSONL file")
    parser.add_argument("-o", "--output-dir", help="Directory to save plots", default=None)
    args = parser.parse_args()
    out = Path(args.output_dir) if args.output_dir else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    plot_failure_analysis(args.sessions, out)
