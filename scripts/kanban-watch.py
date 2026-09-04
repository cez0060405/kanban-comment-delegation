#!/usr/bin/env python3
"""kanban-watch.py — board + comment watchdog for delegation detection.

Outputs a deterministic digest of board state and recent comments, for a cron
monitor to diff against the previous run. When a worker writes a 【委托】
(delegate) comment, the output changes and the orchestrator agent wakes up.

Output identical to last run -> no agent wake (no noise).
Output changed -> agent wakes and can act on the DELEGATE lines.

Delegation dedup (v3, 2026-09-04):
- A worker 【委托】 comment is reported as DELEGATE only ONCE.
- Once a DELEGATE-* task referencing the source task exists on the board
  (orchestrator created it), the comment is marked seen and reported as
  DELEGATED (stable line) — so a second orchestrator pass does not re-dispatch.
- Seen state persists in kanban-watch-state.json next to this script.

Usage:
    python kanban-watch.py            # one digest to stdout
    # wire as cron monitor: runs every N minutes, agent only on change

Reference implementation for the kanban-comment-delegation protocol.
Adjust BOARD_DB / KANBAN_LIST_CMD to your environment.
"""
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime

# --- config ---------------------------------------------------------------
BOARD_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kanban.db")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kanban-watch-state.json")
KANBAN_LIST_CMD = ["hermes", "kanban", "list"]
COMMENT_WINDOW_SECONDS = 600  # only comments from the last 10 minutes
SYSTEM_AUTHORS = {"default", "user", "system"}  # orchestrator/system, not workers
DELEGATE_TASK_PREFIX = "DELEGATE-"  # orchestrator task title prefix
# --------------------------------------------------------------------------

_TASK_LINE_RE = re.compile(r"^[●▶⊘✓✗]\s+(t_[0-9a-f]+)\s+(\S+)\s+(\S+)\s+(.*)$")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen_delegations": {}}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def board_digest():
    """Task status lines from `hermes kanban list`."""
    lines = []
    try:
        out = subprocess.run(
            KANBAN_LIST_CMD,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        ).stdout
        for line in out.splitlines():
            m = _TASK_LINE_RE.match(line)
            if m:
                lines.append(f"{m.group(1)} {m.group(2)} {m.group(4)}")
    except Exception as e:
        lines.append(f"ERROR_LIST {e}")
    return lines


def existing_delegate_tasks(conn):
    """Task ids whose title starts with DELEGATE- (orchestrator-created)."""
    rows = conn.execute(
        "SELECT id, title, body FROM tasks WHERE title LIKE ?",
        (DELEGATE_TASK_PREFIX + "%",),
    ).fetchall()
    return rows  # tuples: (id, title, body)


def comment_digest(conn, state):
    """Recent comments; worker 【委托】 comments flagged DELEGATE (once) or DELEGATED.

    Dedup logic:
    - comment already in seen_delegations -> DELEGATED (stable)
    - a DELEGATE-* task body references this source task -> mark seen, DELEGATED
    - otherwise -> DELEGATE (new signal, wakes orchestrator)
    """
    lines = []
    since = int(datetime.now().timestamp()) - COMMENT_WINDOW_SECONDS
    rows = conn.execute(
        "SELECT id, task_id, author, substr(body,1,80) FROM task_comments "
        "WHERE created_at > ? ORDER BY created_at",
        (since,),
    ).fetchall()

    delegate_tasks = existing_delegate_tasks(conn)
    seen = state.get("seen_delegations", {})
    changed = False

    for cid, task_id, author, body in rows:
        if not body.startswith("【委托】"):
            continue
        if author in SYSTEM_AUTHORS:
            lines.append(f"COMMENT {task_id} {author}: {body}")
            continue
        # worker-authored delegation
        if str(cid) in seen:
            lines.append(f"DELEGATED {task_id}")
            continue
        # already dispatched? a DELEGATE-* task body references this source task
        dispatched = any(
            task_id in (t[2] or "") for t in delegate_tasks
        )
        if dispatched:
            seen[str(cid)] = task_id
            changed = True
            lines.append(f"DELEGATED {task_id}")
            continue
        lines.append(f"DELEGATE {task_id} {author}: {body}")

    if changed:
        state["seen_delegations"] = seen
        save_state(state)
    return lines


def main():
    state = load_state()
    lines = board_digest()
    try:
        conn = sqlite3.connect(BOARD_DB)
        try:
            lines += comment_digest(conn, state)
        finally:
            conn.close()
    except Exception as e:
        lines.append(f"ERROR_COMMENTS {e}")

    if not lines:
        print("NO_TASKS")
        return
    print("\n".join(sorted(lines)))


if __name__ == "__main__":
    main()
