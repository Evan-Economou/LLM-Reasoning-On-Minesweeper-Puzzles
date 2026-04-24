# LLM-Reasoning-On-Minesweeper-Puzzles

## Repo Map

- [minesweeper/](minesweeper/) - Core handling of game logic. Includes puzzle generation, and play session recording and evaluation.
- [llm_runner/](llm_runner/) - Local LLM evaluation helpers and runner utilities.
- [writeup.md](writeup.md) - Project writeup and results.
- [pyproject.toml](pyproject.toml) - Package metadata, dependencies, and script definitions.


## Setup

Create and sync the environment with `uv`:

```bash
uv sync
```

If you want to additionally include pygame to be able to add to the dataset yourself for fun, create the venv with:

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

### 2. Run the deterministic solver to verify the dataset

Quick deterministic baseline for verification of the solvability of each puzzle, also to increase the winrate displayed on the dashboard:

```bash
python -m minesweeper evaluate \
  --dataset datasets/puzzles.jsonl \
  --player-id deterministic_solver \
  --session-log datasets/control_sessions.jsonl
```

### 3. Run the UI to Play Puzzles as a Human

This feature is not very fleshed out, it is not an important piece of the project. However, it is useful for inspecting the dataset in context and getting a baseline for comparison.

Launch the pygame UI against your dataset and log sessions:

```bash
python -m minesweeper ui \
  --dataset datasets/puzzles.jsonl \
  --player-id human_01 \
  --session-log datasets/human_sessions.jsonl
```

Session records are appended to the file specified in --session-log, in this case it's `datasets/control_sessions.jsonl`.

### 4. Run a local LLM to Solve Puzzles

Run a local LLM on the dataset and log model sessions:

```bash
python -m minesweeper llm-local \
  --dataset datasets/puzzles.jsonl \
  --limit 10 \
  --model-id EleutherAI/pythia-14m \
  --player-id pythia14m_local \
  --session-log datasets/model_sessions_local.jsonl \
  --include-cot
```

This downloads the model specified by --model-id from the huggingface api and runs the first `limit` puzzles from the dataset with it. Pythia-14m was chosen just as a proof of concept that the general program flow is working, but instruction tuned models and larger models will produce better results.

Useful optional flags for `llm-local` for controling hyperparameters:

- `--temperature` (default `0.0`): Sampling temperature. Use `0.0` for deterministic decoding, raise it for more randomness.
- `--top-p` (default `1.0`): Nucleus sampling threshold. Lower values restrict generation to higher-probability tokens.
- `--max-new-tokens` (default `32`): Maximum tokens generated per turn, more than the default shouldn't be necessary.
- `--repetition-penalty` (default `1.12`): Penalizes token repetition; higher values reduce repeated loops.
- `--no-repeat-ngram-size` (default `4`): Prevents repeating any n-gram of this length in one response.
- `--style` (default `coordinates`): Board text format passed to the model. Choices: `coordinates`, `flat`, `narrative`.
- `--start-index` (default `0`): Start puzzle index in the dataset.
- `--limit` (default `1`): Number of puzzles to run from `--start-index`.
- `--max-turn-multiplier` (default `3`): Turn budget scaling factor relative to the baseline solver's move count.
- `--include-cot` (flag, default off): Asks the model for brief reasoning before the final action line.
- `--reminder-each-turn` (flag, default off): Repeats the variant constraint text on every turn prompt.


### 5. Run an LLM Agent through an API

Coming soon, to a repo near you

## Session Reporting

Build an HTML dashboard from one or more session logs:

```bash
python -m minesweeper session-report \
  --input datasets/model_sessions_local.jsonl datasets/control_sessions.jsonl datasets/human_sessions.jsonl \
  --output datasets/session_dashboard.html
```

This coalesces all of the listed session reports and builds an html dashboard to display them, which by default is placed alongside the datasets.

## Notes

- Dataset files are JSONL, with one puzzle/session per line.
