"""Tests for gdocs.py — Google Docs highlight extractor (pure functions only)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# gdocs imports Google API packages at module level; mock them before import
from unittest.mock import MagicMock, patch
import unittest.mock as mock

# Patch all Google imports so gdocs.py can be imported without credentials
with mock.patch.dict(
    "sys.modules",
    {
        "google": MagicMock(),
        "google.oauth2": MagicMock(),
        "google.oauth2.credentials": MagicMock(),
        "google_auth_oauthlib": MagicMock(),
        "google_auth_oauthlib.flow": MagicMock(),
        "google.auth": MagicMock(),
        "google.auth.transport": MagicMock(),
        "google.auth.transport.requests": MagicMock(),
        "googleapiclient": MagicMock(),
        "googleapiclient.discovery": MagicMock(),
    },
):
    import gdocs


# ---------------------------------------------------------------------------
# _is_yellow
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rgb,expected",
    [
        # Pure yellow (Google Docs default)
        ({"red": 1.0, "green": 1.0, "blue": 0.0}, True),
        # High R+G, low B — still yellow
        ({"red": 0.9, "green": 0.8, "blue": 0.1}, True),
        # Borderline cases
        ({"red": 0.8, "green": 0.7, "blue": 0.35}, True),
        # Blue too high
        ({"red": 1.0, "green": 1.0, "blue": 0.5}, False),
        # Red too low
        ({"red": 0.7, "green": 1.0, "blue": 0.0}, False),
        # Green too low
        ({"red": 1.0, "green": 0.6, "blue": 0.0}, False),
        # White
        ({"red": 1.0, "green": 1.0, "blue": 1.0}, False),
        # Black
        ({"red": 0.0, "green": 0.0, "blue": 0.0}, False),
        # Empty dict (no color set)
        ({}, False),
    ],
)
def test_is_yellow(rgb, expected):
    assert gdocs._is_yellow(rgb) == expected


# ---------------------------------------------------------------------------
# extract_highlights — helpers
# ---------------------------------------------------------------------------


def _text_run(text: str, yellow: bool = False) -> dict:
    """Build a minimal textRun element."""
    style = {}
    if yellow:
        style["backgroundColor"] = {
            "color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}
        }
    return {"textRun": {"content": text, "textStyle": style}}


def _paragraph(*elements) -> dict:
    return {"paragraph": {"elements": list(elements)}}


def _doc(*blocks) -> dict:
    return {"body": {"content": list(blocks)}}


# ---------------------------------------------------------------------------
# extract_highlights — tests
# ---------------------------------------------------------------------------


def test_extract_highlights_single_highlight():
    doc = _doc(_paragraph(_text_run("God is good", yellow=True)))
    assert gdocs.extract_highlights(doc) == ["God is good"]


def test_extract_highlights_ignores_normal_text():
    doc = _doc(
        _paragraph(
            _text_run("This is normal. "),
            _text_run("Yellow highlight!", yellow=True),
            _text_run(" More normal."),
        )
    )
    assert gdocs.extract_highlights(doc) == ["Yellow highlight!"]


def test_extract_highlights_merges_adjacent_runs():
    # Two consecutive yellow runs in the same paragraph → merged into one
    doc = _doc(
        _paragraph(
            _text_run("God is ", yellow=True),
            _text_run("so good", yellow=True),
        )
    )
    result = gdocs.extract_highlights(doc)
    assert len(result) == 1
    assert result[0] == "God is so good"


def test_extract_highlights_separates_different_paragraphs():
    doc = _doc(
        _paragraph(_text_run("First highlight", yellow=True)),
        _paragraph(_text_run("Second highlight", yellow=True)),
    )
    result = gdocs.extract_highlights(doc)
    assert result == ["First highlight", "Second highlight"]


def test_extract_highlights_non_yellow_breaks_run():
    # Yellow, then normal, then yellow → two separate highlights
    doc = _doc(
        _paragraph(
            _text_run("First ", yellow=True),
            _text_run("break "),
            _text_run("second", yellow=True),
        )
    )
    result = gdocs.extract_highlights(doc)
    assert result == ["First", "second"]


def test_extract_highlights_strips_whitespace():
    doc = _doc(_paragraph(_text_run("  trimmed  ", yellow=True)))
    assert gdocs.extract_highlights(doc) == ["trimmed"]


def test_extract_highlights_skips_blank_runs():
    doc = _doc(_paragraph(_text_run("   ", yellow=True)))
    assert gdocs.extract_highlights(doc) == []


def test_extract_highlights_empty_doc():
    assert gdocs.extract_highlights({"body": {"content": []}}) == []


def test_extract_highlights_no_body():
    assert gdocs.extract_highlights({}) == []


def test_extract_highlights_non_paragraph_block_flushes():
    # A non-paragraph block (e.g. a table) should flush the current run
    doc = {
        "body": {
            "content": [
                _paragraph(_text_run("Before", yellow=True)),
                {"sectionBreak": {}},  # not a paragraph
                _paragraph(_text_run("After", yellow=True)),
            ]
        }
    }
    result = gdocs.extract_highlights(doc)
    assert result == ["Before", "After"]


def test_extract_highlights_multiple_songs():
    doc = _doc(
        _paragraph(
            _text_run("We are justified by faith"),
            _text_run("Key point one", yellow=True),
            _text_run(" more text "),
        ),
        _paragraph(
            _text_run("Key point two", yellow=True),
        ),
    )
    result = gdocs.extract_highlights(doc)
    assert result == ["Key point one", "Key point two"]
