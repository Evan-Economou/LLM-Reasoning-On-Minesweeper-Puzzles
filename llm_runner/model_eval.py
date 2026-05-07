from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from time import monotonic

from minesweeper.board import GameStatus
from minesweeper.dataset import board_from_record, coord_to_position, read_puzzle_dataset
from minesweeper.evaluate import solve_with_trace
from minesweeper.text import TextBoardEncoder
from .model_backends import ChatMessage, ChatModelConfig, create_chat_backend

_ACTION_LINE_RE = re.compile(r"^\s*(?:ACTION|Action)\s*:\s*(REVEAL|FLAG)\s+([A-Za-z]\d+)\s*[.!]?\s*$", re.IGNORECASE)
_BARE_ACTION_LINE_RE = re.compile(r"^\s*(REVEAL|FLAG|Reveal|Flag)\s+([A-Za-z]\d+)\s*[.!]?\s*$", re.IGNORECASE)
# Numeric coordinate patterns: "(1,1)", "(1, 1)", "1,1", "1 1"
_ACTION_NUMERIC_RE = re.compile(r"^\s*(?:ACTION|Action)\s*:\s*(REVEAL|FLAG)\s+[\(]?\s*(\d+)\s*,?\s*(\d+)\s*[\)]?\s*[.!]?\s*$", re.IGNORECASE)
_BARE_ACTION_NUMERIC_RE = re.compile(r"^\s*(REVEAL|FLAG|Reveal|Flag)\s+[\(]?\s*(\d+)\s*,?\s*(\d+)\s*[\)]?\s*[.!]?\s*$", re.IGNORECASE)
_PROMPT_ECHO_RE = re.compile(
    r"(your previous output could not be parsed|output format\s*:|action\s*:\s*\[reveal\|flag\]|respond now\.)",
    re.IGNORECASE,
)
# More tolerant action parsing: allows variations like "REVEAL A1", "ACTION: REVEAL A1", "A1 REVEAL"
_FLEXIBLE_ACTION_RE = re.compile(r"(REVEAL|FLAG|Reveal|Flag)\s+([A-Za-z]\d+)", re.IGNORECASE)
_FLEXIBLE_NUMERIC_ACTION_RE = re.compile(r"(REVEAL|FLAG|Reveal|Flag)\s+[\(]?\s*(\d+)\s*,?\s*(\d+)\s*[\)]?", re.IGNORECASE)
_REASONING_LINE_RE = re.compile(r"^\s*REASONING\s*:\s*(.*)$", re.IGNORECASE)


ModelEvalConfig = ChatModelConfig
LocalModelConfig = ModelEvalConfig


@dataclass(frozen=True, slots=True)
class ModelEvalSummary:
    dataset_path: str
    session_log_path: str
    provider: str
    model_id: str
    evaluated: int
    won: int
    lost: int
    aborted: int


def _load_completed_by_variant(resume_from: str) -> dict[str, set[str]]:
    completed: dict[str, set[str]] = {}
    path = Path(resume_from)
    if not path.exists():
        return completed
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                session = json.loads(line)
                pid = session.get("puzzle_id")
                vc = session.get("variant_code")
                if pid and vc:
                    completed.setdefault(vc, set()).add(pid)
            except json.JSONDecodeError:
                pass
    return completed


