# Coverage baseline

Coverage is measured against production code in `src/html2md`; package-internal test modules are excluded from both collection and reporting. The canonical suite includes unit, integration, and real CLI subprocess tests:

```bash
poetry run coverage erase
poetry run pytest src/html2md/tests tests/config \
  --cov=html2md --cov-report=term-missing:skip-covered
```

On 2026-07-17, Python 3.11.2 measured 4,498 production statements, 1,003
missed, and 77.70% total coverage. The enforced floor is 75%, preserving a
small interpreter-dependent buffer without allowing coverage to fall back to
the earlier stabilization baseline. The floor must not be lowered merely to
make a change pass.

The largest gaps are concentrated in:

| Module | Statements | Missed | Coverage | Tracked work |
|---|---:|---:|---:|---|
| `cli/cli.py` | 387 | 185 | 52% | Continue command-boundary extraction and CLI fixtures |
| `cli/conversion_presenter.py` | 54 | 30 | 44% | Add focused presentation-branch fixtures as behavior changes |
| `cli/config_commands.py` | 310 | 68 | 78% | Add remaining interactive/error fixtures |
| `cookies/session_manager.py` | 561 | 250 | 55% | Add remaining platform/backend boundary fixtures |
| `network/browser_renderer.py` | 103 | 47 | 54% | Extend optional-browser policy/error fixtures |
| `network/safe_http.py` | 217 | 23 | 89% | Extend transport setup/error fixtures as behavior changes |

The post-alpha 75% target is now an enforced regression gate. New or changed
behavior should receive focused tests even when repository-wide coverage remains
above the floor.
