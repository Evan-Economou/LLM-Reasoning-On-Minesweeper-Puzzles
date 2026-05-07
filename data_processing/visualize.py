"""
Generate all visualizations for a session JSONL file.

Usage:
    uv run python data_processing/visualize.py docs/haiku_cot_sessions.jsonl
    uv run python data_processing/visualize.py docs/haiku_cot_sessions.jsonl -o docs/figures/
"""

import argparse
import sys
from pathlib import Path

# Allow running from project root or from data_processing/
sys.path.insert(0, str(Path(__file__).parent))

from plot_win_rate import plot_win_rate
from plot_failure_analysis import plot_failure_analysis
from plot_token_usage import plot_token_usage
from plot_action_quality import plot_action_quality


PLOTS = [
    ("win_rate", plot_win_rate, "Win rate by variant"),
    ("failure_analysis", plot_failure_analysis, "Failure timing, categories, and budget utilisation"),
    ("token_usage", plot_token_usage, "Token usage breakdown"),
    ("action_quality", plot_action_quality, "Action quality and mine-hit analysis"),
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate all visualizations for a Minesweeper LLM session file"
    )
    parser.add_argument("sessions", help="Path to session JSONL file")
    parser.add_argument(
        "-o", "--output-dir",
        help="Directory to save figures (PNG). If omitted, shows interactively.",
        default=None,
    )
    parser.add_argument(
        "--only", nargs="+",
        choices=[name for name, _, _ in PLOTS],
        help="Run only specific plots",
    )
    args = parser.parse_args()

    sessions_path = Path(args.sessions)
    if not sessions_path.exists():
        print(f"Error: session file not found: {sessions_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = None
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    selected = set(args.only) if args.only else {name for name, _, _ in PLOTS}

    for name, fn, desc in PLOTS:
        if name not in selected:
            continue
        print(f"Plotting: {desc}")
        fn(str(sessions_path), output_dir)

    if output_dir:
        print(f"\nAll figures saved to: {output_dir}/")


if __name__ == "__main__":
    main()
