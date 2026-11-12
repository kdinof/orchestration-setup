# Shared orchestration protocol

## Start and resume

Read PROJECT.md, the plan, run README, task cards and existing task artifacts.
Check repository status, current branch/base, available agent tools, worktree
support and verification commands. Do not reset user changes. If the plan
and cards disagree, stop affected tasks and reconcile before dispatch.
Start with a short task/route/parallelism outline. An explicit request to run
work authorizes the run; do not request the same approval again.
If the user asked only for setup or a plan, do not start implementation.

The coordinator is the sole writer of README status, `docs/devlog.md` and
shared run artifacts. Workers return reports instead of appending to a common
journal. The coordinator persists these before advancing state:

- `T0.1-progress.md`: state (pending/design/implementing/review/accepted/blocked),
  attempt count, agent ID, workspace, base revision, changed files, next step.
- `T0.1-design.md` where needed: chosen interfaces, alternatives, constraints.
- `T0.1-result.md`: changes, verification commands/results, limitations.
- `T0.1-review.md`: ACCEPT / RETURN / BLOCKED, criterion-by-criterion evidence,
  reviewed revision or diff fingerprint, findings with severity and locations.
- `gate-review.md`: integrated revision, gate command/scenario, result.

On resume reconcile artifacts with the actual diff/worktree and agent state.
Missing response is not failure or success: inspect/stop an existing worker
before retrying; never dispatch a second writer to the same task. Completed
code without independent review resumes at review. Stale review evidence after
changes requires re-review. A checkbox without evidence is unverified.

## Dispatch and ownership

Dispatch only tasks whose dependencies are ACCEPTED and whose prior stage gate
passed. Honor sequential waves. Otherwise waves are not barriers: when a slot
frees, dispatch the next ready task at once, even from a later wave, unless a
task from its card's "Not parallel with" list is active. Where the host can run
children in the background, do so and handle each completion as it arrives
instead of waiting for the slowest task of a batch. Limit active child agents across ALL roles to
PROJECT.md's limit, including design/review agents, not just worker tasks.
Use scout only for uncertain or large context; skip it when a verified brief
already exists. Load relevant `docs/solutions/` notes before design/implementation.
Use deep-reasoner for large/risky/ambiguous work. For high-stakes decisions,
obtain independent design and adversarial opinions before synthesizing; when
slots are limited run them sequentially with separate contexts.

Brief every child with task ID, goal, exact ownership, context paths, acceptance,
decisions, base/workspace, required commands and expected report. Child agents
must not spawn further agents: only the coordinator controls dispatch/budget.

Parallel writers require separate worktrees based on the recorded integration
revision and disjoint ownership; re-check the actual worktree HEAD before use.
Shared contracts, wiring, lockfiles, generated outputs and migrations with shared
ordering must be serialized even if filenames differ. Use the host's worktree
manager if present. If isolation is unavailable, run writers sequentially.
Read-only research can still run concurrently. Integrate one result at a time,
inspect the real diff including new files, then verify the integrated tree.
Do not launch competing test processes sharing mutable databases/ports/fixtures.

## Verification and bounded repair

Coordinator does planning, dispatch and integration; implementation belongs to
workers. If subagents are unavailable, report the limitation. A sequential
single-agent fallback can implement when within user scope, but cannot claim an
independent ACCEPT: leave review BLOCKED until independent evidence is available.

Reviewer receives the brief, design, base and changed files in a fresh context,
not the implementer's conversation. It checks the actual diff and all acceptance
criteria, runs meaningful applicable checks independently, and reports outcomes.
Avoid repeating the same full suite: workers run the scoped checks for their
ownership, the reviewer runs the full checks once, and the coordinator reruns
them after integration only when review did not run on the integrated revision.
A full run that already passed on the identical tree is not repeated: cite it.
Documentation/config tasks can use focused validation; do not create tests that
merely mirror wording. Missing credentials/environment is BLOCKED, never ACCEPT.
Read-only is a role contract, not a promise that Bash or tests cannot write;
run tests in a suitable isolated workspace without weakening permission controls.

RETURN findings must be actionable, with severity, paths and reproduction or
evidence. Fix blockers within scope; record unrelated issues without scope creep.
At most two worker attempts, then one deep-reasoner diagnosis and one worker
repair. If still failing, persist BLOCKED and ask for the missing decision/input.
Continue independent ready tasks while a blocker is unresolved. A new session
does not reset attempts. Stop retrying tools on a stable permission denial.

Not every open question is a blocker. Decide questions answerable from the plan,
requirements, specs, code or `docs/solutions/` yourself, append a ruling to the
run README (`R<n> · T<ID> · decision · why · cost if wrong · reversible`) and
continue. Persist BLOCKED and ask only for: irreversible or outward-facing
actions (push, merge, deploy, data deletion, messages to people), security or
data-isolation trade-offs, changing a gate or a shared contract beyond its
design, spending beyond the plan, product choices. If unsure, it is a blocker.
Report new rulings ordered by cost if wrong, so the user reviews risky ones first.

Set the task checkbox only after independent ACCEPT and integration checks for
that change. After a wave summarize accepted/returned/blocked/next. Close a run
only when all tasks are accepted AND its integration gate passes; record both
the gate evidence and the separate gate checkbox. A failed gate reopens affected
work. Follow the user's authorized run boundary; setup is not shipping permission.

## Learn and measure

After verified non-obvious fixes, write a concise `docs/solutions/<topic>.md`:
symptom/search terms, root cause, verified solution, evidence/revision, scope
and when to re-check. Skip routine lessons already clear in code/tests; never
promote unverified guesses to permanent rules. Link useful lessons in briefs.

At run close record task counts, first-pass acceptance, repair attempts, blockers,
elapsed time and model/tool usage when available (Claude: the guard hook collects
them in `tasks/.orch/`; `python3 .claude/hooks/orch_guard.py report`). Compare equivalent runs before
claiming speed, cost or quality gains. Do not impose a fixed task count per run:
use integration boundaries and tasks small enough for one reviewable result.
