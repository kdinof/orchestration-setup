from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / 'scripts/install.py'
PLAN = (REPO / 'references/example-plan.md').read_text()


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project with spaces'
        self.root.mkdir()

    def run_script(self, script, *args, ok=True):
        proc = subprocess.run([sys.executable, str(script), *map(str, args)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode == 0, ok, proc.stdout + proc.stderr)
        return proc

    def install(self, *args, ok=True, target='both', mode='setup'):
        return self.run_script(INSTALLER, mode, '--target', target,
                               '--project', self.root, *args, ok=ok)

    def prepare(self, plan=PLAN):
        (self.root / 'tasks').mkdir(exist_ok=True)
        (self.root / 'docs').mkdir(exist_ok=True)
        shutil.copyfile(REPO / 'assets/tasks/_generate.py', self.root / 'tasks/_generate.py')
        (self.root / 'docs/dev-plan.md').write_text(plan)

    def generate(self, *args, ok=True):
        return self.run_script(self.root / 'tasks/_generate.py', *args, ok=ok)

    def test_setup_both_repeat_preserves_configuration_and_progress(self):
        (self.root / 'AGENTS.md').write_text('Existing instructions\n')
        self.install()
        (self.root / 'tasks/PROJECT.md').write_text('Custom project commands\n')
        (self.root / 'docs/devlog.md').write_text('Existing history\n')
        before = snapshot(self.root)
        self.install()
        self.assertEqual(before, snapshot(self.root))
        self.assertTrue((self.root / 'AGENTS.md').read_text().startswith('Existing instructions\n'))
        self.assertTrue((self.root / '.agents/skills/orchestrate/SKILL.md').exists())
        self.assertEqual(len(list((self.root / '.codex/agents').glob('*.toml'))), 4)

    def test_host_targets_are_separate(self):
        self.install(target='codex')
        self.assertFalse((self.root / '.claude').exists())
        self.assertFalse((self.root / 'CLAUDE.md').exists())
        self.install(target='claude')
        self.assertTrue((self.root / '.claude/commands/orchestrate.md').exists())

    def test_balanced_routing_and_idempotence(self):
        self.install('--codex-profile', 'balanced')
        mapping = json.loads((self.root / 'tasks/codex-models.json').read_text())
        expected = json.loads((REPO / 'references/codex-balanced.json').read_text())
        self.assertEqual(mapping, expected)
        for role, settings in mapping.items():
            text = (self.root / '.codex/agents' / (role + '.toml')).read_text()
            for key, value in settings.items():
                self.assertIn(f'{key} = {json.dumps(value)}\n', text)
            if sys.version_info >= (3, 11):
                import tomllib
                parsed = tomllib.loads(text)
                for key, value in settings.items():
                    self.assertEqual(parsed[key], value)
        before = snapshot(self.root)
        self.install('--codex-profile', 'balanced')
        self.assertEqual(before, snapshot(self.root))
        self.assertFalse((self.root / '.codex/config.toml').exists())

    def test_custom_routing_and_inherited_role(self):
        mapping = json.loads((REPO / 'references/codex-balanced.json').read_text())
        mapping['scout'] = {}
        mapping['fast-worker'] = {'model': 'custom-worker', 'model_reasoning_effort': 'high'}
        path = Path(self.temp.name) / 'models.json'
        path.write_text(json.dumps(mapping))
        self.install('--codex-models', path, target='codex')
        self.assertNotIn('\nmodel =', (self.root / '.codex/agents/scout.toml').read_text())
        self.assertIn('custom-worker', (self.root / '.codex/agents/fast-worker.toml').read_text())

    def test_invalid_routing_no_writes(self):
        baseline = json.loads((REPO / 'references/codex-balanced.json').read_text())
        invalid = [[], {}, {**baseline, 'extra': {}}, {**baseline, 'scout': None},
                   {**baseline, 'scout': {'model': 'only-model'}},
                   {**baseline, 'scout': {'model': 'x', 'model_reasoning_effort': []}},
                   {**baseline, 'scout': {'model': 'x\nbad', 'model_reasoning_effort': 'low'}}]
        path = Path(self.temp.name) / 'models.json'
        for mapping in invalid:
            with self.subTest(mapping=mapping):
                path.write_text(json.dumps(mapping))
                self.install('--codex-models', path, ok=False)
                self.assertEqual(snapshot(self.root), {})
        self.install('--codex-profile', 'balanced', target='claude', ok=False)
        self.install('--codex-profile', 'balanced', mode='skill', ok=False)

    def test_profile_change_cannot_overwrite_existing_install(self):
        self.install(target='codex')
        before = snapshot(self.root)
        self.install('--codex-profile', 'balanced', target='codex', ok=False)
        self.assertEqual(before, snapshot(self.root))

    def test_parent_file_prevents_partial_install(self):
        (self.root / 'tasks').write_text('not a directory')
        before = snapshot(self.root)
        self.install(ok=False)
        self.assertEqual(before, snapshot(self.root))

    def test_dry_run_no_writes(self):
        self.install('--dry-run')
        self.assertEqual(snapshot(self.root), {})

    def test_conflict_prevents_all_writes(self):
        path = self.root / '.claude/agents/scout.md'
        path.parent.mkdir(parents=True)
        path.write_text('Local agent')
        before = snapshot(self.root)
        self.install(ok=False)
        self.assertEqual(before, snapshot(self.root))

    def test_legacy_block_refused(self):
        (self.root / 'CLAUDE.md').write_text('## Orchestration workflow\nold')
        before = snapshot(self.root)
        self.install(ok=False)
        self.assertEqual(before, snapshot(self.root))

    def test_malformed_markers_refused(self):
        (self.root / 'AGENTS.md').write_text('<!-- orchestration-setup:begin -->')
        self.install(ok=False)
        self.assertFalse((self.root / '.claude').exists())

    def test_symlink_destination_refused(self):
        other = Path(self.temp.name) / 'other'
        other.mkdir()
        (self.root / 'tasks').symlink_to(other, target_is_directory=True)
        self.install(ok=False)
        self.assertEqual(snapshot(other), {})

    def test_installed_skill_self_contained(self):
        self.install(mode='skill')
        for folder in ('.claude/skills', '.agents/skills'):
            skill = self.root / folder / 'orchestration-setup'
            target = Path(self.temp.name) / ('target-' + folder.split('/')[0])
            self.run_script(skill / 'scripts/install.py', 'setup', '--target', 'both', '--project', target)
            self.assertTrue((target / 'tasks/_generate.py').exists())

    def test_codex_toml(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest('TOML parsing requires Python 3.11+')
        self.install(target='codex')
        for file in (self.root / '.codex/agents').glob('*.toml'):
            agent = tomllib.loads(file.read_text())
            self.assertEqual(agent['name'], file.stem)
            self.assertTrue(agent['developer_instructions'])
            self.assertNotIn('model', agent)

    def test_generate_and_resume_preserves_all_evidence(self):
        self.prepare()
        self.generate('--check')
        self.assertFalse((self.root / 'tasks/run-0').exists())
        self.generate()
        readme = self.root / 'tasks/run-0/README.md'
        readme.write_text(readme.read_text().replace('- [ ] T0.1', '- [x] T0.1'))
        (readme.parent / 'T0.1-review.md').write_text('ACCEPT evidence')
        before = snapshot(self.root)
        self.generate()
        self.assertEqual(before, snapshot(self.root))
        self.assertEqual(len(list(readme.parent.glob('T[0-9]*.md'))), 4)

    def test_changed_plan_preserves_runs(self):
        self.prepare()
        self.generate()
        (self.root / 'docs/dev-plan.md').write_text(PLAN.replace('Health handler', 'Changed handler'))
        before = snapshot(self.root)
        self.generate(ok=False)
        self.assertEqual(before, snapshot(self.root))

    def test_missing_or_edited_card_refused(self):
        self.prepare()
        self.generate()
        card = self.root / 'tasks/run-0/T0.1.md'
        card.write_text('edited')
        self.generate(ok=False)
        card.unlink()
        self.generate(ok=False)
        self.assertFalse(card.exists())

    def test_legacy_runs_not_overwritten(self):
        self.prepare()
        path = self.root / 'tasks/run-0/README.md'
        path.parent.mkdir()
        path.write_text('- [x] T0.1')
        before = snapshot(self.root)
        self.generate(ok=False)
        self.assertEqual(before, snapshot(self.root))

    def test_invalid_plans_write_nothing(self):
        cases = {
            'missing acceptance': PLAN.replace('**Приёмка:**', 'Acceptance:'),
            'invalid size': PLAN.replace('| S |', '| XL |'),
            'unknown dependency': PLAN.replace('| T0.1 | `src/health', '| T9.9 | `src/health'),
            'cycle': PLAN.replace('| S | — |', '| S | T0.2 |'),
            'duplicate ID': PLAN.replace('| T0.3 |', '| T0.2 |'),
            'malformed ID': PLAN.replace('| T0.3 |', '| broken |'),
            'missing gate': PLAN.replace('**Gate:**', '**Missing:**'),
            'ownership overlap': PLAN.replace('`src/version.py`, `tests/test_version.py`', '`src/`'),
            'internal parallel dependency': PLAN.replace('| T0.1 | `src/version', '| T0.2 | `src/version'),
            'traversal': PLAN.replace('`docs/api.md`', '`../outside`'),
            'missing column': PLAN.replace('| S | — |', '| — |'),
            'malformed stage': PLAN.replace('## 1. Этап', '## Этап'),
            'no tasks': '# Empty plan',
        }
        for name, plan in cases.items():
            with self.subTest(name=name):
                self.prepare(plan)
                before = snapshot(self.root)
                self.generate(ok=False)
                self.assertEqual(before, snapshot(self.root))

    def test_sequential_dependency_and_large_design(self):
        self.prepare(PLAN.replace('параллельно', 'последовательно')
                     .replace('| T0.1 | `src/version', '| T0.2 | `src/version')
                     .replace('| S |', '| L |'))
        self.generate()
        self.assertIn('Route: design', (self.root / 'tasks/run-0/T0.3.md').read_text())

    def test_generator_symlink_refused(self):
        self.prepare()
        other = Path(self.temp.name) / 'external'
        other.mkdir()
        (self.root / 'tasks/run-0').symlink_to(other, target_is_directory=True)
        self.generate(ok=False)
        self.assertEqual(snapshot(other), {})


    # --- Claude guard hook -------------------------------------------------

    def hook(self, event, **env):
        import os
        proc = subprocess.run([sys.executable, str(self.root / '.claude/hooks/orch_guard.py')],
                              input=json.dumps(event), capture_output=True, text=True,
                              env={**os.environ, 'CLAUDE_PROJECT_DIR': str(self.root), **env})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def test_claude_hooks_merge_preserves_settings(self):
        settings = self.root / '.claude/settings.json'
        settings.parent.mkdir()
        settings.write_text(json.dumps({'permissions': {'allow': ['Bash(ls)']},
                                        'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'x'}]}]}}))
        self.install(target='claude')
        data = json.loads(settings.read_text())
        self.assertEqual(data['permissions'], {'allow': ['Bash(ls)']})
        self.assertEqual(len(data['hooks']['Stop']), 1)
        for event in ('PreToolUse', 'PostToolUse', 'SubagentStart', 'SubagentStop'):
            self.assertEqual(len(data['hooks'][event]), 1)
        self.assertTrue((self.root / '.claude/hooks/orch_guard.py').exists())
        before = snapshot(self.root)
        self.install(target='claude')
        self.assertEqual(before, snapshot(self.root))

    def test_no_claude_hooks_and_invalid_settings(self):
        self.install('--no-claude-hooks', target='claude')
        self.assertFalse((self.root / '.claude/hooks').exists())
        self.assertFalse((self.root / '.claude/settings.json').exists())
        self.install('--no-claude-hooks', target='codex', ok=False)
        (self.root / '.claude/settings.json').write_text('{broken')
        before = snapshot(self.root)
        self.install(target='claude', ok=False)
        self.assertEqual(before, snapshot(self.root))

    def test_guard_hook_enforces_coordinator_rules(self):
        self.install(target='claude')
        self.prepare()
        self.generate()
        readme = self.root / 'tasks/run-0/README.md'
        def edit(path, old='a', new='b', **extra):
            return self.hook({'hook_event_name': 'PreToolUse', 'tool_name': 'Edit',
                              'tool_input': {'file_path': str(path), 'old_string': old,
                                             'new_string': new}, **extra})
        tick = dict(path=readme, old='- [ ] T0.1', new='- [x] T0.1')
        src = self.root / 'src/health.py'
        self.assertIsNone(edit(src))  # no active run: ordinary sessions unaffected
        (self.root / 'tasks/.active-run').write_text('run-0')
        self.assertEqual(edit(src)['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIsNone(edit(src, agent_id='a1', agent_type='fast-worker'))
        self.assertIsNone(edit(self.root / 'tasks/run-0/T0.1-progress.md'))
        self.assertIsNotNone(edit(**tick))
        self.hook({'hook_event_name': 'SubagentStop', 'agent_id': 'r1', 'agent_type': 'reviewer',
                   'last_assistant_message': '**Task:** T0.1 · **Verdict: RETURN**\n1. gap'})
        self.assertIsNotNone(edit(**tick))
        self.hook({'hook_event_name': 'SubagentStop', 'agent_id': 'r2', 'agent_type': 'reviewer',
                   'last_assistant_message': '**Task:** T0.1 · **Verdict: ACCEPT**\n1. ok'})
        self.assertIsNone(edit(**tick))
        self.assertIsNotNone(edit(self.root / 'tasks/.orch/verdicts.jsonl'))
        import os
        proc = subprocess.run([sys.executable, str(self.root / '.claude/hooks/orch_guard.py'), 'report'],
                              capture_output=True, text=True,
                              env={**os.environ, 'CLAUDE_PROJECT_DIR': str(self.root)})
        self.assertIn('first-pass ACCEPT: 0/1', proc.stdout)

    def test_cross_wave_conflict_and_rulings(self):
        self.prepare(PLAN + '\n### Волна 0.3 — параллельно\n\n'
                     '| ID | Задача | Размер | Зависит | Владение | Контекст | Сделать / Приёмка |\n'
                     '|---|---|---|---|---|---|---|\n'
                     '| T0.4 | Docs | S | T0.1 | `src/health.py` | docs/api.md | Doc. **Приёмка:** ok. |\n')
        self.generate()
        run = self.root / 'tasks/run-0'
        self.assertIn('Not parallel with: T0.4', (run / 'T0.2.md').read_text())
        self.assertIn('Not parallel with: —', (run / 'T0.3.md').read_text())
        self.assertIn('## Rulings', (run / 'README.md').read_text())

if __name__ == '__main__':
    unittest.main()
