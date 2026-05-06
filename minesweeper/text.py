from __future__ import annotations

from dataclasses import dataclass

from .board import MinesweeperBoard
from .variants import STANDARD_VARIANT, VariantRule


@dataclass(frozen=True, slots=True)
class TextBoardEncoder:
    def render(
        self,
        board: MinesweeperBoard,
        variant: VariantRule = STANDARD_VARIANT,
        style: str = "coordinates",
        show_solution: bool = False,
    ) -> str:
        if style == "coordinates":
            return self._render_coordinate_grid(board, variant, show_solution)
        if style == "numeric_coordinates":
            return self._render_numeric_coordinate_grid(board, variant, show_solution)
        if style == "numeric":
            return self._render_numeric_list(board, variant, show_solution)
        if style == "flat":
            return self._render_flat_grid(board, variant, show_solution)
        if style == "narrative":
            return self._render_narrative(board, variant, show_solution)
        raise ValueError(f"unknown board text style: {style}")

    def _render_coordinate_grid(
        self,
        board: MinesweeperBoard,
        variant: VariantRule,
        show_solution: bool,
    ) -> str:
        column_labels = [chr(ord("A") + index) for index in range(board.size)]
        lines = [
            f"Board ({board.size}x{board.size}) - Variant: {variant.name} [{variant.code}]",
            f"Mine count: {board.mine_count}",
            "",
            "   " + "  ".join(column_labels),
        ]
        for row_index in range(board.size):
            tokens = [
                self._visible_token(board, variant, row_index, col_index, show_solution=show_solution)
                for col_index in range(board.size)
            ]
            lines.append(f"{row_index + 1}  " + "  ".join(tokens))
        lines.extend([
            "",
            "Legend: # = hidden, . = revealed safe, F = flagged mine",
        ])
        if show_solution:
            lines[-1] += ", M = hidden mine"
        return "\n".join(lines)

    def _render_numeric_coordinate_grid(
        self,
        board: MinesweeperBoard,
        variant: VariantRule,
        show_solution: bool,
    ) -> str:
        lines = [
            f"Board ({board.size}x{board.size}) - Variant: {variant.name} [{variant.code}]",
            f"Mine count: {board.mine_count}",
            "",
            "   " + "  ".join(str(index + 1) for index in range(board.size)),
        ]
        for row_index in range(board.size):
            tokens = [
                self._visible_token(board, variant, row_index, col_index, show_solution=show_solution)
                for col_index in range(board.size)
            ]
            lines.append(f"{row_index + 1}  " + "  ".join(tokens))
        lines.extend([
            "",
            "Legend: # = hidden, . = revealed safe, F = flagged mine",
        ])
        if show_solution:
            lines[-1] += ", M = hidden mine"
        return "\n".join(lines)

    def _render_numeric_list(
        self,
        board: MinesweeperBoard,
        variant: VariantRule,
        show_solution: bool,
    ) -> str:
        lines = [
            f"Board ({board.size}x{board.size}) - Variant: {variant.name} [{variant.code}]",
            f"Mine count: {board.mine_count}",
            "",
        ]
        for row_index in range(board.size):
            for col_index in range(board.size):
                token = self._visible_token(board, variant, row_index, col_index, show_solution=show_solution)
                # Note: 1-indexed output to match arxiv format
                lines.append(f"({row_index + 1},{col_index + 1}): {token}")
        return "\n".join(lines)

    def _render_flat_grid(
        self,
        board: MinesweeperBoard,
        variant: VariantRule,
        show_solution: bool,
    ) -> str:
        lines = [f"Board ({board.size}x{board.size}) - Variant: {variant.name} [{variant.code}]", f"Mine count: {board.mine_count}", ""]
        flat_tokens = []
        for position in board.positions():
            index = position.row * board.size + position.col
            flat_tokens.append(
                f"{index + 1:02d}:{self._visible_token(board, variant, position.row, position.col, show_solution=show_solution)}"
            )
        lines.append(" ".join(flat_tokens))
        return "\n".join(lines)

    def _render_narrative(
        self,
        board: MinesweeperBoard,
        variant: VariantRule,
        show_solution: bool,
    ) -> str:
        lines = [f"Board ({board.size}x{board.size}) - Variant: {variant.name} [{variant.code}]", f"Mine count: {board.mine_count}", ""]
        for row_index in range(board.size):
            row_tokens = [
                self._visible_token(board, variant, row_index, col_index, show_solution=show_solution)
                for col_index in range(board.size)
            ]
            readable_row = ", ".join(f"{chr(ord('A') + col_index)}{row_index + 1}={token}" for col_index, token in enumerate(row_tokens))
            lines.append(f"Row {row_index + 1}: {readable_row}")
        return "\n".join(lines)

    def _visible_token(
        self,
        board: MinesweeperBoard,
        variant: VariantRule,
        row: int,
        col: int,
        show_solution: bool,
    ) -> str:
        cell = board.cell(row, col)
        if cell.revealed:
            if cell.mine:
                return "*"
            clue = variant.clue_value(board, row, col)
            return "." if clue == 0 else str(clue)
        if cell.flagged:
            return "F"
        if show_solution and cell.mine:
            return "M"
        return "#"
