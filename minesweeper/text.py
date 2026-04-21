from __future__ import annotations

from dataclasses import dataclass

from .board import MinesweeperBoard


@dataclass(frozen=True, slots=True)
class TextBoardEncoder:
    def render(
        self,
        board: MinesweeperBoard,
        variant_name: str = "Standard",
        variant_code: str = "STD",
        style: str = "coordinates",
        show_solution: bool = False,
    ) -> str:
        if style == "coordinates":
            return self._render_coordinate_grid(board, variant_name, variant_code, show_solution)
        if style == "flat":
            return self._render_flat_grid(board, variant_name, variant_code, show_solution)
        if style == "narrative":
            return self._render_narrative(board, variant_name, variant_code, show_solution)
        raise ValueError(f"unknown board text style: {style}")

    def _render_coordinate_grid(
        self,
        board: MinesweeperBoard,
        variant_name: str,
        variant_code: str,
        show_solution: bool,
    ) -> str:
        column_labels = [chr(ord("A") + index) for index in range(board.size)]
        lines = [
            f"Board ({board.size}x{board.size}) - Variant: {variant_name} [{variant_code}]",
            f"Mine count: {board.mine_count}",
            "",
            "   " + "  ".join(column_labels),
        ]
        for row_index in range(board.size):
            tokens = [board.visible_token(row_index, col_index, show_solution=show_solution) for col_index in range(board.size)]
            lines.append(f"{row_index + 1}  " + "  ".join(tokens))
        lines.extend([
            "",
            "Legend: # = hidden, . = revealed safe, F = flagged mine",
        ])
        if show_solution:
            lines[-1] += ", M = hidden mine"
        return "\n".join(lines)

    def _render_flat_grid(
        self,
        board: MinesweeperBoard,
        variant_name: str,
        variant_code: str,
        show_solution: bool,
    ) -> str:
        lines = [f"Board ({board.size}x{board.size}) - Variant: {variant_name} [{variant_code}]", f"Mine count: {board.mine_count}", ""]
        flat_tokens = []
        for position in board.positions():
            index = position.row * board.size + position.col
            flat_tokens.append(f"{index + 1:02d}:{board.visible_token(position.row, position.col, show_solution=show_solution)}")
        lines.append(" ".join(flat_tokens))
        return "\n".join(lines)

    def _render_narrative(
        self,
        board: MinesweeperBoard,
        variant_name: str,
        variant_code: str,
        show_solution: bool,
    ) -> str:
        lines = [f"Board ({board.size}x{board.size}) - Variant: {variant_name} [{variant_code}]", f"Mine count: {board.mine_count}", ""]
        for row_index in range(board.size):
            row_tokens = [board.visible_token(row_index, col_index, show_solution=show_solution) for col_index in range(board.size)]
            readable_row = ", ".join(f"{chr(ord('A') + col_index)}{row_index + 1}={token}" for col_index, token in enumerate(row_tokens))
            lines.append(f"Row {row_index + 1}: {readable_row}")
        return "\n".join(lines)
