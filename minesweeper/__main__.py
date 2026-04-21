from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from llm_runner.local_eval import LocalModelConfig, run_local_llm_dataset
    from minesweeper.dataset import build_puzzle_record, board_from_record, read_puzzle_dataset, write_puzzle_dataset
    from minesweeper.evaluate import evaluate_dataset
    from minesweeper.generator import DeterministicPuzzleGenerator
    from minesweeper.play import PlayConfig, run_interactive_session
    from minesweeper.pygame_ui import launch_pygame_ui
    from minesweeper.session_report import build_session_dashboard
    from minesweeper.text import TextBoardEncoder
    from minesweeper.variants import AVAILABLE_VARIANTS, get_variant
else:
    from llm_runner.local_eval import LocalModelConfig, run_local_llm_dataset
    from .dataset import build_puzzle_record, board_from_record, read_puzzle_dataset, write_puzzle_dataset
    from .evaluate import evaluate_dataset
    from .generator import DeterministicPuzzleGenerator
    from .play import PlayConfig, run_interactive_session
    from .pygame_ui import launch_pygame_ui
    from .session_report import build_session_dashboard
    from .text import TextBoardEncoder
    from .variants import AVAILABLE_VARIANTS, get_variant


def _parse_variant_mine_overrides(values: list[str]) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"invalid --variant-mines value '{raw}', expected CODE=INT")
        code, mine_count = raw.split("=", 1)
        normalized = code.strip().upper()
        if normalized not in AVAILABLE_VARIANTS:
            raise ValueError(f"unknown variant in --variant-mines: {code}")
        overrides[normalized] = int(mine_count)
    return overrides


def _pick_dataset_record(args: argparse.Namespace):
    records = read_puzzle_dataset(args.dataset)
    if not records:
        raise RuntimeError("dataset is empty")
    if args.puzzle_id:
        for record in records:
            if record.puzzle_id == args.puzzle_id:
                return record
        raise RuntimeError(f"puzzle id not found: {args.puzzle_id}")
    if args.index is None:
        return records[0]
    if args.index < 0 or args.index >= len(records):
        raise RuntimeError(f"index {args.index} out of bounds for {len(records)} puzzles")
    return records[args.index]


def cmd_generate(args: argparse.Namespace) -> int:
    variant = get_variant(args.variant)
    generator = DeterministicPuzzleGenerator(
        size=args.size,
        mine_count=args.mines,
        variant=variant,
        seed=args.seed,
        max_attempts=args.max_attempts,
    )
    puzzle = generator.generate()
    encoder = TextBoardEncoder()
    print(encoder.render(puzzle.board, variant=puzzle.variant, style=args.style))
    return 0


def cmd_dataset_build(args: argparse.Namespace) -> int:
    variants = [value.strip().upper() for value in args.variants]
    for variant_code in variants:
        if variant_code not in AVAILABLE_VARIANTS:
            raise ValueError(f"unknown variant code: {variant_code}")

    mine_overrides = _parse_variant_mine_overrides(args.variant_mines)
    all_records = []
    for variant_index, variant_code in enumerate(variants):
        variant = get_variant(variant_code)
        mine_count = mine_overrides.get(variant_code, args.mines)
        for offset in range(args.count_per_variant):
            seed = args.seed + variant_index * 1_000_003 + offset * 1_009
            generator = DeterministicPuzzleGenerator(
                size=args.size,
                mine_count=mine_count,
                variant=variant,
                seed=seed,
                max_attempts=args.max_attempts,
            )
            generated = generator.generate()
            all_records.append(build_puzzle_record(generated))

    write_puzzle_dataset(all_records, args.output, append=args.append)
    print(f"Wrote {len(all_records)} puzzles to {args.output}")
    return 0


def cmd_dataset_list(args: argparse.Namespace) -> int:
    records = read_puzzle_dataset(args.dataset)
    print(f"Dataset: {args.dataset}")
    print(f"Puzzles: {len(records)}")
    if args.verbose:
        for index, record in enumerate(records):
            print(
                f"[{index}] id={record.puzzle_id} variant={record.variant_code} size={record.size} "
                f"mines={record.mine_count} seed={record.seed}"
            )
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    record = _pick_dataset_record(args)
    board, variant = board_from_record(record)
    play_config = PlayConfig(player_id=args.player_id, session_log_path=args.session_log)
    run_interactive_session(record.puzzle_id, board, variant, play_config)
    print(f"Session logged to {args.session_log}")
    return 0


