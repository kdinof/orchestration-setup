# orchestration-setup

Скилл настройки мультиагентной разработки для **Claude Code и Codex**.
Общий протокол: план → задачи с зависимостями → реализация → независимая
приёмка → интеграционный gate → сохранение проверенных решений.

## Установка скилла настройки

Нужен Python 3.9+; внешних Python-зависимостей нет.

```bash
git clone https://github.com/kdinof/orchestration-setup.git
cd orchestration-setup
# Для обоих хостов в выбранном проекте:
python3 scripts/install.py skill --target both --project /path/to/project
# Или персональная установка:
python3 scripts/install.py skill --target both --user
```

Можно выбрать `--target claude` или `--target codex`. Предпросмотр: `--dry-run`.

| Хост | Проект | Персонально | Вызов настройки |
|---|---|---|---|
| Claude Code | `.claude/skills/orchestration-setup` | `~/.claude/skills/orchestration-setup` | `/orchestration-setup` |
| Codex | `.agents/skills/orchestration-setup` | `~/.agents/skills/orchestration-setup` | `$orchestration-setup` |

Совместим и прежний способ `git clone` прямо в каталог скилла Claude.
Установщик копирует самодостаточный пакет, исходный checkout после установки
не требуется. Обновление одинаковых файлов — no-op; отличающиеся файлы требуют
согласования показанного diff. Не устанавливай одну версию сразу в несколько
областей одного хоста без необходимости — возможны дубликаты.

## Настройка проекта

Скажи агенту: «Настрой оркестрацию для Claude и Codex в этом проекте».
Либо создай инфраструктуру напрямую из checkout:

```bash
python3 scripts/install.py setup --target both --project /path/to/project --dry-run
python3 scripts/install.py setup --target both --project /path/to/project
```

Будут созданы:

- Claude: `.claude/agents/*.md`, `.claude/commands/orchestrate.md`, секция `CLAUDE.md`.
- Codex: `.codex/agents/*.toml`, `.agents/skills/orchestrate/`, секция `AGENTS.md`.
- Общее: `tasks/ORCHESTRATION.md`, `tasks/PROJECT.md`, `tasks/roles/`,
  `tasks/_generate.py`, `docs/devlog.md`.

Заполни `tasks/PROJECT.md` и настрой генератор. План должен содержать ID,
размер, зависимости, владение, контекст, проверяемую приёмку и gate этапа.
[Пример плана](references/example-plan.md), [методика](references/BACKLOG.md).

```bash
# В целевом проекте после подготовки плана:
python3 tasks/_generate.py --check
python3 tasks/_generate.py
```

Запуск в Claude: `/orchestrate run-0`; в Codex: `$orchestrate run-0`.
Без имени выбирается первый ран с незакрытыми задачами **или gate**.
Если новые роли не появились, перезапусти хост.

## Что изменилось

- Установка проверяет конфликты до записи и не сбрасывает локальные настройки.
- Генерация проверяет структуру и зависимости, сохраняет прогресс повторного запуска.
- Параллельные исполнители работают в отдельных worktrees; статус и devlog
  записывает только координатор. Без изоляции реализация последовательная.
- Scout вызывается по необходимости. Лимит 3 относится ко всем активным
  сабагентам. Повторы ограничены, ревью и gate требуют сохранённых доказательств.
- Проверенные нетривиальные решения попадают в `docs/solutions/` и используются
  в следующих задачах — подход исследован на примере Every Compound Engineering.
- Claude: хук `.claude/hooks/orch_guard.py` закрепляет кодом, а не промптом,
  «координатор не пишет код» и «чекбокс только после ACCEPT reviewer», и пишет
  метрики сабагентов (модель, токены, время, first-pass acceptance).
- Волна — не барьер: задача стартует, как только готовы зависимости и свободен слот;
  конфликты владения между волнами генератор помечает как «Not parallel with».
- Мелкие развилки координатор решает сам и записывает в Rulings рана с ценой
  ошибки; остановка — только на необратимом, внешнем, security и контрактах.
- Полный набор проверок гоняется один раз на задачу (reviewer), исполнитель —
  только проверки своей области. В Claude это закреплено хуком: полную команду
  из `tasks/checks.json` fast-worker запустить не может, а повторный прогон на
  неизменном коде, который уже прошёл, отклоняется с сохранённым результатом.
  Отчёт показывает, сколько времени ушло на проверки и сколько сэкономил кэш.
  Идеи — из разбора superlite, см. RESEARCH.md.

[Исследование, источники и компромиссы](references/RESEARCH.md).
[Различия хостов и миграция старых установок](references/RUNTIMES.md).

Это набор инструкций и скриптов, а не автономный планировщик: соблюдение runtime
протокола зависит от агента (в Claude два правила дополнительно закреплены хуком;
обход через Bash хук не ловит). Codex по умолчанию наследует модель сессии;
для распределения моделей доступен профиль `balanced` или своя JSON-таблица.
Без сабагентов нельзя заявлять независимую приёмку. Изменение уже сгенерированного
плана требует ручного согласования состояния; автоматического merge статусов нет.

## Проверки

```bash
python3 -m unittest discover -s tests -v
```

MIT — [LICENSE](LICENSE).

## Модели по ролям в Codex

```bash
python3 scripts/install.py setup --target codex --project /path/to/project --codex-profile balanced
```

Профиль: scout — Luna/low, fast-worker — Terra/medium, deep-reasoner и reviewer —
Astra/high. Модель главной сессии не меняется. Без флага остаётся наследование.
Для своих моделей: `--codex-models /path/to/models.json`; за основу возьми
[пример](references/codex-balanced.json). Предпросмотр и защита конфликтов работают
так же, как при обычной установке. Подробности и миграция —
[RUNTIMES.md](references/RUNTIMES.md#model-routing).

Профиль не проверяет доступ к моделям твоего аккаунта и не гарантирует экономию.
Перед первым раном нужно проверить фактическую модель сабагентов; сравнивать
стоимость/время следует с учётом повторных попыток и возвратов с review.
