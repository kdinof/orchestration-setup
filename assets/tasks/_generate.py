#!/usr/bin/env python3
"""Generate tasks/ run folders from the project's dev plan.

One run = one orchestrator session, boundaries = stage gates.
Re-runnable: overwrites generated files (README status checkboxes are
regenerated too, so re-run only BETWEEN runs, never mid-run).

Требуемый формат плана (markdown):
  ## <n>. Этап <N> — <Название этапа>
  **Gate:** <критерий закрытия этапа>
  ### Волна <N.X> — <режим: последовательно/параллельно (...)>
  | ID | Задача | Размер | Зависит | Владение | Контекст | Сделать / Приёмка |
  |---|---|---|---|---|---|---|
  | T0.1 | ... | L | — | ... | ... | ... **Приёмка:** ... |
"""
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

# ============ НАСТРОЙКА ПОД ПРОЕКТ ============
PLAN = "docs/dev-plan.md"  # путь к плану задач от корня проекта

# Этап → (имя папки рана, короткое имя). Ключи = номера этапов из плана.
RUNS = {
    "0": ("run-0-foundation", "Фундамент"),
    "1": ("run-1-core", "Ядро"),
    # "2": ("run-2-...", "..."),
}

# Задачи с дизайн-проходом deep-reasoner до реализации.
# Критерии: L-размер, security, общие контракты/схемы, конкурентность,
# core-механика (pipeline, state, версии данных).
DESIGN = {
    # "T0.1", "T0.2", ...
}

# High-stakes (адверсариальный дизайн deep-reasoner ∥ reviewer):
# общие контракты, auth, изоляция данных, core wiring. Подмножество DESIGN.
HIGH_STAKES = {
    # "T0.2", ...
}

# Контекст, который исполнитель читает всегда (помимо карточки).
ALWAYS_CONTEXT = "план задач (см. CLAUDE.md → Sources of truth)"
# ==============================================

SRC = ROOT / PLAN
OUT = ROOT / "tasks"

stage_re = re.compile(r"^## \d+\. Этап (\d+) — (.+)$")
wave_re = re.compile(r"^### Волна (\S+) — (.+)$")
gate_re = re.compile(r"^\*\*Gate[^:]*:\*\*\s*(.+)$")
task_re = re.compile(r"^\| (T\d+\.\d+) \|")

stages = {}
stage = wave = None

for line in SRC.read_text(encoding="utf-8").splitlines():
    m = stage_re.match(line)
    if m:
        stage = m.group(1)
        stages[stage] = {"title": m.group(2), "gate": "", "waves": []}
        wave = None
        continue
    if stage is None:
        continue
    m = gate_re.match(line)
    if m and not stages[stage]["gate"]:
        stages[stage]["gate"] = m.group(1)
        continue
    m = wave_re.match(line)
    if m:
        wave = (m.group(1), m.group(2), [])
        stages[stage]["waves"].append(wave)
        continue
    if task_re.match(line) and wave is not None:
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) != 7:
            raise SystemExit(f"Bad row ({len(cells)} cells): {line[:80]}")
        tid, name, size, deps, own, ctx, body = cells
        if "**Приёмка:**" in body:
            todo, accept = body.split("**Приёмка:**", 1)
        else:
            todo, accept = body, ""
        wave[2].append({
            "id": tid, "name": name, "size": size, "deps": deps,
            "own": own, "ctx": ctx, "todo": todo.strip(),
            "accept": accept.strip(),
        })


def route_full(tid):
    if tid in HIGH_STAKES:
        return ("scout (контекст-пакет) → deep-reasoner ∥ reviewer "
                "(адверсариальный дизайн, CLAUDE.md правило 2; синтез — оркестратор) → "
                "fast-worker (реализация) → reviewer (приёмка)")
    if tid in DESIGN:
        return ("scout (контекст-пакет) → deep-reasoner (дизайн) → "
                "fast-worker (реализация) → reviewer (приёмка)")
    return "scout (контекст-пакет) → fast-worker (реализация) → reviewer (приёмка)"


def route_label(tid):
    if tid in HIGH_STAKES:
        return "high-stakes дизайн"
    if tid in DESIGN:
        return "дизайн"
    return "стандарт"


