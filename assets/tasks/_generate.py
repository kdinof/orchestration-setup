#!/usr/bin/env python3
"""Generate validated, restart-safe task runs (Python 3.9+, standard library).

Format:
  ## 1. Этап 0 — Foundation
  **Gate:** executable integration scenario
  ### Волна 0.1 — последовательно (or параллельно)
  | ID | Задача | Размер | Зависит | Владение | Контекст | Сделать / Приёмка |
  | T0.1 | Name | S | — | `src/file.py` | spec.md | Work **Приёмка:** result |

Seven columns; no pipes/newlines inside cells. Ownership: comma-separated
literal relative file/directory paths (backticks optional), no globs.
Dependencies: comma-separated IDs, or —. Sequential same-wave dependencies
must reference earlier rows; parallel waves cannot have internal dependencies.
Re-running an unchanged plan preserves ALL files and progress. Changed plans
are refused once generated: archive/reconcile affected runs explicitly first.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
# Project-specific configuration. Empty RUNS means automatic stage names.
PLAN = 'docs/dev-plan.md'
RUNS = {}  # e.g. {'0': ('run-0-foundation', 'Foundation')}
DESIGN = set()
HIGH_STAKES = set()  # subset of DESIGN; L tasks also get design automatically
ALWAYS_CONTEXT = 'tasks/PROJECT.md; tasks/ORCHESTRATION.md'


def fail(message):
    raise ValueError(message)


def ownership(value):
    paths = [part.strip().strip('`').rstrip('/') for part in value.split(',')]
    for path in paths:
        if (not path or path.startswith(('/', '~')) or '\\' in path
                or any(c in path for c in '*?[]') or any(c.isspace() for c in path)
                or any(p in ('', '.', '..') for p in path.split('/'))):
            fail(f'Invalid ownership path: {value}')
    return paths


def overlaps(left, right):
    return any(a == b or a.startswith(b + '/') or b.startswith(a + '/')
               for a in left for b in right)


def parse(text):
    stages, tasks, stage, wave = [], {}, None, None
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        m = re.fullmatch(r'## \d+\. Этап (\d+) — (.+)', line)
        if m:
            if any(s['id'] == m[1] for s in stages):
                fail(f'Line {number}: duplicate stage')
            stage = dict(id=m[1], title=m[2], gate='', waves=[])
            stages.append(stage)
            wave = None
            continue
        m = re.fullmatch(r'\*\*Gate[^:]*:\*\*\s*(.+)', line)
        if m:
            if stage is None or stage['gate']:
                fail(f'Line {number}: missing stage or duplicate gate')
            stage['gate'] = m[1]
            continue
        m = re.fullmatch(r'### Волна (\S+) — (.+)', line)
        if m:
            if stage is None or not m[1].startswith(stage['id'] + '.'):
                fail(f'Line {number}: wave outside its stage')
            if any(w['id'] == m[1] for s in stages for w in s['waves']):
                fail(f'Line {number}: duplicate wave')
            if not re.match(r'^(последовательно|параллельно)\b', m[2]):
                fail(f'Line {number}: unknown wave mode')
            wave = dict(id=m[1], mode=m[2], tasks=[])
            stage['waves'].append(wave)
            continue
        # Reject malformed structural headers rather than silently losing tasks.
        if re.match(r'^##.*Этап|^###.*Волна', line):
            fail(f'Line {number}: malformed stage/wave heading')
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if cells[0] == 'ID' or all(re.fullmatch(r'[: -]+', c) for c in cells):
            continue
        # Non-task tables outside waves are documentation; inside waves every row is a task.
        if wave is None and not cells[0].startswith('T'):
            continue
        if stage is None or wave is None or len(cells) != 7:
            fail(f'Line {number}: task outside wave or not seven columns')
        tid, name, size, deps, own, ctx, body = cells
        if not re.fullmatch(r'T\d+\.\d+', tid) or tid.split('.')[0] != 'T' + stage['id']:
            fail(f'Line {number}: invalid task ID {tid}')
        if tid in tasks:
            fail(f'Line {number}: duplicate {tid}')
        if size not in ('S', 'M', 'L') or not name or not ctx or '**Приёмка:**' not in body:
            fail(f'Line {number}: missing name/context/acceptance or invalid size')
        todo, accept = body.split('**Приёмка:**', 1)
        if not todo.strip() or not accept.strip():
            fail(f'Line {number}: empty work or acceptance')
        dependency_ids = [] if deps in ('—', '-') else [d.strip().strip('`') for d in deps.split(',')]
        if any(not re.fullmatch(r'T\d+\.\d+', d) for d in dependency_ids):
            fail(f'Line {number}: malformed dependencies')
        task = dict(id=tid, name=name, size=size, deps=dependency_ids, own=ownership(own),
                    ctx=ctx, todo=todo.strip(), accept=accept.strip(), stage=stage['id'],
                    wave=wave['id'], mode=wave['mode'], order=len(tasks))
        tasks[tid] = task
        wave['tasks'].append(task)
    if not tasks:
        fail('No tasks found')
    for s in stages:
        if not s['gate'] or not s['waves'] or any(not w['tasks'] for w in s['waves']):
            fail(f'Stage {s["id"]}: gate and nonempty waves required')
    for task in tasks.values():
        for dep in task['deps']:
            if dep not in tasks:
                fail(f'{task["id"]}: unknown dependency {dep}')
    visiting, visited = set(), set()
    def visit(tid):
        if tid in visiting:
            fail(f'Dependency cycle at {tid}')
        if tid in visited:
            return
        visiting.add(tid)
        for dep in tasks[tid]['deps']:
            visit(dep)
        visiting.remove(tid)
        visited.add(tid)
    for tid in tasks:
        visit(tid)
    for task in tasks.values():
        for dep in task['deps']:
            parent = tasks[dep]
            if parent['order'] >= task['order']:
                fail(f'{task["id"]}: dependency {dep} must appear earlier')
            if parent['wave'] == task['wave'] and task['mode'].startswith('параллельно'):
                fail(f'{task["id"]}: dependency inside parallel wave')
    for s in stages:
        for w in s['waves']:
            if w['mode'].startswith('параллельно'):
                for i, a in enumerate(w['tasks']):
                    for b in w['tasks'][i + 1:]:
                        if overlaps(a['own'], b['own']):
                            fail(f'Ownership conflict: {a["id"]} / {b["id"]}')
    if not HIGH_STAKES <= DESIGN or (DESIGN | HIGH_STAKES) - tasks.keys():
        fail('HIGH_STAKES must be a subset of DESIGN; routing IDs must exist')
    return stages, tasks


def render(stages, tasks):
    files, index, names = {}, ['# Tasks\n\nRun in listed order; prior gate must pass.\n'], set()
    for stage in stages:
        sid = stage['id']
        if RUNS and sid not in RUNS:
            fail(f'Stage {sid} missing from RUNS')
        dirname = RUNS[sid][0] if RUNS else f'run-{sid}'
        if not re.fullmatch(r'run-[A-Za-z0-9_-]+', dirname) or dirname in names:
            fail(f'Invalid or duplicate run directory: {dirname}')
        names.add(dirname)
        index.append(f'- [{dirname}: {stage["title"]}]({dirname}/README.md)')
        lines = [f'# {dirname} — {stage["title"]}\n', f'**Gate:** {stage["gate"]}\n',
                 'Claude: `/orchestrate ' + dirname + '`; Codex: `$orchestrate ' + dirname + '`\n',
                 'Rules: `tasks/ORCHESTRATION.md`; project: `tasks/PROJECT.md`.\n']
        for wave in stage['waves']:
            lines.append(f'## Волна {wave["id"]} — {wave["mode"]}\n')
            for t in wave['tasks']:
                route = ('high-stakes: independent design + adversarial review' if t['id'] in HIGH_STAKES
                         else 'design' if t['id'] in DESIGN or t['size'] == 'L' else 'standard')
                lines.append(f'- [ ] {t["id"]} — [{t["name"]}]({t["id"]}.md) ({route})')
                files[f'{dirname}/{t["id"]}.md'] = (
                    f'# {t["id"]} — {t["name"]}\n\n'
                    f'- Stage / wave: {sid} / {wave["id"]}\n- Size: {t["size"]}\n'
                    f'- Dependencies: {", ".join(t["deps"]) or "—"}\n'
                    f'- Ownership: {", ".join(t["own"])}\n- Context: {t["ctx"]}; {ALWAYS_CONTEXT}\n'
                    f'- Route: {route} → fast-worker → independent reviewer; scout only if needed\n\n'
                    f'## Сделать\n\n{t["todo"]}\n\n## Приёмка\n\n{t["accept"]}\n\n'
                    'Follow tasks/ORCHESTRATION.md. Return changes and verification evidence; '
                    'only the coordinator writes status/devlog.\n')
        lines += ['\n## Gate status\n', '- [ ] Gate passed (evidence: gate-review.md)\n',
                  '## Findings (coordinator, append-only)\n']
        files[f'{dirname}/README.md'] = '\n'.join(lines)
    files['README.md'] = '\n'.join(index) + '\n'
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate without writing')
    args = parser.parse_args()
    try:
        stages, tasks = parse((ROOT / PLAN).read_text())
        files = render(stages, tasks)
        out = ROOT / 'tasks'
        # Fingerprint generated immutable content, so plan/config changes cannot reset progress.
        digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        manifest = out / '.generation.json'
        destinations = [out / name for name in files] + [manifest]
        for path in destinations:
            if any(p.is_symlink() for p in [path, *path.parents] if p != ROOT and ROOT in p.parents):
                fail(f'Symlink destination: {path}')
        if manifest.exists():
            previous = json.loads(manifest.read_text())
            if previous.get('digest') != digest:
                fail('Plan/config changed. Existing runs preserved; reconcile/archive generated runs and manifest before regenerating.')
            for name, expected in files.items():
                path = out / name
                if not path.is_file():
                    fail(f'Missing generated file: {name}; restore it before continuing')
                if path.name != 'README.md' and path.read_text() != expected:
                    fail(f'Edited task card: {name}; reconcile with plan before continuing')
            print(f'Unchanged: {len(tasks)} tasks; all progress preserved')
            return 0
        if any(path.exists() for path in destinations) or (out.exists() and any(out.glob('run-*'))):
            fail('Existing generated/legacy files without matching manifest; nothing overwritten')
        if not args.check:
            for name, content in files.items():
                path = out / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            manifest.write_text(json.dumps({'version': 1, 'digest': digest}, indent=2) + '\n')
        print(f'{"Validated" if args.check else "Generated"}: {len(tasks)} tasks, {len(stages)} runs')
        return 0
    except (ValueError, OSError, RecursionError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
