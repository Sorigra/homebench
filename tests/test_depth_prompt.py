"""Depth spec parsing and synthetic context prompts.

Offline by construction: the tokenizer is injected, never fetched.
Requirements: PERF-11 (the --depths spec), PERF-12 (prompt at a target depth).
"""

import pytest

from homebench.metrics.depth import parse_depths


# =====================================================================
# parse_depths (PERF-11)
# =====================================================================
def test_parse_depths_reads_the_default_spec():
    assert parse_depths("0,8192,32768") == [0, 8192, 32768]


def test_parse_depths_preserves_the_given_order():
    # deliberately unlike parse_levels, which sorts
    assert parse_depths("32768,0,8192") == [32768, 0, 8192]


def test_parse_depths_does_not_deduplicate():
    # two depths may resolve to the same prompt; both are still measured
    assert parse_depths("8192,8192") == [8192, 8192]


def test_parse_depths_empty_spec_means_depth_zero():
    assert parse_depths("") == [0]
    assert parse_depths(",") == [0]
    assert parse_depths("   ") == [0]


def test_parse_depths_rejects_a_non_integer_value():
    with pytest.raises(ValueError) as exc:
        parse_depths("0,abc,8192")
    assert "abc" in str(exc.value)


def test_parse_depths_rejects_a_negative_value():
    with pytest.raises(ValueError) as exc:
        parse_depths("0,-1")
    assert "-1" in str(exc.value)
