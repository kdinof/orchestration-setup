## Orchestration workflow

When running `$orchestrate`, read `tasks/ORCHESTRATION.md` and
`tasks/PROJECT.md`. Use `.codex/agents/` when custom agents are available;
otherwise pass the matching `tasks/roles/*.md` body to an available subagent.
Do not assume Claude tools, model aliases or slash commands exist in Codex.
These instructions apply to orchestration runs, not unrelated requests.

Before dispatch read `tasks/codex-models.json` and check it against native role
settings. Select the named custom role, or pass its model/effort explicitly with
its prompt if the host supports model overrides. If unavailable, report the
mismatch rather than claiming the profile was applied. Record requested and
actual model/effort when exposed; otherwise mark actual model unverified.
