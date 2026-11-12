#!/usr/bin/env python3
"""Install the setup skill or project runtime without overwriting local edits."""
import argparse
import difflib
import json
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parents[1]
BEGIN = '<!-- orchestration-setup:begin -->'
END = '<!-- orchestration-setup:end -->'
ROLES = {'scout', 'fast-worker', 'deep-reasoner', 'reviewer'}
# Claude Code guard hook: wired into .claude/settings.json by a structural, additive merge.
HOOK_COMMAND = 'python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/orch_guard.py"'
HOOK_EVENTS = (('PreToolUse', 'Edit|Write|MultiEdit|NotebookEdit|Bash'),
               ('PostToolUse', 'SubagentHandback|Bash'), ('PostToolUseFailure', 'Bash'),
               ('SubagentStart', None), ('SubagentStop', None))


def load_models(profile='inherit', custom=None):
    if custom is None and profile == 'inherit':
        return {role: {} for role in sorted(ROLES)}
    path = custom or SOURCE / 'references/codex-balanced.json'
    mapping = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(mapping, dict) or set(mapping) != ROLES:
        raise ValueError('Codex model map must contain exactly: ' + ', '.join(sorted(ROLES)))
    for role, config in mapping.items():
        if not isinstance(config, dict):
            raise ValueError(f'{role}: expected an object')
        if not config:  # Explicit inheritance for this role.
            continue
        if set(config) != {'model', 'model_reasoning_effort'}:
            raise ValueError(f'{role}: specify both model and model_reasoning_effort, or {{}}')
        model, effort = config['model'], config['model_reasoning_effort']
        if not isinstance(model, str) or not model or any(c.isspace() or ord(c) < 32 for c in model):
            raise ValueError(f'{role}: invalid model ID')
        if not isinstance(effort, str) or effort not in ('minimal', 'low', 'medium', 'high', 'xhigh', 'max'):
            raise ValueError(f'{role}: invalid reasoning effort')
    return mapping


def merged_settings(path):
    """Return settings.json bytes with the guard hook added; other settings are kept as is."""
    old = path.read_bytes() if path.exists() else None
    try:
        settings = json.loads(old.decode('utf-8')) if old and old.strip() else {}
    except ValueError as exc:
        raise ValueError(f'Invalid JSON in {path}: {exc}; fix it or use --no-claude-hooks')
    hooks = settings.setdefault('hooks', {}) if isinstance(settings, dict) else None
    if not isinstance(hooks, dict):
        raise ValueError(f'Unexpected structure in {path}; fix it or use --no-claude-hooks')
    changed = False
    for event, matcher in HOOK_EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError(f'{path}: hooks.{event} must be a list')
        if any(isinstance(g, dict) and isinstance(h, dict) and h.get('command') == HOOK_COMMAND
               for g in groups for h in (g.get('hooks') or [])):
            continue
        group = {'hooks': [{'type': 'command', 'command': HOOK_COMMAND, 'timeout': 60}]}
        groups.append({'matcher': matcher, **group} if matcher else group)
        changed = True
    if old is not None and not changed:
        return old
    return (json.dumps(settings, indent=2, ensure_ascii=False) + '\n').encode()


