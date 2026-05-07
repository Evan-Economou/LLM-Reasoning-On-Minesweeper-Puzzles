"""Win rate by variant — bar chart with sample-size annotations."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from load_sessions import load_sessions, VARIANT_LABELS


def plot_win_rate(sessions_path: str, output_dir: Path | None = None) -> None:
    df = load_sessions(sessions_path)

    variant_order = [v for v in VARIANT_LABELS if v in df["variant_code"].unique()]
    if not variant_order:
        variant_order = sorted(df["variant_code"].unique())

    stats = (
        df.groupby("variant_code")
        .agg(total=("won", "count"), wins=("won", "sum"))
        .assign(win_rate=lambda x: x["wins"] / x["total"])
        .reindex([v for v in variant_order if v in df["variant_code"].unique()])
    )

    labels = [VARIANT_LABELS.get(v, v) for v in stats.index]
    win_rates = stats["win_rate"].values
    totals = stats["total"].values

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.9), 5))

    colors = ["#2ecc71" if r >= 0.5 else "#e74c3c" for r in win_rates]
    bars = ax.bar(labels, win_rates * 100, color=colors, edgecolor="white", linewidth=0.8, zorder=3)

    ax.axhline(50, color="gray", linewidth=0.8, linestyle="--", zorder=2, label="50%")

    for bar, rate, n in zip(bars, win_rates, totals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                f"{rate*100:.0f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax.text(bar.get_x() + bar.get_width() / 2, -5,
                f"n={n}", ha="center", va="top", fontsize=8, color="#555555")

    ax.set_ylim(-10, 115)
    ax.set_ylabel("Win Rate (%)", fontsize=11)
    ax.set_title("Win Rate by Variant", fontsize=13, fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", rotation=15)

    player = df["player_id"].iloc[0] if "player_id" in df.columns else ""
    model = df["model_id"].iloc[0] if "model_id" in df.columns else ""
    if player or model:
        fig.text(0.99, 0.01, f"{player} · {model}", ha="right", va="bottom",
                 fontsize=7, color="#888888")

    fig.tight_layout()
    if output_dir:
        out = output_dir / "win_rate.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved: {out}")
    else:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot win rate by variant")
    parser.add_argument("sessions", help="Path to session JSONL file")
    parser.add_argument("-o", "--output-dir", help="Directory to save plot", default=None)
    args = parser.parse_args()
    out = Path(args.output_dir) if args.output_dir else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    plot_win_rate(args.sessions, out)
