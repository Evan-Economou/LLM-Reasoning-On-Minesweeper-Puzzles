from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from time import monotonic

from .board import GameStatus, MinesweeperBoard, Position
from .dataset import SessionMove, SessionRecord, append_session_record, board_from_record, read_puzzle_dataset
from .text import TextBoardEncoder
from .variants import VariantRule


@dataclass(frozen=True, slots=True)
class PygameConfig:
    dataset_path: str
    session_log_path: str
    player_id: str
    start_index: int = 0
    window_width: int = 900
    window_height: int = 700


class PygameMinesweeperApp:
    def __init__(self, config: PygameConfig) -> None:
        self.config = config
        self.records = read_puzzle_dataset(config.dataset_path)
        if not self.records:
            raise RuntimeError("dataset is empty")
        self.index = max(0, min(config.start_index, len(self.records) - 1))
        self.board: MinesweeperBoard
        self.variant: VariantRule
        self.current_record = None
        self.moves: list[SessionMove] = []
        self.started_at = ""
        self.start_clock = 0.0
        self._load_record(self.index)

    def run(self) -> None:
        import pygame

        pygame.init()
        pygame.display.set_caption("Minesweeper Dataset Player")
        screen = pygame.display.set_mode((self.config.window_width, self.config.window_height))
        clock = pygame.time.Clock()
        font = pygame.font.SysFont("arial", 24)
        small_font = pygame.font.SysFont("arial", 18)

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._finalize_session()
                    running = False
                elif event.type == pygame.KEYDOWN:
                    running = self._handle_key(event.key, pygame)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_click(event.pos, event.button)

            self._draw(screen, font, small_font)
            pygame.display.flip()
            clock.tick(60)

        pygame.quit()

    def _handle_key(self, key: int, pygame_module) -> bool:
        if key in {pygame_module.K_ESCAPE, pygame_module.K_q}:
            self._finalize_session()
            return False
        if key in {pygame_module.K_r}:
            self._reload_current()
        elif key in {pygame_module.K_n, pygame_module.K_RIGHT}:
            self._advance(1)
        elif key in {pygame_module.K_p, pygame_module.K_LEFT}:
            self._advance(-1)
        return True

    def _handle_click(self, position: tuple[int, int], button: int) -> None:
        board_rect = self._board_rect()
        cell_size = self._cell_size()
        x, y = position
        if not board_rect.collidepoint(x, y):
            if self._button_hit(position, "prev"):
                self._advance(-1)
            elif self._button_hit(position, "next"):
                self._advance(1)
            elif self._button_hit(position, "restart"):
                self._reload_current()
            elif self._button_hit(position, "quit"):
                self._finalize_session()
                raise SystemExit
            return

        if self.board.status != GameStatus.IN_PROGRESS:
            return

        grid_x = x - board_rect.x
        grid_y = y - board_rect.y
        col = grid_x // cell_size
        row = grid_y // cell_size
        if not (0 <= row < self.board.size and 0 <= col < self.board.size):
            return

        coord = self._coord_from_position(Position(row=row, col=col))
        if button == 1:
            outcome = self.board.reveal(row, col)
            self._record_move("REVEAL", coord, outcome.changed, outcome.hit_mine)
        elif button == 3:
            outcome = self.board.toggle_flag(row, col)
            self._record_move("FLAG", coord, outcome.changed, False)

        if self.board.status != GameStatus.IN_PROGRESS:
            self._finalize_session()

    def _record_move(self, action: str, coord: str, changed: bool, hit_mine: bool) -> None:
        self.moves.append(
            SessionMove(
                turn=len(self.moves) + 1,
                action=action,
                coordinate=coord,
                changed=changed,
                hit_mine=hit_mine,
                status_after=self.board.status.value,
            )
        )

    def _advance(self, delta: int) -> None:
        self._finalize_session()
        self.index = (self.index + delta) % len(self.records)
        self._load_record(self.index)

    def _reload_current(self) -> None:
        self._finalize_session()
        self._load_record(self.index)

    def _load_record(self, index: int) -> None:
        record = self.records[index]
        self.current_record = record
        self.board, self.variant = board_from_record(record)
        self.moves = []
        self.started_at = _now_iso()
        self.start_clock = monotonic()

    def _finalize_session(self) -> None:
        if self.current_record is None:
            return
        if not self.started_at:
            return

        session = SessionRecord(
            session_id=_session_id(self.config.player_id, self.current_record.puzzle_id),
            puzzle_id=self.current_record.puzzle_id,
            player_id=self.config.player_id,
            started_at_utc=self.started_at,
            ended_at_utc=_now_iso(),
            duration_seconds=round(monotonic() - self.start_clock, 3),
            won=self.board.status == GameStatus.WON,
            lost=self.board.status == GameStatus.LOST,
            variant_code=self.variant.code,
            move_count=len(self.moves),
            moves=self.moves,
        )
        append_session_record(session, self.config.session_log_path)
        self.started_at = ""

    def _draw(self, screen, font, small_font) -> None:
        import pygame

        screen.fill((18, 22, 28))
        self._draw_header(screen, font, small_font)
        self._draw_board(screen, font, small_font)
        self._draw_buttons(screen, small_font)
        self._draw_footer(screen, small_font)

    def _draw_header(self, screen, font, small_font) -> None:
        import pygame

        title = font.render(
            f"{self.current_record.puzzle_id} | {self.variant.name} [{self.variant.code}]",
            True,
            (245, 245, 245),
        )
        subtitle = small_font.render(
            f"Puzzle {self.index + 1}/{len(self.records)}   Moves: {len(self.moves)}   Status: {self.board.status.value}",
            True,
            (180, 186, 196),
        )
        screen.blit(title, (24, 18))
        screen.blit(subtitle, (24, 52))

    def _draw_board(self, screen, font, small_font) -> None:
        import pygame

        board_rect = self._board_rect()
        cell_size = self._cell_size()
        encoder = TextBoardEncoder()
        for row in range(self.board.size):
            for col in range(self.board.size):
                cell = self.board.cell(row, col)
                rect = pygame.Rect(board_rect.x + col * cell_size, board_rect.y + row * cell_size, cell_size, cell_size)
                token = self._cell_token(row, col)
                color = (48, 54, 64)
                if cell.revealed:
                    color = (214, 219, 226)
                    if cell.mine:
                        color = (214, 88, 88)
                elif cell.flagged:
                    color = (219, 177, 76)
                pygame.draw.rect(screen, color, rect, border_radius=6)
                pygame.draw.rect(screen, (27, 31, 39), rect, width=2, border_radius=6)

                label = font.render(token, True, (15, 20, 25) if cell.revealed else (245, 245, 245))
                label_rect = label.get_rect(center=rect.center)
                screen.blit(label, label_rect)

        for col in range(self.board.size):
            label = small_font.render(chr(ord("A") + col), True, (180, 186, 196))
            screen.blit(label, (board_rect.x + col * cell_size + cell_size // 2 - label.get_width() // 2, board_rect.y - 22))
        for row in range(self.board.size):
            label = small_font.render(str(row + 1), True, (180, 186, 196))
            screen.blit(label, (board_rect.x - 18, board_rect.y + row * cell_size + cell_size // 2 - label.get_height() // 2))

    def _draw_buttons(self, screen, small_font) -> None:
        import pygame

        for name, text, rect in self._buttons():
            pygame.draw.rect(screen, (34, 40, 49), rect, border_radius=8)
            pygame.draw.rect(screen, (92, 99, 109), rect, width=1, border_radius=8)
            label = small_font.render(text, True, (235, 235, 235))
            screen.blit(label, label.get_rect(center=rect.center))

    def _draw_footer(self, screen, small_font) -> None:
        import pygame

        lines = [
            "Left click: reveal   Right click: flag   R: restart   N/P or arrows: next/prev   Q/Esc: quit",
            "Dataset moves and outcomes are written to the session log when you switch puzzles or exit.",
        ]
        y = self.config.window_height - 52
        for line in lines:
            label = small_font.render(line, True, (180, 186, 196))
            screen.blit(label, (24, y))
            y += 20

    def _cell_token(self, row: int, col: int) -> str:
        cell = self.board.cell(row, col)
        if cell.flagged:
            return "F"
        if not cell.revealed:
            return ""
        if cell.mine:
            return "*"
        clue = self.variant.clue_value(self.board, row, col)
        return "." if clue == 0 else str(clue)

    def _board_rect(self):
        import pygame

        cell_size = self._cell_size()
        width = cell_size * self.board.size
        height = cell_size * self.board.size
        x = (self.config.window_width - width) // 2
        y = 110
        return pygame.Rect(x, y, width, height)

    def _cell_size(self) -> int:
        return 78 if self.board.size <= 5 else 64

    def _buttons(self):
        import pygame

        top = 86
        left = 24
        width = 92
        height = 32
        gap = 10
        names = [("prev", "Prev"), ("next", "Next"), ("restart", "Restart"), ("quit", "Quit")]
        buttons = []
        for index, (name, text) in enumerate(names):
            rect = pygame.Rect(left + index * (width + gap), top, width, height)
            buttons.append((name, text, rect))
        return buttons

    def _button_hit(self, position: tuple[int, int], button_name: str) -> bool:
        x, y = position
        for name, _, rect in self._buttons():
            if name == button_name and rect.collidepoint(x, y):
                return True
        return False

    @staticmethod
    def _coord_from_position(position: Position) -> str:
        return f"{chr(ord('A') + position.col)}{position.row + 1}"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _session_id(player_id: str, puzzle_id: str) -> str:
    payload = f"{player_id}|{puzzle_id}|{_now_iso()}"
    return sha1(payload.encode("utf-8")).hexdigest()[:16]


def launch_pygame_ui(
    dataset_path: str,
    session_log_path: str,
    player_id: str,
    start_index: int = 0,
    window_width: int = 900,
    window_height: int = 700,
) -> None:
    config = PygameConfig(
        dataset_path=dataset_path,
        session_log_path=session_log_path,
        player_id=player_id,
        start_index=start_index,
        window_width=window_width,
        window_height=window_height,
    )
    app = PygameMinesweeperApp(config)
    app.run()
