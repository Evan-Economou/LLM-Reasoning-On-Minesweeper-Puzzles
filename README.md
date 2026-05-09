# LLM-Reasoning-On-Minesweeper-Puzzles

## Repo Map

- [minesweeper/](minesweeper/) - Core game logic: puzzle generation, variants, solver, play session recording and evaluation.
- [llm_runner/](llm_runner/) - Provider-backed model evaluation helpers and runner utilities.
- [data_processing/](data_processing/) - Analysis and visualization scripts for session JSONL files.
- [docs/](docs/) - GitHub Pages site. `data/` holds the puzzle dataset, `results/` holds session logs, `figures/` holds generated plots, and the HTML dashboards are at the root.
- [writeup/](writeup/) - LaTeX source and compiled PDF of the project writeup.
- [pyproject.toml](pyproject.toml) - Package metadata, dependencies, and script definitions.

## Website

https://evan-economou.github.io/LLM-Reasoning-On-Minesweeper-Puzzles/

## Setup

Create and sync the environment with `uv`:

```bash
uv sync
```

If you want to additionally include pygame to play puzzles yourself, create the venv with:

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
  --variants STD Q C T O D S R H P L X \
  --count-per-variant 50 \
  --variant-mines Q=8 C=6 D=6 L=6 P=6 X=6 \
  --max-attempts 2000
```

Inspect what was generated:

```bash
python -m minesweeper dataset-list --dataset datasets/puzzles.jsonl --verbose
```

### 2. Run the Deterministic Solver to Verify the Dataset

Quick deterministic baseline for verification of the solvability of each puzzle, also to establish a turn budget for LLM evaluations:

```bash
python -m minesweeper evaluate \
  --dataset datasets/puzzles.jsonl \
  --player-id deterministic_solver \
  --session-log datasets/control_sessions.jsonl
```

### 3. Run the UI to Play Puzzles as a Human

Launch the pygame UI against your dataset and log sessions (requires `--extra all`), this is just for fun and to understand the variants:

```bash
python -m minesweeper ui \
  --dataset datasets/puzzles.jsonl \
  --player-id human_01 \
  --session-log datasets/human_sessions.jsonl
```

### 4. Run an LLM/API Model to Solve Puzzles

Run a provider-backed model on the dataset and log model sessions:

```bash
python -m minesweeper llm-eval \
  --dataset datasets/puzzles.jsonl \
  --limit 10 \
  --provider ollama \
  --model-id llama3.2:3b \
  --player-id model_runner \
  --session-log datasets/model_sessions.jsonl \
  --include-cot
```

This uses the provider selected by `--provider` and runs the first `limit` puzzles of each variant with it. The default configuration targets an Ollama server, but the same command also supports Anthropic.

Useful optional flags for `llm-eval`:

- `--provider` (default `ollama`): Backend to use. Supported values are `ollama` and `anthropic`.
- `--base-url` (default empty for API providers): Override the provider endpoint. Ollama defaults to `http://localhost:11434`.
- `--api-key` (default empty): API key for hosted providers.
- `--timeout-seconds` (default `300.0`): Per-puzzle timeout in seconds.
- `--temperature` (default `0.0`): Sampling temperature. Use `0.0` for deterministic decoding, raise it for more randomness.
- `--top-p` (default `1.0`): Nucleus sampling threshold. Lower values restrict generation to higher-probability tokens.
- `--max-new-tokens` (default `64`): Maximum tokens generated per turn.
- `--repetition-penalty` (default `1.12`): Penalizes token repetition; higher values reduce repeated loops.
- `--no-repeat-ngram-size` (default `4`): Prevents repeating any n-gram of this length in one response.
- `--style` (default `numeric`): Board text format passed to the model. Choices: `coordinates`, `numeric`, `flat`, `narrative`.
- `--start-index` (default `0`): Within each variant's puzzle group, skip this many puzzles before starting.
- `--limit` (default `1`): Maximum number of puzzles to evaluate per variant, starting from `--start-index`.
- `--max-turn-multiplier` (default `3`): Turn budget scaling factor relative to the baseline solver's move count.
- `--include-cot` (flag, default off): Asks the model for brief reasoning before the final action line.
- `--thinking-budget-tokens` (default `2000`): Token budget for Anthropic extended thinking (used when `--include-cot` and `--provider anthropic`).
- `--reminder-each-turn` (flag, default off): Repeats the variant constraint text on every turn prompt.
- `--resume-from` (default empty): Path to an existing session log; puzzles already present are skipped per variant up to `--limit`.


