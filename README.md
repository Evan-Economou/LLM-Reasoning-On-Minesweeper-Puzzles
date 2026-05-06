# LLM-Reasoning-On-Minesweeper-Puzzles

## Repo Map

- [minesweeper/](minesweeper/) - Core handling of game logic. Includes puzzle generation, and play session recording and evaluation.
- [llm_runner/](llm_runner/) - Provider-backed model evaluation helpers and runner utilities.
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
python -m minesweeper dataset-build 
  --output datasets/puzzles.jsonl 
  --variants STD Q C T O D S R H P L X 
  --count-per-variant 50 
  --variant-mines Q=8 C=6 D=6 L=6 P=6 X=6 
  --max-attempts 2000
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

This uses the provider selected by `--provider` and runs the first `limit` puzzles from the dataset with it. The default configuration targets an Ollama server and the `llama3.2:3b` model, but the same command also supports hosted providers like OpenAI and Anthropic. The older `llm-local` subcommand remains as an alias for backward compatibility.

Useful optional flags for `llm-eval` for controling hyperparameters:

- `--provider` (default `ollama`): Backend to use. Supported values are `ollama`, `openai`, and `anthropic`.
- `--base-url` (default empty for API providers): Override the provider endpoint. Ollama defaults to `http://localhost:11434`.
- `--api-key` (default empty): API key for hosted providers.
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


### 5. Run an API-Hosted Model (Example)

```bash
python -m minesweeper llm-eval \
  --dataset datasets/puzzles.jsonl \
  --limit 10 \
  --provider anthropic \
  --model-id claude-3-5-haiku-latest \
  --api-key "$ANTHROPIC_API_KEY" \
  --session-log datasets/model_sessions.jsonl
```

## Session Reporting

Build an HTML dashboard from one or more session logs:

```bash
python -m minesweeper session-report \
  --input datasets/model_sessions.jsonl datasets/control_sessions.jsonl datasets/human_sessions.jsonl \
  --output datasets/session_dashboard.html
```

This coalesces all of the listed session reports and builds an html dashboard to display them, which by default is placed alongside the datasets.

## Notes

- Dataset files are JSONL, with one puzzle/session per line.



                                                                                                                                                        
  ---                                                                                                                                                      
  Stage 1 — Pilot: 1 puzzle/variant, no CoT (12 total)
  python -m minesweeper llm-eval \
    --dataset docs/puzzles.jsonl \
    --limit 12 --provider anthropic --model-id claude-haiku-4-5-20251001 \
    --api-key "$ANTHROPIC_API_KEY" \
    --player-id haiku_pilot \
    --session-log docs/haiku_pilot_sessions.jsonl
                                                                                                                                                           
  ---                                                                                                                                                      
  Stage 2 — Haiku baseline: 5 puzzles/variant, no CoT (60 total)                                                                                         
  python -m minesweeper llm-eval \
    --dataset docs/puzzles.jsonl \
    --limit 60 --provider anthropic --model-id claude-haiku-4-5-20251001 \
    --api-key "$ANTHROPIC_API_KEY" \
    --player-id haiku_baseline \
    --session-log docs/haiku_baseline_sessions.jsonl
                                                                                                                                                           
  ---                                                                                                                                                      
  Stage 3 — Haiku with CoT: 5 puzzles/variant (60 total)
  python -m minesweeper llm-eval \
    --dataset docs/puzzles.jsonl \
    --limit 60 --provider anthropic --model-id claude-haiku-4-5-20251001 \
    --api-key "$ANTHROPIC_API_KEY" \                                      
    --player-id haiku_cot \
    --session-log docs/haiku_cot_sessions.jsonl \
    --include-cot                                    
                                                                                                                                                           
  ---                                                                                                                                                    
  Stage 4 — Sonnet comparison: 5 puzzles/variant (60 total)                                                                                                
  python -m minesweeper llm-eval \
    --dataset docs/puzzles.jsonl \
    --limit 60 --provider anthropic --model-id claude-sonnet-4-6 \
    --api-key "$ANTHROPIC_API_KEY" \
    --player-id sonnet_baseline \
    --session-log docs/sonnet_baseline_sessions.jsonl
                                                                                                                                                           
  ---
  Deterministic solver baseline (free, run once)                                                                                                           
  python -m minesweeper evaluate \
    --dataset docs/puzzles.jsonl \
    --player-id deterministic_solver \
    --session-log docs/control_sessions.jsonl
   
  ---                                                                                                                                                      
  Build dashboard from all session logs                                                                                                                  
  python -m minesweeper session-report \
    --input docs/control_sessions.jsonl \
             docs/haiku_pilot_sessions.jsonl \
             docs/haiku_baseline_sessions.jsonl \
             docs/haiku_cot_sessions.jsonl \     
             docs/sonnet_baseline_sessions.jsonl \
    --output docs/session_dashboard.html
   
  ---