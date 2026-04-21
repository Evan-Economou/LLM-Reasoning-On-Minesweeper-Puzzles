# LLM-Reasoning-On-Minesweeper-Puzzles

Deterministic Minesweeper engine for the project plan in `minesweeper_llm_project_plan.md`.

## Quick Start

Generate a puzzle with the built-in deterministic generator:

```bash
python -m minesweeper --seed 7 --mines 5 --size 5
```

The package provides:

- a 5x5 board engine with reveal, flag, win, and loss logic
- a logic solver that applies standard Minesweeper deductions
- an exact solution counter used to guarantee unique puzzles during generation
- multiple plain-text encodings for model-facing prompts

The code is pure Python and has no third-party dependencies.
