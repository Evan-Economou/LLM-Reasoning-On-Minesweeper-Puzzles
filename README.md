# LLM-Reasoning-On-Minesweeper-Puzzles

Deterministic Minesweeper engine for the project plan in `minesweeper_llm_project_plan.md`.

## Quick Start

Generate a puzzle with the built-in deterministic generator:

```bash
python -m minesweeper --seed 7 --mines 5 --size 5
```

Generate a variant puzzle (example: Quad):

```bash
python -m minesweeper --variant Q --seed 11 --mines 8 --size 5
```

The package provides:

- a 5x5 board engine with reveal, flag, win, and loss logic
- a logic solver/counter that evaluate puzzles under selected variant rules
- an exact solution counter used to guarantee unique puzzles during generation
- multiple plain-text encodings for model-facing prompts

For non-standard variants, generation enforces two checks:

- the puzzle has a unique solution under that variant's rules
- the same revealed clues are not uniquely solvable under standard Minesweeper assumptions

The code is pure Python and has no third-party dependencies.