def run_model_llm_dataset(
    dataset_path: str,
    session_log_path: str,
    model_config: ModelEvalConfig,
    player_id: str = "model",
    style: str = "numeric",
    start_index: int = 0,
    limit: int | None = None,
    max_turn_multiplier: int = 3,
    include_cot: bool = True,
    reminder_each_turn: bool = False,
    resume_from: str | None = None,
) -> ModelEvalSummary:
    records = read_puzzle_dataset(dataset_path)
    if not records:
        raise RuntimeError("dataset is empty")

    # For Anthropic + CoT, use extended thinking instead of in-text CoT instructions.
    use_extended_thinking = include_cot and model_config.provider.lower() == "anthropic"
    if use_extended_thinking and not model_config.extended_thinking:
        from dataclasses import replace
        model_config = replace(model_config, extended_thinking=True)

    model = create_chat_backend(model_config)
    encoder = TextBoardEncoder()
    runtime_base_url = model_config.base_url or ("http://localhost:11434" if model_config.provider == "ollama" else "")

    won = 0
    lost = 0
    aborted = 0

    # Load already-completed puzzle IDs per variant from a prior session log.
    completed_by_variant = _load_completed_by_variant(resume_from) if resume_from else {}

    # Group records by variant, preserving dataset order within each group.
    variant_groups: dict[str, list] = {}
    for record in records:
        variant_groups.setdefault(record.variant_code, []).append(record)

    # Select up to `limit` records per variant starting at `start_index`,
    # skipping any puzzle IDs that already appear in the resume file.
    begin = max(start_index, 0)
    selected_records = []
    skipped_summary: list[str] = []
    for variant_code, group in variant_groups.items():
        completed = completed_by_variant.get(variant_code, set())
        done_count = len(completed)
        if limit is not None and done_count >= limit:
            skipped_summary.append(f"  {variant_code}: skipped entirely ({done_count}/{limit} already done)")
            continue
        remaining_limit = None if limit is None else limit - done_count
        candidates = [r for r in group[begin:] if r.puzzle_id not in completed]
        if remaining_limit is not None:
            candidates = candidates[:remaining_limit]
        if done_count and candidates:
            skipped_summary.append(f"  {variant_code}: resuming after {done_count} completed, running {len(candidates)} more")
        selected_records.extend(candidates)

    total_selected = len(selected_records)
    per_variant_desc = f"puzzles {begin + 1}–{begin + limit}" if limit is not None else f"all puzzles from index {begin}"

    resume_line = f"  Resume file: {resume_from}\n" if resume_from else ""
    skipped_lines = ("\n".join(skipped_summary) + "\n") if skipped_summary else ""
    print(
        f"{'='*70}\n"
        f"Starting LLM puzzle evaluation:\n"
        f"  Provider: {model_config.provider}\n"
        f"  Model: {model_config.model_id}\n"
        f"  Base URL: {runtime_base_url or '(default)'}\n"
        f"  Dataset: {dataset_path} ({len(records)} puzzles total)\n"
        f"  Processing: {per_variant_desc} of each variant ({total_selected} puzzles total)\n"
        f"  Player ID: {player_id}\n"
        f"{resume_line}"
        f"{skipped_lines}"
        f"{'='*70}\n"
    )

    for idx, record in enumerate(selected_records, start=1):
        board, variant = board_from_record(record)
        started_at = _now_iso()
        start_clock = monotonic()

        baseline_board = board.clone()
        baseline_moves, _ = solve_with_trace(baseline_board, variant)
        turn_limit = max(1, max_turn_multiplier * max(1, len(baseline_moves)))

        system_prompt = _build_system_prompt(variant.code, variant.name, variant.description, include_cot, use_extended_thinking)
        moves: list[dict] = []
        final_failure_category: str | None = None
        parse_fail_turns = 0
        echo_like_outputs = 0
        session_input_tokens = 0
        session_output_tokens = 0

        for turn in range(1, turn_limit + 1):
            if board.status != GameStatus.IN_PROGRESS:
                break

            board_text = encoder.render(board, variant=variant, style=style)
            prompt = _build_turn_prompt(
                board_text=board_text,
                turn=turn,
                history=moves,
                reminder=variant.description if reminder_each_turn else None,
            )

            parse_failures = 0
            parse_failure_modes: list[str] = []
            action = None
            coord = None
            parsed_reasoning: str | None = None
            model_output = ""
            thinking_output: str | None = None
            attempt_prompt = prompt
            turn_input_tokens = 0
            turn_output_tokens = 0
            while parse_failures < 2:
                attempt_messages = [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=attempt_prompt),
                ]
                result = model.generate(attempt_messages)
                model_output = result.text
                thinking_output = result.thinking
                if result.usage:
                    turn_input_tokens += result.usage.get("input_tokens", 0)
                    turn_output_tokens += result.usage.get("output_tokens", 0)
                parsed = _parse_action(model_output)
                if parsed is not None:
                    action, coord, parsed_reasoning = parsed
                    prompt = attempt_prompt
                    break
                mode = _classify_unparsed_output(model_output)
                parse_failure_modes.append(mode)
                if mode == "prompt_echo_response":
                    echo_like_outputs += 1
                parse_failures += 1
                if parse_failures < 2:
                    attempt_prompt = _build_repair_prompt(model_output)
                    prompt = attempt_prompt

            turn_usage = {"input_tokens": turn_input_tokens, "output_tokens": turn_output_tokens} if (turn_input_tokens or turn_output_tokens) else None
            session_input_tokens += turn_input_tokens
            session_output_tokens += turn_output_tokens

            if action is None or coord is None:
                parse_fail_turns += 1
                if "prompt_echo_response" in parse_failure_modes:
                    final_failure_category = "prompt_echo_response"
                elif "no_response" in parse_failure_modes:
                    final_failure_category = "no_response"
                else:
                    final_failure_category = "format_failure_loop"
                moves.append(
                    {
                        "turn": turn,
                        "prompt": prompt,
                        "model_output": model_output,
                        "thinking": thinking_output,
                        "action": None,
                        "coordinate": None,
                        "reasoning": parsed_reasoning,
                        "changed": False,
                        "hit_mine": False,
                        "status_after": board.status.value,
                        "error": "could not parse ACTION line after 2 attempts",
                        "failure_category": final_failure_category,
                        "usage": turn_usage,
                    }
                )
                break

            try:
                position = coord_to_position(coord, board.size)
                if action == "REVEAL":
                    outcome = board.reveal(position.row, position.col)
                    failure_category = "clue_misread" if outcome.hit_mine else None
                    if outcome.hit_mine:
                        final_failure_category = failure_category
                else:
                    outcome = board.set_flag(position.row, position.col, True)
                    failure_category = None

                if not outcome.changed:
                    final_failure_category = "invalid_repeated_move"
                    moves.append(
                        {
                            "turn": turn,
                            "prompt": prompt,
                            "model_output": model_output,
                            "thinking": thinking_output,
                            "action": action,
                            "coordinate": coord,
                            "reasoning": parsed_reasoning,
                            "changed": False,
                            "hit_mine": False,
                            "status_after": board.status.value,
                            "error": "invalid move: attempted to act on an already revealed/flagged cell",
                            "failure_category": "invalid_repeated_move",
                            "usage": turn_usage,
                        }
                    )
                    break

                moves.append(
                    {
                        "turn": turn,
                        "prompt": prompt,
                        "model_output": model_output,
                        "thinking": thinking_output,
                        "action": action,
                        "coordinate": coord,
                        "reasoning": parsed_reasoning,
                        "changed": outcome.changed,
                        "hit_mine": outcome.hit_mine,
                        "status_after": board.status.value,
                        "error": None,
                        "failure_category": failure_category,
                        "usage": turn_usage,
                    }
                )

                # Intermediate progress output to avoid long silent gaps.
                move_elapsed_seconds = monotonic() - start_clock
                print(
                    f"  turn={turn:2} action={action:6} coord={coord:4} "
                    f"changed={'Y' if outcome.changed else 'N'} "
                    f"status={board.status.value:11} "
                    f"elapsed={move_elapsed_seconds:7.2f}s"
                )
            except Exception as exc:
                final_failure_category = "spatial_reasoning_error"
                moves.append(
                    {
                        "turn": turn,
                        "prompt": prompt,
                        "model_output": model_output,
                        "thinking": thinking_output,
                        "action": action,
                        "coordinate": coord,
                        "reasoning": parsed_reasoning,
                        "changed": False,
                        "hit_mine": False,
                        "status_after": board.status.value,
                        "error": str(exc),
                        "failure_category": "spatial_reasoning_error",
                        "usage": turn_usage,
                    }
                )
                break

        ended_at = _now_iso()
        duration_seconds = round(monotonic() - start_clock, 3)

        won_flag = board.status == GameStatus.WON
        lost_flag = board.status == GameStatus.LOST
        aborted_flag = not won_flag and not lost_flag

        if won_flag:
            won += 1
        elif lost_flag:
            lost += 1
        else:
            aborted += 1
            if final_failure_category is None:
                final_failure_category = "rule_misinterpretation"

        payload = {
            "session_id": _session_id(player_id, record.puzzle_id),
            "puzzle_id": record.puzzle_id,
            "player_id": player_id,
            "provider": model_config.provider,
            "started_at_utc": started_at,
            "ended_at_utc": ended_at,
            "duration_seconds": duration_seconds,
            "won": won_flag,
            "lost": lost_flag,
            "variant_code": variant.code,
            "move_count": len(moves),
            "turn_limit": turn_limit,
            "failure_category": final_failure_category,
            "diagnostics": {
                "parse_fail_turns": parse_fail_turns,
                "echo_like_outputs": echo_like_outputs,
            },
            "token_usage": {
                "input_tokens": session_input_tokens,
                "output_tokens": session_output_tokens,
            } if (session_input_tokens or session_output_tokens) else None,
            "model": {
                "provider": model_config.provider,
                "id": model_config.model_id,
                "base_url": runtime_base_url,
                "max_new_tokens": model_config.max_new_tokens,
                "temperature": model_config.temperature,
                "top_p": model_config.top_p,
                "repetition_penalty": model_config.repetition_penalty,
                "no_repeat_ngram_size": model_config.no_repeat_ngram_size,
            },
            "prompting": {
                "include_cot": include_cot,
                "extended_thinking": use_extended_thinking,
                "reminder_each_turn": reminder_each_turn,
            },
            "moves": moves,
        }
        _append_jsonl(payload, session_log_path)

        # Progress output
        outcome = "WON" if won_flag else "LOST" if lost_flag else "ABORTED"
        print(
            f"[{idx}/{total_selected}] {record.puzzle_id:12} ({variant.code:2}) {outcome:12} "
            f"moves={len(moves):2} time={duration_seconds:6.2f}s"
        )

    # Final summary
    total_evaluated = total_selected
    win_rate = (won / total_evaluated * 100) if total_evaluated > 0 else 0
    print(
        f"\n{'='*70}\n"
        f"Complete! Evaluated {total_evaluated} puzzles:\n"
        f"  Won: {won} ({win_rate:.1f}%) | Lost: {lost} | Aborted: {aborted}\n"
        f"  Session log: {session_log_path}\n"
        f"{'='*70}"
    )

    return ModelEvalSummary(
        dataset_path=dataset_path,
        session_log_path=session_log_path,
        provider=model_config.provider,
        model_id=model_config.model_id,
        evaluated=total_selected,
        won=won,
        lost=lost,
        aborted=aborted,
    )


