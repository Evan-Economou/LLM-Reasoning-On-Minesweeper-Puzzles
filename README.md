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

Build a reusable puzzle dataset:

```bash
python -m minesweeper dataset-build \
	--output datasets/puzzles.jsonl \
	--variants STD Q C L P X \
	--count-per-variant 10 \
	--variant-mines Q=8 C=6 L=6 P=6 X=6
```

List dataset contents:

```bash
python -m minesweeper dataset-list --dataset datasets/puzzles.jsonl --verbose
```

Play a puzzle and log a session result (control dataset):

```bash
python -m minesweeper play \
	--dataset datasets/puzzles.jsonl \
	--index 0 \
	--player-id human_01 \
	--session-log datasets/control_sessions.jsonl
```

Play through levels sequentially and log each one:

```bash
python -m minesweeper play-all \
	--dataset datasets/puzzles.jsonl \
	--start-index 0 \
	--limit 14 \
	--player-id human_01 \
	--session-log datasets/control_sessions.jsonl
```

Run the internal baseline evaluator and log model-style sessions:

```bash
python -m minesweeper evaluate \
	--dataset datasets/puzzles.jsonl \
	--player-id solver_baseline \
	--session-log datasets/model_sessions.jsonl
```

Launch the simple pygame UI:

```bash
python -m minesweeper ui \
	--dataset datasets/puzzles.jsonl \
	--player-id human_01 \
	--session-log datasets/control_sessions.jsonl
```

The package provides:

- a 5x5 board engine with reveal, flag, win, and loss logic
- a logic solver/counter that evaluate puzzles under selected variant rules
- an exact solution counter used to guarantee unique puzzles during generation
- multiple plain-text encodings for model-facing prompts

For non-standard variants, generation enforces two checks:

- the puzzle has a unique solution under that variant's rules
- the same revealed clues are not uniquely solvable under standard Minesweeper assumptions

Dataset format details:

- puzzle dataset is JSONL (`datasets/puzzles.jsonl`) with one puzzle per line
- each puzzle stores puzzle id, variant, size, mine positions, initial reveals, and rendered initial board text
- play sessions are appended to JSONL (`datasets/control_sessions.jsonl`) with move-by-move logs and final outcome
- the baseline evaluator writes the same session schema to `datasets/model_sessions.jsonl`
- the pygame UI supports mouse reveal/flag play plus next/prev and restart controls

The code is pure Python and has no third-party dependencies.
