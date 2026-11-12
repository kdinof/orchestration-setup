#!/usr/bin/env python3
"""Orchestration guard for Claude Code (Python 3.9+, standard library).

Enforces two protocol rules in code instead of prompts, and records metrics.
Installed by `scripts/install.py setup --target claude|both` into .claude/hooks/
and wired in .claude/settings.json. Codex is not affected.

  PreToolUse  Edit|Write|MultiEdit|NotebookEdit
      1. Главная сессия (нет agent_id) во время активного рана пишет только в
         tasks/**, docs/devlog.md и docs/solutions/**. Код — только через сабагентов.
      2. Чекбокс «- [x] T<ID>» в README рана ставится, только если последний
         вердикт reviewer по этой задаче — ACCEPT (журнал ведёт сам хук).
      3. Журналы хука (tasks/.orch/) главной сессии не редактируются.
  SubagentStart             → метрики: старт агента.
  SubagentStop              → метрики (модель, токены, время, вызовы) + вердикт reviewer.
  PostToolUse SubagentHandback (reviewer) → вердикт, если отчёт сдан через handback.

Активный ран = файл tasks/.active-run (имя папки рана). Его создаёт /orchestrate
на старте и удаляет при закрытии рана. Нет файла → охрана редактирования выключена
(обычные сессии в проекте не мешаются), метрики и вердикты пишутся всё равно.

Аварийный выход для владельца (нет сабагентов, разрешённый single-agent fallback):
запустить claude с ORCH_ALLOW_MAIN_EDITS=1.

Отчёт по метрикам:  python3 .claude/hooks/orch_guard.py report [run-папка]
"""
import json
import os
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
TASKS = ROOT / "tasks"
ORCH = TASKS / ".orch"
METRICS = ORCH / "metrics.jsonl"
VERDICTS = ORCH / "verdicts.jsonl"
ACTIVE = TASKS / ".active-run"

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
REVIEWER = "reviewer"
TASK_ID = re.compile(r"\bT\d+\.\d+\b")
VERDICT = re.compile(r"Verdict\W{0,6}(ACCEPT|RETURN|BLOCKED)\b", re.I)
CHECKED = re.compile(r"^\s*- \[[xX]\] (T\d+\.\d+)\b", re.M)
README = re.compile(r"^tasks/run-[^/]+/README\.md$")


# ---------- utils ----------

def append(path, rec):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_jsonl(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def active_run():
    try:
        return ACTIVE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def rel(path_str):
    """Path relative to project root (posix) or None if outside the project."""
    if not path_str:
        return None
    p = pathlib.Path(path_str)
    if not p.is_absolute():
        p = ROOT / p
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return None


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))
    sys.exit(0)


# ---------- PreToolUse: edit guard ----------

def content_after(tool, inp, current):
    """Best-effort text of the file after the edit (for README checkbox diff)."""
    if tool == "Write":
        return inp.get("content", "")
    edits = inp.get("edits") if tool == "MultiEdit" else [inp]
    text = current
    for e in edits or []:
        old, new = e.get("old_string", ""), e.get("new_string", "")
        if not old:
            continue
        text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
    return text


def last_verdict(tid):
    verdict = None
    for rec in read_jsonl(VERDICTS):
        if rec.get("task") == tid:
            verdict = rec.get("verdict")
    return verdict


def pre_tool_use(ev):
    tool = ev.get("tool_name")
    if tool not in EDIT_TOOLS or ev.get("agent_id"):
        return  # subagents are governed by their own role files + reviewer
    inp = ev.get("tool_input") or {}
    path = rel(inp.get("file_path") or inp.get("notebook_path"))
    if path is None:
        return  # outside the project — not our business

    if path.startswith("tasks/.orch/"):
        deny("tasks/.orch/ — журналы хука (метрики, вердикты reviewer). "
             "Их пишет только хук; оркестратор их читает, но не редактирует.")

    if README.match(path):
        current = ""
        try:
            current = (ROOT / path).read_text(encoding="utf-8")
        except OSError:
            pass
        before = set(CHECKED.findall(current))
        after = set(CHECKED.findall(content_after(tool, inp, current)))
        missing = sorted(t for t in after - before if last_verdict(t) != "ACCEPT")
        if missing:
            deny("Чекбокс ставится только после вердикта ACCEPT от reviewer. "
                 f"Нет ACCEPT в tasks/.orch/verdicts.jsonl для: {', '.join(missing)}. "
                 "Отправь задачу reviewer'у; его ответ должен начинаться строкой "
                 "«**Task:** T<ID> · **Verdict: ACCEPT**» — хук запишет вердикт сам.")
        return

    run = active_run()
    if not run or os.environ.get("ORCH_ALLOW_MAIN_EDITS") == "1":
        return
    if path.startswith(("tasks/", "docs/solutions/")) or path == "docs/devlog.md":
        return
    deny(f"Идёт ран {run}: координатор не пишет код и проектные файлы ({path}). "
         "Делегируй fast-worker с самодостаточным брифом из карточки задачи "
         "(конфликт при интеграции — тоже задача для fast-worker). "
         "Не снимай tasks/.active-run, чтобы обойти правило: если правка правда "
         "нужна от главной сессии — спроси владельца проекта.")


