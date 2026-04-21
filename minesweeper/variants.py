from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .board import MinesweeperBoard, Position


class VariantRule(Protocol):
    code: str
    name: str
    description: str

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        ...

    def clue_value(self, board: MinesweeperBoard, row: int, col: int) -> int:
        ...


@dataclass(frozen=True, slots=True)
class StandardVariant:
    code: str = "STD"
    name: str = "Standard"
    description: str = "Classic Minesweeper rules."

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        return True

    def clue_value(self, board: MinesweeperBoard, row: int, col: int) -> int:
        return board.adjacent_mine_count(row, col)


def orthogonal_touching_pairs(board: MinesweeperBoard) -> list[tuple[Position, Position]]:
    pairs: list[tuple[Position, Position]] = []
    for position in board.positions():
        for neighbor in board.orthogonal_positions(position.row, position.col):
            if position.row < neighbor.row or position.col < neighbor.col:
                pairs.append((position, neighbor))
    return pairs
