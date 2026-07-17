"""Tests for presentation-neutral CLI conversion orchestration."""

from unittest.mock import Mock

from html2md.cli import conversion_service


def test_url_conversion_builds_one_session_and_threads_security_options(
    monkeypatch, tmp_path
):
    session = Mock()
    statuses = []
    convert = Mock(return_value="# converted")
    apply_cookies = Mock(return_value=session)
    header_manager = Mock()
    header_manager.get_headers.return_value = {"User-Agent": "html2md-test"}

    monkeypatch.setattr(
        conversion_service,
        "load_config",
        lambda: {"browser": {"preferred": "firefox"}},
    )
    monkeypatch.setattr(conversion_service, "build_header_config", Mock())
    monkeypatch.setattr(
        conversion_service, "HeaderManager", Mock(return_value=header_manager)
    )
    get_session = Mock(return_value=session)
    monkeypatch.setattr(conversion_service, "get_session", get_session)
    monkeypatch.setattr(conversion_service, "apply_browser_cookies", apply_cookies)
    monkeypatch.setattr(conversion_service, "html_to_markdown", convert)

    output = tmp_path / "docs" / "page.md"
    result = conversion_service.convert_source(
        "https://example.com/page",
        output=output,
        no_cookies=False,
        browser_cookies=True,
        browser="firefox",
        cookie_json=tmp_path / "cookies.json",
        download_images=True,
        insecure=True,
        include_metadata=True,
        on_status=statuses.append,
    )

    assert result.succeeded
    assert result.markdown == "# converted"
    get_session.assert_called_once_with(verify_ssl=False)
    apply_cookies.assert_called_once_with(
        session,
        "https://example.com/page",
        tmp_path / "cookies.json",
        browser="firefox",
    )
    assert convert.call_args.kwargs["headers"] == {"User-Agent": "html2md-test"}
    assert convert.call_args.kwargs["output_dir"] == output.parent.resolve()
    assert convert.call_args.kwargs["verify_ssl"] is False
    assert convert.call_args.kwargs["include_metadata"] is True
    assert statuses[-1] == "Converting https://example.com/page to markdown"


def test_local_conversion_uses_source_directory_for_downloaded_images(
    monkeypatch, tmp_path
):
    source = tmp_path / "input" / "page.html"
    source.parent.mkdir()
    source.write_text("<h1>Example</h1>", encoding="utf-8")
    convert = Mock(return_value="# Example")
    monkeypatch.setattr(conversion_service, "local_html_to_markdown", convert)

    result = conversion_service.convert_source(
        str(source),
        output=None,
        no_cookies=True,
        browser_cookies=False,
        browser=None,
        local=True,
        download_images=True,
    )

    assert result.succeeded
    assert result.is_remote is False
    assert result.source_label == str(source.resolve())
    assert convert.call_args.args == (source.resolve(),)
    assert convert.call_args.kwargs["output_dir"] == source.parent.resolve()
    assert convert.call_args.kwargs["verify_ssl"] is True


def test_conversion_exceptions_become_typed_failures(monkeypatch):
    monkeypatch.setattr(
        conversion_service, "load_config", Mock(side_effect=OSError("bad config"))
    )

    result = conversion_service.convert_source(
        "https://example.com",
        output=None,
        no_cookies=True,
        browser_cookies=False,
        browser=None,
    )

    assert result.succeeded is False
    assert result.error == "bad config"
    assert result.markdown is None


def test_empty_conversion_is_not_success(monkeypatch, tmp_path):
    source = tmp_path / "empty.html"
    source.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        conversion_service, "local_html_to_markdown", Mock(return_value=None)
    )

    result = conversion_service.convert_source(
        str(source),
        output=None,
        no_cookies=True,
        browser_cookies=False,
        browser=None,
        local=True,
    )

    assert result.succeeded is False
    assert result.error is None


def test_browser_rendering_rejects_local_files_and_cookie_import(tmp_path):
    source = tmp_path / "page.html"
    source.write_text("<h1>Local</h1>", encoding="utf-8")

    local = conversion_service.convert_source(
        str(source),
        output=None,
        no_cookies=True,
        browser_cookies=False,
        browser=None,
        local=True,
        render_js=True,
    )
    authenticated = conversion_service.convert_source(
        "https://example.com",
        output=None,
        no_cookies=False,
        browser_cookies=True,
        browser="chrome",
        render_js=True,
    )

    assert local.succeeded is False
    assert "only for HTTP(S)" in (local.error or "")
    assert authenticated.succeeded is False
    assert "does not import" in (authenticated.error or "")


def test_remote_conversion_loads_private_headers_and_render_storage_state(
    monkeypatch, tmp_path
):
    headers_path = tmp_path / "headers.json"
    state_path = tmp_path / "state.json"
    loaded_headers = {"Authorization": "Bearer secret"}
    convert = Mock(return_value="# rendered")
    header_manager = Mock()
    header_manager.get_headers.return_value = {"User-Agent": "html2md-test"}
    monkeypatch.setattr(conversion_service, "load_config", lambda: {})
    monkeypatch.setattr(conversion_service, "build_header_config", Mock())
    monkeypatch.setattr(
        conversion_service, "HeaderManager", Mock(return_value=header_manager)
    )
    monkeypatch.setattr(
        conversion_service, "load_private_headers", Mock(return_value=loaded_headers)
    )
    monkeypatch.setattr(
        conversion_service,
        "load_storage_state",
        Mock(return_value={"cookies": [], "origins": []}),
    )
    monkeypatch.setattr(conversion_service, "html_to_markdown", convert)

    result = conversion_service.convert_source(
        "https://example.com",
        output=None,
        no_cookies=True,
        browser_cookies=False,
        browser=None,
        render_js=True,
        headers_file=headers_path,
        storage_state=state_path,
    )

    assert result.succeeded
    assert convert.call_args.kwargs["headers"] == {
        "User-Agent": "html2md-test",
        "Authorization": "Bearer secret",
    }
    assert convert.call_args.kwargs["storage_state"] == {
        "cookies": [],
        "origins": [],
    }


def test_storage_state_requires_rendering_and_auth_inputs_reject_local_files(tmp_path):
    remote = conversion_service.convert_source(
        "https://example.com",
        output=None,
        no_cookies=True,
        browser_cookies=False,
        browser=None,
        storage_state=tmp_path / "state.json",
    )
    source = tmp_path / "page.html"
    source.write_text("<h1>Local</h1>", encoding="utf-8")
    local = conversion_service.convert_source(
        str(source),
        output=None,
        no_cookies=True,
        browser_cookies=False,
        browser=None,
        local=True,
        headers_file=tmp_path / "headers.json",
    )

    assert remote.succeeded is False
    assert "requires --render-js" in (remote.error or "")
    assert local.succeeded is False
    assert "only for HTTP(S)" in (local.error or "")
