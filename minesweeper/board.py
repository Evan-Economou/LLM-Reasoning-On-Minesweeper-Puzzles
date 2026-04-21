from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Iterator, Sequence


@dataclass(frozen=True, slots=True)
class Position:
    row: int
    col: int


@dataclass(slots=True)
class Cell:
    mine: bool = False
    revealed: bool = False
    flagged: bool = False


@dataclass(frozen=True, slots=True)
class MoveOutcome:
    changed: bool
    hit_mine: bool = False
    newly_revealed: tuple[Position, ...] = ()


class GameStatus(Enum):
    IN_PROGRESS = "in_progress"
    WON = "won"
    LOST = "lost"


class MinesweeperBoard:
    def __init__(self, size: int = 5, mines: Iterable[tuple[int, int]] | None = None) -> None:
        if size <= 0:
            raise ValueError("size must be positive")
        self.size = size
        mine_set = {Position(row, col) for row, col in mines or []}
        for position in mine_set:
            self._validate_position(position.row, position.col)
        self._cells = [[Cell() for _ in range(size)] for _ in range(size)]
        for position in mine_set:
            self._cells[position.row][position.col].mine = True
        self._mine_count = len(mine_set)
        self._lost = False

    @property
    def mine_count(self) -> int:
        return self._mine_count

    @property
    def status(self) -> GameStatus:
        if self._lost:
            return GameStatus.LOST
        if self.is_won():
            return GameStatus.WON
        return GameStatus.IN_PROGRESS

    def clone(self) -> "MinesweeperBoard":
        cloned = MinesweeperBoard(self.size)
        cloned._mine_count = self._mine_count
        cloned._lost = self._lost
        for row in range(self.size):
            for col in range(self.size):
                source = self._cells[row][col]
                cloned._cells[row][col] = Cell(
                    mine=source.mine,
                    revealed=source.revealed,
                    flagged=source.flagged,
                )
        return cloned

    def _validate_position(self, row: int, col: int) -> None:
        if row < 0 or col < 0 or row >= self.size or col >= self.size:
            raise IndexError(f"position {(row, col)} is out of bounds for {self.size}x{self.size} board")

    def positions(self) -> Iterator[Position]:
        for row in range(self.size):
            for col in range(self.size):
                yield Position(row, col)

    def adjacent_positions(self, row: int, col: int) -> tuple[Position, ...]:
        self._validate_position(row, col)
        adjacent: list[Position] = []
        for delta_row in (-1, 0, 1):
            for delta_col in (-1, 0, 1):
                if delta_row == 0 and delta_col == 0:
                    continue
                next_row = row + delta_row
                next_col = col + delta_col
                if 0 <= next_row < self.size and 0 <= next_col < self.size:
                    adjacent.append(Position(next_row, next_col))
        return tuple(adjacent)

    def orthogonal_positions(self, row: int, col: int) -> tuple[Position, ...]:
        self._validate_position(row, col)
        candidates = (
            Position(row - 1, col),
            Position(row + 1, col),
            Position(row, col - 1),
            Position(row, col + 1),
        )
        return tuple(position for position in candidates if 0 <= position.row < self.size and 0 <= position.col < self.size)

    def cell(self, row: int, col: int) -> Cell:
        self._validate_position(row, col)
        return self._cells[row][col]

    def has_mine(self, row: int, col: int) -> bool:
        return self.cell(row, col).mine

    def is_revealed(self, row: int, col: int) -> bool:
        return self.cell(row, col).revealed

    def is_flagged(self, row: int, col: int) -> bool:
        return self.cell(row, col).flagged

    def hidden_positions(self) -> tuple[Position, ...]:
        return tuple(position for position in self.positions() if not self.cell(position.row, position.col).revealed)

    def revealed_positions(self) -> tuple[Position, ...]:
        return tuple(position for position in self.positions() if self.cell(position.row, position.col).revealed)

    def flagged_positions(self) -> tuple[Position, ...]:
        return tuple(position for position in self.positions() if self.cell(position.row, position.col).flagged)

    def adjacent_mine_count(self, row: int, col: int) -> int:
        return sum(1 for position in self.adjacent_positions(row, col) if self.has_mine(position.row, position.col))

    def revealed_clue(self, row: int, col: int) -> int:
        cell = self.cell(row, col)
        if not cell.revealed or cell.mine:
            raise ValueError("clue is only available for revealed safe cells")
        return self.adjacent_mine_count(row, col)

    def reveal(self, row: int, col: int) -> MoveOutcome:
        self._validate_position(row, col)
        cell = self._cells[row][col]
        if cell.flagged:
            raise ValueError("cannot reveal a flagged cell")
        if cell.revealed:
            return MoveOutcome(changed=False)

        cell.revealed = True
        newly_revealed = [Position(row, col)]
        if cell.mine:
            self._lost = True
            return MoveOutcome(changed=True, hit_mine=True, newly_revealed=tuple(newly_revealed))

        queue: deque[Position] = deque()
        if self.adjacent_mine_count(row, col) == 0:
            queue.append(Position(row, col))

        seen = {Position(row, col)}
        while queue:
            position = queue.popleft()
            for neighbor in self.adjacent_positions(position.row, position.col):
                neighbor_cell = self.cell(neighbor.row, neighbor.col)
                if neighbor in seen or neighbor_cell.revealed or neighbor_cell.flagged or neighbor_cell.mine:
                    continue
                neighbor_cell.revealed = True
                newly_revealed.append(neighbor)
                seen.add(neighbor)
                if self.adjacent_mine_count(neighbor.row, neighbor.col) == 0:
                    queue.append(neighbor)

        return MoveOutcome(changed=True, newly_revealed=tuple(newly_revealed))

    def set_flag(self, row: int, col: int, flagged: bool = True) -> MoveOutcome:
        self._validate_position(row, col)
        cell = self._cells[row][col]
        if cell.revealed:
            raise ValueError("cannot flag a revealed cell")
        if cell.flagged == flagged:
            return MoveOutcome(changed=False)
        cell.flagged = flagged
        return MoveOutcome(changed=True)

    def toggle_flag(self, row: int, col: int) -> MoveOutcome:
        return self.set_flag(row, col, not self.cell(row, col).flagged)

    def is_won(self) -> bool:
        if self._lost:
            return False
        for position in self.positions():
            cell = self.cell(position.row, position.col)
            if not cell.mine and not cell.revealed:
                return False
        return True

    def is_lost(self) -> bool:
        return self._lost

    def visible_token(self, row: int, col: int, show_solution: bool = False) -> str:
        cell = self.cell(row, col)
        if cell.revealed:
            if cell.mine:
                return "*"
            clue = self.adjacent_mine_count(row, col)
            return "." if clue == 0 else str(clue)
        if cell.flagged:
            return "F"
        if show_solution and cell.mine:
            return "M"
        return "#"

    def visible_grid(self, show_solution: bool = False) -> tuple[tuple[str, ...], ...]:
        return tuple(
            tuple(self.visible_token(row, col, show_solution=show_solution) for col in range(self.size))
            for row in range(self.size)
        )

    def clue_constraints(self) -> tuple[tuple[Position, frozenset[Position], int], ...]:
        constraints: list[tuple[Position, frozenset[Position], int]] = []
        for position in self.revealed_positions():
            cell = self.cell(position.row, position.col)
            if cell.mine:
                continue
            hidden_neighbors = [
                neighbor
                for neighbor in self.adjacent_positions(position.row, position.col)
                if not self.cell(neighbor.row, neighbor.col).revealed and not self.cell(neighbor.row, neighbor.col).flagged
            ]
            flagged_neighbors = sum(1 for neighbor in self.adjacent_positions(position.row, position.col) if self.cell(neighbor.row, neighbor.col).flagged)
            required_mines = self.adjacent_mine_count(position.row, position.col) - flagged_neighbors
            constraints.append((position, frozenset(hidden_neighbors), required_mines))
        return tuple(constraints)

    def count_hidden_safe_cells(self) -> int:
        return sum(1 for position in self.positions() if not self.cell(position.row, position.col).revealed and not self.cell(position.row, position.col).mine)

    def count_revealed_safe_cells(self) -> int:
        return sum(1 for position in self.positions() if self.cell(position.row, position.col).revealed and not self.cell(position.row, position.col).mine)

    def count_hidden_cells(self) -> int:
        return sum(1 for position in self.positions() if not self.cell(position.row, position.col).revealed)
