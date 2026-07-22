"""Explicit validation and CLI parsing for grab2md configuration."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Any, Mapping, Sequence

from grab2md.utils.crawl_policy import (
    compile_follow_option,
    validate_delay,
    validate_max_depth,
    validate_max_pages,
    validate_rate_limit,
)

ConfigPath = tuple[str, ...]
NoneType = type(None)


VALUE_TYPES: dict[ConfigPath, tuple[type, ...]] = {
    ("logging", "level"): (str,),
    ("browser", "preferred"): (str,),
    ("headers", "enhanced_user_agent"): (bool,),
    ("headers", "contact_email"): (str, NoneType),
    ("headers", "contact_url"): (str, NoneType),
    ("headers", "user_agent_name"): (str,),
    ("headers", "enable_compression"): (bool,),
    ("headers", "compression_methods"): (str,),
    ("headers", "respect_caching"): (bool,),
    ("headers", "include_accept_language"): (bool,),
    ("headers", "preferred_language"): (str,),
    ("cli_defaults", "batch", "hierarchical"): (bool,),
    ("cli_defaults", "batch", "flatten"): (bool,),
    ("cli_defaults", "batch", "flatten_all"): (bool,),
    ("cli_defaults", "batch", "content_mode"): (str,),
    ("cli_defaults", "batch", "selector"): (str, NoneType),
    ("cli_defaults", "batch", "metadata"): (bool,),
    ("cli_defaults", "batch", "enhanced_headers"): (bool,),
    ("cli_defaults", "batch", "user_agent_contact"): (str, NoneType),
    ("cli_defaults", "batch", "visualize"): (bool,),
    ("cli_defaults", "batch", "quiet"): (bool,),
    ("cli_defaults", "batch", "allow_private_network"): (bool,),
    ("cli_defaults", "crawl", "hierarchical"): (bool,),
    ("cli_defaults", "crawl", "flatten"): (bool,),
    ("cli_defaults", "crawl", "follow"): (str,),
    ("cli_defaults", "crawl", "max_depth"): (int,),
    ("cli_defaults", "crawl", "max_pages"): (int,),
    ("cli_defaults", "crawl", "delay"): (float,),
    ("cli_defaults", "crawl", "respect_robots"): (bool,),
    ("cli_defaults", "crawl", "rate_limit"): (int, NoneType),
    ("cli_defaults", "crawl", "enhanced_headers"): (bool,),
    ("cli_defaults", "crawl", "user_agent_contact"): (str, NoneType),
    ("cli_defaults", "crawl", "polite"): (bool,),
    ("cli_defaults", "crawl", "show_progress"): (bool,),
    ("cli_defaults", "crawl", "content_mode"): (str,),
    ("cli_defaults", "crawl", "selector"): (str, NoneType),
    ("cli_defaults", "crawl", "metadata"): (bool,),
    ("cli_defaults", "crawl", "visualize"): (bool,),
    ("cli_defaults", "crawl", "quiet"): (bool,),
    ("cli_defaults", "crawl", "allow_private_network"): (bool,),
    ("cli_defaults", "convert", "browser_cookies"): (bool,),
    ("cli_defaults", "convert", "no_cookies"): (bool,),
    ("cli_defaults", "convert", "browser"): (str, NoneType),
    ("cli_defaults", "convert", "enhanced_headers"): (bool,),
    ("cli_defaults", "convert", "user_agent_contact"): (str, NoneType),
    ("cli_defaults", "convert", "content_mode"): (str,),
    ("cli_defaults", "convert", "selector"): (str, NoneType),
    ("cli_defaults", "convert", "download_images"): (bool,),
    ("cli_defaults", "convert", "images_dir"): (str,),
    ("cli_defaults", "convert", "metadata"): (bool,),
    ("cli_defaults", "convert", "render_js"): (bool,),
    ("cli_defaults", "convert", "fancy"): (bool,),
    ("cli_defaults", "convert", "local"): (bool,),
    ("cli_defaults", "convert", "allow_private_network"): (bool,),
}

ENUM_VALUES: dict[ConfigPath, frozenset[Any]] = {
    ("logging", "level"): frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}),
    ("browser", "preferred"): frozenset({"chrome", "firefox"}),
    ("cli_defaults", "convert", "browser"): frozenset({"chrome", "firefox", None}),
    ("cli_defaults", "convert", "content_mode"): frozenset(
        {"full", "main", "selector"}
    ),
    ("cli_defaults", "batch", "content_mode"): frozenset({"full", "main", "selector"}),
    ("cli_defaults", "crawl", "content_mode"): frozenset({"full", "main", "selector"}),
}

CLI_OPTION_DESCRIPTIONS = {
    "allow_private_network": "Allow destinations on private or local networks",
    "browser": "Browser used for cookie extraction (chrome/firefox)",
    "browser_cookies": "Load cookies from the selected browser",
    "content_mode": "Content mode (full/main/selector)",
    "delay": "Delay between requests in seconds (with jitter)",
    "download_images": "Download referenced page images",
    "enhanced_headers": "Use an identified crawler user agent",
    "fancy": "Enable interactive progress output",
    "flatten": "Write files directly below each domain directory",
    "flatten_all": "Write all files to one output directory",
    "follow": "Link scope (domain-only/host-only/subdomain/regex)",
    "hierarchical": "Create hierarchical domain directories",
    "images_dir": "Directory name for downloaded images",
    "local": "Treat sources as local files by default",
    "max_depth": "Maximum crawl depth",
    "max_pages": "Maximum page attempts per starting URL",
    "metadata": "Prepend YAML document metadata",
    "no_cookies": "Disable cookie loading by default",
    "polite": "Enable the preset polite crawl delay",
    "quiet": "Reduce output verbosity",
    "rate_limit": "Maximum requests per minute for each destination origin",
    "render_js": "Render JavaScript with optional Chromium",
    "respect_robots": "Honor robots.txt rules and crawl delay",
    "selector": "CSS selector used in selector content mode",
    "show_progress": "Show crawl progress",
    "user_agent_contact": "Crawler contact email or URL",
    "visualize": "Show the planned directory structure",
}


class ConfigValidationError(ValueError):
    """Raised when a known configuration value violates the schema."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("Invalid configuration: " + "; ".join(self.errors))