LocalEvalSummary = ModelEvalSummary


def run_local_llm_dataset(
    dataset_path: str,
    session_log_path: str,
    model_config: LocalModelConfig,
    player_id: str = "model_runner",
    style: str = "coordinates",
    start_index: int = 0,
    limit: int | None = None,
    max_turn_multiplier: int = 3,
    include_cot: bool = True,
    reminder_each_turn: bool = False,
    resume_from: str | None = None,
) -> ModelEvalSummary:
    # Backward-compatible alias for older imports.
    return run_model_llm_dataset(
        dataset_path=dataset_path,
        session_log_path=session_log_path,
        model_config=model_config,
        player_id=player_id,
        style=style,
        start_index=start_index,
        limit=limit,
        max_turn_multiplier=max_turn_multiplier,
        include_cot=include_cot,
        reminder_each_turn=reminder_each_turn,
        resume_from=resume_from,
    )


def _build_system_prompt(variant_code: str, variant_name: str, variant_description: str, include_cot: bool, extended_thinking: bool = False) -> str:
    if extended_thinking or not include_cot:
        # Extended thinking: the model reasons natively in its thinking block;
        # the visible output should just be concise action + reasoning lines.
        reasoning_instruction = "Do NOT include in-depth chain-of-thought. Provide a concise Action line followed by a concise Reasoning line."
    else:
        reasoning_instruction = "For each move, provide the action first and then the reasoning.\nFormat exactly as:\nAction: REVEAL (row,col)\nReasoning: <brief reasoning>"
    return (
        "Rules: Standard Minesweeper rules apply. You may only REVEAL or FLAG a single cell each turn.\n"
        f"Variant [{variant_code}] - {variant_name}: {variant_description}\n"
        "\n"
        "CRITICAL CONSTRAINT: PICK ONLY HIDDEN CELLS ('#').\n"
        "  Before outputting an action, check the exact target token on the current board.\n"
        "  If the token is not '#', that move is invalid; choose a different coordinate.\n"
        "  Never target '.', '1'-'8', or 'F'.\n"
        "\n"
        "Board Format:\n"
        "  The board is represented as a list of cells in (row,col): token format, where:\n"
        "  - # = hidden (unrevealed) cell - THE ONLY TYPE YOU SHOULD SELECT\n"
        "  - . = revealed safe cell with 0 adjacent mines - DO NOT SELECT\n"
        "  - 1-8 = revealed safe cell with that many adjacent mines - DO NOT SELECT\n"
        "  - F = flagged mine cell - DO NOT SELECT\n"
        "  - Rows are numbered 1-N from top to bottom\n"
        "  - Columns are numbered 1-N from left to right\n"
        "\n"
        "Key Logic:\n"
        "  - A number (e.g., '2') means exactly that many adjacent hidden cells are mines unless the variant rule says otherwise\n"
        "  - A '.' (zero) means all adjacent cells are safe to reveal\n"
        "  - Hidden cells adjacent to many low numbers are safer than those near high numbers\n"
        "  - Do not copy coordinates from the examples; choose the best hidden (#) cell from the current board state\n"
        "\n"
        "Action Format:\n"
        "  - Action: Use REVEAL (row,col) or FLAG (row,col)\n"
        "  - Reasoning: A brief sentence or two explaining why you choose the move.\n"
        f"{reasoning_instruction}\n"
        "Examples (all selecting hidden # cells):\n"
        "```\n"
        "Action: REVEAL (1,3)\n"
        "Reasoning: Cell (1,3) is hidden (#) and adjacent to a '0', so all neighbors are safe.\n"
        "```\n"
        "```\n"
        "Action: REVEAL (4,4)\n"
        "Reasoning: Cell (4,4) is hidden (#) and is the only unaccounted adjacent cell to a '1'.\n"
        "```\n"
        "```\n"
        "Action: FLAG (5,1)\n"
        "Reasoning: Cell (5,1) is hidden (#), and all other neighbors of the '2' at (5,2) are already accounted for.\n"
        "```\n"
    )