# ---------- metrics & verdicts ----------

def transcript_stats(path):
    stats = {"models": [], "input": 0, "output": 0, "cache_read": 0,
             "cache_write": 0, "tool_calls": 0}
    seen = set()
    try:
        lines = pathlib.Path(os.path.expanduser(path)).read_text(encoding="utf-8").splitlines()
    except (OSError, TypeError):
        return stats
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("type") != "assistant":
            continue
        msg = row.get("message") or {}
        stats["tool_calls"] += sum(
            1 for c in msg.get("content") or [] if isinstance(c, dict) and c.get("type") == "tool_use")
        mid = msg.get("id")
        if mid in seen:
            continue  # one API message is split into several rows (one per block)
        seen.add(mid)
        model = msg.get("model")
        if model and model not in stats["models"]:
            stats["models"].append(model)
        u = msg.get("usage") or {}
        stats["input"] += u.get("input_tokens") or 0
        stats["output"] += u.get("output_tokens") or 0
        stats["cache_read"] += u.get("cache_read_input_tokens") or 0
        stats["cache_write"] += u.get("cache_creation_input_tokens") or 0
    return stats


def record_verdict(text, agent_id, source):
    if not text:
        return
    head = text[:600]
    m = VERDICT.search(head)
    t = TASK_ID.search(head)
    if not (m and t):
        return  # design review / free-form answer — no acceptance verdict
    append(VERDICTS, {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": t.group(0),
                      "verdict": m.group(1).upper(), "agent_id": agent_id,
                      "run": active_run(), "source": source})


def subagent_start(ev):
    append(METRICS, {"event": "start", "ts": time.time(), "agent_id": ev.get("agent_id"),
                     "agent_type": ev.get("agent_type"), "run": active_run()})


def subagent_stop(ev):
    aid, atype = ev.get("agent_id"), ev.get("agent_type")
    if not aid or not atype:
        return  # internal Claude Code agents (prompt suggestions, /btw) report an empty type
    started = next((r["ts"] for r in read_jsonl(METRICS)
                    if r.get("event") == "start" and r.get("agent_id") == aid), None)
    now = time.time()
    rec = {"event": "stop", "ts": now, "agent_id": aid, "agent_type": atype,
           "run": active_run(),
           "duration_s": round(now - started, 1) if started else None}
    rec.update(transcript_stats(ev.get("agent_transcript_path")))
    append(METRICS, rec)
    if atype == REVIEWER:
        record_verdict(ev.get("last_assistant_message"), aid, "stop")


def post_tool_use(ev):
    if ev.get("tool_name") == "SubagentHandback" and ev.get("agent_type") == REVIEWER:
        record_verdict((ev.get("tool_input") or {}).get("message"), ev.get("agent_id"), "handback")


# ---------- report ----------

def report(run=None):
    rows = [r for r in read_jsonl(METRICS) if r.get("event") == "stop"
            and (run is None or r.get("run") == run)]
    if not rows:
        print("Метрик пока нет" + (f" для {run}" if run else "") + ".")
        return
    agg = {}
    for r in rows:
        a = agg.setdefault(r.get("agent_type") or "?", {"n": 0, "sec": 0.0, "in": 0,
                                                       "out": 0, "cr": 0, "cw": 0})
        a["n"] += 1
        a["sec"] += r.get("duration_s") or 0
        a["in"] += r.get("input", 0)
        a["out"] += r.get("output", 0)
        a["cr"] += r.get("cache_read", 0)
        a["cw"] += r.get("cache_write", 0)
    print(f"Метрики сабагентов{' — ' + run if run else ''}")
    print(f"{'агент':<16}{'запусков':>9}{'мин':>8}{'input':>10}{'output':>10}"
          f"{'cache rd':>11}{'cache wr':>11}")
    for name, a in sorted(agg.items(), key=lambda kv: -kv[1]["out"]):
        print(f"{name:<16}{a['n']:>9}{a['sec'] / 60:>8.1f}{a['in']:>10}{a['out']:>10}"
              f"{a['cr']:>11}{a['cw']:>11}")
    verdicts = [v for v in read_jsonl(VERDICTS) if run is None or v.get("run") == run]
    first = {}
    for v in verdicts:
        first.setdefault(v.get("task"), v.get("verdict"))
    ret = sum(1 for v in verdicts if v.get("verdict") == "RETURN")
    fp = sum(1 for verdict in first.values() if verdict == "ACCEPT")
    print(f"Вердиктов reviewer: {len(verdicts)} (RETURN: {ret}); "
          f"first-pass ACCEPT: {fp}/{len(first)} задач")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report(sys.argv[2] if len(sys.argv) > 2 else active_run())
        return
    try:
        ev = json.loads(sys.stdin.read(), strict=False)
    except ValueError:
        return
    handler = {"PreToolUse": pre_tool_use, "SubagentStart": subagent_start,
               "SubagentStop": subagent_stop, "PostToolUse": post_tool_use,
               }.get(ev.get("hook_event_name"))
    if handler:
        handler(ev)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # never break the session because of a guard bug
        print(f"orch_guard: {exc}", file=sys.stderr)
        sys.exit(0)
