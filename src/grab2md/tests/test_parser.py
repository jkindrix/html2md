"""Crawler link-scope boundary tests."""

import pytest

from grab2md.utils.crawl_policy import compile_follow_option
from grab2md.utils.parser import should_follow_link


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("https://example.com/page", True),
        ("https://example.com:443/page", True),
        ("https://example.com:8443/page", False),
        ("https://sub.example.com/page", False),
    ],
)
def test_domain_only_requires_the_same_hostname_and_effective_port(candidate, expected):
    assert (
        should_follow_link(candidate, "https://example.com/start", "domain-only")
        is expected
    )


def test_host_only_requires_the_exact_hostname():
    assert should_follow_link(
        "http://example.com:8080/page", "https://example.com/start", "host-only"
    )
    assert not should_follow_link(
        "https://sub.example.com/page", "https://example.com/start", "host-only"
    )


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("https://example.com/page", True),
        ("https://docs.example.com/page", True),
        ("https://deep.docs.example.com/page", True),
        ("https://evilexample.com/page", False),
        ("https://example.com.evil.test/page", False),
    ],
)
def test_subdomain_scope_uses_a_dot_delimited_hostname_boundary(candidate, expected):
    assert (
        should_follow_link(candidate, "https://example.com/start", "subdomain")
        is expected
    )


@pytest.mark.parametrize(
    "candidate",
    [
        "https://user:secret@example.com/page",
        "file:///etc/passwd",
        "https://example.com:invalid/page",
    ],
)
def test_all_follow_modes_reject_malformed_or_credential_urls(candidate):
    for follow_option in ("domain-only", "host-only", "subdomain", ".*"):
        assert not should_follow_link(
            candidate, "https://example.com/start", follow_option
        )


def test_follow_regex_is_compiled_before_link_evaluation():
    pattern = compile_follow_option(r"/docs(?:/|$)")

    assert should_follow_link(
        "https://example.com/docs/guide", "https://example.com/start", pattern
    )
    assert not should_follow_link(
        "https://example.com/blog/post", "https://example.com/start", pattern
    )

    with pytest.raises(ValueError, match="Invalid --follow regex pattern"):
        compile_follow_option("[")
