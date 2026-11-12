## Orchestration workflow

When running `/orchestrate`, read `tasks/ORCHESTRATION.md` and
`tasks/PROJECT.md`. Use `.claude/agents/` for role definitions.
These instructions apply to orchestration runs, not unrelated requests.
A guard hook in `.claude/hooks/` enforces two rules during a run (marked by
`tasks/.active-run`): the coordinator does not edit project code, and a task
checkbox requires a reviewer ACCEPT that the hook itself recorded.
