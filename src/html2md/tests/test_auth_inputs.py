"""Security contracts for caller-supplied authentication files."""

import json
import os

import pytest

from html2md.network.auth_inputs import load_private_headers, load_storage_state


def _private_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)
    return path


def test_private_header_file_accepts_generic_credentials(tmp_path):
    path = _private_json(
        tmp_path / "headers.json",
        {"Authorization": "Bearer secret", "X-Tenant": "docs"},
    )

    assert load_private_headers(path) == {
        "Authorization": "Bearer secret",
        "X-Tenant": "docs",
    }


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"Host": "example.com"}, "transport header"),
        ({"X-Test\nInjected": "value"}, "invalid"),
        ({"X-Test": "value\r\nInjected: yes"}, "invalid"),
        ({"X-Test": 3}, "must be strings"),
        ({}, "non-empty"),
    ],
)
def test_header_file_rejects_unsafe_shapes(tmp_path, payload, message):
    path = _private_json(tmp_path / "headers.json", payload)

    with pytest.raises(ValueError, match=message):
        load_private_headers(path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
def test_authentication_files_reject_group_or_world_access(tmp_path):
    path = tmp_path / "headers.json"
    path.write_text('{"Authorization":"secret"}', encoding="utf-8")
    path.chmod(0o640)

    with pytest.raises(ValueError, match="chmod 600"):
        load_private_headers(path)


def test_authentication_files_reject_symlinks(tmp_path):
    target = _private_json(tmp_path / "target.json", {"X-Test": "value"})
    link = tmp_path / "headers.json"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="regular file"):
        load_private_headers(link)


def test_storage_state_requires_playwright_shape_and_returns_loaded_document(tmp_path):
    path = _private_json(
        tmp_path / "state.json",
        {"cookies": [], "origins": []},
    )

    assert load_storage_state(path) == {"cookies": [], "origins": []}

    invalid = _private_json(
        tmp_path / "invalid-state.json",
        {"cookies": {}, "origins": []},
    )
    with pytest.raises(ValueError, match="arrays"):
        load_storage_state(invalid)
