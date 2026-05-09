"""Generate a markdown statistics report from a session JSONL file."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from load_sessions import load_sessions, load_moves, VARIANT_LABELS


def _pct(n, total):
    return f"{n/total*100:.1f}%" if total > 0 else "—"


def _fmt_k(x):
    return f"{x/1000:.1f}k" if x >= 1000 else str(int(round(x)))


def generate_stats_report(sessions_path: str, output: Path | None = None) -> str:
    df = load_sessions(sessions_path)
    moves_df = load_moves(sessions_path)

    lines = []

    # ── Header ──────────────────────────────────────────────────────────────
    player = df["player_id"].iloc[0] if not df.empty else "unknown"
    model  = df["model_id"].iloc[0]  if not df.empty else "unknown"
    ext_thinking = bool(df["extended_thinking"].iloc[0]) if not df.empty else False
    cot          = bool(df["include_cot"].iloc[0])       if not df.empty else False

    lines += [
        f"# Session Statistics Report",
        f"",
        f"**Player:** {player}  ",
        f"**Model:** {model}  ",
        f"**Extended thinking:** {'yes' if ext_thinking else 'no'}  ",
        f"**Chain-of-thought:** {'yes' if cot else 'no'}  ",
        f"**Source:** `{sessions_path}`",
        f"",
    ]

    # ── Overall summary ──────────────────────────────────────────────────────
    n_total  = len(df)
    n_won    = df["won"].sum()
    n_lost   = (~df["won"]).sum()
    wr       = n_won / n_total if n_total > 0 else 0
    variants = df["variant_code"].nunique()

    lines += [
        "## Overall Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total sessions | {n_total} |",
        f"| Variants covered | {variants} |",
        f"| Wins | {n_won} ({_pct(n_won, n_total)}) |",
        f"| Losses | {n_lost} ({_pct(n_lost, n_total)}) |",
        f"| Mean moves per session | {df['move_count'].mean():.1f} |",
        f"| Median moves per session | {df['move_count'].median():.0f} |",
        f"| Mean budget used | {df['budget_used'].mean()*100:.1f}% |",
        f"| Mean total tokens | {_fmt_k(df['total_tokens'].mean())} |",
        f"| Median total tokens | {_fmt_k(df['total_tokens'].median())} |",
        f"| Mean session duration | {df['duration_seconds'].mean():.1f}s |",
        "",
    ]

    # ── Per-variant breakdown ────────────────────────────────────────────────
    variant_order = [v for v in VARIANT_LABELS if v in df["variant_code"].unique()]

    var_stats = (
        df.groupby("variant_code")
        .agg(
            n=("won", "count"),
            wins=("won", "sum"),
            mean_moves=("move_count", "mean"),
            median_moves=("move_count", "median"),
            mean_tokens=("total_tokens", "mean"),
            mean_budget=("budget_used", "mean"),
        )
        .assign(win_rate=lambda x: x["wins"] / x["n"])
        .reindex([v for v in variant_order if v in df["variant_code"].unique()])
    )

    lines += [
        "## Win Rate by Variant",
        "",
        "| Variant | n | Wins | Win Rate | Mean Moves | Median Moves | Mean Tokens | Mean Budget Used |",
        "|---------|---|------|----------|------------|--------------|-------------|-----------------|",
    ]
    for code, row in var_stats.iterrows():
        label = VARIANT_LABELS.get(code, code)
        lines.append(
            f"| {label} | {int(row['n'])} | {int(row['wins'])} | {row['win_rate']*100:.0f}% "
            f"| {row['mean_moves']:.1f} | {row['median_moves']:.0f} "
            f"| {_fmt_k(row['mean_tokens'])} | {row['mean_budget']*100:.1f}% |"
        )
    lines.append("")

    # ── Failure analysis ─────────────────────────────────────────────────────
    lost = df[~df["won"]]
    lines += ["## Failure Analysis", ""]

    if not lost.empty:
        # Turn-of-failure distribution
        fail_turns = lost["move_count"]
        first_move_fail = (fail_turns == 1).sum()
        lines += [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total losses | {len(lost)} |",
            f"| Failed on move 1 | {first_move_fail} ({_pct(first_move_fail, len(lost))}) |",
            f"| Failed on move ≤ 3 | {(fail_turns <= 3).sum()} ({_pct((fail_turns <= 3).sum(), len(lost))}) |",
            f"| Mean move of failure | {fail_turns.mean():.1f} |",
            f"| Median move of failure | {fail_turns.median():.0f} |",
            f"| Earliest failure | move {int(fail_turns.min())} |",
            f"| Latest failure | move {int(fail_turns.max())} |",
            "",
        ]

        # Failures by variant (sorted worst first)
        fail_by_var = (
            lost.groupby("variant_code")
            .agg(losses=("won", "count"), mean_fail_turn=("move_count", "mean"))
            .reindex([v for v in variant_order if v in lost["variant_code"].unique()])
        )
        lines += [
            "### Losses per Variant",
            "",
            "| Variant | Losses | Mean Failure Turn |",
            "|---------|--------|-------------------|",
        ]
        for code, row in fail_by_var.iterrows():
            lines.append(
                f"| {VARIANT_LABELS.get(code, code)} | {int(row['losses'])} | {row['mean_fail_turn']:.1f} |"
            )
        lines.append("")

        # Failure categories
        cats = lost["failure_category"].dropna()
        if not cats.empty:
            cat_counts = cats.value_counts()
            lines += [
                "### Failure Categories",
                "",
                "| Category | Count | % of Losses |",
                "|----------|-------|-------------|",
            ]
            for cat, count in cat_counts.items():
                lines.append(f"| {cat} | {count} | {_pct(count, len(lost))} |")
            lines.append("")
    else:
        lines += ["No losses recorded.", ""]

    # ── Action quality ───────────────────────────────────────────────────────
    lines += ["## Action Quality", ""]

    if not moves_df.empty:
        reveals = moves_df[moves_df["action"] == "REVEAL"]
        flags   = moves_df[moves_df["action"] == "FLAG"]
        total_moves = len(moves_df)
        n_reveals = len(reveals)
        n_flags   = len(flags)
        n_hits    = reveals["hit_mine"].sum() if not reveals.empty else 0

        lines += [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total moves | {total_moves} |",
            f"| REVEAL moves | {n_reveals} ({_pct(n_reveals, total_moves)}) |",
            f"| FLAG moves | {n_flags} ({_pct(n_flags, total_moves)}) |",
            f"| Mine hits on REVEAL | {int(n_hits)} ({_pct(int(n_hits), n_reveals)}) |",
            "",
        ]

        # Mine hit rate by variant
        if not reveals.empty:
            hit_by_var = (
                reveals.groupby("variant_code")["hit_mine"]
                .agg(["mean", "count"])
                .reindex([v for v in variant_order if v in reveals["variant_code"].unique()])
            )
            lines += [
                "### Mine Hit Rate by Variant (REVEAL actions only)",
                "",
                "| Variant | REVEAL moves | Mine hit rate |",
                "|---------|-------------|---------------|",
            ]
            for code, row in hit_by_var.iterrows():
                lines.append(
                    f"| {VARIANT_LABELS.get(code, code)} | {int(row['count'])} | {row['mean']*100:.1f}% |"
                )
            lines.append("")
    else:
        lines += ["No move data available.", ""]

    # ── Token usage ──────────────────────────────────────────────────────────
    lines += ["## Token Usage", ""]

    if not moves_df.empty and "output_tokens" in moves_df.columns:
        total_input  = df["input_tokens"].sum()
        total_output = df["output_tokens"].sum()
        total_all    = total_input + total_output

        # Peak output turn
        traj = moves_df.groupby("turn")["output_tokens"].mean()
        peak_turn = int(traj.idxmax()) if not traj.empty else "—"
        peak_val  = _fmt_k(traj.max()) if not traj.empty else "—"

        lines += [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total input tokens | {_fmt_k(total_input)} |",
            f"| Total output tokens | {_fmt_k(total_output)} |",
            f"| Total tokens (all sessions) | {_fmt_k(total_all)} |",
            f"| Output / Input ratio | {total_output/total_input:.2f}x |" if total_input > 0 else "| Output / Input ratio | — |",
            f"| Mean output tokens per turn | {_fmt_k(moves_df['output_tokens'].mean())} |",
            f"| Peak output turn | turn {peak_turn} ({peak_val} tokens avg) |",
            "",
        ]

        # Tokens by variant
        tok_by_var = (
            df.groupby("variant_code")[["input_tokens", "output_tokens", "total_tokens"]]
            .mean()
            .reindex([v for v in variant_order if v in df["variant_code"].unique()])
        )
        lines += [
            "### Mean Tokens per Session by Variant",
            "",
            "| Variant | Input | Output | Total | Output:Input |",
            "|---------|-------|--------|-------|--------------|",
        ]
        for code, row in tok_by_var.iterrows():
            ratio = f"{row['output_tokens']/row['input_tokens']:.1f}x" if row["input_tokens"] > 0 else "—"
            lines.append(
                f"| {VARIANT_LABELS.get(code, code)} "
                f"| {_fmt_k(row['input_tokens'])} "
                f"| {_fmt_k(row['output_tokens'])} "
                f"| {_fmt_k(row['total_tokens'])} "
                f"| {ratio} |"
            )
        lines.append("")

    report = "\n".join(lines)

    if output:
        output.write_text(report, encoding="utf-8")
        print(f"Saved: {output}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate statistics report")
    parser.add_argument("sessions", help="Path to session JSONL file")
    parser.add_argument("-o", "--output", help="Output .md path", default=None)
    args = parser.parse_args()
    out = Path(args.output) if args.output else None
    report = generate_stats_report(args.sessions, out)
    if not out:
        print(report)
