from __future__ import annotations

from dataclasses import dataclass
from math import comb
from typing import Iterable

from .board import MinesweeperBoard, Position


@dataclass(frozen=True, slots=True)
class ExactSolutionCounter:
    limit: int = 2

    def count(self, board: MinesweeperBoard) -> int:
        if board.is_lost():
            return 0

        flagged_positions = set(board.flagged_positions())
        revealed_positions = set(board.revealed_positions())
        if any(board.has_mine(position.row, position.col) and position in revealed_positions for position in revealed_positions):
            return 0

        constraints: list[tuple[frozenset[Position], int]] = []
        constrained_cells: set[Position] = set()
        for _, hidden_neighbors, required_mines in board.clue_constraints():
            if required_mines < 0 or required_mines > len(hidden_neighbors):
                return 0
            if hidden_neighbors:
                constraints.append((hidden_neighbors, required_mines))
                constrained_cells.update(hidden_neighbors)

        unknown_cells = {
            position
            for position in board.positions()
            if position not in revealed_positions and position not in flagged_positions
        }
        free_cells = unknown_cells - constrained_cells
        remaining_mines = board.mine_count - len(flagged_positions)
        if remaining_mines < 0 or remaining_mines > len(unknown_cells):
            return 0

        solution_count = self._search(constraints, tuple(sorted(constrained_cells, key=lambda position: (position.row, position.col))), free_cells, remaining_mines, {})
        return min(solution_count, self.limit)

    def _search(
        self,
        constraints: list[tuple[frozenset[Position], int]],
        constrained_order: tuple[Position, ...],
        free_cells: set[Position],
        remaining_mines: int,
        assignments: dict[Position, bool],
    ) -> int:
        propagated_assignments, propagated_constraints, propagated_remaining_mines = self._propagate(constraints, remaining_mines, assignments)
        if propagated_assignments is None:
            return 0

        unassigned_constrained = [
            position for position in constrained_order if position not in propagated_assignments
        ]
        if not unassigned_constrained:
            free_count = len(free_cells)
            if propagated_remaining_mines < 0 or propagated_remaining_mines > free_count:
                return 0
            return comb(free_count, propagated_remaining_mines)

        best_position = self._choose_branch_cell(propagated_constraints, unassigned_constrained)
        if best_position is None:
            free_count = len(free_cells)
            if propagated_remaining_mines < 0 or propagated_remaining_mines > free_count:
                return 0
            return comb(free_count, propagated_remaining_mines)

        total = 0
        for value in (False, True):
            next_assignments = dict(propagated_assignments)
            next_assignments[best_position] = value
            next_remaining_mines = propagated_remaining_mines - int(value)
            total += self._search(propagated_constraints, constrained_order, free_cells, next_remaining_mines, next_assignments)
            if total >= self.limit:
                return self.limit
        return total

    def _propagate(
        self,
        constraints: list[tuple[frozenset[Position], int]],
        remaining_mines: int,
        assignments: dict[Position, bool],
    ) -> tuple[dict[Position, bool] | None, list[tuple[frozenset[Position], int]], int]:
        current_assignments = dict(assignments)
        current_remaining_mines = remaining_mines
        current_constraints = constraints

        while True:
            updated = False
            next_constraints: list[tuple[frozenset[Position], int]] = []
            for cells, required_mines in current_constraints:
                assigned_mines = sum(1 for position in cells if current_assignments.get(position) is True)
                assigned_safe = sum(1 for position in cells if current_assignments.get(position) is False)
                unassigned = frozenset(position for position in cells if position not in current_assignments)
                remaining_required = required_mines - assigned_mines
                if remaining_required < 0 or remaining_required > len(unassigned):
                    return None, [], 0
                if not unassigned:
                    if remaining_required != 0:
                        return None, [], 0
                    continue
                if remaining_required == 0:
                    for position in unassigned:
                        if position in current_assignments and current_assignments[position] is True:
                            return None, [], 0
                        if position not in current_assignments:
                            current_assignments[position] = False
                            updated = True
                    continue
                if remaining_required == len(unassigned):
                    for position in unassigned:
                        if position in current_assignments and current_assignments[position] is False:
                            return None, [], 0
                        if position not in current_assignments:
                            current_assignments[position] = True
                            current_remaining_mines -= 1
                            updated = True
                    continue
                next_constraints.append((unassigned, remaining_required))

            current_constraints = next_constraints
            if current_remaining_mines < 0:
                return None, [], 0
            if not updated:
                break

        return current_assignments, current_constraints, current_remaining_mines

    def _choose_branch_cell(
        self,
        constraints: list[tuple[frozenset[Position], int]],
        unassigned_constrained: list[Position],
    ) -> Position | None:
        if not unassigned_constrained:
            return None
        score: dict[Position, int] = {position: 0 for position in unassigned_constrained}
        for cells, _ in constraints:
            for position in cells:
                if position in score:
                    score[position] += 1
        return max(unassigned_constrained, key=lambda position: (score[position], -position.row, -position.col))


@dataclass
class LogicSolver:
    max_iterations: int = 128

    def solve(self, board: MinesweeperBoard) -> bool:
        for _ in range(self.max_iterations):
            if board.is_won() or board.is_lost():
                return board.is_won()
            changed = False
            constraints = board.clue_constraints()
            changed |= self._apply_basic_rules(board, constraints)
            changed |= self._apply_subset_rules(board, constraints)
            if not changed:
                break
        return board.is_won()

    def _apply_basic_rules(self, board: MinesweeperBoard, constraints: Iterable[tuple[Position, frozenset[Position], int]]) -> bool:
        changed = False
        for _, hidden_neighbors, required_mines in constraints:
            if not hidden_neighbors:
                continue
            hidden_positions = tuple(hidden_neighbors)
            if required_mines == 0:
                for position in hidden_positions:
                    changed |= board.reveal(position.row, position.col).changed
            elif required_mines == len(hidden_positions):
                for position in hidden_positions:
                    changed |= board.set_flag(position.row, position.col, True).changed
        return changed

    def _apply_subset_rules(self, board: MinesweeperBoard, constraints: Iterable[tuple[Position, frozenset[Position], int]]) -> bool:
        changed = False
        constraint_list = [(position, set(hidden_neighbors), required_mines) for position, hidden_neighbors, required_mines in constraints if hidden_neighbors]
        for index, (position_a, cells_a, required_a) in enumerate(constraint_list):
            for position_b, cells_b, required_b in constraint_list[index + 1 :]:
                if cells_a == cells_b:
                    continue
                if cells_a.issubset(cells_b):
                    changed |= self._subset_infer(board, cells_a, required_a, cells_b, required_b)
                elif cells_b.issubset(cells_a):
                    changed |= self._subset_infer(board, cells_b, required_b, cells_a, required_a)
        return changed

    def _subset_infer(
        self,
        board: MinesweeperBoard,
        subset_cells: set[Position],
        subset_required: int,
        superset_cells: set[Position],
        superset_required: int,
    ) -> bool:
        changed = False
        difference = superset_cells - subset_cells
        difference_required = superset_required - subset_required
        if difference_required == 0:
            for position in difference:
                changed |= board.reveal(position.row, position.col).changed
        elif difference_required == len(difference):
            for position in difference:
                changed |= board.set_flag(position.row, position.col, True).changed
        return changed