TASK_TMPL = """# {id} — {name}

- **Этап / волна:** {stage} / {wave} ({mode})
- **Размер:** {size}
- **Зависит:** {deps}
- **Владение (менять можно только это):** {own}
- **Контекст-пакет:** {ctx}
  - плюс всегда: {always}
- **Маршрут:** {route}

## Сделать

{todo}

## Приёмка

{accept}

## Протокол исполнителя

Только своя область владения; тесты обязательны (задача без зелёных тестов не сделана); без scope creep — смежные находки в `docs/devlog.md`. Если в брифе назван дизайн-файл `T*-design.md` — он обязателен к исполнению. По завершении: запись в devlog (3–5 строк) + краткий отчёт оркестратору (файлы, статус тестов, отклонения от брифа). Чекбокс статуса ставит только оркестратор — в README рана, после вердикта ACCEPT от reviewer.
"""

RUN_TMPL = """# Run {stage} — Этап {stage}: {title}

**Gate (ран закрыт, когда):** {gate}

**Задач:** {count} · один запуск оркестратора (Fable 5, effort high) на весь ран · правила: `CLAUDE.md`

## Как запустить

1. Терминал в корне проекта → `claude` → `/model` → Fable 5, Reasoning effort: High.
2. `/orchestrate {dirname}` — команда сама определяет, старт это или продолжение после обрыва.

{waves}
## Статус (отмечает только оркестратор, после ACCEPT от reviewer)

{status}

### Обнаруженное в ходе рана (append-only)

_(пусто)_
"""

OUT.mkdir(exist_ok=True)
total = 0
run_index = []

for stage_num, info in stages.items():
    if stage_num not in RUNS:
        raise SystemExit(f"Этап {stage_num} есть в плане, но не описан в RUNS")
    dirname, _short = RUNS[stage_num]
    rdir = OUT / dirname
    rdir.mkdir(exist_ok=True)

    waves_md, status_md, count = [], [], 0
    for wlabel, wmode, wtasks in info["waves"]:
        waves_md.append(f"### Волна {wlabel} — {wmode}\n")
        waves_md.append("| Задача | Размер | Зависит | Маршрут |")
        waves_md.append("|---|---|---|---|")
        for t in wtasks:
            count += 1
            total += 1
            fname = f"{t['id']}.md"
            (rdir / fname).write_text(TASK_TMPL.format(
                stage=stage_num, wave=wlabel, mode=wmode, always=ALWAYS_CONTEXT,
                route=route_full(t["id"]), **t), encoding="utf-8")
            waves_md.append(
                f"| [{t['id']} — {t['name']}]({fname}) | {t['size']} | "
                f"{t['deps']} | {route_label(t['id'])} |")
            status_md.append(f"- [ ] {t['id']} — {t['name']}")
        waves_md.append("")

    (rdir / "README.md").write_text(RUN_TMPL.format(
        stage=stage_num, title=info["title"], gate=info["gate"],
        count=count, dirname=dirname,
        waves="\n".join(waves_md), status="\n".join(status_md)),
        encoding="utf-8")
    run_index.append((dirname, info["title"], count))

index = ["# Tasks — раны оркестратора\n"]
index.append(
    f"Задачи плана `{PLAN}` разложены на **раны**: "
    "один ран = один запуск сессии-оркестратора, границы ранов = gate'ы этапов "
    "(пока gate не зелёный, следующий этап не начинается). Запускать строго по порядку.\n")
index.append("| Ран | Этап | Задач | Статус |")
index.append("|---|---|---|---|")
for dirname, title, count in run_index:
    index.append(f"| [{dirname}]({dirname}/README.md) | {title} | {count} | см. README рана |")
index.append("""
## Как это устроено

- **README рана** — оперативный план оркестратора: волны, маршруты, чеклист «Статус» (источник правды по прогрессу).
- **Карточка задачи (`T*.md`)** — самодостаточный бриф: владение, контекст-пакет, приёмка, маршрут агентов. Сабагенту показывают только его карточку, не весь план.
- **Маршруты:** «стандарт» — scout → fast-worker → reviewer; «дизайн» — плюс deep-reasoner до реализации (L-задачи, security, конкурентность); «high-stakes дизайн» — дизайн прогоняется адверсариально (deep-reasoner ∥ reviewer): контракты, auth, изоляция данных, core wiring. Дизайн сохраняется в `T<ID>-design.md` рядом с карточкой.
- Требования и полный контекст остаются в плане и PRD — карточки из них сгенерированы и при расхождении проигрывают плану.
""")
(OUT / "README.md").write_text("\n".join(index), encoding="utf-8")

for stage_num, info in stages.items():
    n = sum(len(w[2]) for w in info["waves"])
    print(f"Этап {stage_num}: {n} задач, {len(info['waves'])} волн — {RUNS[stage_num][0]}")
print(f"Всего: {total} задач")