def cmd_play_all(args: argparse.Namespace) -> int:
    records = read_puzzle_dataset(args.dataset)
    if not records:
        raise RuntimeError("dataset is empty")

    start = max(args.start_index, 0)
    end = len(records) if args.limit is None else min(len(records), start + args.limit)
    play_config = PlayConfig(player_id=args.player_id, session_log_path=args.session_log)

    for index in range(start, end):
        record = records[index]
        print(f"\n=== Level {index + 1}/{len(records)}: {record.puzzle_id} ({record.variant_code}) ===")
        board, variant = board_from_record(record)
        run_interactive_session(record.puzzle_id, board, variant, play_config)
        print(f"Session logged to {args.session_log}")

        if index < end - 1:
            response = input("Press Enter for next level or type q to stop: ").strip().lower()
            if response in {"q", "quit", "exit"}:
                break

    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    summary = evaluate_dataset(args.dataset, args.session_log, player_id=args.player_id)
    print(
        f"Evaluated {summary.evaluated} puzzles | won={summary.won} lost={summary.lost} | "
        f"log={args.session_log}"
    )
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    launch_pygame_ui(
        dataset_path=args.dataset,
        session_log_path=args.session_log,
        player_id=args.player_id,
        start_index=args.start_index,
        window_width=args.window_width,
        window_height=args.window_height,
    )
    return 0


def cmd_llm_local(args: argparse.Namespace) -> int:
    model_config = LocalModelConfig(
        model_id=args.model_id,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
    )
    summary = run_local_llm_dataset(
        dataset_path=args.dataset,
        session_log_path=args.session_log,
        model_config=model_config,
        player_id=args.player_id,
        style=args.style,
        start_index=args.start_index,
        limit=args.limit,
        max_turn_multiplier=args.max_turn_multiplier,
        include_cot=args.include_cot,
        reminder_each_turn=args.reminder_each_turn,
    )
    print(
        f"Evaluated {summary.evaluated} puzzles with {summary.model_id} | "
        f"won={summary.won} lost={summary.lost} aborted={summary.aborted} | "
        f"log={summary.session_log_path}"
    )
    return 0