### 5. Run an API-Hosted Model (Example)

```bash
python -m minesweeper llm-eval \
  --dataset datasets/puzzles.jsonl \
  --limit 10 \
  --provider anthropic \
  --model-id claude-haiku-4-5-20251001 \
  --api-key "$ANTHROPIC_API_KEY" \
  --session-log datasets/model_sessions.jsonl
```

## Session Reporting

Build an HTML dashboard from one or more session logs:

```bash
python -m minesweeper session-report \
  --input docs/results/control_sessions.jsonl \
          docs/results/haiku_pilot_sessions.jsonl \
          docs/results/haiku_pilot_sessions_1.jsonl \
          docs/results/haiku_cot_sessions.jsonl \
          docs/results/haiku_cot_sessions_old.jsonl \
  --output docs/index.html
```

## Data Analysis

Run the visualization suite against one or more session logs:

```bash
uv run python data_processing/visualize.py docs/results/haiku_cot_sessions.jsonl -o docs/figures/
# or interactively:
uv run python data_processing/visualize.py docs/results/haiku_cot_sessions.jsonl
# or a subset of plots:
uv run python data_processing/visualize.py docs/results/haiku_cot_sessions.jsonl --only win_rate failure_analysis
```

## Experimental Stages

The experiments used `docs/data/puzzles.jsonl` (12 variants × 5 puzzles = 60 puzzles total) and stored session logs in `docs/results/`.

### Stage 1 — Pilot (12 puzzles, no CoT)

```bash
python -m minesweeper llm-eval \
  --dataset docs/data/puzzles.jsonl \
  --limit 1 --provider anthropic --model-id claude-haiku-4-5-20251001 \
  --api-key "$ANTHROPIC_API_KEY" \
  --player-id haiku_pilot \
  --session-log docs/results/haiku_pilot_sessions.jsonl
```

### Stage 2 — Haiku Baseline (60 puzzles, no CoT)

```bash
python -m minesweeper llm-eval \
  --dataset docs/data/puzzles.jsonl \
  --limit 5 --provider anthropic --model-id claude-haiku-4-5-20251001 \
  --api-key "$ANTHROPIC_API_KEY" \
  --player-id haiku_baseline \
  --session-log docs/results/haiku_baseline_sessions.jsonl
```

### Stage 3 — Haiku with CoT (60 puzzles)

```bash
python -m minesweeper llm-eval \
  --dataset docs/data/puzzles.jsonl \
  --limit 5 --provider anthropic --model-id claude-haiku-4-5-20251001 \
  --api-key "$ANTHROPIC_API_KEY" \
  --player-id haiku_cot \
  --session-log docs/results/haiku_cot_sessions.jsonl \
  --include-cot
```

### Deterministic Solver Baseline

```bash
python -m minesweeper evaluate \
  --dataset docs/data/puzzles.jsonl \
  --player-id deterministic_solver \
  --session-log docs/results/control_sessions.jsonl
```

### Build Dashboard from All Stages

```bash
python -m minesweeper session-report \
  --input docs/results/control_sessions.jsonl \
          docs/results/haiku_pilot_sessions.jsonl \
          docs/results/haiku_pilot_sessions_1.jsonl \
          docs/results/haiku_cot_sessions.jsonl \
          docs/results/haiku_cot_sessions_old.jsonl \
  --output docs/index.html
```

## Notes

- Dataset files are JSONL, with one puzzle/session per line.
