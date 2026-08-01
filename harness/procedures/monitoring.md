# Procedure: Smart Monitoring Protocol (generic)

Generic protocol for long-running script execution. Project specifics (which
commands are long-running, project grep patterns, log locations) live in the
`## Monitoring` section of `.claude/preferences.md`; if that file is absent,
apply this generic protocol with the default filters below.

Applies to any script or command expected to exceed ~45 seconds. Phases that
involve only file writes, document edits, or command rewrites with no script
execution do not need it; fast synchronous scripts under ~45s are covered by
ordinary verification commands.

## Script design rules

All long-running scripts must:

1. **Log to a file handler** -- use `logging` with a `FileHandler`; never
   `print()` for progress or results.
2. **Prefix every log line** with exactly one of: `[RESULT]` (a computed output
   value), `[ERROR]` (recoverable problem), `[PROGRESS]` (milestone update),
   `[FATAL]` (unrecoverable -- script cannot continue).
3. **Emit `[PROGRESS]` at 10% milestones AND every 60 seconds** (whichever comes
   first). Format: `[PROGRESS] N/total | X% | elapsed Xs | ETA Xs`.
4. **Decouple interactive display from the log** -- `tqdm(file=sys.stderr)` for
   terminal bars; the file log must never contain tqdm control characters.
5. **Final line rule** -- the last log line is always `[DONE] success` or
   `[FATAL] <reason> -- <remediation hint>`. No script exits without one.

## Background + Monitor rules

1. **Always background + Monitor** -- `run_in_background: true` + the Monitor
   tool for anything over ~45s or more than ~10 lines of output. Never blocking
   Bash for long ops.
2. **Minimum grep filter** -- `[ERROR]|[FATAL]|[DONE]`; catches all terminal
   states and recoverable errors without flooding context.
3. **Live-update filter** -- add `[RESULT]|[PROGRESS]` when you need
   intermediate results or progress confirmation. Widen the filter to catch
   periodic progress markers (counts, elapsed time) so you can give the user
   ETA updates, not just a final completion event.
4. **Stop on terminal line** -- call `TaskStop` immediately when `[DONE]` or
   `[FATAL]` arrives (or immediately after the task-completed notification).
   Never leave a monitor running after its target process has exited.
5. **One monitor at a time** -- never start a second Monitor while one is
   running; `TaskStop` the previous monitor first. Violating this creates
   orphaned watchers that consume resources and confuse event routing.
6. **No Monitor available?** If no Monitor tool is registered in the session,
   use `run_in_background: true` plus the background-task completion
   notification and grep the script's own prefixed log lines to watch progress
   and detect terminal states -- do not block a long op on a Monitor that is
   not available.
7. **Working directory** -- background Bash commands do NOT inherit the current
   working directory. Always prefix with `cd /absolute/path/to/project &&` or
   use absolute paths in the command.
