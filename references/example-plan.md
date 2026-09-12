# Example dev plan

Replace paths and criteria with facts from the target repository.

## 1. Этап 0 — Foundation

**Gate:** Run project tests; both health and version endpoints return the documented JSON.

### Волна 0.1 — последовательно

| ID | Задача | Размер | Зависит | Владение | Контекст | Сделать / Приёмка |
|---|---|---|---|---|---|---|
| T0.1 | Define HTTP contract | S | — | `docs/api.md` | README.md | Document health and version responses. **Приёмка:** Both responses specify fields, types and HTTP codes. |

### Волна 0.2 — параллельно

| ID | Задача | Размер | Зависит | Владение | Контекст | Сделать / Приёмка |
|---|---|---|---|---|---|---|
| T0.2 | Health handler | S | T0.1 | `src/health.py`, `tests/test_health.py` | docs/api.md | Implement health response. **Приёмка:** Handler test verifies code and exact documented JSON. |
| T0.3 | Version handler | S | T0.1 | `src/version.py`, `tests/test_version.py` | docs/api.md | Implement version response. **Приёмка:** Handler test verifies code and version field. |
