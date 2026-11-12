---
description: Запустить или продолжить ран из tasks/ с независимой приёмкой
argument-hint: "[run-папка; без аргумента — первый незакрытый ран]"
---

Read `tasks/ORCHESTRATION.md` and `tasks/PROJECT.md`, then execute the
requested run from `tasks/$ARGUMENTS`. With no argument choose the first
run in `tasks/README.md` whose tasks OR gate are not complete.
Follow the shared protocol for dispatch, recovery, verification and stopping.

Before dispatch write the run folder name to `tasks/.active-run`; delete it when
the run closes or stops at its boundary. While it exists the guard hook
(`.claude/hooks/orch_guard.py`) denies coordinator edits outside `tasks/`,
`docs/devlog.md` and `docs/solutions/`, and denies a task checkbox without a
recorded reviewer ACCEPT. A denial means delegate, not work around it. Launch
children with `run_in_background` and react to each completion. Include
`python3 .claude/hooks/orch_guard.py report` in wave and run-close summaries.