def put_tree(files, source, destination):
    for path in sorted(source.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            files[destination / path.relative_to(source)] = path.read_bytes()


def build(root, target, mode, models=None, hooks=True):
    files = {}
    hosts = ['claude', 'codex'] if target == 'both' else [target]
    for host in hosts:
        skill_root = root / ('.claude/skills' if host == 'claude' else '.agents/skills')
        if mode == 'skill':
            destination = skill_root / 'orchestration-setup'
            files[destination / 'SKILL.md'] = (SOURCE / 'SKILL.md').read_bytes()
            files[destination / 'LICENSE'] = (SOURCE / 'LICENSE').read_bytes()
            for folder in ('assets', 'references', 'scripts'):
                put_tree(files, SOURCE / folder, destination / folder)
            continue
        if host == 'claude':
            put_tree(files, SOURCE / 'assets/agents', root / '.claude/agents')
            put_tree(files, SOURCE / 'assets/commands', root / '.claude/commands')
            if hooks:
                put_tree(files, SOURCE / 'assets/hooks', root / '.claude/hooks')
                files[root / '.claude/settings.json'] = merged_settings(root / '.claude/settings.json')
        else:
            models = models if models is not None else load_models()
            for path in sorted((SOURCE / 'assets/agents').glob('*.md')):
                _, header, body = path.read_text().split('---', 2)
                description = next(line.split(':', 1)[1].strip() for line in header.splitlines()
                                   if line.startswith('description:'))
                # JSON basic strings are valid TOML strings for these text values.
                config = (f'name = {json.dumps(path.stem)}\n'
                          f'description = {json.dumps(description)}\n'
                          f'developer_instructions = {json.dumps(body.strip())}\n')
                for key, value in models[path.stem].items():
                    config += f'{key} = {json.dumps(value)}\n'
                files[root / '.codex/agents' / (path.stem + '.toml')] = config.encode()
            files[root / 'tasks/codex-models.json'] = (json.dumps(models, indent=2) + '\n').encode()
            put_tree(files, SOURCE / 'assets/orchestrate', skill_root / 'orchestrate')
        name = 'CLAUDE' if host == 'claude' else 'AGENTS'
        path = root / (name + '.md')
        text = path.read_text() if path.exists() else ''
        block = BEGIN + '\n' + (SOURCE / f'assets/{name}-orchestration.md').read_text() + END
        if BEGIN in text or END in text:
            if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
                raise ValueError(f'Malformed managed block: {path}')
            start, end = text.index(BEGIN), text.index(END) + len(END)
            updated = text[:start] + block + text[end:]
        else:
            if '## Orchestration workflow' in text:
                raise ValueError(f'Legacy orchestration block: {path}. Reconcile manually before setup.')
            updated = text + ('\n\n' if text and not text.endswith('\n\n') else '') + block + '\n'
        files[path] = updated.encode()
    if mode == 'setup':
        put_tree(files, SOURCE / 'assets/tasks', root / 'tasks')
        for path in (SOURCE / 'assets/agents').glob('*.md'):
            files[root / 'tasks/roles' / path.name] = path.read_text().split('---', 2)[2].strip().encode() + b'\n'
        files[root / 'docs/devlog.md'] = b'# Devlog\n\nCoordinator writes verified task summaries here.\n'
        # User-owned configuration/journal are create-only.
        for path in (root / 'tasks/PROJECT.md', root / 'tasks/checks.json', root / 'docs/devlog.md'):
            if path.exists():
                files[path] = path.read_bytes()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['skill', 'setup'])
    parser.add_argument('--target', choices=['claude', 'codex', 'both'], required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--project', type=Path)
    scope.add_argument('--user', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without writing')
    routing = parser.add_mutually_exclusive_group()
    routing.add_argument('--codex-profile', choices=['inherit', 'balanced'])
    routing.add_argument('--codex-models', type=Path, help='JSON role-to-model map; all four roles required')
    parser.add_argument('--no-claude-hooks', action='store_true',
                        help='Do not install the Claude guard hook or touch .claude/settings.json')
    args = parser.parse_args()
    if args.no_claude_hooks and (args.mode != 'setup' or args.target == 'codex'):
        parser.error('--no-claude-hooks requires setup --target claude or both')
    if args.user and args.mode != 'skill':
        parser.error('--user is only supported for installing the setup skill')
    if (args.codex_profile or args.codex_models) and (args.mode != 'setup' or args.target == 'claude'):
        parser.error('Codex routing options require setup --target codex or both')
    root = (Path.home() if args.user else args.project).resolve()
    try:
        models = load_models(args.codex_profile or 'inherit', args.codex_models)
        files = build(root, args.target, args.mode, models, hooks=not args.no_claude_hooks)
        conflicts, pending = [], []
        for path, data in files.items():
            # Reject symlinks even when they resolve inside root: don't mutate linked configuration.
            if any(p.is_symlink() for p in [path, *path.parents] if p != root and root in p.parents):
                raise ValueError(f'Symlink destination: {path}')
            if any(p.exists() and not p.is_dir() for p in path.parents):
                raise ValueError(f'Parent is not a directory: {path}')
            if path.exists() and not path.is_file():
                raise ValueError(f'Not a regular file: {path}')
            old = path.read_bytes() if path.exists() else None
            if old == data:
                continue
            # Only adding a new marked block to existing instructions is automatic.
            append_only = (path.name in ('CLAUDE.md', 'AGENTS.md') and old is not None
                           and BEGIN.encode() not in old and data.startswith(old))
            # settings.json is only ever extended with the guard hook (see merged_settings).
            additive = path == root / '.claude/settings.json'
            if old is not None and not (append_only or additive):
                conflicts.append(path)
            pending.append((path, data))
            print(('CHANGE ' if old is not None else 'CREATE ') + str(path))
            if old is not None:
                print(''.join(difflib.unified_diff(old.decode().splitlines(True),
                      data.decode().splitlines(True), fromfile=str(path), tofile='proposed')), end='')
        if conflicts:
            raise ValueError('Conflicts; no files written. Review diff, back up/reconcile listed files, then retry.')
        if not args.dry_run:
            for path, data in pending:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        print(f'{"Planned" if args.dry_run else "Installed"}: {len(pending)} changed files')
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
