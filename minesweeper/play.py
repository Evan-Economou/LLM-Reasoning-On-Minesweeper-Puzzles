from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from time import monotonic

from .board import GameStatus, MinesweeperBoard
from .dataset import SessionMove, SessionRecord, append_session_record, coord_to_position
from .text import TextBoardEncoder
from .variants import VariantRule


@dataclass(frozen=True, slots=True)
class PlayConfig:
    player_id: str
    session_log_path: str


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _session_id(player_id: str, puzzle_id: str) -> str:
    payload = f"{player_id}|{puzzle_id}|{_now_iso()}"
    return sha1(payload.encode("utf-8")).hexdigest()[:16]


def run_interactive_session(
    puzzle_id: str,
    board: MinesweeperBoard,
    variant: VariantRule,
    config: PlayConfig,
) -> SessionRecord:
    encoder = TextBoardEncoder()
    started_at = _now_iso()
    start_clock = monotonic()
    moves: list[SessionMove] = []

    print(f"Puzzle {puzzle_id} | Variant {variant.code} ({variant.name}) | Mines {board.mine_count}")
    print("Commands: reveal B3 | flag B3 | unflag B3 | show | quit")

    while board.status == GameStatus.IN_PROGRESS:
        print()
        print(encoder.render(board, variant=variant, style="coordinates"))
        raw = input("move> ").strip()
        if not raw:
            continue

        lower = raw.lower()
        if lower in {"show", "s"}:
            continue
        if lower in {"quit", "q", "exit"}:
            break

        parts = raw.split()
        if len(parts) != 2:
            print("Invalid command. Expected: <action> <coord>, e.g. reveal B3")
            continue

        action = parts[0].lower()
        coord = parts[1].upper()
        try:
            position = coord_to_position(coord, board.size)
            if action in {"reveal", "r"}:
                outcome = board.reveal(position.row, position.col)
                moves.append(
                    SessionMove(
                        turn=len(moves) + 1,
                        action="REVEAL",
                        coordinate=coord,
                        changed=outcome.changed,
                        hit_mine=outcome.hit_mine,
                        status_after=board.status.value,
                    )
                )
            elif action in {"flag", "f"}:
                outcome = board.set_flag(position.row, position.col, True)
                moves.append(
                    SessionMove(
                        turn=len(moves) + 1,
                        action="FLAG",
                        coordinate=coord,
                        changed=outcome.changed,
                        hit_mine=False,
                        status_after=board.status.value,
                    )
                )
            elif action in {"unflag", "u"}:
                outcome = board.set_flag(position.row, position.col, False)
                moves.append(
                    SessionMove(
                        turn=len(moves) + 1,
                        action="UNFLAG",
                        coordinate=coord,
                        changed=outcome.changed,
                        hit_mine=False,
                        status_after=board.status.value,
                    )
                )
            else:
                print("Unknown action. Use reveal, flag, or unflag.")
        except Exception as exc:
            print(f"Move rejected: {exc}")
            moves.append(
                SessionMove(
                    turn=len(moves) + 1,
                    action=action.upper(),
                    coordinate=coord,
                    changed=False,
                    hit_mine=False,
                    status_after=board.status.value,
                    error=str(exc),
                )
            )

    ended_at = _now_iso()
    duration_seconds = round(monotonic() - start_clock, 3)
    won = board.status == GameStatus.WON
    lost = board.status == GameStatus.LOST

    print()
    print(encoder.render(board, variant=variant, style="coordinates"))
    if won:
        print("Result: WON")
    elif lost:
        print("Result: LOST")
    else:
        print("Result: ABORTED")

    record = SessionRecord(
        session_id=_session_id(config.player_id, puzzle_id),
        puzzle_id=puzzle_id,
        player_id=config.player_id,
        started_at_utc=started_at,
        ended_at_utc=ended_at,
        duration_seconds=duration_seconds,
        won=won,
        lost=lost,
        variant_code=variant.code,
        move_count=len(moves),
        moves=moves,
    )
    append_session_record(record, config.session_log_path)
    return record
