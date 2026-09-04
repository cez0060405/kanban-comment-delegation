# Delegation Protocol — 委托协议

> The inter-agent handoff protocol for multi-agent kanban orchestration.
> 多智能体看板编排的跨身份委托协议。

## 1. Purpose

When a worker agent encounters a subtask **outside its own identity's specialty** mid-task, it must not silently do a poor job, and must not silently stall. Instead, it hands the subtask to the right specialist through the kanban board's comment channel. The orchestrator (main agent) is the router.

## 2. The rule (one sentence)

> **这活是不是我身份该干的？是 → 自己干；不是 → 评论委托。**
> Is this work my identity's job? Yes → do it yourself. No → delegate via comment.

### Allowed
- Delegating work that is **not** your identity's specialty (e.g. a `codereview` worker delegating visual design to `designer`).

### Forbidden
- Delegating work that **is** your identity's core specialty (a `programmer` delegating code writing, a `designer` delegating visual design). That is your job — do it.

## 3. Comment format

Workers write the delegation request as a comment on their **current task**:

```
【委托】<subtask description> 需要 <identity> 处理。
建议：<specific approach or reference files>
```

Example (real, 2026-09-04):

```
【委托】为视频设计一个 3 色配色方案（主色/副色/强调色，给出 hex 值+用途说明）需要 designer 处理。
这是设计领域工作，非 codereview 本职（代码审查），按委托规则转交。请主控创建新任务派给 designer 身份。
```

## 4. Orchestrator flow

1. **Detect**: the watchdog script (`scripts/kanban-watch.py`) emits a `DELEGATE <task_id> <author>: <body>` line when a worker-authored `【委托】` comment appears. The cron monitor wakes the orchestrator on output change.
2. **Collect**: the orchestrator reads the full comment from the board DB (`task_comments` table).
3. **Create**: creates a new kanban task with:
   - title: `DELEGATE-<summary>（<author>委托）`
   - assignee: the requested identity
   - workspace: the same shared workspace (so the specialist has context)
   - body: delegation source + full subtask description + acceptance criteria
4. **Dispatch**: the dispatcher picks it up and runs it with the specialist identity.

## 5. Acceptance criteria

- The delegating worker's own core work is **still completed by itself** (delegation is for out-of-scope work only).
- The delegated task's deliverable lands in the shared workspace (file or comment).
- The delegation context (source comment, background, acceptance) is carried into the new task body — the specialist is a fresh session with no memory of the delegator's task.

## 6. Pitfalls

- **Duplicate dispatch** (solved in v3): two orchestrators (or a manual + automatic pass) may both see the same `【委托】` comment and create two tasks. The watchdog now dedups: a worker `【委托】` comment is reported as `DELEGATE` only until a `DELEGATE-*` task referencing the source task exists on the board; after that it reports a stable `DELEGATED` line and records the comment id in `kanban-watch-state.json`. A second orchestrator pass sees `DELEGATED` and does not re-dispatch. (Real case 2026-09-04: before dedup, the same delegation was dispatched twice; the specialist reused the first deliverable — luck, not mechanism.)
- **Watchdog must distinguish worker comments from system events**: `SCHEDULED`/`UNBLOCK` comments and orchestrator-planted instructions (`【委托方式】` explainers) must not trigger delegation. Only worker-authored `【委托】` comments count (author not in `default`/`user`/`system`; note `【委托方式】` does not match the `【委托】` prefix, so explainers are naturally excluded).
- **Fresh-session context**: the specialist worker has no memory of the delegator's task. Everything it needs must be in the new task body or in the shared workspace files.

## 7. Why comments, not a side channel?

- **Zero new infrastructure** — the board already has comments; the protocol is just a convention on top.
- **Auditable** — every handoff is a permanent, timestamped comment on the board.
- **Orchestrator stays cheap** — it only wakes when a delegation actually happens (watchdog change-detection), not on every worker heartbeat.
