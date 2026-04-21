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

    def clue_matches(self, board: MinesweeperBoard, row: int, col: int, displayed_value: int) -> bool:
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

    def clue_matches(self, board: MinesweeperBoard, row: int, col: int, displayed_value: int) -> bool:
        return self.clue_value(board, row, col) == displayed_value


@dataclass(frozen=True, slots=True)
class QuadVariant(StandardVariant):
    code: str = "Q"
    name: str = "Quad"
    description: str = "Each 2x2 block must contain at least one mine."

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        for row in range(board.size - 1):
            for col in range(board.size - 1):
                mines = 0
                for dr in (0, 1):
                    for dc in (0, 1):
                        mines += int(board.has_mine(row + dr, col + dc))
                if mines == 0:
                    return False
        return True


@dataclass(frozen=True, slots=True)
class ConnectedVariant(StandardVariant):
    code: str = "C"
    name: str = "Connected"
    description: str = "All mines must be in one 8-connected component."

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        mines = _mine_positions(board)
        if len(mines) <= 1:
            return True
        seen = _flood_fill(board, {next(iter(mines))}, mines, include_diagonal=True)
        return len(seen) == len(mines)


@dataclass(frozen=True, slots=True)
class TripletVariant(StandardVariant):
    code: str = "T"
    name: str = "Triplet"
    description: str = "No 3 mines can appear in a contiguous orthogonal/diagonal line."

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        directions = ((0, 1), (1, 0), (1, 1), (1, -1))
        for row in range(board.size):
            for col in range(board.size):
                for dr, dc in directions:
                    r3 = row + 2 * dr
                    c3 = col + 2 * dc
                    if not (0 <= r3 < board.size and 0 <= c3 < board.size):
                        continue
                    if (
                        board.has_mine(row, col)
                        and board.has_mine(row + dr, col + dc)
                        and board.has_mine(r3, c3)
                    ):
                        return False
        return True


@dataclass(frozen=True, slots=True)
class OutsideVariant(StandardVariant):
    code: str = "O"
    name: str = "Outside"
    description: str = "Safe cells are connected, and each mine must connect to the border through mines."

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        mines = _mine_positions(board)
        safe = {position for position in board.positions() if position not in mines}
        if safe:
            safe_seen = _flood_fill(board, {next(iter(safe))}, safe, include_diagonal=True)
            if len(safe_seen) != len(safe):
                return False

        border_mines = {
            position
            for position in mines
            if position.row in (0, board.size - 1) or position.col in (0, board.size - 1)
        }
        if not mines:
            return True
        if not border_mines:
            return False
        mine_seen = _flood_fill(board, {next(iter(border_mines))}, mines, include_diagonal=True)
        return len(mine_seen) == len(mines)


@dataclass(frozen=True, slots=True)
class DualVariant(StandardVariant):
    code: str = "D"
    name: str = "Dual"
    description: str = "Mines form disjoint non-touching orthogonal pairs."

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        mines = _mine_positions(board)
        if len(mines) % 2 != 0:
            return False

        components = _components(board, mines, include_diagonal=False)
        for component in components:
            if len(component) != 2:
                return False

        for i, comp_a in enumerate(components):
            for comp_b in components[i + 1 :]:
                for a in comp_a:
                    for b in comp_b:
                        if max(abs(a.row - b.row), abs(a.col - b.col)) <= 1:
                            return False
        return True


@dataclass(frozen=True, slots=True)
class SnakeVariant(StandardVariant):
    code: str = "S"
    name: str = "Snake"
    description: str = "Mines form one non-self-touching orthogonal path."

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        mines = _mine_positions(board)
        if not mines:
            return False

        components = _components(board, mines, include_diagonal=False)
        if len(components) != 1:
            return False

        degree_one = 0
        for mine in mines:
            orth_neighbors = [
                neighbor
                for neighbor in board.orthogonal_positions(mine.row, mine.col)
                if neighbor in mines
            ]
            if len(orth_neighbors) > 2:
                return False
            if len(orth_neighbors) == 1:
                degree_one += 1

            for neighbor in board.adjacent_positions(mine.row, mine.col):
                if neighbor in mines and neighbor not in orth_neighbors:
                    return False

        if len(mines) == 1:
            return True
        return degree_one == 2


@dataclass(frozen=True, slots=True)
class RowColVariant(StandardVariant):
    code: str = "R"
    name: str = "RowCol"
    description: str = "All rows and columns contain the same number of mines."

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        row_counts = [sum(int(board.has_mine(row, col)) for col in range(board.size)) for row in range(board.size)]
        col_counts = [sum(int(board.has_mine(row, col)) for row in range(board.size)) for col in range(board.size)]
        return len(set(row_counts)) == 1 and len(set(col_counts)) == 1 and row_counts[0] == col_counts[0]


