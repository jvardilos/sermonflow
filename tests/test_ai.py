"""Tests for ai.py — Claude API formatting layer."""

import os
import sys
import json

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Patch the anthropic import and ANTHROPIC_API_KEY before importing ai
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")

import ai


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------

def test_parse_json_plain():
    raw = '{"slides": [{"text": "Hello", "section_label": "Verse 1"}]}'
    result = ai._parse_json_response(raw)
    assert result["slides"][0]["text"] == "Hello"


def test_parse_json_strips_markdown_fences():
    raw = '```json\n{"slides": [{"text": "Hello"}]}\n```'
    result = ai._parse_json_response(raw)
    assert result["slides"][0]["text"] == "Hello"


def test_parse_json_strips_plain_fences():
    raw = '```\n{"slides": []}\n```'
    result = ai._parse_json_response(raw)
    assert result["slides"] == []


def test_parse_json_strips_leading_whitespace():
    raw = '   \n{"slides": [{"text": "Grace"}]}'
    result = ai._parse_json_response(raw)
    assert result["slides"][0]["text"] == "Grace"


def test_parse_json_raises_on_invalid():
    with pytest.raises(json.JSONDecodeError):
        ai._parse_json_response("not json at all")


# ---------------------------------------------------------------------------
# format_lyric_slides
# ---------------------------------------------------------------------------

def _make_message(json_body: dict):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(json_body))]
    return msg


@patch("ai._get_client")
def test_format_lyric_slides_returns_slides(mock_client_fn):
    client = MagicMock()
    mock_client_fn.return_value = client
    client.messages.create.return_value = _make_message(
        {"slides": [
            {"text": "Amazing grace how sweet the sound", "section_label": "Verse 1 (1/2)"},
            {"text": "That saved a wretch like me",        "section_label": "Verse 1 (2/2)"},
        ]}
    )

    sections = [{"label": "Verse 1", "lyrics": "Amazing grace how sweet the sound\nThat saved a wretch like me"}]
    result = ai.format_lyric_slides("Amazing Grace", sections)

    assert len(result) == 2
    assert result[0]["text"] == "Amazing grace how sweet the sound"
    assert result[0]["section_label"] == "Verse 1 (1/2)"


@patch("ai._get_client")
def test_format_lyric_slides_empty_sections(mock_client_fn):
    result = ai.format_lyric_slides("Amazing Grace", [])
    mock_client_fn.assert_not_called()
    assert result == []


@patch("ai._get_client")
def test_format_lyric_slides_prompt_includes_title(mock_client_fn):
    client = MagicMock()
    mock_client_fn.return_value = client
    client.messages.create.return_value = _make_message({"slides": []})

    ai.format_lyric_slides("Holy Spirit", [{"label": "Verse 1", "lyrics": "Come fill this place"}])

    call_kwargs = client.messages.create.call_args
    user_prompt = call_kwargs.kwargs["messages"][0]["content"]
    assert "Holy Spirit" in user_prompt


# ---------------------------------------------------------------------------
# generate_sermon_slides
# ---------------------------------------------------------------------------

@patch("ai._get_client")
def test_generate_sermon_slides_returns_slides(mock_client_fn):
    client = MagicMock()
    mock_client_fn.return_value = client
    client.messages.create.return_value = _make_message(
        {"slides": [
            {"text": "God's Grace Is Sufficient"},
            {"text": "Justified by Faith"},
        ]}
    )

    result = ai.generate_sermon_slides([
        "God's grace is sufficient for every need",
        "We are justified by faith not by works",
    ])

    assert len(result) == 2
    assert result[0]["text"] == "God's Grace Is Sufficient"


@patch("ai._get_client")
def test_generate_sermon_slides_empty(mock_client_fn):
    result = ai.generate_sermon_slides([])
    mock_client_fn.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# format_schema_slides
# ---------------------------------------------------------------------------

@patch("ai.format_lyric_slides")
def test_format_schema_slides_populates_sections(mock_format):
    mock_format.return_value = [
        {"text": "Amazing grace how sweet", "section_label": "Verse 1 (1/1)"},
        {"text": "My chains are gone",      "section_label": "Chorus (1/1)"},
    ]

    schema = {
        "items": [{
            "item_type": "song",
            "title": "Amazing Grace",
            "song": {
                "sections": [
                    {"label": "Verse 1", "lyrics": "Amazing grace...", "slides": []},
                    {"label": "Chorus",  "lyrics": "My chains...",     "slides": []},
                ]
            }
        }]
    }

    result = ai.format_schema_slides(schema)

    verse_slides  = result["items"][0]["song"]["sections"][0]["slides"]
    chorus_slides = result["items"][0]["song"]["sections"][1]["slides"]
    assert "Amazing grace how sweet" in verse_slides
    assert "My chains are gone" in chorus_slides


@patch("ai.format_lyric_slides")
def test_format_schema_slides_skips_non_songs(mock_format):
    schema = {
        "items": [
            {"item_type": "header", "title": "Welcome", "song": {}},
        ]
    }
    ai.format_schema_slides(schema)
    mock_format.assert_not_called()


@patch("ai.format_lyric_slides")
def test_format_schema_slides_fallback_appends_to_last_section(mock_format):
    # Slide whose label doesn't match any section → goes to last section
    mock_format.return_value = [
        {"text": "Unmatched slide", "section_label": "Unknown (1/1)"},
    ]

    schema = {
        "items": [{
            "item_type": "song",
            "title": "Song",
            "song": {
                "sections": [
                    {"label": "Verse 1", "lyrics": "...", "slides": []},
                    {"label": "Chorus",  "lyrics": "...", "slides": []},
                ]
            }
        }]
    }

    ai.format_schema_slides(schema)

    last_section = schema["items"][0]["song"]["sections"][-1]
    assert "Unmatched slide" in last_section["slides"]
