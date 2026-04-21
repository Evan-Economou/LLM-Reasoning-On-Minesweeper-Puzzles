from __future__ import annotations

from dataclasses import dataclass
from random import Random

from .board import MinesweeperBoard, Position
from .solver import ExactSolutionCounter, LogicSolver, PuzzleObservation
from .variants import STANDARD_VARIANT, VariantRule


@dataclass(frozen=True, slots=True)
class GeneratedPuzzle:
    board: MinesweeperBoard
    variant: VariantRule
    seed: int
    attempt: int
    revealed_seed_cells: tuple[Position, ...]


class DeterministicPuzzleGenerator:
    def __init__(
        self,
        size: int = 5,
        mine_count: int = 5,
        variant: VariantRule = STANDARD_VARIANT,
        seed: int = 0,
        max_attempts: int = 500,
    ) -> None:
        if mine_count <= 0:
            raise ValueError("mine_count must be positive")
        if mine_count >= size * size:
            raise ValueError("mine_count must be smaller than the number of cells")
        self.size = size
        self.mine_count = mine_count
        self.variant = variant
        self.seed = seed
        self.max_attempts = max_attempts
        self._logic_solver = LogicSolver()
        self._solution_counter = ExactSolutionCounter(limit=2)

    def generate(self) -> GeneratedPuzzle:
        for attempt in range(self.max_attempts):
            attempt_seed = self.seed + attempt * 104729
            mines = self._sample_mines(attempt_seed)
            solution_board = MinesweeperBoard(self.size, mines)
            if not self.variant.validate_solution(solution_board):
                continue
            for safe_cells in self._seed_orders(solution_board, attempt_seed):
                for prefix_length in range(1, len(safe_cells) + 1):
                    candidate = MinesweeperBoard(self.size, mines)
                    revealed_seed_cells: list[Position] = []
                    for position in safe_cells[:prefix_length]:
                        revealed_seed_cells.extend(candidate.reveal(position.row, position.col).newly_revealed)

                    if candidate.is_won() or candidate.count_hidden_safe_cells() == 0:
                        continue
                    observation = PuzzleObservation.from_board(candidate, self.variant)
                    if self._solution_counter.count_observation(observation, self.variant) != 1:
                        continue
                    if self.variant.code != STANDARD_VARIANT.code:
                        # If this is uniquely solvable under standard clues too, variant reasoning is not required.
                        if self._solution_counter.count_observation(observation, STANDARD_VARIANT) == 1:
                            continue

                    logic_trial = candidate.clone()
                    if not self._logic_solver.solve(logic_trial, self.variant):
                        continue

                    return GeneratedPuzzle(
                        board=candidate,
                        variant=self.variant,
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

    def _seed_orders(self, board: MinesweeperBoard, attempt_seed: int) -> tuple[list[Position], ...]:
        base = self._ordered_safe_cells(board)
        center = (board.size - 1) / 2.0

        by_center = sorted(
            base,
            key=lambda p: (
                abs(p.row - center) + abs(p.col - center),
                board.adjacent_mine_count(p.row, p.col),
                p.row,
                p.col,
            ),
        )

        by_information = sorted(
            base,
            key=lambda p: (
                -board.adjacent_mine_count(p.row, p.col),
                p.row,
                p.col,
            ),
        )

        rng = Random(attempt_seed ^ 0xA5A5A5A5)
        shuffled = list(base)
        rng.shuffle(shuffled)

        return (base, by_center, by_information, shuffled)
