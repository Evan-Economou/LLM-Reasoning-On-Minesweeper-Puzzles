"""
Token usage analysis:
  1. Total tokens per session by variant (box plot)
  2. Tokens per turn over the course of games (average trajectory)
  3. Input vs output token breakdown
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

from load_sessions import load_sessions, load_moves, VARIANT_LABELS


def _fmt_k(x, _):
    return f"{x/1000:.0f}k" if x >= 1000 else str(int(x))


def plot_tokens_by_variant(df: pd.DataFrame, output: Path | None = None) -> None:
    variant_order = [VARIANT_LABELS[v] for v in VARIANT_LABELS if v in df["variant_code"].unique()]

    fig, ax = plt.subplots(figsize=(max(6, len(variant_order) * 0.9), 5))
    sns.boxplot(
        data=df, x="variant_label", y="total_tokens",
        order=variant_order, palette="Blues", hue="variant_label",
        legend=False, ax=ax,
        linewidth=0.8, flierprops={"markersize": 3, "alpha": 0.5},
    )
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_k))
    ax.set_xlabel("")
    ax.set_ylabel("Total tokens / session", fontsize=11)
    ax.set_title("Token Usage by Variant", fontsize=13, fontweight="bold")
    ax.tick_params(axis="x", rotation=15)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved: {output}")
    else:
        plt.show()
    plt.close(fig)


def plot_token_trajectory(moves_df: pd.DataFrame, output: Path | None = None) -> None:
    """Average output tokens per turn across all sessions."""
    fig, ax = plt.subplots(figsize=(7, 5))

    if moves_df.empty or "output_tokens" not in moves_df.columns:
        ax.text(0.5, 0.5, "No per-turn token data", ha="center", va="center", transform=ax.transAxes)
    else:
        traj = (
            moves_df.groupby("turn")["output_tokens"]
            .agg(["mean", "sem"])
            .reset_index()
        )
        ax.plot(traj["turn"], traj["mean"], color="#3498db", linewidth=2)
        ax.fill_between(
            traj["turn"],
            traj["mean"] - traj["sem"],
            traj["mean"] + traj["sem"],
            alpha=0.2, color="#3498db",
        )

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f"{x/1000:.1f}k" if x >= 1000 else str(int(x))
    ))
    ax.set_xlabel("Turn number", fontsize=11)
    ax.set_ylabel("Output tokens (mean ± SE)", fontsize=11)
    ax.set_title("Output Tokens per Turn (across all sessions)", fontsize=13, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(linestyle="--", alpha=0.4)

    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved: {output}")
    else:
        plt.show()
    plt.close(fig)


def plot_io_split(df: pd.DataFrame, output: Path | None = None) -> None:
    """Stacked bar: mean input vs output tokens per variant."""
    variant_order = [VARIANT_LABELS[v] for v in VARIANT_LABELS if v in df["variant_code"].unique()]
    means = (
        df.groupby("variant_label")[["input_tokens", "output_tokens"]]
        .mean()
        .reindex(variant_order)
    )

    fig, ax = plt.subplots(figsize=(max(6, len(variant_order) * 0.9), 5))
    means[["input_tokens", "output_tokens"]].plot(
        kind="bar", stacked=True, ax=ax,
        color=["#3498db", "#e67e22"], edgecolor="white", linewidth=0.5,
    )
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_k))
    ax.set_xlabel("")
    ax.set_ylabel("Mean tokens / session", fontsize=11)
    ax.set_title("Input vs Output Tokens by Variant", fontsize=13, fontweight="bold")
    ax.legend(["Input tokens", "Output tokens"], fontsize=9, framealpha=0.8)
    ax.tick_params(axis="x", rotation=15)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved: {output}")
    else:
        plt.show()
    plt.close(fig)


def plot_token_usage(sessions_path: str, output_dir: Path | None = None) -> None:
    df = load_sessions(sessions_path)
    moves_df = load_moves(sessions_path)
    plot_tokens_by_variant(df, output_dir / "tokens_by_variant.png" if output_dir else None)
    plot_token_trajectory(moves_df, output_dir / "token_trajectory.png" if output_dir else None)
    plot_io_split(df, output_dir / "io_split.png" if output_dir else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Token usage analysis")
    parser.add_argument("sessions", help="Path to session JSONL file")
    parser.add_argument("-o", "--output-dir", help="Directory to save plots", default=None)
    args = parser.parse_args()
    out = Path(args.output_dir) if args.output_dir else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    plot_token_usage(args.sessions, out)