def cmd_session_report(args: argparse.Namespace) -> int:
    summary = build_session_dashboard(
        input_paths=args.input,
        output_path=args.output,
        title=args.title,
    )
    print(
        f"Dashboard generated with {summary['sessions']} sessions "
        f"(won={summary['won']} lost={summary['lost']} aborted={summary['aborted']}) | "
        f"output={summary['output_path']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minesweeper research CLI")
    subparsers = parser.add_subparsers(dest="command")

    generate = subparsers.add_parser("generate", help="Generate one deterministic puzzle")
    generate.add_argument("--size", type=int, default=5)
    generate.add_argument("--mines", type=int, default=5)
    generate.add_argument("--variant", choices=sorted(AVAILABLE_VARIANTS), default="STD")
    generate.add_argument("--seed", type=int, default=0)
    generate.add_argument("--max-attempts", type=int, default=500)
    generate.add_argument("--style", choices=["coordinates", "flat", "narrative"], default="coordinates")
    generate.set_defaults(func=cmd_generate)

    dataset_build = subparsers.add_parser("dataset-build", help="Build reusable puzzle dataset")
    dataset_build.add_argument("--output", default="datasets/puzzles.jsonl")
    dataset_build.add_argument("--size", type=int, default=5)
    dataset_build.add_argument("--mines", type=int, default=5)
    dataset_build.add_argument("--variants", nargs="+", default=["STD"])
    dataset_build.add_argument("--variant-mines", nargs="*", default=[], help="Override mine count per variant, e.g. Q=8 C=6")
    dataset_build.add_argument("--count-per-variant", type=int, default=10)
    dataset_build.add_argument("--seed", type=int, default=0)
    dataset_build.add_argument("--max-attempts", type=int, default=500)
    dataset_build.add_argument("--append", action="store_true")
    dataset_build.set_defaults(func=cmd_dataset_build)

    dataset_list = subparsers.add_parser("dataset-list", help="List puzzles in a dataset file")
    dataset_list.add_argument("--dataset", default="datasets/puzzles.jsonl")
    dataset_list.add_argument("--verbose", action="store_true")
    dataset_list.set_defaults(func=cmd_dataset_list)

    play = subparsers.add_parser("play", help="Play a puzzle from dataset and log result")
    play.add_argument("--dataset", default="datasets/puzzles.jsonl")
    play.add_argument("--puzzle-id", default=None)
    play.add_argument("--index", type=int, default=None)
    play.add_argument("--player-id", default="human")
    play.add_argument("--session-log", default="datasets/control_sessions.jsonl")
    play.set_defaults(func=cmd_play)

    play_all = subparsers.add_parser("play-all", help="Play dataset levels sequentially and log each session")
    play_all.add_argument("--dataset", default="datasets/puzzles.jsonl")
    play_all.add_argument("--start-index", type=int, default=0)
    play_all.add_argument("--limit", type=int, default=None)
    play_all.add_argument("--player-id", default="human")
    play_all.add_argument("--session-log", default="datasets/control_sessions.jsonl")
    play_all.set_defaults(func=cmd_play_all)

    evaluate = subparsers.add_parser("evaluate", help="Run the internal solver across a dataset and log results")
    evaluate.add_argument("--dataset", default="datasets/puzzles.jsonl")
    evaluate.add_argument("--player-id", default="solver_baseline")
    evaluate.add_argument("--session-log", default="datasets/model_sessions.jsonl")
    evaluate.set_defaults(func=cmd_evaluate)

    ui = subparsers.add_parser("ui", help="Launch the pygame puzzle UI")
    ui.add_argument("--dataset", default="datasets/puzzles.jsonl")
    ui.add_argument("--start-index", type=int, default=0)
    ui.add_argument("--player-id", default="human")
    ui.add_argument("--session-log", default="datasets/control_sessions.jsonl")
    ui.add_argument("--window-width", type=int, default=900)
    ui.add_argument("--window-height", type=int, default=700)
    ui.set_defaults(func=cmd_ui)

    llm_local = subparsers.add_parser("llm-local", help="Run local LLM turn loop and log model sessions")
    llm_local.add_argument("--dataset", default="datasets/puzzles.jsonl")
    llm_local.add_argument("--session-log", default="datasets/model_sessions_local.jsonl")
    llm_local.add_argument("--player-id", default="pythia14m_local")
    llm_local.add_argument("--model-id", default="EleutherAI/pythia-14m")
    llm_local.add_argument("--max-new-tokens", type=int, default=64)
    llm_local.add_argument("--temperature", type=float, default=0.0)
    llm_local.add_argument("--top-p", type=float, default=1.0)
    llm_local.add_argument("--style", choices=["coordinates", "flat", "narrative"], default="coordinates")
    llm_local.add_argument("--start-index", type=int, default=0)
    llm_local.add_argument("--limit", type=int, default=1)
    llm_local.add_argument("--max-turn-multiplier", type=int, default=3)
    llm_local.add_argument("--include-cot", action="store_true")
    llm_local.add_argument("--reminder-each-turn", action="store_true")
    llm_local.set_defaults(func=cmd_llm_local)

    session_report = subparsers.add_parser("session-report", help="Build an interactive HTML dashboard from session JSONL logs")
    session_report.add_argument("--input", nargs="+", default=["datasets/model_sessions_local.jsonl"])
    session_report.add_argument("--output", default="datasets/session_dashboard.html")
    session_report.add_argument("--title", default="Minesweeper Session Dashboard")
    session_report.set_defaults(func=cmd_session_report)

    return parser


def main() -> None:
    parser = build_parser()

    known_commands = {
        "generate",
        "dataset-build",
        "dataset-list",
        "play",
        "play-all",
        "evaluate",
        "ui",
        "llm-local",
        "session-report",
        "-h",
        "--help",
    }
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands:
        # Backward-compatible mode: treat old flags as one-off generate command.
        legacy_args = ["generate", *sys.argv[1:]]
        args = parser.parse_args(legacy_args)
    else:
        args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
