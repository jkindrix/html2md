# Coverage baseline

Coverage is measured against production code in `src/html2md`; package-internal test modules are excluded from both collection and reporting. The canonical suite includes unit, integration, and real CLI subprocess tests:

```bash
poetry run coverage erase
poetry run pytest src/html2md/tests tests/config \
  --cov=html2md --cov-report=term-missing:skip-covered
```

On 2026-07-17, Python 3.11.2 measured 4,403 production statements, 1,047
missed, and 76.22% total coverage. The enforced floor is 75%, preserving a
small interpreter-dependent buffer without allowing coverage to fall back to
the earlier stabilization baseline. The floor must not be lowered merely to
make a change pass.

The largest gaps are concentrated in:

| Module | Statements | Missed | Coverage | Tracked work |
|---|---:|---:|---:|---|
| `cli/cli.py` | 433 | 215 | 50% | Continue command-boundary extraction and CLI fixtures |
| `cli/config_commands.py` | 310 | 68 | 78% | Add remaining interactive/error fixtures |
| `cookies/session_manager.py` | 477 | 296 | 38% | Add platform/backend boundary fixtures |
| `network/browser_renderer.py` | 103 | 47 | 54% | Extend optional-browser policy/error fixtures |

The post-alpha 75% target is now an enforced regression gate. New or changed
behavior should receive focused tests even when repository-wide coverage remains
above the floor.