def _path_name(path: ConfigPath) -> str:
    return ".".join(path)


def _expected_types(path: ConfigPath, default: Any) -> tuple[type, ...]:
    del default
    try:
        return VALUE_TYPES[path]
    except KeyError as error:
        raise RuntimeError(
            f"Configuration schema missing {_path_name(path)}"
        ) from error


def _type_names(types: tuple[type, ...]) -> str:
    return " or ".join(
        "null" if expected is NoneType else expected.__name__ for expected in types
    )


def _coerce_known_value(path: ConfigPath, value: Any, default: Any) -> Any:
    expected = _expected_types(path, default)

    if value is None and NoneType in expected:
        return None
    if bool in expected:
        if type(value) is bool:
            return value
    elif int in expected:
        if type(value) is int:
            return value
        if type(value) is float and math.isfinite(value) and value.is_integer():
            return int(value)
    elif float in expected:
        if type(value) in {int, float} and not isinstance(value, bool):
            converted = float(value)
            if math.isfinite(converted):
                return converted
    elif any(type(value) is candidate for candidate in expected):
        return value

    raise ConfigValidationError(
        [
            f"{_path_name(path)} expected {_type_names(expected)}, "
            f"got {type(value).__name__}"
        ]
    )


def _validate_enum(path: ConfigPath, value: Any) -> Any:
    allowed = ENUM_VALUES.get(path)
    if allowed is not None and value not in allowed:
        choices = ", ".join(
            "null" if item is None else str(item) for item in sorted(allowed, key=str)
        )
        raise ConfigValidationError([f"{_path_name(path)} must be one of: {choices}"])
    return value


def _validate_constraint(path: ConfigPath, value: Any) -> Any:
    try:
        if path == ("cli_defaults", "crawl", "follow"):
            compile_follow_option(value)
        elif path == ("cli_defaults", "crawl", "max_depth"):
            validate_max_depth(value)
        elif path == ("cli_defaults", "crawl", "max_pages"):
            validate_max_pages(value)
        elif path == ("cli_defaults", "crawl", "delay"):
            validate_delay(value)
        elif path == ("cli_defaults", "crawl", "rate_limit"):
            validate_rate_limit(value)
    except ValueError as error:
        raise ConfigValidationError([f"{_path_name(path)}: {error}"]) from error
    return value


def _validate_known_value(path: ConfigPath, value: Any, default: Any) -> Any:
    coerced = _coerce_known_value(path, value, default)
    return _validate_constraint(path, _validate_enum(path, coerced))


