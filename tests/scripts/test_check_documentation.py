from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "check_documentation.py"


def _run_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        check=False,
        text=True,
    )


def _write_contract(root: Path, *, version: str = "1.2.3") -> None:
    (root / "docs").mkdir(parents=True)
    (root / "extension").mkdir()
    (root / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "extension" / "manifest.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    (root / "README.md").write_text(
        f"""\
# Example

- Development/release-candidate version: `{version}`

The hidden compatibility alias `grab2md convert SOURCE` remains accepted.

## Commands

| Command | Purpose |
|---|---|
| `grab2md SOURCE...` | Convert input. |

## More

[Guide](docs/guide.md)
""",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        f"The pending first public `{version}` alpha is next.\n", encoding="utf-8"
    )
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")


def test_documentation_check_accepts_repository_contract() -> None:
    root = Path(__file__).parents[2]

    result = _run_check(root)

    assert result.returncode == 0, result.stderr


def test_documentation_check_rejects_version_drift(tmp_path: Path) -> None:
    _write_contract(tmp_path)
    manifest = tmp_path / "extension" / "manifest.json"
    manifest.write_text(json.dumps({"version": "1.2.2"}), encoding="utf-8")

    result = _run_check(tmp_path)

    assert result.returncode == 1
    assert "extension/manifest.json version is 1.2.2, expected 1.2.3" in result.stderr


def test_documentation_check_rejects_hidden_alias_in_command_table(
    tmp_path: Path,
) -> None:
    _write_contract(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "| `grab2md SOURCE...` | Convert input. |",
            "| `convert` | Convert input. |",
        ),
        encoding="utf-8",
    )

    result = _run_check(tmp_path)

    assert result.returncode == 1
    assert "README command table must present `grab2md SOURCE...`" in result.stderr
    assert "README command table must not present hidden `convert`" in result.stderr


def test_documentation_check_rejects_broken_local_link(tmp_path: Path) -> None:
    _write_contract(tmp_path)
    (tmp_path / "docs" / "guide.md").unlink()

    result = _run_check(tmp_path)

    assert result.returncode == 1
    assert (
        "README.md:15: local Markdown link does not exist: docs/guide.md"
        in result.stderr
    )
