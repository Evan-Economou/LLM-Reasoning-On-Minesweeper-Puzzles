"""
Analyze token usage and estimated API cost from session JSONL logs.

Usage:
    python token_analysis.py <session_log.jsonl> [<session_log2.jsonl> ...]

Results are printed to stdout and written to docs/tokendata/<session_name>.md.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from io import StringIO
from pathlib import Path

# Pricing per million tokens (update as needed)
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-haiku-4-5":          {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
    "claude-opus-4-7":           {"input": 15.00, "output": 75.00},
}
DEFAULT_PRICING = {"input": 1.00, "output": 5.00}


def _cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model_id, DEFAULT_PRICING)
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


def _load_sessions(paths: list[Path]) -> list[dict]:
    sessions = []
    for path in paths:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    sessions.append(json.loads(line))
    return sessions


def _fmt_cost(dollars: float) -> str:
    if dollars < 0.01:
        return f"${dollars * 100:.4f}¢"
    return f"${dollars:.4f}"


def analyze(sessions: list[dict], out_path: Path | None = None) -> None:
    buf = StringIO()

    def p(*args, **kwargs):
        print(*args, **kwargs)
        print(*args, file=buf, **kwargs)

    if not sessions:
        p("No sessions found.")
        return

    tracked = [s for s in sessions if s.get("token_usage")]
    untracked = len(sessions) - len(tracked)

    if not tracked:
        p("No token_usage data found in any session. Re-run experiments after the model_eval update.")
        return

    by_model: dict[str, dict] = defaultdict(lambda: {
        "sessions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "by_variant": defaultdict(lambda: {"sessions": 0, "input_tokens": 0, "output_tokens": 0}),
    })

    for s in tracked:
        model_id = s.get("model", {}).get("id", "unknown")
        variant  = s.get("variant_code", "?")
        usage    = s["token_usage"]
        inp      = usage.get("input_tokens", 0)
        out      = usage.get("output_tokens", 0)

        by_model[model_id]["sessions"] += 1
        by_model[model_id]["input_tokens"] += inp
        by_model[model_id]["output_tokens"] += out
        by_model[model_id]["by_variant"][variant]["sessions"] += 1
        by_model[model_id]["by_variant"][variant]["input_tokens"] += inp
        by_model[model_id]["by_variant"][variant]["output_tokens"] += out

    grand_input = grand_output = grand_cost = 0.0

    for model_id, data in sorted(by_model.items()):
        n        = data["sessions"]
        inp      = data["input_tokens"]
        out      = data["output_tokens"]
        total_cost = _cost(model_id, inp, out)
        avg_inp  = inp / n
        avg_out  = out / n
        avg_cost = total_cost / n

        grand_input  += inp
        grand_output += out
        grand_cost   += total_cost

        p(f"\n{'='*62}")
        p(f"Model: {model_id}")
        p(f"  Sessions:      {n}")
        p(f"  Total tokens:  {inp:,} in  /  {out:,} out")
        p(f"  Per puzzle:    {avg_inp:,.0f} in  /  {avg_out:,.0f} out  ({_fmt_cost(avg_cost)} each)")
        p(f"  Total cost:    {_fmt_cost(total_cost)}")

        p(f"\n  {'Variant':<10} {'Sessions':>8} {'Avg In':>10} {'Avg Out':>9} {'Avg Cost':>10} {'Total Cost':>11}")
        p(f"  {'-'*10} {'-'*8} {'-'*10} {'-'*9} {'-'*10} {'-'*11}")
        for variant, vd in sorted(data["by_variant"].items()):
            vn   = vd["sessions"]
            vi   = vd["input_tokens"]
            vo   = vd["output_tokens"]
            vc   = _cost(model_id, vi, vo)
            p(
                f"  {variant:<10} {vn:>8} {vi/vn:>10,.0f} {vo/vn:>9,.0f}"
                f" {_fmt_cost(vc/vn):>10} {_fmt_cost(vc):>11}"
            )

    p(f"\n{'='*62}")
    p(f"Grand total across all models:")
    p(f"  Tokens:  {grand_input:,} in  /  {grand_output:,} out")
    p(f"  Cost:    {_fmt_cost(grand_cost)}")
    if untracked:
        p(f"\n  Note: {untracked} session(s) had no token_usage data and were skipped.")

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(f"```\n{buf.getvalue()}```\n", encoding="utf-8")
        print(f"\nReport written to {out_path}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: python token_analysis.py <session.jsonl> [<session2.jsonl> ...]", file=sys.stderr)
        sys.exit(1)

    paths = [Path(a) for a in args]
    missing = [p for p in paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"Error: file not found: {p}", file=sys.stderr)
        sys.exit(1)

    sessions = _load_sessions(paths)
    print(f"Loaded {len(sessions)} session(s) from {len(paths)} file(s).")

    stem = paths[0].stem
    out_path = Path("docs/tokendata") / f"{stem}.md"
    analyze(sessions, out_path=out_path)


if __name__ == "__main__":
    main()
