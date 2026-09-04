# kanban-comment-delegation

**Comment-driven task delegation for multi-agent kanban orchestration.**

A lightweight protocol + watchdog that lets AI worker agents hand off out-of-scope subtasks to the right specialist — by writing a `【委托】` (delegate) comment on their current kanban task. The orchestrator (main agent) picks up the comment, creates a new task, and dispatches it to the matching identity. No new infrastructure: it reuses the kanban board's existing comment channel as the inter-agent protocol.

> 中文：多智能体看板编排的「评论即协议」委托闭环。worker 遇到非本职子任务时，在当前任务评论写【委托】→ 哨兵检测 → 主控收集 → 新建任务派给对应身份。零新增基础设施，复用看板评论通道。

## Why this exists

Multi-agent kanban systems usually solve delegation in one of two ways:

1. **Orchestrator pre-plans everything** — brittle; workers can't adapt when they hit unexpected out-of-scope work mid-task.
2. **Workers silently do everything** — a `programmer` forced to design a color scheme, or a `designer` forced to debug code. Quality suffers.

This protocol is the middle path: **workers stay honest about their boundaries, and the board's comment channel becomes the delegation bus.** The orchestrator stays in the loop without polling every worker's every move.

## How it works

```
┌─────────────┐  writes 【委托】comment   ┌──────────────────┐
│  Worker A   │ ───────────────────────▶ │  Kanban board    │
│ (e.g. code- │                          │  (task_comments) │
│  review)    │                          └────────┬─────────┘
└─────────────┘                                   │
                                                  │ watchdog polls
                                                  ▼
                                        ┌──────────────────┐
                                        │  Watchdog script  │
                                        │  (kanban-watch.py)│
                                        └────────┬─────────┘
                                                 │ output changed
                                                 ▼
                                        ┌──────────────────┐
                                        │  Orchestrator     │
                                        │  (main agent)     │
                                        └────────┬─────────┘
                                                 │ creates task
                                                 ▼
                                        ┌──────────────────┐
                                        │  Worker B        │
                                        │  (specialist)    │
                                        └──────────────────┘
```

### The loop

1. **Worker hits out-of-scope work** → writes a `【委托】` comment on its current task:
   ```
   【委托】<subtask description> 需要 <identity> 处理。
   建议：<specific approach or reference files>
   ```
2. **Watchdog detects the comment** → the kanban-watch script's output changes → the cron monitor wakes the orchestrator.
3. **Orchestrator collects the comment** → creates a new task with the delegation context in the body → dispatches to the matching identity.
4. **Specialist completes the task** → deliverable lands in the shared workspace.

### The one rule

> **"Is this work my identity's job? Yes → do it yourself. No → delegate via comment."**

Workers may delegate **out-of-scope** work only. Delegating your own identity's core work is forbidden (a `programmer` must not delegate writing code).

## Files

| File | Purpose |
|---|---|
| `docs/delegation-protocol.md` | The full protocol spec: comment format, rules, acceptance criteria |
| `scripts/kanban-watch.py` | Watchdog: deterministic board+comment digest for cron monitor change-detection |
| `examples/real-case-2026-09-04.md` | A real end-to-end run: code-review worker delegated a color-scheme design to a designer |

## Quick start

1. Copy `scripts/kanban-watch.py` to your agent's scripts dir (adjust the DB path).
2. Wire it as a cron monitor (runs every N minutes; agent wakes only when output changes).
3. Put the delegation rule in your worker task bodies (see `docs/delegation-protocol.md`).
4. When the watchdog emits a `DELEGATE` line, the orchestrator creates the new task.

## Requirements

- A kanban board with a comment channel per task (SQLite-backed `task_comments` table in this reference implementation)
- A cron/monitor system that can run a script and wake an agent on output change
- Multi-identity agent setup (workers with distinct specialties)

## License

MIT
