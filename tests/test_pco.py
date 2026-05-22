"""Tests for pco.py — Planning Center API client."""

import os
import sys

# Set dummy credentials before importing pco (module-level env-var check)
os.environ.setdefault("PCO_ID", "test_id")
os.environ.setdefault("PCO_SECRET", "test_secret")

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pco

# ---------------------------------------------------------------------------
# _infer_section_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,expected",
    [
        ("Verse 1", "verse"),
        ("VERSE 2", "verse"),
        ("Chorus", "chorus"),
        ("CHORUS", "chorus"),
        ("Bridge", "bridge"),
        ("Pre-Chorus", "pre_chorus"),
        ("Intro", "intro"),
        ("Outro", "outro"),
        ("Tag", "tag"),
        ("Interlude", "other"),
        ("", "other"),
    ],
)
def test_infer_section_type(label, expected):
    assert pco._infer_section_type(label) == expected


# ---------------------------------------------------------------------------
# extract_songs
# ---------------------------------------------------------------------------


def _make_item(item_type: str, title: str = "X") -> dict:
    return {"attributes": {"item_type": item_type, "title": title}}


def test_extract_songs_returns_only_songs():
    items = [
        _make_item("song", "Amazing Grace"),
        _make_item("header", "Welcome"),
        _make_item("song", "Holy Spirit"),
        _make_item("item", "Offering"),
    ]
    result = pco.extract_songs(items)
    assert len(result) == 2
    assert all(i["attributes"]["item_type"] == "song" for i in result)


def test_extract_songs_empty():
    assert pco.extract_songs([]) == []


def test_extract_songs_no_songs():
    items = [_make_item("header"), _make_item("item")]
    assert pco.extract_songs(items) == []


# ---------------------------------------------------------------------------
# _get (HTTP helper)
# ---------------------------------------------------------------------------


@patch("pco.requests.get")
def test_get_bare_path(mock_get):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"data": []}
    mock_get.return_value = mock_resp

    pco._get("/services/v2/service_types")

    mock_get.assert_called_once_with(
        "https://api.planningcenteronline.com/services/v2/service_types",
        auth=pco.AUTH,
        params=None,
    )


@patch("pco.requests.get")
def test_get_full_url(mock_get):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"data": []}
    mock_get.return_value = mock_resp

    pco._get("https://other.example.com/page2")

    mock_get.assert_called_once_with(
        "https://other.example.com/page2",
        auth=pco.AUTH,
        params=None,
    )


@patch("pco.requests.get")
def test_get_raises_on_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.text = "Unauthorized"
    mock_resp.raise_for_status.side_effect = Exception("401")
    mock_get.return_value = mock_resp

    with pytest.raises(Exception):
        pco._get("/services/v2/service_types")


# ---------------------------------------------------------------------------
# _get_all (pagination)
# ---------------------------------------------------------------------------


@patch("pco._get")
def test_get_all_single_page(mock_get):
    mock_get.return_value = {
        "data": [{"id": "1"}, {"id": "2"}],
        "links": {},
    }
    result = pco._get_all("/some/path")
    assert result == [{"id": "1"}, {"id": "2"}]
    mock_get.assert_called_once_with("/some/path", {"per_page": 100})


@patch("pco._get")
def test_get_all_multiple_pages(mock_get):
    page1 = {
        "data": [{"id": "1"}],
        "links": {"next": "https://api.pco.app/page2"},
    }
    page2 = {
        "data": [{"id": "2"}, {"id": "3"}],
        "links": {},
    }
    mock_get.side_effect = [page1, page2]

    result = pco._get_all("/some/path")

    assert result == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    assert mock_get.call_count == 2
    # Second call must use the next URL with no extra params
    mock_get.assert_called_with("https://api.pco.app/page2", {})


@patch("pco._get")
def test_get_all_respects_existing_per_page(mock_get):
    mock_get.return_value = {"data": [], "links": {}}
    pco._get_all("/path", {"per_page": 25, "filter": "future"})
    mock_get.assert_called_once_with("/path", {"per_page": 25, "filter": "future"})


# ---------------------------------------------------------------------------
# _get_all_with_included
# ---------------------------------------------------------------------------


