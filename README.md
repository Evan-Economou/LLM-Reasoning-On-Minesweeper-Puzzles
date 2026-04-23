# LLM-Reasoning-On-Minesweeper-Puzzles

## Repo Map

- [minesweeper/](minesweeper/) - Core handling of game logic. Includes puzzle generation, and play session recording and evaluation.
- [llm_runner/](llm_runner/) - Local LLM evaluation helpers and runner utilities.
- [writeup.md](writeup.md) - Project writeup and results.
- [pyproject.toml](pyproject.toml) - Package metadata, dependencies, and script definitions.

Deterministic Minesweeper environment for building puzzle datasets, collecting human play sessions, and evaluating local LLM agents.

## Setup

Create and sync the environment with `uv`:

```bash
uv sync
```

If you want every optional feature (`pygame` UI + local LLM dependencies), use:

```bash
uv sync --extra all
```

Run commands from the project root using:

```bash
python -m minesweeper <subcommand>
```

## Main Run Configurations

### 1. Build a Dataset with the Puzzle Generator

Generate reusable puzzles across variants into JSONL:

```bash
python -m minesweeper dataset-build \
  --output datasets/puzzles.jsonl \
  --variants STD Q C L P X \
  --count-per-variant 10 \
  --variant-mines Q=8 C=6 L=6 P=6 X=6
```

Inspect what was generated:

```bash
python -m minesweeper dataset-list --dataset datasets/puzzles.jsonl --verbose
```

### 2. Run the UI to Play Puzzles as a Human

Launch the pygame UI against your dataset and log sessions:

```bash
python -m minesweeper ui \
  --dataset datasets/puzzles.jsonl \
  --player-id human_01 \
  --session-log datasets/control_sessions.jsonl
```

Session records are appended to `datasets/control_sessions.jsonl`.

### 3. Run an LLM Agent to Solve Puzzles

Run a local causal LLM on the dataset and log model sessions:

```bash
python -m minesweeper llm-local \
  --dataset datasets/puzzles.jsonl \
  --limit 10 \
  --model-id EleutherAI/pythia-14m \
  --player-id pythia14m_local \
  --session-log datasets/model_sessions_local.jsonl \
  --include-cot
```

Quick deterministic baseline (no external model) for comparison:

```bash
python -m minesweeper evaluate \
  --dataset datasets/puzzles.jsonl \
  --player-id solver_baseline \
  --session-log datasets/model_sessions.jsonl
```

## Session Reporting

Build an HTML dashboard from one or more session logs:

```bash
python -m minesweeper session-report \
  --input datasets/model_sessions_local.jsonl datasets/model_sessions.jsonl datasets/control_sessions.jsonl \
  --output datasets/session_dashboard.html
```

## Notes

- Dataset files are JSONL, one puzzle/session per line.
- For non-standard variants, generation enforces variant-unique solvability checks.
- UI supports mouse reveal/flag and level navigation (next/prev/restart).
