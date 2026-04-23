from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .dataset import board_from_record, coord_to_position, read_puzzle_dataset
from .text import TextBoardEncoder

_BOARD_ENCODER = TextBoardEncoder()


def build_session_dashboard(
    input_paths: list[str],
    output_path: str,
    title: str = "Minesweeper Session Dashboard",
) -> dict[str, int | str]:
    sessions: list[dict] = []
    for raw_path in input_paths:
        sessions.extend(_read_jsonl_sessions(raw_path))

    puzzle_lookup = _load_puzzle_lookup(input_paths)
    normalized: list[dict] = []
    for entry in sessions:
        session = _normalize_session(entry)
        puzzle_record = puzzle_lookup.get(session["puzzle_id"])
        session["board_progression"] = _build_board_progression(session, puzzle_record) if puzzle_record else []
        normalized.append(session)

    normalized.sort(key=lambda item: item.get("started_at_utc", ""), reverse=True)
    summary = _build_summary(normalized)
    html_text = _render_dashboard_html(
        title=title,
        generated_at_utc=_now_iso(),
        sessions=normalized,
        summary=summary,
        input_paths=input_paths,
    )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")

    return {
        "output_path": str(path),
        "sessions": len(normalized),
        "won": summary["won"],
        "lost": summary["lost"],
        "aborted": summary["aborted"],
    }


def _read_jsonl_sessions(input_path: str) -> list[dict]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"session log not found: {input_path}")

    sessions: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {input_path}:{index}") from exc
            if isinstance(payload, dict):
                payload["_source_file"] = input_path
                sessions.append(payload)
    return sessions


def _normalize_session(session: dict) -> dict:
    moves = session.get("moves")
    if not isinstance(moves, list):
        moves = []

    model = session.get("model") if isinstance(session.get("model"), dict) else {}
    model_id = model.get("id") if isinstance(model.get("id"), str) else ""
    won = bool(session.get("won", False))
    lost = bool(session.get("lost", False))

    return {
        "session_id": str(session.get("session_id", "")),
        "puzzle_id": str(session.get("puzzle_id", "")),
        "player_id": str(session.get("player_id", "")),
        "variant_code": str(session.get("variant_code", "")),
        "started_at_utc": str(session.get("started_at_utc", "")),
        "ended_at_utc": str(session.get("ended_at_utc", "")),
        "duration_seconds": _safe_float(session.get("duration_seconds", 0.0)),
        "won": won,
        "lost": lost,
        "aborted": not won and not lost,
        "move_count": int(session.get("move_count", len(moves)) or 0),
        "turn_limit": int(session.get("turn_limit", 0) or 0),
        "failure_category": str(session.get("failure_category") or ""),
        "model_id": model_id,
        "moves": moves,
        "source_file": str(session.get("_source_file", "")),
    }


def _load_puzzle_lookup(input_paths: list[str]) -> dict[str, object]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for raw_path in input_paths:
        candidate = Path(raw_path).with_name("puzzles.jsonl")
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)

    fallback = Path("datasets/puzzles.jsonl")
    if str(fallback) not in seen:
        candidates.append(fallback)

    lookup: dict[str, object] = {}
    for candidate in candidates:
        if not candidate.exists():
            continue
        for puzzle in read_puzzle_dataset(str(candidate)):
            lookup[puzzle.puzzle_id] = puzzle
    return lookup


