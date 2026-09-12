# Project configuration

Fill these values from the repository before starting a run. Missing values
are configuration work, not permission to guess commands or requirements.

- Requirements: TODO
- Plan: `docs/dev-plan.md`
- Specs / research: TODO (write “none” if absent)
- Verification commands and required environment: TODO
- Integration gate command/scenario: see each run README
- Maximum active child agents, across ALL roles: 3 (or lower host limit)
- Runtime: TODO (claude / codex)
- Model routing: Claude defaults in `.claude/agents/`; Codex inherits the
  session model by default; explicit routing is in `.codex/agents/*.toml`
  and `tasks/codex-models.json` (keep them consistent).
- Work isolation: sequential in the current checkout by default;
  parallel writers require separate worktrees with a recorded common base.
- Fix budget: two worker attempts, one diagnosed repair, then BLOCKED.
- Run boundary: stop after this run; continue subsequent runs only when
  the user's request includes them.

Record actual host/model availability before dispatch. Unavailable role or
effort is a capability mismatch: use a supported equivalent and report it.
Never claim cheaper routing when every child inherits the main model.
