# Preference: Project Monitoring Specifics

Project-specific parameters for harness/procedures/monitoring.md. The generic
protocol (log-prefix scheme, background + Monitor rules, TaskStop discipline)
lives in the procedure file; this file holds only what is specific to this
project. Edit the placeholders below; leave the structure intact.

## Long-running commands in this project

- [fill in -- list each command expected to exceed ~45s and what it does, e.g.
  `bash build.sh` (full build + tests), a training/ingest job, a benchmark
  script].
- Never invoke a long-running command synchronously; always
  `run_in_background: true` + Monitor. [Add any project-specific note, e.g. "the
  script activates its own environment internally".]

## Grep patterns

- Minimum filter (always): [fill in -- e.g. `[ERROR]|[FATAL]|[DONE]`].
- Live-update filter (add when progress visibility is needed): [fill in -- e.g.
  `[RESULT]|[PROGRESS]`].
- Useful progress markers emitted by this project's scripts: [fill in -- e.g.
  per-stage progress lines, elapsed time, row/item counts].

## Log locations

- Application log: [fill in -- e.g. `logs/app.log` and its handler/rotation].
- Script/job logs: [fill in -- where background jobs write, and the final-line
  convention, e.g. `[DONE] success` / `[FATAL] <reason>`].
