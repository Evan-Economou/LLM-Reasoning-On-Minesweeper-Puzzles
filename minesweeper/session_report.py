from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path


def build_session_dashboard(
    input_paths: list[str],
    output_path: str,
    title: str = "Minesweeper Session Dashboard",
) -> dict[str, int | str]:
    sessions: list[dict] = []
    for raw_path in input_paths:
        sessions.extend(_read_jsonl_sessions(raw_path))

    normalized = [_normalize_session(entry) for entry in sessions]
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

    result: dict[str, int | str] = {
        "output_path": str(path),
        "sessions": len(normalized),
        "won": summary["won"],
        "lost": summary["lost"],
        "aborted": summary["aborted"],
    }
    return result


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
    won = bool(session.get("won", False))
    lost = bool(session.get("lost", False))
    aborted = not won and not lost
    moves = session.get("moves")
    if not isinstance(moves, list):
        moves = []

    model = session.get("model") if isinstance(session.get("model"), dict) else {}
    model_id = model.get("id") if isinstance(model.get("id"), str) else ""

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
        "aborted": aborted,
        "move_count": int(session.get("move_count", len(moves)) or 0),
        "turn_limit": int(session.get("turn_limit", 0) or 0),
        "failure_category": str(session.get("failure_category") or ""),
        "model_id": model_id,
        "moves": moves,
        "source_file": str(session.get("_source_file", "")),
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
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
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
      font-family: Georgia, \"Times New Roman\", serif;
    }
    .shell {
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
    }
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
    .code {
      white-space: pre-wrap;
      background: #f8f8f8;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 8px;
      font-family: \"Courier New\", monospace;
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
    }
  </style>
</head>
<body>
  <div class=\"shell\">
    <section class=\"hero\">
      <h1 id=\"title\"></h1>
      <div class=\"subtle\" id=\"meta\"></div>
      <div class=\"stats\">
        <div class=\"card\"><div class=\"value\" id=\"stat-total\">0</div><div class=\"label\">Total</div></div>
        <div class=\"card\"><div class=\"value ok\" id=\"stat-won\">0</div><div class=\"label\">Won</div></div>
        <div class=\"card\"><div class=\"value bad\" id=\"stat-lost\">0</div><div class=\"label\">Lost</div></div>
        <div class=\"card\"><div class=\"value warn\" id=\"stat-aborted\">0</div><div class=\"label\">Aborted</div></div>
        <div class=\"card\"><div class=\"value\" id=\"stat-winrate\">0%</div><div class=\"label\">Win Rate</div></div>
      </div>
    </section>

    <section class=\"controls\">
      <input id=\"search\" placeholder=\"Search session, puzzle, player, model, failure...\" />
      <select id=\"variant\"><option value=\"\">All variants</option></select>
      <select id=\"outcome\">
        <option value=\"\">All outcomes</option>
        <option value=\"won\">Won</option>
        <option value=\"lost\">Lost</option>
        <option value=\"aborted\">Aborted</option>
      </select>
      <select id=\"failure\"><option value=\"\">All failure categories</option></select>
    </section>

    <section class=\"layout\">
      <div class=\"table-wrap\">
        <table id=\"session-table\">
          <thead>
            <tr>
              <th data-sort=\"started_at_utc\">Started</th>
              <th data-sort=\"player_id\">Player</th>
              <th data-sort=\"model_id\">Model</th>
              <th data-sort=\"variant_code\">Variant</th>
              <th data-sort=\"move_count\">Moves</th>
              <th data-sort=\"duration_seconds\">Duration</th>
              <th data-sort=\"failure_category\">Failure</th>
              <th data-sort=\"outcome\">Outcome</th>
            </tr>
          </thead>
          <tbody id=\"session-body\"></tbody>
        </table>
      </div>

      <aside class=\"detail\">
        <h2 style=\"margin-top:0;\">Session Details</h2>
        <div class=\"subtle\">Click a row to inspect all moves and raw model outputs.</div>
        <div id=\"detail\" class=\"subtle\" style=\"margin-top:10px;\">No session selected.</div>
      </aside>
    </section>
  </div>

  <script id=\"dashboard-data\" type=\"application/json\">__DATA_JSON__</script>
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

    function compare(a, b, key) {
      if (key === 'outcome') {
        return outcomeLabel(a).localeCompare(outcomeLabel(b));
      }
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
          const hay = [
            s.session_id,
            s.puzzle_id,
            s.player_id,
            s.model_id,
            s.failure_category,
            s.variant_code,
          ].join(' ').toLowerCase();
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
          <td>${escapeHtml(s.started_at_utc || '-')}</td>
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
        return `
          <tr>
            <td>${escapeHtml(String(move.turn ?? '-'))}</td>
            <td>${escapeHtml(action)}</td>
            <td>${escapeHtml(coordinate)}</td>
            <td>${escapeHtml(changed)}</td>
            <td>${escapeHtml(hitMine)}</td>
            <td>${escapeHtml(status)}</td>
            <td>${escapeHtml(error || failure || '-')}</td>
          </tr>
          <tr>
            <td colspan="7">
              <details>
                <summary>Prompt and model output for turn ${escapeHtml(String(move.turn ?? '-'))}</summary>
                <div class="code"><strong>Prompt</strong>\n${escapeHtml(prompt || '(none)')}\n\n<strong>Model output</strong>\n${escapeHtml(output || '(none)')}</div>
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