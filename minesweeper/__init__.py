from .board import Cell, MoveOutcome, MinesweeperBoard, Position
from .dataset import PuzzleRecord, SessionMove, SessionRecord, build_puzzle_record, read_puzzle_dataset, write_puzzle_dataset
from .evaluate import EvaluationSummary, evaluate_dataset, solve_with_trace
from .generator import DeterministicPuzzleGenerator, GeneratedPuzzle
from .play import PlayConfig, run_interactive_session
from .pygame_ui import PygameConfig, PygameMinesweeperApp, launch_pygame_ui
from .solver import ExactSolutionCounter, LogicSolver, PuzzleObservation, SolutionEnumerator
from .text import TextBoardEncoder
from .variants import AVAILABLE_VARIANTS, STANDARD_VARIANT, StandardVariant, VariantRule, get_variant

__all__ = [
    "Cell",
    "MoveOutcome",
    "MinesweeperBoard",
    "Position",
    "PuzzleRecord",
    "SessionMove",
    "SessionRecord",
    "build_puzzle_record",
    "read_puzzle_dataset",
    "write_puzzle_dataset",
    "EvaluationSummary",
    "evaluate_dataset",
    "solve_with_trace",
    "DeterministicPuzzleGenerator",
    "GeneratedPuzzle",
    "PlayConfig",
    "run_interactive_session",
    "PygameConfig",
    "PygameMinesweeperApp",
    "launch_pygame_ui",
    "ExactSolutionCounter",
    "LogicSolver",
    "PuzzleObservation",
    "SolutionEnumerator",
    "TextBoardEncoder",
    "AVAILABLE_VARIANTS",
    "STANDARD_VARIANT",
    "StandardVariant",
    "VariantRule",
    "get_variant",
]
