"""Shared validation for crawl scope and numeric budgets."""

from __future__ import annotations

import math
import re
from typing import Pattern

BUILTIN_FOLLOW_OPTIONS = frozenset({"domain-only", "host-only", "subdomain"})
FollowRule = str | Pattern[str]


def compile_follow_option(follow_option: str) -> FollowRule:
    """Return a built-in scope name or one compiled user regular expression."""
    if follow_option in BUILTIN_FOLLOW_OPTIONS:
        return follow_option
    try:
        return re.compile(follow_option)
    except re.error as error:
        raise ValueError(
            f"Invalid --follow regex pattern: {follow_option!r}"
        ) from error


def validate_max_depth(max_depth: int) -> None:
    if max_depth < 0:
        raise ValueError("--max-depth must be non-negative")


def validate_max_pages(max_pages: int) -> None:
    if max_pages <= 0:
        raise ValueError("--max-pages must be positive")


def validate_delay(delay: float) -> None:
    if not math.isfinite(delay) or delay < 0:
        raise ValueError("--delay must be a finite non-negative number")


def validate_rate_limit(rate_limit: int | None) -> None:
    if rate_limit is not None and rate_limit <= 0:
        raise ValueError("--rate-limit must be positive")


def validate_crawl_policy(
    *,
    follow_option: str,
    max_depth: int,
    max_pages: int,
    delay: float,
    rate_limit: int | None,
) -> FollowRule:
    """Validate all public crawl policy values before any crawl side effects."""
    rule = compile_follow_option(follow_option)
    validate_max_depth(max_depth)
    validate_max_pages(max_pages)
    validate_delay(delay)
    validate_rate_limit(rate_limit)
    return rule
