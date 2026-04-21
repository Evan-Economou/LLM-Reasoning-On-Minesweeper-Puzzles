from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .board import MinesweeperBoard, Position
from .variants import STANDARD_VARIANT, VariantRule


@dataclass(frozen=True, slots=True)
class PuzzleObservation:
    size: int
    mine_count: int
    revealed_safe: frozenset[Position]
    flagged: frozenset[Position]
    clues: dict[Position, int]

    @classmethod
    def from_board(cls, board: MinesweeperBoard, variant: VariantRule = STANDARD_VARIANT) -> "PuzzleObservation":
        revealed_safe = frozenset(
            position
            for position in board.revealed_positions()
            if not board.has_mine(position.row, position.col)
        )
        clues = {
            position: variant.clue_value(board, position.row, position.col)
            for position in revealed_safe
        }
        return cls(
            size=board.size,
            mine_count=board.mine_count,
            revealed_safe=revealed_safe,
            flagged=frozenset(board.flagged_positions()),
            clues=clues,
        )


class SolutionEnumerator:
    def count_solutions(
        self,
        observation: PuzzleObservation,
        variant: VariantRule,
        limit: int = 2,
    ) -> int:
        count = 0
        for _ in self._iter_solutions(observation, variant):
            count += 1
            if count >= limit:
                return limit
        return count

    def all_solutions(
        self,
        observation: PuzzleObservation,
        variant: VariantRule,
    ) -> list[frozenset[Position]]:
        return list(self._iter_solutions(observation, variant))

    def _iter_solutions(
        self,
        observation: PuzzleObservation,
        variant: VariantRule,
    ):
        all_positions = {
            Position(row, col)
            for row in range(observation.size)
            for col in range(observation.size)
        }
        hidden_unflagged = sorted(
            all_positions - set(observation.revealed_safe) - set(observation.flagged),
            key=lambda pos: (pos.row, pos.col),
        )
        remaining_mines = observation.mine_count - len(observation.flagged)
        if remaining_mines < 0 or remaining_mines > len(hidden_unflagged):
            return

        flagged = set(observation.flagged)
        for combo in combinations(hidden_unflagged, remaining_mines):
            mine_set = flagged | set(combo)
            board = MinesweeperBoard(observation.size, [(p.row, p.col) for p in mine_set])
            if not variant.validate_solution(board):
                continue
            if not self._clues_match(board, observation, variant):
                continue
            yield frozenset(mine_set)

    def _clues_match(
        self,
        board: MinesweeperBoard,
        observation: PuzzleObservation,
        variant: VariantRule,
    ) -> bool:
        for position in observation.revealed_safe:
            if board.has_mine(position.row, position.col):
                return False
            displayed = observation.clues[position]
            if not variant.clue_matches(board, position.row, position.col, displayed):
                return False
        return True


@dataclass(frozen=True, slots=True)
class ExactSolutionCounter:
    limit: int = 2

    def count(self, board: MinesweeperBoard, variant: VariantRule = STANDARD_VARIANT) -> int:
        observation = PuzzleObservation.from_board(board, variant)
        return self.count_observation(observation, variant)

    def count_observation(self, observation: PuzzleObservation, variant: VariantRule) -> int:
        enumerator = SolutionEnumerator()
        return enumerator.count_solutions(observation, variant, limit=self.limit)


@dataclass
class LogicSolver:
    max_iterations: int = 64

    def solve(self, board: MinesweeperBoard, variant: VariantRule = STANDARD_VARIANT) -> bool:
        enumerator = SolutionEnumerator()

        for _ in range(self.max_iterations):
            if board.is_won() or board.is_lost():
                return board.is_won()

            observation = PuzzleObservation.from_board(board, variant)
            solutions = enumerator.all_solutions(observation, variant)
            if not solutions:
                return False

            hidden_cells = [
                position
                for position in board.hidden_positions()
                if position not in board.flagged_positions()
            ]
            if not hidden_cells:
                return board.is_won()

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

            changed = False
            for position in forced_mines:
                changed |= board.set_flag(position.row, position.col, True).changed
            for position in forced_safe:
                changed |= board.reveal(position.row, position.col).changed

            if not changed:
                break

        return board.is_won()