def _build_turn_prompt(board_text: str, turn: int, history: list[dict], reminder: str | None) -> str:
    pieces = []
    if reminder:
        pieces.append(f"Constraint reminder: {reminder}")
    pieces.append(f"Turn: {turn}")
    # Action history (previous moves)
    pieces.append("Action History:")
    if history:
        hist_lines: list[str] = []
        for m in history:
            r = m.get("reasoning") or ""
            a = m.get("action") or m.get("model_output") or ""
            coord = m.get("coordinate") or ""
            hist_lines.append(f"Turn {m.get('turn')}: Reasoning: {r} Action: {a} {coord}")
        pieces.append("\n".join(hist_lines))
    else:
        pieces.append("(none)")

    pieces.append("Current board:")
    pieces.append(board_text)
    pieces.append("Respond now. Return exactly two lines: 'Action: REVEAL|FLAG <row,col>' then 'Reasoning: ...'. Target must be '#'.")
    return "\n\n".join(pieces)


def _build_repair_prompt(previous_output: str) -> str:
    return (
        "Your last response could not be parsed as a move.\n"
        "Here was your last response:\n"
        f"{previous_output.strip()}\n\n"
        "IMPORTANT: Choose ONLY a cell currently marked '#'.\n"
        "If your chosen coordinate is not '#', pick another coordinate. Never select revealed cells or 'F'.\n\n"
        "Please return exactly two lines in this format:\n"
        "Action: REVEAL (row,col)\n"
        "Reasoning: <one short sentence>\n\n"
        "Do not include extra text or code blocks.\n\n"
        "Now output the two lines as described."
    )