def _build_board_progression(session: dict, puzzle_record: object) -> list[dict[str, object]]:
    board, variant = board_from_record(puzzle_record)
    progression: list[dict[str, object]] = [
        {
            "label": "Initial board",
            "board_text": _BOARD_ENCODER.render(board, variant=variant, style="coordinates"),
      "board_grid": _board_grid_payload(board, variant),
            "move": None,
        }
    ]

    for move in session.get("moves", []):
        action = str(move.get("action") or "").upper()
        coordinate = str(move.get("coordinate") or "").strip()
        if action and coordinate:
            try:
                position = coord_to_position(coordinate, board.size)
                if action == "REVEAL":
                    board.reveal(position.row, position.col)
                elif action == "FLAG":
                    board.set_flag(position.row, position.col, True)
            except Exception:
                pass

        turn = move.get("turn")
        progression.append(
            {
                "label": f"Turn {turn}" if turn is not None else "Turn ?",
                "board_text": _BOARD_ENCODER.render(board, variant=variant, style="coordinates"),
            "board_grid": _board_grid_payload(board, variant),
                "move": {
                    "turn": turn,
                    "action": action or "-",
                    "coordinate": coordinate or "-",
                    "status_after": move.get("status_after") or "-",
                    "changed": bool(move.get("changed")),
                    "hit_mine": bool(move.get("hit_mine")),
                },
            }
        )

    return progression


def _board_grid_payload(board: object, variant: object) -> dict[str, object]:
  rows: list[list[dict[str, object]]] = []
  for row in range(board.size):
    current_row: list[dict[str, object]] = []
    for col in range(board.size):
      cell = board.cell(row, col)
      if cell.revealed:
        if cell.mine:
          token = "*"
        else:
          clue = int(variant.clue_value(board, row, col))
          token = "." if clue == 0 else str(clue)
      elif cell.flagged:
        token = "F"
      else:
        token = "#"

      current_row.append(
        {
          "row": row,
          "col": col,
          "coord": f"{chr(ord('A') + col)}{row + 1}",
          "token": token,
        }
      )
    rows.append(current_row)

  return {
    "size": board.size,
    "rows": rows,
  }


def _safe_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return 0.0


def _build_summary(sessions: list[dict]) -> dict[str, int]:
    summary = {
        "total": len(sessions),
        "won": 0,
        "lost": 0,
        "aborted": 0,
    }
    for session in sessions:
        if session["won"]:
            summary["won"] += 1
        elif session["lost"]:
            summary["lost"] += 1
        else:
            summary["aborted"] += 1
    return summary


