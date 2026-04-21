from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Iterable

from .board import MinesweeperBoard, Position
from .generator import GeneratedPuzzle
from .text import TextBoardEncoder
from .variants import VariantRule, get_variant


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def position_to_coord(position: Position) -> str:
    return f"{chr(ord('A') + position.col)}{position.row + 1}"


def coord_to_position(coord: str, size: int) -> Position:
    stripped = coord.strip().upper()
    if len(stripped) < 2:
        raise ValueError(f"invalid coordinate: {coord}")
    col_char = stripped[0]
    row_part = stripped[1:]
    if not col_char.isalpha() or not row_part.isdigit():
        raise ValueError(f"invalid coordinate: {coord}")
    col = ord(col_char) - ord("A")
    row = int(row_part) - 1
    if not (0 <= row < size and 0 <= col < size):
        raise ValueError(f"coordinate out of bounds: {coord}")
    return Position(row=row, col=col)


@dataclass(frozen=True, slots=True)
class PuzzleRecord:
    puzzle_id: str
    created_at_utc: str
    size: int
    mine_count: int
    variant_code: str
    variant_name: str
    seed: int
    attempt: int
    mine_positions: list[str]
    initial_revealed_positions: list[str]
    initial_board_coordinates: str = ""


@dataclass(frozen=True, slots=True)
class SessionMove:
    turn: int
    action: str
    coordinate: str
    changed: bool
    hit_mine: bool
    status_after: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: str
    puzzle_id: str
    player_id: str
    started_at_utc: str
    ended_at_utc: str
    duration_seconds: float
    won: bool
    lost: bool
    variant_code: str
    move_count: int
    moves: list[SessionMove]


def build_puzzle_record(generated: GeneratedPuzzle) -> PuzzleRecord:
    encoder = TextBoardEncoder()
    mine_positions = sorted(
        position_to_coord(position)
        for position in generated.board.positions()
        if generated.board.has_mine(position.row, position.col)
    )
    revealed = sorted({position_to_coord(position) for position in generated.revealed_seed_cells})
    fingerprint = "|".join(
        [
            generated.variant.code,
            str(generated.board.size),
            str(generated.board.mine_count),
            ",".join(mine_positions),
            ",".join(revealed),
        ]
    )
    puzzle_id = sha1(fingerprint.encode("utf-8")).hexdigest()[:16]
    return PuzzleRecord(
        puzzle_id=puzzle_id,
        created_at_utc=_now_iso(),
        size=generated.board.size,
        mine_count=generated.board.mine_count,
        variant_code=generated.variant.code,
        variant_name=generated.variant.name,
        seed=generated.seed,
        attempt=generated.attempt,
        mine_positions=mine_positions,
        initial_revealed_positions=revealed,
        initial_board_coordinates=encoder.render(generated.board, variant=generated.variant, style="coordinates"),
    )


def board_from_record(record: PuzzleRecord) -> tuple[MinesweeperBoard, VariantRule]:
    variant = get_variant(record.variant_code)
    mine_positions = [coord_to_position(value, record.size) for value in record.mine_positions]
    board = MinesweeperBoard(record.size, [(position.row, position.col) for position in mine_positions])
    for coord in record.initial_revealed_positions:
        position = coord_to_position(coord, record.size)
        board.reveal(position.row, position.col)
    return board, variant


def write_puzzle_dataset(records: Iterable[PuzzleRecord], output_path: str, append: bool = False) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def read_puzzle_dataset(dataset_path: str) -> list[PuzzleRecord]:
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"dataset not found: {dataset_path}")
    records: list[PuzzleRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            payload.setdefault("initial_board_coordinates", "")
            records.append(PuzzleRecord(**payload))
    return records


def append_session_record(record: SessionRecord, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
