"""Tests for the explicit configuration schema."""

import pytest

from grab2md.config.loader import DEFAULT_CONFIG
from grab2md.config.schema import (
    ConfigValidationError,
    VALUE_TYPES,
    default_at_path,
    parse_cli_value,
    validate_and_merge,
)


def test_explicit_schema_covers_every_default_leaf():
    paths = set()

    def collect(tree, prefix=()):
        for key, value in tree.items():
            path = (*prefix, key)
            if isinstance(value, dict):
                collect(value, path)
            else:
                paths.add(path)

    collect(DEFAULT_CONFIG)

    assert paths == set(VALUE_TYPES)


def test_optional_values_round_trip_without_default_type_inference():
    supplied = {
        "headers": {"contact_email": "crawler@example.com"},
        "cli_defaults": {
            "crawl": {
                "rate_limit": 30,
                "user_agent_contact": "https://example.com/bot",
            },
            "convert": {"browser": "firefox"},
        },
    }

    merged, errors = validate_and_merge(supplied, DEFAULT_CONFIG, strict=True)

    assert errors == ()
    assert merged["headers"]["contact_email"] == "crawler@example.com"
    assert merged["cli_defaults"]["crawl"]["rate_limit"] == 30
    assert merged["cli_defaults"]["convert"]["browser"] == "firefox"


def test_numeric_coercion_is_narrow_and_deterministic():
    supplied = {
        "cli_defaults": {"crawl": {"delay": 3}},
    }

    merged, _ = validate_and_merge(supplied, DEFAULT_CONFIG, strict=True)

    assert merged["cli_defaults"]["crawl"]["delay"] == 3.0


@pytest.mark.parametrize(
    "supplied, path",
    [
        (
            {"cli_defaults": {"crawl": {"rate_limit": "30"}}},
            "cli_defaults.crawl.rate_limit",
        ),
        ({"cli_defaults": {"crawl": {"delay": True}}}, "cli_defaults.crawl.delay"),
        ({"logging": {"level": "VERBOSE"}}, "logging.level"),
    ],
)
def test_strict_validation_rejects_invalid_known_values(supplied, path):
    with pytest.raises(ConfigValidationError, match=path):
        validate_and_merge(supplied, DEFAULT_CONFIG, strict=True)


def test_non_strict_loading_uses_in_memory_default_and_reports_error():
    supplied = {"cli_defaults": {"crawl": {"rate_limit": "30"}}}

    merged, errors = validate_and_merge(supplied, DEFAULT_CONFIG, strict=False)

    assert merged["cli_defaults"]["crawl"]["rate_limit"] is None
    assert errors == ("cli_defaults.crawl.rate_limit expected int or null, got str",)


def test_unknown_extension_keys_are_preserved_defensively():
    supplied = {"plugin": {"custom": [1, 2, 3]}}

    merged, _ = validate_and_merge(supplied, DEFAULT_CONFIG, strict=True)
    supplied["plugin"]["custom"].append(4)

    assert merged["plugin"] == {"custom": [1, 2, 3]}


@pytest.mark.parametrize(
    "path, raw, expected",
    [
        (("cli_defaults", "convert", "content_mode"), "main", "main"),
        (("cli_defaults", "crawl", "max_pages"), "250", 250),
        (("cli_defaults", "crawl", "delay"), "1.25", 1.25),
        (("cli_defaults", "crawl", "rate_limit"), "45", 45),
        (("cli_defaults", "crawl", "rate_limit"), "null", None),
        (("cli_defaults", "convert", "browser"), "firefox", "firefox"),
        (("cli_defaults", "convert", "images_dir"), "page assets", "page assets"),
    ],
)
def test_cli_values_are_parsed_by_schema(path, raw, expected):
    assert parse_cli_value(DEFAULT_CONFIG, path, raw) == expected


def test_default_lookup_returns_a_defensive_copy():
    value = default_at_path(DEFAULT_CONFIG, ("cli_defaults", "crawl"))
    value["max_pages"] = 1

    assert DEFAULT_CONFIG["cli_defaults"]["crawl"]["max_pages"] == 100


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("follow", "["),
        ("max_depth", -1),
        ("max_pages", 0),
        ("delay", -1.0),
        ("rate_limit", 0),
    ],
)
def test_crawl_policy_values_obey_semantic_constraints(key, value):
    supplied = {"cli_defaults": {"crawl": {key: value}}}

    with pytest.raises(ConfigValidationError, match=f"crawl.{key}"):
        validate_and_merge(supplied, DEFAULT_CONFIG, strict=True)