def _render_dashboard_html(
    title: str,
    generated_at_utc: str,
    sessions: list[dict],
    summary: dict[str, int],
    input_paths: list[str],
) -> str:
    data_payload = {
        "title": title,
        "generated_at_utc": generated_at_utc,
        "sessions": sessions,
        "summary": summary,
        "input_paths": input_paths,
    }
    data_json = json.dumps(data_payload, ensure_ascii=True)
    escaped_title = html.escape(title)

    html_template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --ink: #1e2b26;
      --muted: #5c6b64;
      --line: #d9d1c2;
      --ok: #2f7d4a;
      --bad: #a83c2f;
      --warn: #9b6a12;
      --accent: #0b5c66;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 10%, #efe6d5 0%, transparent 35%),
        radial-gradient(circle at 90% 90%, #dfe9e4 0%, transparent 45%),
        var(--bg);
      font-family: Georgia, "Times New Roman", serif;
    }
    .shell { max-width: 1280px; margin: 0 auto; padding: 24px; }
    .hero {
      background: linear-gradient(110deg, #fff8ea, #edf8f3);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px 20px;
      box-shadow: 0 8px 24px rgba(30, 43, 38, 0.08);
    }
    h1 { margin: 0; font-size: 30px; letter-spacing: 0.2px; }
    .subtle { color: var(--muted); font-size: 14px; }
    .stats {
      margin-top: 14px;
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
    }
    .value { font-size: 24px; font-weight: bold; line-height: 1; }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
    .ok { color: var(--ok); }
    .bad { color: var(--bad); }
    .warn { color: var(--warn); }
    .controls {
      margin-top: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      display: grid;
      grid-template-columns: 2fr 1fr 1fr 1fr;
      gap: 8px;
    }
    .controls input, .controls select {
      width: 100%;
      border: 1px solid #c5bcae;
      border-radius: 8px;
      padding: 8px 10px;
      background: #fff;
      color: var(--ink);
      font-size: 14px;
    }
    .layout {
      margin-top: 16px;
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 12px;
    }
    .table-wrap {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: auto;
      max-height: 68vh;
    }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    thead th {
      position: sticky;
      top: 0;
      background: #f8f3e9;
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 9px;
      cursor: pointer;
      user-select: none;
    }
    tbody td { border-top: 1px solid #efe7d8; padding: 8px 9px; vertical-align: top; }
    tbody tr:hover { background: #f8f5ef; }
    tbody tr.active { background: #f0efe7; outline: 1px solid #d7cebf; }
    .pill {
      display: inline-block;
      border: 1px solid currentColor;
      border-radius: 999px;
      padding: 1px 7px;
      font-size: 12px;
      font-weight: bold;
    }
    .detail {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      overflow: auto;
      max-height: 68vh;
    }
    .meta { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }
    .meta .card { min-height: 58px; }
    .moves { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
    .moves table { font-size: 12px; }
    .board-progress { display: grid; gap: 10px; margin-top: 12px; }
    .board-card {
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
      padding: 10px;
    }
    .board-card-head {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: baseline;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .board-text {
      margin: 0;
      padding: 10px;
      border-radius: 8px;
      border: 1px solid #ddd4c1;
      background: #fbfaf6;
      font-family: "Courier New", monospace;
      font-size: 12px;
      line-height: 1.35;
      white-space: pre;
      overflow: auto;
    }
    .board-figure {
      border: 1px solid #ddd4c1;
      border-radius: 10px;
      background: #faf7ef;
      padding: 10px;
      overflow: auto;
    }
    .ms-board {
      --cell: 28px;
      display: grid;
      grid-template-columns: var(--cell) repeat(var(--size, 5), var(--cell));
      grid-auto-rows: var(--cell);
      width: max-content;
      gap: 2px;
      align-items: center;
      justify-items: center;
      font-family: "Courier New", monospace;
    }
    .axis,
    .corner {
      color: #64756a;
      font-size: 11px;
      font-weight: bold;
      width: var(--cell);
      height: var(--cell);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .tile {
      width: var(--cell);
      height: var(--cell);
      border-radius: 6px;
      border: 1px solid #b7c2ba;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      line-height: 1;
      font-weight: bold;
      user-select: none;
    }
    .tile-hidden {
      background: linear-gradient(180deg, #dbe5dd, #c8d5cb);
      border-color: #98a99c;
      color: transparent;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
    }
    .tile-flag {
      background: #f8d9a0;
      border-color: #c08f3f;
      color: #6e4208;
    }
    .tile-mine {
      background: #f4b1a8;
      border-color: #b2473c;
      color: #5f1d16;
    }
    .tile-safe {
      background: #f2f7f3;
      border-color: #c2cec5;
      color: #52645a;
    }
    .n1 { color: #2269b5; }
    .n2 { color: #2f8f49; }
    .n3 { color: #c74a3a; }
    .n4 { color: #6842b2; }
    .n5 { color: #a25414; }
    .n6 { color: #0e7b84; }
    .n7 { color: #37414b; }
    .n8 { color: #6f7b84; }
    .board-fallback { margin-top: 8px; }
    .code {
      white-space: pre-wrap;
      background: #f8f8f8;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 8px;
      font-family: "Courier New", monospace;
      font-size: 12px;
      max-height: 200px;
      overflow: auto;
    }
    details { margin-top: 6px; }
    summary { cursor: pointer; color: var(--accent); }
    @media (max-width: 980px) {
      .stats { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .controls { grid-template-columns: 1fr; }
      .layout { grid-template-columns: 1fr; }
      .meta { grid-template-columns: 1fr; }
      .io-grid { grid-template-columns: 1fr; }
    }
    .io-grid {
      margin-top: 8px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .io-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    .io-head {
      padding: 6px 8px;
      font-size: 12px;
      font-weight: bold;
      border-bottom: 1px solid var(--line);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .io-head.prompt { background: #eef4fb; color: #204c73; }
    .io-head.output { background: #f8efe2; color: #70471b; }
    .kv { margin-top: 6px; color: var(--muted); font-size: 12px; }
    .rules-menu {
      margin-top: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
    }
    .rules-menu summary {
      font-size: 14px;
      font-weight: 600;
      color: var(--accent);
      cursor: pointer;
      user-select: none;
    }
    .rules-content {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      color: var(--ink);
      font-size: 13px;
      line-height: 1.6;
    }
    .rules-section {
      margin-bottom: 14px;
    }
    .rules-section h3 {
      margin: 8px 0 6px 0;
      font-size: 13px;
      font-weight: bold;
      color: var(--ink);
    }
    .rules-section p {
      margin: 6px 0;
      color: var(--ink);
    }
    .variant-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 12px;
      margin-top: 8px;
    }
    .variant-card {
      border: 1px solid #ddd4c1;
      border-radius: 8px;
      padding: 8px;
      background: #fbfaf6;
    }
    .variant-code {
      font-weight: bold;
      color: var(--accent);
      font-family: "Courier New", monospace;
      font-size: 12px;
    }
    .variant-name {
      font-weight: 600;
      color: var(--ink);
      font-size: 12px;
    }
    .variant-desc {
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
      line-height: 1.4;
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1 id="title"></h1>
      <div class="subtle" id="meta"></div>
      <div class="stats">
        <div class="card"><div class="value" id="stat-total">0</div><div class="label">Total</div></div>
        <div class="card"><div class="value ok" id="stat-won">0</div><div class="label">Won</div></div>
        <div class="card"><div class="value bad" id="stat-lost">0</div><div class="label">Lost</div></div>
        <div class="card"><div class="value warn" id="stat-aborted">0</div><div class="label">Aborted</div></div>
        <div class="card"><div class="value" id="stat-winrate">0%</div><div class="label">Win Rate</div></div>
      </div>
    </section>

    <section class="controls">
      <input id="search" placeholder="Search session, puzzle, player, model, failure..." />
      <select id="variant"><option value="">All variants</option></select>
      <select id="outcome">
        <option value="">All outcomes</option>
        <option value="won">Won</option>
        <option value="lost">Lost</option>
        <option value="aborted">Aborted</option>
      </select>
      <select id="failure"><option value="">All failure categories</option></select>
    </section>

    <section class="rules-menu">
      <details>
        <summary>Minesweeper Base Rules & Variants</summary>
        <div class="rules-content">
          <div class="rules-section">
            <h3>Basic Minesweeper Rules</h3>
            <p><strong>Goal:</strong> Reveal all safe cells without hitting any mines.</p>
            <p><strong>Gameplay:</strong></p>
            <ul style="margin: 6px 0; padding-left: 20px;">
              <li>Each revealed cell shows the number of adjacent mines (0-8), or is empty</li>
              <li>Flag cells you believe contain mines to keep track</li>
              <li>Use logical deduction to identify safe cells</li>
              <li>Win by revealing all non-mine cells</li>
              <li>Lose by revealing a mine</li>
            </ul>
          </div>

          <div class="rules-section">
            <h3>Variant Rules</h3>
            <p>Standard Minesweeper can be modified with additional constraints:</p>
            <div class="variant-grid">
              <div class="variant-card">
                <div class="variant-code">STD</div>
                <div class="variant-name">Standard</div>
                <div class="variant-desc">Classic Minesweeper rules with no additional constraints.</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">Q</div>
                <div class="variant-name">Quad</div>
                <div class="variant-desc">Each 2×2 block must contain at least one mine.</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">C</div>
                <div class="variant-name">Connected</div>
                <div class="variant-desc">All mines must be in one 8-connected component.</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">T</div>
                <div class="variant-name">Triplet</div>
                <div class="variant-desc">No 3 mines can appear in a contiguous line (horizontal, vertical, or diagonal).</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">O</div>
                <div class="variant-name">Outside</div>
                <div class="variant-desc">Safe cells are connected. Each mine must connect to the border through mines.</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">D</div>
                <div class="variant-name">Dual</div>
                <div class="variant-desc">Mines form disjoint non-touching orthogonal pairs (exactly 2 mines per pair).</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">S</div>
                <div class="variant-name">Snake</div>
                <div class="variant-desc">Mines form one non-self-intersecting orthogonal path.</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">R</div>
                <div class="variant-name">RowCol</div>
                <div class="variant-desc">All rows and columns contain the same number of mines.</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">H</div>
                <div class="variant-name">Horizontal</div>
                <div class="variant-desc">No two mines can touch horizontally (orthogonal pairs are forbidden).</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">P</div>
                <div class="variant-name">Partition</div>
                <div class="variant-desc">Clue number = count of consecutive mine groups in the 8-neighbor ring around the cell.</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">L</div>
                <div class="variant-name">Liar</div>
                <div class="variant-desc">Each clue differs from the true adjacent mine count by exactly one.</div>
              </div>
              <div class="variant-card">
                <div class="variant-code">X</div>
                <div class="variant-name">Cross</div>
                <div class="variant-desc">Clue counts mines in a plus-shaped region (up to distance 2 in cardinal directions).</div>
              </div>
            </div>
          </div>
        </div>
      </details>
    </section>

    <section class="layout">
      <div class="table-wrap">
        <table id="session-table">
          <thead>
            <tr>
              <th data-sort="player_id">Player</th>
              <th data-sort="model_id">Model</th>
              <th data-sort="variant_code">Variant</th>
              <th data-sort="move_count">Moves</th>
              <th data-sort="duration_seconds">Duration</th>
              <th data-sort="failure_category">Failure</th>
              <th data-sort="outcome">Outcome</th>
            </tr>
          </thead>
          <tbody id="session-body"></tbody>
        </table>
      </div>

      <aside class="detail">
        <h2 style="margin-top:0;">Session Details</h2>
        <div class="subtle">Click a row to inspect the board after each move and the raw model outputs.</div>
        <div id="detail" class="subtle" style="margin-top:10px;">No session selected.</div>
      </aside>
    </section>
  </div>

  <script id="dashboard-data" type="application/json">__DATA_JSON__</script>
  <script>
    const data = JSON.parse(document.getElementById('dashboard-data').textContent);
    const sessions = data.sessions || [];

    const state = {
      sortKey: 'started_at_utc',
      sortDir: 'desc',
      search: '',
      variant: '',
      outcome: '',
      failure: '',
      selectedSessionId: '',
    };

    const byId = new Map(sessions.map((s) => [s.session_id, s]));

    const titleEl = document.getElementById('title');
    const metaEl = document.getElementById('meta');
    titleEl.textContent = data.title;
    metaEl.textContent = `Generated ${data.generated_at_utc} from ${data.input_paths.length} file(s)`;

    const statTotal = document.getElementById('stat-total');
    const statWon = document.getElementById('stat-won');
    const statLost = document.getElementById('stat-lost');
    const statAborted = document.getElementById('stat-aborted');
    const statWinrate = document.getElementById('stat-winrate');

    const searchEl = document.getElementById('search');
    const variantEl = document.getElementById('variant');
    const outcomeEl = document.getElementById('outcome');
    const failureEl = document.getElementById('failure');
    const bodyEl = document.getElementById('session-body');
    const detailEl = document.getElementById('detail');

    function outcomeLabel(s) {
      if (s.won) return 'won';
      if (s.lost) return 'lost';
      return 'aborted';
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    function fmtSeconds(value) {
      const n = Number(value || 0);
      return `${n.toFixed(3)}s`;
    }

    function parseBoardFromText(boardText) {
      if (!boardText) return null;
      const lines = String(boardText)
        .split('\\n')
        .map((line) => line.trimEnd());
      const rowLines = lines.filter((line) => /^\\d+\\s+/.test(line));
      if (rowLines.length === 0) return null;

      const rows = [];
      let maxWidth = 0;
      for (const rowLine of rowLines) {
        const tokens = rowLine.trim().split(/\\s+/).slice(1);
        if (tokens.length > 0) {
          rows.push(tokens);
          maxWidth = Math.max(maxWidth, tokens.length);
        }
      }
      if (rows.length === 0 || maxWidth === 0) return null;

      const normalizedRows = rows.map((tokens, rowIndex) => {
        const padded = [...tokens];
        while (padded.length < maxWidth) padded.push('#');
        return padded.map((token, colIndex) => ({
          row: rowIndex,
          col: colIndex,
          coord: `${String.fromCharCode(65 + colIndex)}${rowIndex + 1}`,
          token,
        }));
      });

      return {
        size: maxWidth,
        rows: normalizedRows,
      };
    }

    function renderBoardGrid(boardGrid, boardText) {
      const grid = boardGrid || parseBoardFromText(boardText || '');
      if (!grid || !Array.isArray(grid.rows) || grid.rows.length === 0) {
        return `<pre class="board-text">${escapeHtml(boardText || '(unavailable)')}</pre>`;
      }

      const size = Number(grid.size || (grid.rows[0] ? grid.rows[0].length : 0) || 0);
      if (!size) {
        return `<pre class="board-text">${escapeHtml(boardText || '(unavailable)')}</pre>`;
      }

      const alpha = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
      let htmlOut = `<div class="board-figure"><div class="ms-board" style="--size:${size}">`;
      htmlOut += `<div class="corner"></div>`;
      for (let col = 0; col < size; col += 1) {
        htmlOut += `<div class="axis">${escapeHtml(alpha[col] || String(col + 1))}</div>`;
      }

      for (let row = 0; row < grid.rows.length; row += 1) {
        htmlOut += `<div class="axis">${row + 1}</div>`;
        const cells = grid.rows[row] || [];
        for (let col = 0; col < size; col += 1) {
          const cell = cells[col] || { token: '#', coord: `${alpha[col] || col + 1}${row + 1}` };
          const token = String(cell.token || '#');
          const coord = String(cell.coord || `${alpha[col] || col + 1}${row + 1}`);

          let cls = 'tile tile-hidden';
          let glyph = '';
          if (token === 'F') {
            cls = 'tile tile-flag';
            glyph = 'F';
          } else if (token === '*') {
            cls = 'tile tile-mine';
            glyph = '*';
          } else if (token === '.' || /^\\d$/.test(token)) {
            cls = 'tile tile-safe';
            if (/^[1-8]$/.test(token)) {
              cls += ` n${token}`;
            }
            glyph = token === '.' ? '' : token;
          }

          htmlOut += `<div class="${cls}" title="${escapeHtml(coord)}">${escapeHtml(glyph)}</div>`;
        }
      }

      htmlOut += `</div>`;
      if (boardText) {
        htmlOut += `<details class="board-fallback"><summary>Show ASCII board text</summary><pre class="board-text">${escapeHtml(boardText)}</pre></details>`;
      }
      htmlOut += `</div>`;
      return htmlOut;
    }

    function compare(a, b, key) {
      if (key === 'outcome') return outcomeLabel(a).localeCompare(outcomeLabel(b));
      const left = a[key] ?? '';
      const right = b[key] ?? '';
      if (typeof left === 'number' || typeof right === 'number') {
        return Number(left) - Number(right);
      }
      return String(left).localeCompare(String(right));
    }

    function buildSelectOptions() {
      const variants = [...new Set(sessions.map((s) => s.variant_code).filter(Boolean))].sort();
      const failures = [...new Set(sessions.map((s) => s.failure_category).filter(Boolean))].sort();
      for (const variant of variants) {
        const opt = document.createElement('option');
        opt.value = variant;
        opt.textContent = variant;
        variantEl.appendChild(opt);
      }
      for (const failure of failures) {
        const opt = document.createElement('option');
        opt.value = failure;
        opt.textContent = failure;
        failureEl.appendChild(opt);
      }
    }

    function filteredSessions() {
      const needle = state.search.trim().toLowerCase();
      return sessions.filter((s) => {
        if (state.variant && s.variant_code !== state.variant) return false;
        if (state.failure && s.failure_category !== state.failure) return false;
        if (state.outcome && outcomeLabel(s) !== state.outcome) return false;
        if (needle) {
          const hay = [s.session_id, s.puzzle_id, s.player_id, s.model_id, s.failure_category, s.variant_code].join(' ').toLowerCase();
          if (!hay.includes(needle)) return false;
        }
        return true;
      });
    }

    function updateStats(rows) {
      let won = 0;
      let lost = 0;
      let aborted = 0;
      for (const s of rows) {
        if (s.won) won += 1;
        else if (s.lost) lost += 1;
        else aborted += 1;
      }
      const total = rows.length;
      const winRate = total === 0 ? 0 : Math.round((1000 * won) / total) / 10;
      statTotal.textContent = String(total);
      statWon.textContent = String(won);
      statLost.textContent = String(lost);
      statAborted.textContent = String(aborted);
      statWinrate.textContent = `${winRate}%`;
    }

    function renderTable() {
      const rows = filteredSessions().sort((a, b) => {
        const cmp = compare(a, b, state.sortKey);
        return state.sortDir === 'asc' ? cmp : -cmp;
      });

      updateStats(rows);
      bodyEl.innerHTML = '';
      for (const s of rows) {
        const tr = document.createElement('tr');
        tr.dataset.sessionId = s.session_id;
        if (s.session_id === state.selectedSessionId) tr.classList.add('active');

        const outcome = outcomeLabel(s);
        const outcomeClass = outcome === 'won' ? 'ok' : outcome === 'lost' ? 'bad' : 'warn';
        const failure = s.failure_category || '-';

        tr.innerHTML = `
          <td>${escapeHtml(s.player_id || '-')}</td>
          <td>${escapeHtml(s.model_id || '-')}</td>
          <td>${escapeHtml(s.variant_code || '-')}</td>
          <td>${escapeHtml(String(s.move_count || 0))}</td>
          <td>${escapeHtml(fmtSeconds(s.duration_seconds || 0))}</td>
          <td>${escapeHtml(failure)}</td>
          <td><span class="pill ${outcomeClass}">${escapeHtml(outcome)}</span></td>
        `;
        tr.addEventListener('click', () => {
          state.selectedSessionId = s.session_id;
          renderTable();
          renderDetail();
        });
        bodyEl.appendChild(tr);
      }

      if (!state.selectedSessionId && rows.length > 0) {
        state.selectedSessionId = rows[0].session_id;
        renderTable();
        renderDetail();
      }
      if (rows.length === 0) {
        detailEl.innerHTML = '<div class="subtle">No sessions match the current filters.</div>';
      }
    }

    function renderDetail() {
      const s = byId.get(state.selectedSessionId);
      if (!s) {
        detailEl.innerHTML = '<div class="subtle">No session selected.</div>';
        return;
      }

      const boardProgression = s.board_progression || [];
      let initialBoardHtml = '';
      const boardByTurn = new Map();
      for (const step of boardProgression) {
        if (!step || !step.move) {
          if (!initialBoardHtml && step && step.board_text) {
            initialBoardHtml = `
              <details>
                <summary>Initial board before the first move</summary>
                ${renderBoardGrid(step.board_grid, step.board_text || '')}
              </details>
            `;
          }
          continue;
        }
        const turn = step.move.turn;
        if (turn !== undefined && turn !== null && !boardByTurn.has(turn)) {
          boardByTurn.set(turn, {
            board_text: step.board_text || '',
            board_grid: step.board_grid || null,
          });
        }
      }

      const moveRows = (s.moves || []).map((move) => {
        const action = move.action || '-';
        const coordinate = move.coordinate || '-';
        const changed = move.changed ? 'yes' : 'no';
        const hitMine = move.hit_mine ? 'yes' : 'no';
        const status = move.status_after || '-';
        const error = move.error || '';
        const failure = move.failure_category || '';
        const prompt = move.prompt || '';
        const output = move.model_output || '';
        const turn = move.turn ?? '-';
        const boardAfterTurn = boardByTurn.get(move.turn) || { board_text: '', board_grid: null };
        return `
          <tr>
            <td>${escapeHtml(String(turn))}</td>
            <td>${escapeHtml(action)}</td>
            <td>${escapeHtml(coordinate)}</td>
            <td>${escapeHtml(changed)}</td>
            <td>${escapeHtml(hitMine)}</td>
            <td>${escapeHtml(status)}</td>
            <td>${escapeHtml(error || failure || '-')}</td>
          </tr>
          <tr>
            <td colspan="7">
              <div class="kv">Board after turn ${escapeHtml(String(turn))}</div>
              ${renderBoardGrid(boardAfterTurn.board_grid, boardAfterTurn.board_text || '(unavailable)')}
            </td>
          </tr>
          <tr>
            <td colspan="7">
              <details>
                <summary>Turn ${escapeHtml(String(turn))} prompt and output</summary>
                <div class="kv">Parsed move recorded by evaluator: ${escapeHtml(String(action))} ${escapeHtml(String(coordinate))}</div>
                <div class="io-grid">
                  <div class="io-card">
                    <div class="io-head prompt">Prompt sent to model</div>
                    <div class="code">${escapeHtml(prompt || '(none)')}</div>
                  </div>
                  <div class="io-card">
                    <div class="io-head output">Raw model output</div>
                    <div class="code">${escapeHtml(output || '(none)')}</div>
                  </div>
                </div>
              </details>
            </td>
          </tr>
        `;
      }).join('');

      detailEl.innerHTML = `
        <div class="meta">
          <div class="card"><div class="label">Session ID</div><div>${escapeHtml(s.session_id || '-')}</div></div>
          <div class="card"><div class="label">Source File</div><div>${escapeHtml(s.source_file || '-')}</div></div>
          <div class="card"><div class="label">Puzzle</div><div>${escapeHtml(s.puzzle_id || '-')}</div></div>
          <div class="card"><div class="label">Player / Model</div><div>${escapeHtml((s.player_id || '-') + ' / ' + (s.model_id || '-'))}</div></div>
          <div class="card"><div class="label">Variant</div><div>${escapeHtml(s.variant_code || '-')}</div></div>
          <div class="card"><div class="label">Outcome</div><div>${escapeHtml(outcomeLabel(s))}</div></div>
          <div class="card"><div class="label">Duration / Moves</div><div>${escapeHtml(fmtSeconds(s.duration_seconds))} / ${escapeHtml(String(s.move_count || 0))}</div></div>
          <div class="card"><div class="label">Failure Category</div><div>${escapeHtml(s.failure_category || '-')}</div></div>
        </div>
        ${initialBoardHtml}
        <div class="moves">
          <table>
            <thead>
              <tr>
                <th>Turn</th><th>Action</th><th>Coord</th><th>Changed</th><th>Hit Mine</th><th>Status</th><th>Error / Failure</th>
              </tr>
            </thead>
            <tbody>${moveRows || '<tr><td colspan="7">No move records.</td></tr>'}</tbody>
          </table>
        </div>
      `;
    }

    function wireEvents() {
      searchEl.addEventListener('input', () => { state.search = searchEl.value; renderTable(); });
      variantEl.addEventListener('change', () => { state.variant = variantEl.value; renderTable(); });
      outcomeEl.addEventListener('change', () => { state.outcome = outcomeEl.value; renderTable(); });
      failureEl.addEventListener('change', () => { state.failure = failureEl.value; renderTable(); });

      document.querySelectorAll('th[data-sort]').forEach((th) => {
        th.addEventListener('click', () => {
          const key = th.getAttribute('data-sort');
          if (!key) return;
          if (state.sortKey === key) {
            state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
          } else {
            state.sortKey = key;
            state.sortDir = key === 'started_at_utc' ? 'desc' : 'asc';
          }
          renderTable();
        });
      });
    }

    function init() {
      buildSelectOptions();
      wireEvents();
      renderTable();
      renderDetail();
    }

    init();
  </script>
</body>
</html>
"""
    return html_template.replace("__TITLE__", escaped_title).replace("__DATA_JSON__", data_json)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
