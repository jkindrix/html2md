# Coverage baseline

Coverage is measured against production code in `src/grab2md`; package-internal test modules are excluded from both collection and reporting. The canonical suite includes unit, integration, and real CLI subprocess tests:

```bash
poetry run coverage erase
poetry run pytest src/grab2md/tests tests/config \
  --cov=grab2md --cov-report=term-missing:skip-covered
```

On 2026-07-19, Python 3.11.2 measured **5,014 production statements, 592
missed, and 88.19% total coverage** (`490 passed, 4 skipped`) at
`17b935232cc66ba3c2f03ea7753ca59a55fdda99`. The enforced floor is 85%,
preserving an interpreter-dependent buffer without allowing coverage to fall
far below the earlier stabilization baseline. The floor must not be lowered
merely to make a change pass.

The denominator differs from the pre-remediation 4,773-statement review
snapshot because command callbacks, crawler setup, batch stages, browser-cookie
adapters, image redirect handling, and direct-source dispatch were decomposed
or consolidated. Tests and configuration fixtures moved with the import package
from `html2md` to `grab2md`; production modules remain the measured denominator.

The largest gaps are concentrated in:

| Module | Statements | Missed | Coverage | Tracked work |
|---|---:|---:|---:|---|
| `cli/cli.py` | 237 | 70 | 70% | Keep callbacks limited to dispatch, option translation, rendering, and exit status |
| `cli/command_runtime.py` | 154 | 4 | 97% | Preserve direct presentation-neutral command tests |
| `cli/conversion_presenter.py` | 53 | 10 | 81% | Preserve success/failure/output presentation fixtures |
| `cli/config_commands.py` | 238 | 37 | 84% | Add remaining interactive/error fixtures |
| `cookies/browser_paths.py` | 45 | 18 | 60% | Preserve platform/config path contracts and add WSL edge fixtures as behavior evolves |
| `cookies/chrome.py` | 103 | 36 | 65% | Add supported Windows DPAPI fixtures on hosted Windows as formats evolve |
| `cookies/firefox.py` | 102 | 23 | 77% | Preserve profile-selection, row-isolation, and database-failure fixtures |
| `network/browser_renderer.py` | 143 | 10 | 93% | Preserve lifecycle, policy, budget, and cleanup fixtures |
| `network/safe_http.py` | 266 | 29 | 89% | Preserve shared buffered/streaming policy fixtures |

The post-alpha 75% target has been exceeded; an 85% regression floor now
ratchets the verified baseline. New or changed behavior should receive focused
tests even when repository-wide coverage remains
above the floor.
