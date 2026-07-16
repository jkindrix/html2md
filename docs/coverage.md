# Coverage baseline

Coverage is measured against production code in `src/html2md`; package-internal test modules are excluded from both collection and reporting. The canonical suite includes unit, integration, and real CLI subprocess tests:

```bash
poetry run coverage erase
poetry run pytest src/html2md/tests tests/config \
  --cov=html2md --cov-report=term-missing:skip-covered
```

On 2026-07-16, Python 3.11.2 measured 4,328 production statements, 1,591 missed, and 63.24% total coverage. The enforced floor is 59%, which allows rounding and small interpreter-dependent line differences while preventing a material regression. The floor must not be lowered to make a change pass.

The largest gaps are concentrated in:

| Module | Statements | Missed | Coverage | Tracked work |
|---|---:|---:|---:|---|
| `cli/cli.py` | 994 | 648 | 35% | H2M-050–051 |
| `cookies/session_manager.py` | 476 | 296 | 38% | H2M-050–051 |
| `utils/progress_display.py` | 151 | 151 | 0% | H2M-050 |
| `network/chatgpt_handler.py` | 221 | 135 | 39% | H2M-036–046 |
| `network/concurrent_limiter.py` | 185 | 40 | 78% | H2M-048 |

The stabilization target is at least 75% production statement coverage after dead concurrency code is removed and the CLI is decomposed. New or changed behavior should receive focused tests even when the repository-wide percentage remains above the floor.