@dataclass(frozen=True, slots=True)
class HorizVariant(StandardVariant):
    code: str = "H"
    name: str = "Horiz"
    description: str = "No two mines can touch horizontally."

    def validate_solution(self, board: MinesweeperBoard) -> bool:
        for row in range(board.size):
            for col in range(board.size - 1):
                if board.has_mine(row, col) and board.has_mine(row, col + 1):
                    return False
        return True


@dataclass(frozen=True, slots=True)
class PartitionVariant(StandardVariant):
    code: str = "P"
    name: str = "Partition"
    description: str = "Clue is the number of consecutive mine groups around the 8-neighbor ring."

    def clue_value(self, board: MinesweeperBoard, row: int, col: int) -> int:
        ring_offsets = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
        ring = []
        for dr, dc in ring_offsets:
            rr = row + dr
            cc = col + dc
            if 0 <= rr < board.size and 0 <= cc < board.size:
                ring.append(int(board.has_mine(rr, cc)))
            else:
                ring.append(0)
        if not any(ring):
            return 0
        groups = 0
        previous = ring[-1]
        for current in ring:
            if current == 1 and previous == 0:
                groups += 1
            previous = current
        return groups


@dataclass(frozen=True, slots=True)
class LiarVariant(StandardVariant):
    code: str = "L"
    name: str = "Liar"
    description: str = "Each clue differs from the true adjacent mine count by exactly one."

    def clue_value(self, board: MinesweeperBoard, row: int, col: int) -> int:
        actual = board.adjacent_mine_count(row, col)
        if actual == 0:
            return 1
        if actual == 8:
            return 7
        return actual + 1 if (row + col) % 2 == 0 else actual - 1

    def clue_matches(self, board: MinesweeperBoard, row: int, col: int, displayed_value: int) -> bool:
        actual = board.adjacent_mine_count(row, col)
        return abs(displayed_value - actual) == 1 and 0 <= displayed_value <= 8


@dataclass(frozen=True, slots=True)
class CrossVariant(StandardVariant):
    code: str = "X"
    name: str = "Cross"
    description: str = "Clue counts mines in a plus-shaped region up to distance 2."

    def clue_value(self, board: MinesweeperBoard, row: int, col: int) -> int:
        positions = [(row - 2, col), (row - 1, col), (row + 1, col), (row + 2, col), (row, col - 2), (row, col - 1), (row, col + 1), (row, col + 2)]
        total = 0
        for rr, cc in positions:
            if 0 <= rr < board.size and 0 <= cc < board.size and board.has_mine(rr, cc):
                total += 1
        return total


def _mine_positions(board: MinesweeperBoard) -> set[Position]:
    return {position for position in board.positions() if board.has_mine(position.row, position.col)}


def _flood_fill(
    board: MinesweeperBoard,
    seeds: set[Position],
    domain: set[Position],
    include_diagonal: bool,
) -> set[Position]:
    stack = list(seeds)
    seen: set[Position] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        neighbors = board.adjacent_positions(current.row, current.col) if include_diagonal else board.orthogonal_positions(current.row, current.col)
        for neighbor in neighbors:
            if neighbor in domain and neighbor not in seen:
                stack.append(neighbor)
    return seen


def _components(board: MinesweeperBoard, domain: set[Position], include_diagonal: bool) -> list[set[Position]]:
    remaining = set(domain)
    components: list[set[Position]] = []
    while remaining:
        start = next(iter(remaining))
        component = _flood_fill(board, {start}, domain, include_diagonal=include_diagonal)
        components.append(component)
        remaining -= component
    return components


def orthogonal_touching_pairs(board: MinesweeperBoard) -> list[tuple[Position, Position]]:
    pairs: list[tuple[Position, Position]] = []
    for position in board.positions():
        for neighbor in board.orthogonal_positions(position.row, position.col):
            if position.row < neighbor.row or position.col < neighbor.col:
                pairs.append((position, neighbor))
    return pairs


STANDARD_VARIANT = StandardVariant()
AVAILABLE_VARIANTS: dict[str, VariantRule] = {
    variant.code: variant
    for variant in (
        STANDARD_VARIANT,
        QuadVariant(),
        ConnectedVariant(),
        TripletVariant(),
        OutsideVariant(),
        DualVariant(),
        SnakeVariant(),
        RowColVariant(),
        HorizVariant(),
        PartitionVariant(),
        LiarVariant(),
        CrossVariant(),
    )
}


def get_variant(code: str) -> VariantRule:
    normalized = code.strip().upper()
    if normalized not in AVAILABLE_VARIANTS:
        known = ", ".join(sorted(AVAILABLE_VARIANTS))
        raise ValueError(f"unknown variant '{code}'. Available codes: {known}")
    return AVAILABLE_VARIANTS[normalized]