def _parse_action(text: str) -> tuple[str, str, str] | None:
    # Parse only full standalone lines (prefer the final lines). Expect two lines:
    # Action: REVEAL (1,1)\nReasoning: ...
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    # Find the last line that contains an action
    action_idx = None
    action_match = None
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        # Try letter-based first
        if _ACTION_LINE_RE.match(line) or _BARE_ACTION_LINE_RE.match(line):
            action_idx = i
            action_match = lines[i]
            break
        # Then try numeric-based
        if _ACTION_NUMERIC_RE.match(line) or _BARE_ACTION_NUMERIC_RE.match(line):
            action_idx = i
            action_match = lines[i]
            break
        if not _PROMPT_ECHO_RE.search(line):
            # Try letter-based flexible
            flexible = _FLEXIBLE_ACTION_RE.search(line)
            if flexible:
                action_idx = i
                action_match = lines[i]
                break
            # Try numeric-based flexible
            flexible_numeric = _FLEXIBLE_NUMERIC_ACTION_RE.search(line)
            if flexible_numeric:
                action_idx = i
                action_match = lines[i]
                break

    if action_idx is None:
        return None

    # Parse action and coord from the matched line
    # Try letter-based patterns first
    m = _ACTION_LINE_RE.match(action_match)
    if m:
        act, coord = m.group(1).upper(), m.group(2).upper()
    else:
        m2 = _BARE_ACTION_LINE_RE.match(action_match)
        if m2:
            act, coord = m2.group(1).upper(), m2.group(2).upper()
        else:
            flex = _FLEXIBLE_ACTION_RE.search(action_match)
            if flex:
                act, coord = flex.group(1).upper(), flex.group(2).upper()
            else:
                # Try numeric patterns
                m3 = _ACTION_NUMERIC_RE.match(action_match)
                if m3:
                    act, row, col = m3.group(1).upper(), m3.group(2), m3.group(3)
                    coord = f"{row},{col}"
                else:
                    m4 = _BARE_ACTION_NUMERIC_RE.match(action_match)
                    if m4:
                        act, row, col = m4.group(1).upper(), m4.group(2), m4.group(3)
                        coord = f"{row},{col}"
                    else:
                        flex_numeric = _FLEXIBLE_NUMERIC_ACTION_RE.search(action_match)
                        if flex_numeric:
                            act, row, col = flex_numeric.group(1).upper(), flex_numeric.group(2), flex_numeric.group(3)
                            coord = f"{row},{col}"
                        else:
                            return None

    # Extract reasoning: look for any line starting with 'Reasoning:'
    reasoning = ""
    for j in range(len(lines) - 1, -1, -1):
        rl = lines[j]
        rr = _REASONING_LINE_RE.match(rl)
        if rr:
            reasoning = rr.group(1).strip()
            break

    return act, coord, reasoning


def _classify_unparsed_output(text: str) -> str:
    if not text.strip():
        return "no_response"
    if _PROMPT_ECHO_RE.search(text):
        return "prompt_echo_response"
    return "invalid_move_format"


def _append_jsonl(payload: dict, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _session_id(player_id: str, puzzle_id: str) -> str:
    payload = f"{player_id}|{puzzle_id}|{_now_iso()}"
    return sha1(payload.encode("utf-8")).hexdigest()[:16]
