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

_ACTION_LINE_RE = re.compile(r"^\s*ACTION\s*:\s*(REVEAL|FLAG)\s+([A-Za-z]\d+)\s*[.!]?\s*$", re.IGNORECASE)
_BARE_ACTION_LINE_RE = re.compile(r"^\s*(REVEAL|FLAG)\s+([A-Za-z]\d+)\s*[.!]?\s*$", re.IGNORECASE)
_PROMPT_ECHO_RE = re.compile(
    r"(your previous output could not be parsed|output format\s*:|action\s*:\s*\[reveal\|flag\]|respond now\.)",
    re.IGNORECASE,
)
# More tolerant action parsing: allows variations like "REVEAL A1", "ACTION: REVEAL A1", "A1 REVEAL"
_FLEXIBLE_ACTION_RE = re.compile(r"(REVEAL|FLAG)\s+([A-Za-z]\d+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class LocalModelConfig:
    model_id: str = "EleutherAI/pythia-14m"
    max_new_tokens: int = 32
    temperature: float = 0.0
    top_p: float = 1.0
    repetition_penalty: float = 1.12
    no_repeat_ngram_size: int = 4


@dataclass(frozen=True, slots=True)
class LocalEvalSummary:
    dataset_path: str
    session_log_path: str
    model_id: str
    evaluated: int
    won: int
    lost: int
    aborted: int


class LocalCausalLM:
    def __init__(self, config: LocalModelConfig) -> None:
        self.config = config
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except Exception as exc:  # pragma: no cover - import guidance path
            raise RuntimeError(
                "transformers is required for local model runs. Install with: pip install transformers torch"
            ) from exc

        self._tokenizer = AutoTokenizer.from_pretrained(config.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(config.model_id)
        
        # Detect if model has chat template (instruct/chat models)
        self._has_chat_template = hasattr(self._tokenizer, 'chat_template') and self._tokenizer.chat_template is not None

    def generate(self, prompt: str) -> str:
        # Format prompt using chat template if available
        if self._has_chat_template:
            formatted_prompt = self._tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True
            )
        else:
            formatted_prompt = prompt
        
        encoded = self._tokenizer(formatted_prompt, return_tensors="pt")
        
        # Prepare stop tokens: use eos_token or common stop strings
        stop_token_ids = [self._tokenizer.eos_token_id] if self._tokenizer.eos_token_id is not None else []
        kwargs = {
            "max_new_tokens": self.config.max_new_tokens,
            "do_sample": self.config.temperature > 0.0,
            "temperature": self.config.temperature if self.config.temperature > 0.0 else None,
            "top_p": self.config.top_p,
            "repetition_penalty": self.config.repetition_penalty,
            "no_repeat_ngram_size": self.config.no_repeat_ngram_size,
            "renormalize_logits": True,
            "pad_token_id": self._tokenizer.eos_token_id,
        }
        
        # Add stopping criteria: stop at newline after common prompt endings
        if stop_token_ids:
            kwargs["eos_token_id"] = stop_token_ids
        
        outputs = self._model.generate(**encoded, **kwargs)
        
        generated = outputs[0][encoded["input_ids"].shape[1] :]
        return self._tokenizer.decode(generated, skip_special_tokens=True).strip()


def run_local_llm_dataset(
    dataset_path: str,
    session_log_path: str,
    model_config: LocalModelConfig,
    player_id: str = "pythia14m_local",
    style: str = "coordinates",
    start_index: int = 0,
    limit: int | None = None,
    max_turn_multiplier: int = 3,
    include_cot: bool = True,
    reminder_each_turn: bool = False,
) -> LocalEvalSummary:
    records = read_puzzle_dataset(dataset_path)
    if not records:
        raise RuntimeError("dataset is empty")

    model = LocalCausalLM(model_config)
    encoder = TextBoardEncoder()

    won = 0
    lost = 0
    aborted = 0

    begin = max(start_index, 0)
    end = len(records) if limit is None else min(len(records), begin + limit)

    print(
        f"{'='*70}\n"
        f"Starting LLM puzzle evaluation:\n"
        f"  Model: {model_config.model_id}\n"
        f"  Dataset: {dataset_path} ({len(records)} puzzles total)\n"
        f"  Processing: puzzles {begin + 1} to {end}\n"
        f"  Player ID: {player_id}\n"
        f"{'='*70}\n"
    )

    for idx, record in enumerate(records[begin:end], start=begin + 1):
        board, variant = board_from_record(record)
        started_at = _now_iso()
        start_clock = monotonic()

        baseline_board = board.clone()
        baseline_moves, _ = solve_with_trace(baseline_board, variant)
        turn_limit = max(1, max_turn_multiplier * max(1, len(baseline_moves)))

        system_prompt = _build_system_prompt(variant.code, variant.name, variant.description, include_cot)
        moves: list[dict] = []
        final_failure_category: str | None = None
        parse_fail_turns = 0
        echo_like_outputs = 0

        for turn in range(1, turn_limit + 1):
            if board.status != GameStatus.IN_PROGRESS:
                break

            board_text = encoder.render(board, variant=variant, style=style)
            prompt = _build_turn_prompt(
                system_prompt=system_prompt,
                board_text=board_text,
                turn=turn,
                reminder=variant.description if reminder_each_turn else None,
            )

            parse_failures = 0
            parse_failure_modes: list[str] = []
            action = None
            coord = None
            model_output = ""
            attempt_prompt = prompt
            while parse_failures < 2:
                model_output = model.generate(attempt_prompt)
                parsed = _parse_action(model_output)
                if parsed is not None:
                    action, coord = parsed
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
                        "action": None,
                        "coordinate": None,
                        "changed": False,
                        "hit_mine": False,
                        "status_after": board.status.value,
                        "error": "could not parse ACTION line after 2 attempts",
                        "failure_category": final_failure_category,
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
                            "action": action,
                            "coordinate": coord,
                            "changed": False,
                            "hit_mine": False,
                            "status_after": board.status.value,
                            "error": "invalid move: attempted to act on an already revealed/flagged cell",
                            "failure_category": "invalid_repeated_move",
                        }
                    )
                    break

                moves.append(
                    {
                        "turn": turn,
                        "prompt": prompt,
                        "model_output": model_output,
                        "action": action,
                        "coordinate": coord,
                        "changed": outcome.changed,
                        "hit_mine": outcome.hit_mine,
                        "status_after": board.status.value,
                        "error": None,
                        "failure_category": failure_category,
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
                        "action": action,
                        "coordinate": coord,
                        "changed": False,
                        "hit_mine": False,
                        "status_after": board.status.value,
                        "error": str(exc),
                        "failure_category": "spatial_reasoning_error",
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
            "model": {
                "id": model_config.model_id,
                "max_new_tokens": model_config.max_new_tokens,
                "temperature": model_config.temperature,
                "top_p": model_config.top_p,
                "repetition_penalty": model_config.repetition_penalty,
                "no_repeat_ngram_size": model_config.no_repeat_ngram_size,
            },
            "prompting": {
                "include_cot": include_cot,
                "reminder_each_turn": reminder_each_turn,
            },
            "moves": moves,
        }
        _append_jsonl(payload, session_log_path)

        # Progress output
        outcome = "WON" if won_flag else "LOST" if lost_flag else "ABORTED"
        print(
            f"[{idx}/{end - begin}] {record.puzzle_id:12} ({variant.code:2}) {outcome:12} "
            f"moves={len(moves):2} time={duration_seconds:6.2f}s"
        )

    # Final summary
    total_evaluated = max(0, end - begin)
    win_rate = (won / total_evaluated * 100) if total_evaluated > 0 else 0
    print(
        f"\n{'='*70}\n"
        f"Complete! Evaluated {total_evaluated} puzzles:\n"
        f"  Won: {won} ({win_rate:.1f}%) | Lost: {lost} | Aborted: {aborted}\n"
        f"  Session log: {session_log_path}\n"
        f"{'='*70}"
    )

    return LocalEvalSummary(
        dataset_path=dataset_path,
        session_log_path=session_log_path,
        model_id=model_config.model_id,
        evaluated=max(0, end - begin),
        won=won,
        lost=lost,
        aborted=aborted,
    )


def _build_system_prompt(variant_code: str, variant_name: str, variant_description: str, include_cot: bool) -> str:
    reasoning_instruction = (
        "Think step by step briefly, then provide the action line."
        if include_cot
        else "Do not include reasoning. Provide only the action line."
    )
    return (
        "You are solving a Minesweeper puzzle. Standard Minesweeper rules apply.\n"
        f"Variant [{variant_code}] - {variant_name}: {variant_description}\n"
        f"{reasoning_instruction}\n"
        "Output format: ACTION: [REVEAL|FLAG] [col][row]\n"
        "Examples:\n"
        "```\n"
        "ACTION: REVEAL A1\n"
        "```\n"
        "```\n"
        "ACTION: FLAG C3\n"
        "```"
        "\n"
        "```\n"
        "ACTION: REVEAL E5\n"
        "```\n"
        "```\n"
        "ACTION: FLAG B4\n"
        "```"
    )


def _build_turn_prompt(system_prompt: str, board_text: str, turn: int, reminder: str | None) -> str:
    pieces = [system_prompt]
    if reminder:
        pieces.append(f"Constraint reminder: {reminder}")
    pieces.append(f"Turn: {turn}")
    pieces.append("Current board:")
    pieces.append(board_text)
    pieces.append("Respond now.")
    return "\n\n".join(pieces)


def _build_repair_prompt(previous_output: str) -> str:
    return (
        "Your last response could not be parsed as a move.\n"
        "Return exactly one line in this format: ACTION: [REVEAL|FLAG] [col][row].\n"
        "Do not include any explanation or extra lines.\n\n"
        "Now output exactly one ACTION line."
    )


def _parse_action(text: str) -> tuple[str, str] | None:
    # Parse only full standalone lines (prefer the final line), so echoed prompt text
    # like "format: ACTION: ..." is not mistaken for the model's actual move.
    lines = [line for line in text.splitlines() if line.strip()]
    
    for line in reversed(lines):
        # Strict format: "ACTION: REVEAL A1" or similar
        match = _ACTION_LINE_RE.match(line)
        if match:
            return match.group(1).upper(), match.group(2).upper()
        
        # Bare format: "REVEAL A1"
        fallback = _BARE_ACTION_LINE_RE.match(line)
        if fallback:
            return fallback.group(1).upper(), fallback.group(2).upper()
        
        # Flexible format: allows more variations like "A1 REVEAL" or "Reveal A1"
        # But skip lines that look like prompt echoes
        if not _PROMPT_ECHO_RE.search(line):
            flexible = _FLEXIBLE_ACTION_RE.search(line)
            if flexible:
                return flexible.group(1).upper(), flexible.group(2).upper()
    
    return None


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
