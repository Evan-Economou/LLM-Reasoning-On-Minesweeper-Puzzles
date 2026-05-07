"""Shared utilities for loading and flattening session JSONL files."""

import json
from pathlib import Path

import pandas as pd


VARIANT_LABELS = {
    "STD": "Standard",
    "Q": "Quad",
    "C": "Connected",
    "T": "Triplet",
    "O": "Outside",
    "D": "Dual",
    "S": "Snake",
    "R": "RowCol",
    "H": "Horiz",
    "P": "Partition",
    "L": "Liar",
    "X": "Cross",
}

FAILURE_LABELS = {
    "clue_misread": "Clue Misread",
    "format_failure_loop": "Format Failure",
    "prompt_echo_response": "Prompt Echo",
    "no_response": "No Response",
    "invalid_repeated_move": "Repeated Move",
    "spatial_reasoning_error": "Spatial Error",
    "rule_misinterpretation": "Rule Misread",
}


def load_sessions(path: str | Path) -> pd.DataFrame:
    """Load a session JSONL file into a flat DataFrame (one row per session)."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            records.append({
                "session_id": s.get("session_id"),
                "puzzle_id": s.get("puzzle_id"),
                "player_id": s.get("player_id"),
                "variant_code": s.get("variant_code"),
                "variant_label": VARIANT_LABELS.get(s.get("variant_code", ""), s.get("variant_code", "")),
                "won": bool(s.get("won")),
                "lost": bool(s.get("lost")),
                "move_count": s.get("move_count", 0),
                "turn_limit": s.get("turn_limit", 0),
                "failure_category": s.get("failure_category"),
                "duration_seconds": s.get("duration_seconds"),
                "input_tokens": (s.get("token_usage") or {}).get("input_tokens", 0),
                "output_tokens": (s.get("token_usage") or {}).get("output_tokens", 0),
                "model_id": (s.get("model") or {}).get("id"),
                "provider": s.get("provider"),
                "extended_thinking": (s.get("prompting") or {}).get("extended_thinking", False),
                "include_cot": (s.get("prompting") or {}).get("include_cot", False),
                "moves": s.get("moves", []),
            })
    df = pd.DataFrame(records)
    df["budget_used"] = df["move_count"] / df["turn_limit"].replace(0, pd.NA)
    df["total_tokens"] = df["input_tokens"] + df["output_tokens"]
    df["outcome"] = df["won"].map({True: "Win", False: "Loss"})
    return df


def load_moves(path: str | Path) -> pd.DataFrame:
    """Load all moves across all sessions into a flat DataFrame (one row per move)."""
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            session_id = s.get("session_id")
            variant = s.get("variant_code")
            won = bool(s.get("won"))
            for m in s.get("moves", []):
                rows.append({
                    "session_id": session_id,
                    "variant_code": variant,
                    "variant_label": VARIANT_LABELS.get(variant, variant),
                    "won": won,
                    "turn": m.get("turn"),
                    "action": m.get("action"),
                    "hit_mine": bool(m.get("hit_mine")),
                    "changed": bool(m.get("changed")),
                    "status_after": m.get("status_after"),
                    "failure_category": m.get("failure_category"),
                    "input_tokens": (m.get("usage") or {}).get("input_tokens", 0),
                    "output_tokens": (m.get("usage") or {}).get("output_tokens", 0),
                })
    return pd.DataFrame(rows)
