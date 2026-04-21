from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from time import monotonic

from .board import GameStatus, MinesweeperBoard, Position
from .dataset import SessionMove, SessionRecord, append_session_record, board_from_record, read_puzzle_dataset
from .solver import PuzzleObservation, SolutionEnumerator
from .variants import VariantRule


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    dataset_path: str
    player_id: str
    evaluated: int
    won: int
    lost: int


def solve_with_trace(board: MinesweeperBoard, variant: VariantRule, max_iterations: int = 64) -> tuple[list[SessionMove], GameStatus]:
    enumerator = SolutionEnumerator()
    moves: list[SessionMove] = []

    for _ in range(max_iterations):
        if board.status != GameStatus.IN_PROGRESS:
            break

        observation = PuzzleObservation.from_board(board, variant)
        solutions = enumerator.all_solutions(observation, variant)
        if not solutions:
            break

        hidden_cells = [
            position
            for position in board.hidden_positions()
            if position not in board.flagged_positions()
        ]
        if not hidden_cells:
            break

        forced_mines = {
            position
            for position in hidden_cells
            if all(position in solution for solution in solutions)
        }
        forced_safe = {
            position
            for position in hidden_cells
            if all(position not in solution for solution in solutions)
        }

        if not forced_mines and not forced_safe:
            break

        for position in sorted(forced_mines, key=lambda item: (item.row, item.col)):
            outcome = board.set_flag(position.row, position.col, True)
            moves.append(
                SessionMove(
                    turn=len(moves) + 1,
                    action="FLAG",
                    coordinate=_position_to_coord(position),
                    changed=outcome.changed,
                    hit_mine=False,
                    status_after=board.status.value,
                )
            )

        for position in sorted(forced_safe, key=lambda item: (item.row, item.col)):
            outcome = board.reveal(position.row, position.col)
            moves.append(
                SessionMove(
                    turn=len(moves) + 1,
                    action="REVEAL",
                    coordinate=_position_to_coord(position),
                    changed=outcome.changed,
                    hit_mine=outcome.hit_mine,
                    status_after=board.status.value,
                )
            )

    return moves, board.status


def evaluate_dataset(dataset_path: str, session_log_path: str, player_id: str = "solver_baseline") -> EvaluationSummary:
    records = read_puzzle_dataset(dataset_path)
    won = 0
    lost = 0

    for record in records:
        board, variant = board_from_record(record)
        started_at = _now_iso()
        start_clock = monotonic()
        moves, status = solve_with_trace(board, variant)
        ended_at = _now_iso()
        duration_seconds = round(monotonic() - start_clock, 3)
        if status == GameStatus.WON:
            won += 1
        elif status == GameStatus.LOST:
            lost += 1

        session = SessionRecord(
            session_id=_session_id(player_id, record.puzzle_id),
            puzzle_id=record.puzzle_id,
            player_id=player_id,
            started_at_utc=started_at,
            ended_at_utc=ended_at,
            duration_seconds=duration_seconds,
            won=status == GameStatus.WON,
            lost=status == GameStatus.LOST,
            variant_code=variant.code,
            move_count=len(moves),
            moves=moves,
        )
        append_session_record(session, session_log_path)

    return EvaluationSummary(
        dataset_path=dataset_path,
        player_id=player_id,
        evaluated=len(records),
        won=won,
        lost=lost,
    )


def _position_to_coord(position: Position) -> str:
    return f"{chr(ord('A') + position.col)}{position.row + 1}"


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).isoformat()


def _session_id(player_id: str, puzzle_id: str) -> str:
    from datetime import datetime, timezone

    payload = f"{player_id}|{puzzle_id}|{datetime.now(tz=timezone.utc).isoformat()}"
    return sha1(payload.encode("utf-8")).hexdigest()[:16]
