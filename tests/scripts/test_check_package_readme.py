from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "check_package_readme.py"


def _run_check(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        check=False,
        text=True,
    )


def test_package_readme_accepts_repository_readme() -> None:
    readme = Path(__file__).parents[2] / "README.md"

    result = _run_check(readme)

    assert result.returncode == 0
    assert result.stderr == ""


def test_package_readme_rejects_relative_targets(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        """\
[guide](docs/guide.md)
![logo](assets/logo.png)
[contributing][contributing]

[contributing]: <CONTRIBUTING.md>
""",
        encoding="utf-8",
    )

    result = _run_check(readme)

    assert result.returncode == 1
    assert (
        "README.md:1: package description link must be absolute: docs/guide.md"
        in result.stderr
    )
    assert (
        "README.md:2: package description link must be absolute: assets/logo.png"
        in result.stderr
    )
    assert (
        "README.md:5: package description link must be absolute: CONTRIBUTING.md"
        in result.stderr
    )
