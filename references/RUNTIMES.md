# Runtime adapters and migration

## Claude Code

Setup skill: `.claude/skills/orchestration-setup/SKILL.md` (or user scope).
Runtime: native command `/orchestrate` and `.claude/agents/*.md`.
Defaults remain scout=haiku/low, fast-worker=sonnet/medium,
deep-reasoner=opus/xhigh, reviewer=opus/high. Aliases are preferences, not
immutable model versions; check actual model/effort support before dispatch.
Do not assume built-in Explore always inherits an expensive main model.

### Guard hook

`setup --target claude|both` installs `.claude/hooks/orch_guard.py` and adds it
to `.claude/settings.json` (PreToolUse on Edit/Write/MultiEdit/NotebookEdit,
PostToolUse on SubagentHandback, SubagentStart, SubagentStop). The merge only
adds missing entries and keeps every other setting; `--no-claude-hooks` skips
both the file and the settings change. Hooks of a project run only after the
user accepts the folder trust dialog.

While `tasks/.active-run` exists, the hook denies main-session file edits outside
`tasks/`, `docs/devlog.md` and `docs/solutions/` (subagent calls carry `agent_id`
and are not restricted by it). It records reviewer verdicts from the first report
line (`**Task:** T<ID> · **Verdict: …**`) in `tasks/.orch/verdicts.jsonl` and
denies a README checkbox whose last recorded verdict is not ACCEPT. It records
per-agent model, tokens, duration and tool calls in `tasks/.orch/metrics.jsonl`;
`python3 .claude/hooks/orch_guard.py report [run]` summarizes them with
first-pass acceptance. Limits: Bash writes are not intercepted; ownership of a
worker's edits is still checked by the reviewer; token totals come from the
subagent transcript and are best effort. The owner can lift the edit guard for
an authorized single-agent fallback with `ORCH_ALLOW_MAIN_EDITS=1`. A stale
`tasks/.active-run` after an aborted run must be deleted by the owner.

## Codex

Setup/runtime skills use `.agents/skills/` (or `~/.agents/skills/`).
The installer emits native `.codex/agents/*.toml` containing name, description
and developer_instructions. No Claude frontmatter is copied into TOML.
Models and reasoning effort inherit the session by default. Set supported
`model` and `model_reasoning_effort` explicitly when configuring cost routing;
there is no automatic Haiku-to-OpenAI model translation.

### Model routing

`setup --target codex --codex-profile balanced` writes model AND effort to each
native role and saves the same map to `tasks/codex-models.json`. The default
`--codex-profile inherit` leaves both unset. The main coordinator's model is
not changed by either profile.

| Role | balanced model | Effort |
|---|---|---|
| scout | gpt-5.6-luna | low |
| fast-worker | gpt-5.6-terra | medium |
| deep-reasoner | gpt-6-astra | high |
| reviewer | gpt-6-astra | high |

This is a starting hypothesis for large runs, not a benchmarked optimum.
Model positioning checked 2026-09-12 against the
[OpenAI model catalog](https://developers.openai.com/api/docs/models).
Per-role configuration follows the
[Codex subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents).
Availability in an account/client is checked at runtime, not proved by a JSON file.

For custom routing copy `references/codex-balanced.json`, adjust it, and pass
`--codex-models /path/to/models.json` instead of the profile flag. All four roles
must be present; each value is either `{}` (inherit) or an object with exactly
`model` and `model_reasoning_effort`. The installer validates structure, not model
availability. Unsupported models/effort must be resolved before task dispatch.

For an existing installation, preview the profile and reconcile the displayed
role files and model map together; the installer does not silently overwrite
an earlier profile or local edits. On subsequent installs use the same profile/map.
If manually adjusting installed TOML, update the saved map as well.

Before dispatch, compare native role config with the saved map. If custom agents
are unavailable but explicit model selection exists, pass the role prompt AND
its mapped model/effort when spawning. Use fresh context where the host requires
it for model overrides. Never just paste a model name into a prompt and claim
routing took effect. If selection isn't available, report inherited-model mode;
if a requested model is unavailable, surface the mismatch and use only an
explicitly configured/user-authorized alternative. Record requested and actual
model/effort when the host exposes them; otherwise mark actual model unverified.
Do not claim cost savings from the profile alone. After bounded worker failures,
use the existing deep-reasoner repair route; don't silently rewrite model config.

The installer leaves `.codex/config.toml`, permissions and user settings alone.
If the current client doesn't expose custom agents, pass `tasks/roles/<role>.md`
to its available subagent mechanism. If no subagent mechanism is available,
report degraded operation: sequential implementation may proceed within scope,
but independent review remains BLOCKED. Do not fabricate successful delegation.
Role prompts are behavioral constraints, not sandbox enforcement.

## Existing installations

1. Inspect changes and preserve a backup in a location chosen for this project.
2. Run the installer with `--dry-run`; existing differing agents/scripts are
   conflicts. Reconcile the displayed changes while preserving local additions.
3. A legacy unmarked `Orchestration workflow` section in CLAUDE.md/AGENTS.md
   requires manual reconciliation with the new short reference block. Preserve
   other sections, move project-specific Sources of truth into tasks/PROJECT.md,
   and use the installer's begin/end markers around the new reference block.
4. Existing generated runs have no `.generation.json`. Do not invent one or
   blindly regenerate: completed checkboxes may be the only surviving evidence.
   Archive old generated run directories and tasks/README.md after reconciling
   them with actual changes; keep implementation/design/review evidence. Then
   generate the revised plan and explicitly restore only verified task status.
5. For newer runs, a changed plan/config also refuses regeneration. Stop affected
   workers, reconcile changed acceptance/dependencies, archive generated files
   and manifest together, regenerate, and re-review affected accepted tasks.
6. An unchanged plan rerun preserves README progress and other artifacts. Missing
   generated files or manually edited cards fail validation instead of being
   silently repaired. Restore the file or follow the reconciliation process.
7. Generators older than the Rulings / "Not parallel with" release render
   different cards, so after updating `tasks/_generate.py` an existing run's
   manifest no longer matches. Finish or archive the run first (step 5), or keep
   the old generator until the run closes. The guard hook can be added to an
   existing Claude setup on its own: rerun setup and reconcile the displayed diff.

The generator validates literal ownership paths, not semantic interactions.
Only comma-separated repository-relative paths are supported; no globs, spaces
or inline pipes. Prefix conflicts are detected (`src/` vs `src/api.py`). Shared
runtime resources still need coordinator review. Writers must never run the
installer or generator concurrently against the same destination. Preflight
prevents known conflicts before writes; an I/O failure may leave partial files,
so inspect the output before resuming rather than claiming a transaction.