@patch("pco._get")
def test_get_all_with_included_builds_index(mock_get):
    mock_get.return_value = {
        "data": [{"id": "item-1", "type": "Item"}],
        "included": [
            {"type": "Song", "id": "song-1", "attributes": {}},
            {"type": "Arrangement", "id": "arr-1", "attributes": {}},
        ],
        "links": {},
    }
    data, included = pco._get_all_with_included("/items")

    assert len(data) == 1
    assert ("Song", "song-1") in included
    assert ("Arrangement", "arr-1") in included


@patch("pco._get")
def test_get_all_with_included_merges_pages(mock_get):
    mock_get.side_effect = [
        {
            "data": [{"id": "1", "type": "Item"}],
            "included": [{"type": "Song", "id": "s1", "attributes": {}}],
            "links": {"next": "https://pco/page2"},
        },
        {
            "data": [{"id": "2", "type": "Item"}],
            "included": [{"type": "Song", "id": "s2", "attributes": {}}],
            "links": {},
        },
    ]
    data, included = pco._get_all_with_included("/items")

    assert len(data) == 2
    assert ("Song", "s1") in included
    assert ("Song", "s2") in included


# ---------------------------------------------------------------------------
# find_service_type
# ---------------------------------------------------------------------------


@patch("pco.get_service_types")
def test_find_service_type_match(mock_get_st):
    mock_get_st.return_value = [
        {"id": "1", "attributes": {"name": "Sunday Morning"}},
        {"id": "2", "attributes": {"name": "Wednesday Night"}},
    ]
    result = pco.find_service_type("sunday")
    assert result["id"] == "1"


@patch("pco.get_service_types")
def test_find_service_type_case_insensitive(mock_get_st):
    mock_get_st.return_value = [
        {"id": "1", "attributes": {"name": "Sunday Morning"}},
    ]
    assert pco.find_service_type("SUNDAY") is not None
    assert pco.find_service_type("morning") is not None


@patch("pco.get_service_types")
def test_find_service_type_no_match(mock_get_st):
    mock_get_st.return_value = [
        {"id": "1", "attributes": {"name": "Sunday Morning"}},
    ]
    assert pco.find_service_type("friday") is None


@patch("pco.get_service_types")
def test_find_service_type_empty(mock_get_st):
    mock_get_st.return_value = []
    assert pco.find_service_type("sunday") is None


# ---------------------------------------------------------------------------
# get_next_sunday_plan
# ---------------------------------------------------------------------------


def _plan(sort_date: str) -> dict:
    return {"id": sort_date, "attributes": {"sort_date": sort_date + "T00:00:00Z"}}


@patch("pco.get_future_plans")
@patch("pco.date")
def test_get_next_sunday_plan_finds_next_sunday(mock_date, mock_plans):
    # Pin today to Monday 2026-05-18; next Sunday = 2026-05-24
    mock_date.today.return_value = date(2026, 5, 18)
    mock_date.fromisoformat = date.fromisoformat
    mock_plans.return_value = [
        _plan("2026-05-24"),
        _plan("2026-05-31"),
    ]

    result = pco.get_next_sunday_plan("st-1")

    assert result["id"] == "2026-05-24"


@patch("pco.get_future_plans")
@patch("pco.date")
def test_get_next_sunday_plan_skips_past_sunday(mock_date, mock_plans):
    # Pin today to Monday; plans only have a past date → fallback to plans[0]
    mock_date.today.return_value = date(2026, 5, 18)
    mock_date.fromisoformat = date.fromisoformat
    mock_plans.return_value = [_plan("2026-05-10")]

    result = pco.get_next_sunday_plan("st-1")

    assert result["id"] == "2026-05-10"  # fallback


@patch("pco.get_future_plans")
def test_get_next_sunday_plan_no_plans(mock_plans):
    mock_plans.return_value = []
    assert pco.get_next_sunday_plan("st-1") is None


@patch("pco.get_future_plans")
@patch("pco.date")
def test_get_next_sunday_plan_on_sunday(mock_date, mock_plans):
    # Today IS Sunday — the function should return NEXT Sunday, not today
    mock_date.today.return_value = date(2026, 5, 24)  # a Sunday
    mock_date.fromisoformat = date.fromisoformat
    mock_date.side_effect = None
    # days_until_sunday = (6 - 6) % 7 or 7 = 0 or 7 = 7 → next Sunday = 2026-05-31
    mock_plans.return_value = [
        _plan("2026-05-24"),  # today — should be skipped
        _plan("2026-05-31"),  # next Sunday — should be returned
    ]

    result = pco.get_next_sunday_plan("st-1")

    assert result["id"] == "2026-05-31"