def validate_and_merge(
    config_data: Any,
    defaults: Mapping[str, Any],
    *,
    strict: bool,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Merge known defaults and validate their values against the explicit schema."""
    if not isinstance(config_data, dict):
        error = f"configuration root expected dict, got {type(config_data).__name__}"
        if strict:
            raise ConfigValidationError([error])
        return deepcopy(dict(defaults)), (error,)

    merged = deepcopy(dict(defaults))

    def deep_merge(target: dict[str, Any], source: Mapping[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(target.get(key), dict) and isinstance(value, dict):
                deep_merge(target[key], value)
            else:
                target[key] = deepcopy(value)

    deep_merge(merged, config_data)
    errors: list[str] = []

    def validate_tree(
        target: dict[str, Any], default_tree: Mapping[str, Any], path: ConfigPath = ()
    ) -> None:
        for key, default in default_tree.items():
            current_path = (*path, key)
            value = target[key]
            if isinstance(default, dict):
                if not isinstance(value, dict):
                    errors.append(
                        f"{_path_name(current_path)} expected dict, got {type(value).__name__}"
                    )
                    if not strict:
                        target[key] = deepcopy(default)
                    continue
                validate_tree(value, default, current_path)
                continue
            try:
                target[key] = _validate_known_value(current_path, value, default)
            except ConfigValidationError as error:
                errors.extend(error.errors)
                if not strict:
                    target[key] = deepcopy(default)

    validate_tree(merged, defaults)
    if errors and strict:
        raise ConfigValidationError(errors)
    return merged, tuple(errors)


def default_at_path(defaults: Mapping[str, Any], path: ConfigPath) -> Any:
    """Return a defensive copy of one known default value."""
    current: Any = defaults
    for component in path:
        if not isinstance(current, Mapping) or component not in current:
            raise ConfigValidationError(
                [f"unknown configuration path: {_path_name(path)}"]
            )
        current = current[component]
    return deepcopy(current)


def parse_cli_value(
    defaults: Mapping[str, Any], path: ConfigPath, raw_value: str
) -> Any:
    """Parse a CLI string using the same leaf schema used during load and save."""
    default = default_at_path(defaults, path)
    expected = _expected_types(path, default)
    normalized = raw_value.strip()

    if NoneType in expected and normalized.lower() in {"none", "null"}:
        candidate: Any = None
    elif bool in expected:
        boolean_values = {
            "true": True,
            "yes": True,
            "1": True,
            "on": True,
            "false": False,
            "no": False,
            "0": False,
            "off": False,
        }
        try:
            candidate = boolean_values[normalized.lower()]
        except KeyError as error:
            raise ConfigValidationError(
                [f"{_path_name(path)} expected boolean true/false"]
            ) from error
    elif int in expected:
        try:
            candidate = int(normalized)
        except ValueError as error:
            raise ConfigValidationError([f"{_path_name(path)} expected int"]) from error
    elif float in expected:
        try:
            candidate = float(normalized)
        except ValueError as error:
            raise ConfigValidationError(
                [f"{_path_name(path)} expected float"]
            ) from error
    elif str in expected:
        candidate = raw_value
    else:
        raise ConfigValidationError(
            [f"{_path_name(path)} cannot be set from a command-line string"]
        )

    return _validate_known_value(path, candidate, default)


def parse_config_value(
    defaults: Mapping[str, Any], path: ConfigPath, raw_value: str
) -> Any:
    """Parse known leaves through the schema and custom leaves as JSON/string."""
    if path in VALUE_TYPES:
        try:
            decoded = json.loads(raw_value)
        except json.JSONDecodeError:
            decoded = raw_value
        normalized = decoded if isinstance(decoded, str) else raw_value
        return parse_cli_value(defaults, path, normalized)
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def cli_option_rows(
    defaults: Mapping[str, Any],
) -> dict[str, tuple[tuple[str, str, str], ...]]:
    """Derive CLI-option help rows from canonical defaults and schema types."""
    cli_defaults = defaults.get("cli_defaults")
    if not isinstance(cli_defaults, Mapping):
        raise ConfigValidationError(["cli_defaults expected mapping"])

    rows: dict[str, tuple[tuple[str, str, str], ...]] = {}
    for command, options in cli_defaults.items():
        if not isinstance(options, Mapping):
            raise ConfigValidationError([f"cli_defaults.{command} expected mapping"])
        command_rows: list[tuple[str, str, str]] = []
        for option, default in options.items():
            path = ("cli_defaults", str(command), str(option))
            option_type = _type_names(_expected_types(path, default))
            description = CLI_OPTION_DESCRIPTIONS.get(
                str(option), str(option).replace("_", " ").capitalize()
            )
            command_rows.append((str(option), option_type, description))
        rows[str(command)] = tuple(command_rows)
    return rows
