from __future__ import annotations

from dataclasses import dataclass
from random import Random

from .board import MinesweeperBoard, Position
from .solver import ExactSolutionCounter, LogicSolver


@dataclass(frozen=True, slots=True)
class GeneratedPuzzle:
    board: MinesweeperBoard
    seed: int
    attempt: int
    revealed_seed_cells: tuple[Position, ...]


class DeterministicPuzzleGenerator:
    def __init__(
        self,
        size: int = 5,
        mine_count: int = 5,
        seed: int = 0,
        max_attempts: int = 500,
    ) -> None:
        if mine_count <= 0:
            raise ValueError("mine_count must be positive")
        if mine_count >= size * size:
            raise ValueError("mine_count must be smaller than the number of cells")
        self.size = size
        self.mine_count = mine_count
        self.seed = seed
        self.max_attempts = max_attempts
        self._logic_solver = LogicSolver()
        self._solution_counter = ExactSolutionCounter(limit=2)

    def generate(self) -> GeneratedPuzzle:
        for attempt in range(self.max_attempts):
            attempt_seed = self.seed + attempt * 104729
            mines = self._sample_mines(attempt_seed)
            solution_board = MinesweeperBoard(self.size, mines)
            safe_cells = self._ordered_safe_cells(solution_board)

            for prefix_length in range(1, len(safe_cells) + 1):
                candidate = MinesweeperBoard(self.size, mines)
                revealed_seed_cells: list[Position] = []
                for position in safe_cells[:prefix_length]:
                    revealed_seed_cells.extend(candidate.reveal(position.row, position.col).newly_revealed)

                if candidate.is_won() or candidate.count_hidden_safe_cells() == 0:
                    continue
                if self._solution_counter.count(candidate) != 1:
                    continue

                logic_trial = candidate.clone()
                if not self._logic_solver.solve(logic_trial):
                    continue

                return GeneratedPuzzle(
                    board=candidate,
                    seed=attempt_seed,
                    attempt=attempt,
                    revealed_seed_cells=tuple(revealed_seed_cells),
                )

        raise RuntimeError("failed to generate a deterministically solvable puzzle within the attempt limit")

    def _sample_mines(self, attempt_seed: int) -> tuple[tuple[int, int], ...]:
        rng = Random(attempt_seed)
        cells = [(row, col) for row in range(self.size) for col in range(self.size)]
        rng.shuffle(cells)
        return tuple(sorted(cells[: self.mine_count]))

    def _ordered_safe_cells(self, board: MinesweeperBoard) -> list[Position]:
        safe_cells = [position for position in board.positions() if not board.has_mine(position.row, position.col)]
        return sorted(safe_cells, key=lambda position: (board.adjacent_mine_count(position.row, position.col), position.row, position.col))
