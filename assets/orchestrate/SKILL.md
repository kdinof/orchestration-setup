---
name: orchestrate
description: Запускает или продолжает настроенный ран мультиагентной разработки из tasks/run-*. Используй для выполнения рана по карточкам с зависимостями и независимой приёмкой; для установки инфраструктуры используй orchestration-setup.
---

Read `tasks/ORCHESTRATION.md` and `tasks/PROJECT.md` in the target project.
Execute the run named in the user's message, or the first run in
`tasks/README.md` whose tasks OR gate are not complete.
Follow the shared protocol for dispatch, recovery, verification and stopping.
Claude: use the installed named agents. Codex: use installed custom agents
if available; otherwise pass the matching `tasks/roles/*.md` body to an
available subagent with a self-contained brief. Never invent tool names.

For Codex, read `tasks/codex-models.json` and reconcile it with the native role
settings before dispatch. With no custom-agent support, apply model/effort through
actual spawn options if supported; prompt text alone cannot select a model.
Report unsupported routing; record actual model/effort or mark them unverified.
