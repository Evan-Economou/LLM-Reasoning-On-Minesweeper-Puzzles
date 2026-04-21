from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Support direct execution: python minesweeper/__main__.py
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from minesweeper.generator import DeterministicPuzzleGenerator
    from minesweeper.text import TextBoardEncoder
else:
    from .generator import DeterministicPuzzleGenerator
    from .text import TextBoardEncoder


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a deterministically solvable Minesweeper puzzle")
    parser.add_argument("--size", type=int, default=5)
    parser.add_argument("--mines", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--style", choices=["coordinates", "flat", "narrative"], default="coordinates")
    args = parser.parse_args()

    generator = DeterministicPuzzleGenerator(size=args.size, mine_count=args.mines, seed=args.seed)
    puzzle = generator.generate()
    encoder = TextBoardEncoder()
    print(encoder.render(puzzle.board, style=args.style))


if __name__ == "__main__":
    main()
