"""Depth spec parsing and synthetic context prompts.

Offline by construction: the tokenizer is injected, never fetched.
Requirements: PERF-11 (the --depths spec), PERF-12 (prompt at a target depth).
"""

import re

import pytest

from homebench.metrics.depth import build_context_prompt, parse_depths


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


# =====================================================================
# build_context_prompt (PERF-12)
# =====================================================================
#: the filler unit whose tokenization was measured against the live router:
#: one repetition is 11 tokens, one hundred are 1001 -- 10 per unit plus a
#: single BOS token. ``_realistic`` reproduces exactly that.
FILLER = "The quick brown fox jumps over the lazy dog. "

PROMPT = "Write three detailed paragraphs about how a CPU runs a program."


def _realistic(text: str) -> int:
    """Word-and-punctuation tokenizer with a one-token BOS offset."""
    return 1 + len(re.findall(r"\w+|[^\w\s]", text))


def _coarse(text: str) -> int:
    """A tokenizer whose grain (7 tokens a word) cannot land on every target."""
    return 1 + 7 * len(text.split())


def test_build_context_prompt_hits_the_target_exactly_with_a_tokenizer():
    for target in (8192, 32768):
        text, count = build_context_prompt(target, _realistic, base_prompt=PROMPT)
        assert count == target, f"target {target} produced {count}"
        assert _realistic(text) == target


def test_build_context_prompt_accounts_for_the_bos_offset():
    # the calibration measured live; a model of "11 tokens per unit" would
    # land ~9% short of the target
    assert _realistic(FILLER) == 11
    assert _realistic(FILLER * 100) == 1001

    text, count = build_context_prompt(1001, _realistic, base_prompt=PROMPT)
    assert count == 1001
    assert _realistic(text) == 1001


def test_build_context_prompt_without_a_tokenizer_reports_no_count():
    text, count = build_context_prompt(8192, None, base_prompt=PROMPT)
    assert count is None                      # never a disguised guess
    assert PROMPT in text                     # the instruction survives
    assert len(text.split()) > 1000           # filler was actually synthesised


def test_build_context_prompt_at_depth_zero_returns_the_speed_prompt():
    seen = []

    def tok(text):
        seen.append(text)
        return _realistic(text)

    text, count = build_context_prompt(0, tok, base_prompt=PROMPT)
    assert text == PROMPT                     # the short speed prompt, verbatim
    assert "quick brown fox" not in text      # no filler at depth 0
    assert count is None
    assert seen == []                         # nothing to measure, nothing called


def test_build_context_prompt_counts_only_through_the_injected_tokenizer():
    seen = []

    def tok(text):
        seen.append(text)
        return _realistic(text)

    text, count = build_context_prompt(4096, tok, base_prompt=PROMPT)
    assert count == _realistic(text)          # the count describes the text returned
    assert text in seen                       # it was measured, not extrapolated


def test_build_context_prompt_stays_within_ten_percent_of_a_coarse_target():
    text, count = build_context_prompt(8192, _coarse, base_prompt=PROMPT)
    assert count == _coarse(text)
    assert abs(count - 8192) <= 0.10 * 8192
