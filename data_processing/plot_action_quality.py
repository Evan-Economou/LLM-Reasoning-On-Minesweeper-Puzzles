"""
Action quality plots:
  1. Mine-hit rate by variant (fraction of REVEAL moves that hit mines)
  2. Cumulative mine hits over turn number (losses only)
  3. Flag vs Reveal action mix by variant
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

from load_sessions import load_sessions, load_moves, VARIANT_LABELS


def plot_mine_hit_rate(moves_df: pd.DataFrame, output: Path | None = None) -> None:
    reveals = moves_df[moves_df["action"] == "REVEAL"].copy()

    fig, ax = plt.subplots(figsize=(max(6, len(VARIANT_LABELS) * 0.9), 5))

    if reveals.empty:
        ax.text(0.5, 0.5, "No REVEAL actions found", ha="center", va="center", transform=ax.transAxes)
    else:
        variant_order = [VARIANT_LABELS[v] for v in VARIANT_LABELS if v in reveals["variant_code"].unique()]
        hit_rate = (
            reveals.groupby("variant_label")["hit_mine"]
            .agg(["mean", "count"])
            .reindex(variant_order)
            .reset_index()
        )
        colors = ["#e74c3c" if r > 0.1 else "#e67e22" if r > 0.05 else "#2ecc71"
                  for r in hit_rate["mean"]]
        bars = ax.bar(hit_rate["variant_label"], hit_rate["mean"] * 100,
                      color=colors, edgecolor="white", linewidth=0.8, zorder=3)
        for bar, rate, n in zip(bars, hit_rate["mean"], hit_rate["count"]):
            if rate > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                        f"{rate*100:.1f}%", ha="center", va="bottom", fontsize=8)
            ax.text(bar.get_x() + bar.get_width() / 2, -0.5,
                    f"n={n}", ha="center", va="top", fontsize=7, color="#555555")
        ax.set_ylim(-1.5, None)

    ax.set_xlabel("")
    ax.set_ylabel("Mine hit rate (%)", fontsize=11)
    ax.set_title("Mine Hit Rate per REVEAL by Variant", fontsize=13, fontweight="bold")
    ax.tick_params(axis="x", rotation=15)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)

    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved: {output}")
    else:
        plt.show()
    plt.close(fig)


def plot_cumulative_hits(moves_df: pd.DataFrame, output: Path | None = None) -> None:
    """Cumulative mine hits over turns for losing sessions."""
    fig, ax = plt.subplots(figsize=(7, 5))

    if moves_df.empty:
        ax.text(0.5, 0.5, "No move data", ha="center", va="center", transform=ax.transAxes)
    else:
        losses = moves_df[moves_df["won"] == False].copy()
        if not losses.empty:
            losses = losses.sort_values(["session_id", "turn"])
            losses["cum_hits"] = losses.groupby("session_id")["hit_mine"].cumsum()
            traj = losses.groupby("turn")["cum_hits"].agg(["mean", "sem"]).reset_index()
            ax.plot(traj["turn"], traj["mean"], color="#e74c3c", linewidth=2)
            ax.fill_between(traj["turn"],
                            traj["mean"] - traj["sem"],
                            traj["mean"] + traj["sem"],
                            alpha=0.15, color="#e74c3c")

    ax.set_xlabel("Turn number", fontsize=11)
    ax.set_ylabel("Cumulative mine hits (mean ± SE)", fontsize=11)
    ax.set_title("Cumulative Mine Hits over Turns (Losses)", fontsize=13, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(linestyle="--", alpha=0.4)

    fig.tight_layout()
    if output:
        fig.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved: {output}")
    else:
        plt.show()
    plt.close(fig)


def plot_reveal_vs_flag(moves_df: pd.DataFrame, output: Path | None = None) -> None:
    """Fraction of moves that are FLAG vs REVEAL, split by variant."""
    fig, ax = plt.subplots(figsize=(max(6, len(VARIANT_LABELS) * 0.9), 5))

    if moves_df.empty:
        ax.text(0.5, 0.5, "No move data", ha="center", va="center", transform=ax.transAxes)
    else:
        variant_order = [VARIANT_LABELS[v] for v in VARIANT_LABELS if v in moves_df["variant_code"].unique()]
        pivot = (
            moves_df.groupby(["variant_label", "action"])
            .size()
            .unstack(fill_value=0)
            .reindex(variant_order)
        )
        pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
        color_map = {"REVEAL": "#3498db", "FLAG": "#e67e22"}
        bottom = np.zeros(len(pivot_pct))
        for action in pivot_pct.columns:
            vals = pivot_pct[action].fillna(0).values
            ax.bar(pivot_pct.index, vals, bottom=bottom,
                   label=action, color=color_map.get(action, "#aaa"),
                   edgecolor="white", linewidth=0.5)
            bottom += vals
        ax.set_ylim(0, 110)

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax.set_xlabel("")
    ax.set_ylabel("% of moves", fontsize=11)
    ax.set_title("Action Mix by Variant", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9, framealpha=0.8)
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


def plot_action_quality(sessions_path: str, output_dir: Path | None = None) -> None:
    moves_df = load_moves(sessions_path)
    plot_mine_hit_rate(moves_df, output_dir / "mine_hit_rate.png" if output_dir else None)
    plot_cumulative_hits(moves_df, output_dir / "cumulative_hits.png" if output_dir else None)
    plot_reveal_vs_flag(moves_df, output_dir / "action_mix.png" if output_dir else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Action quality analysis")
    parser.add_argument("sessions", help="Path to session JSONL file")
    parser.add_argument("-o", "--output-dir", help="Directory to save plots", default=None)
    args = parser.parse_args()
    out = Path(args.output_dir) if args.output_dir else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    plot_action_quality(args.sessions, out)
