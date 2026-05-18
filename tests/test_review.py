"""Tests for review.py — PDF generation and approval gate."""

import os
import sys

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import review


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_schema():
    return {
        "service": {
            "plan_title": "Sunday Morning",
            "plan_date": "2026-05-24T00:00:00Z",
        },
        "items": [],
    }


@pytest.fixture
def song_schema():
    return {
        "service": {
            "plan_title": "Sunday Morning",
            "plan_date": "2026-05-24T00:00:00Z",
        },
        "items": [
            {
                "sequence": 1,
                "item_type": "song",
                "title": "Amazing Grace",
                "song": {
                    "sections": [
                        {
                            "label": "Verse 1",
                            "slides": [
                                "Amazing grace how sweet the sound",
                                "That saved a wretch like me",
                            ],
                        },
                        {
                            "label": "Chorus",
                            "slides": ["My chains are gone"],
                        },
                    ]
                },
            },
            {
                "sequence": 2,
                "item_type": "header",
                "title": "Sermon",
                "slides_to_generate": ["God is faithful", "Trust in Him"],
            },
        ],
    }


# ---------------------------------------------------------------------------
# generate_pdf
# ---------------------------------------------------------------------------

def test_generate_pdf_creates_file(tmp_path, minimal_schema):
    out = str(tmp_path / "test.pdf")
    result = review.generate_pdf(minimal_schema, out)
    assert result == out
    assert os.path.exists(out)
    assert os.path.getsize(out) > 0


def test_generate_pdf_title_page_and_slides(tmp_path, song_schema):
    out = str(tmp_path / "slides.pdf")
    review.generate_pdf(song_schema, out)
    assert os.path.exists(out)
    assert os.path.getsize(out) > 100


def test_generate_pdf_returns_path(tmp_path, minimal_schema):
    out = str(tmp_path / "out.pdf")
    assert review.generate_pdf(minimal_schema, out) == out


def test_generate_pdf_empty_items(tmp_path):
    schema = {
        "service": {"plan_title": "Test", "plan_date": "2026-05-24"},
        "items": [],
    }
    out = str(tmp_path / "empty.pdf")
    review.generate_pdf(schema, out)
    assert os.path.exists(out)


def test_generate_pdf_song_without_slides(tmp_path):
    schema = {
        "service": {"plan_title": "Test", "plan_date": "2026-05-24"},
        "items": [{
            "sequence": 1,
            "item_type": "song",
            "title": "Song",
            "song": {"sections": [{"label": "V1", "slides": []}]},
        }],
    }
    out = str(tmp_path / "no_slides.pdf")
    review.generate_pdf(schema, out)
    assert os.path.exists(out)


# ---------------------------------------------------------------------------
# wait_for_approval
# ---------------------------------------------------------------------------

def test_wait_for_approval_approved(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "_APPROVED_FLAG", tmp_path / "APPROVED")
    monkeypatch.setattr(review, "_REJECTED_FLAG", tmp_path / "REJECTED")

    call_count = 0

    def fake_sleep(_):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            (tmp_path / "APPROVED").touch()

    with patch("review.time.sleep", side_effect=fake_sleep):
        result = review.wait_for_approval(timeout_secs=60, poll_secs=0.01)

    assert result is True
    assert not (tmp_path / "APPROVED").exists()  # flag cleaned up


def test_wait_for_approval_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "_APPROVED_FLAG", tmp_path / "APPROVED")
    monkeypatch.setattr(review, "_REJECTED_FLAG", tmp_path / "REJECTED")

    call_count = 0

    def fake_sleep(_):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            (tmp_path / "REJECTED").touch()

    with patch("review.time.sleep", side_effect=fake_sleep):
        result = review.wait_for_approval(timeout_secs=60, poll_secs=0.01)

    assert result is False
    assert not (tmp_path / "REJECTED").exists()


def test_wait_for_approval_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "_APPROVED_FLAG", tmp_path / "APPROVED")
    monkeypatch.setattr(review, "_REJECTED_FLAG", tmp_path / "REJECTED")

    # poll_secs > timeout_secs → one iteration, then elapsed >= timeout
    with patch("review.time.sleep", side_effect=lambda s: None):
        result = review.wait_for_approval(timeout_secs=1, poll_secs=10)

    assert result is False


def test_wait_for_approval_clears_stale_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "_APPROVED_FLAG", tmp_path / "APPROVED")
    monkeypatch.setattr(review, "_REJECTED_FLAG", tmp_path / "REJECTED")

    # Stale flags left from a previous run
    (tmp_path / "APPROVED").touch()
    (tmp_path / "REJECTED").touch()

    call_count = 0

    def fake_sleep(_):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            (tmp_path / "APPROVED").touch()

    with patch("review.time.sleep", side_effect=fake_sleep):
        result = review.wait_for_approval(timeout_secs=60, poll_secs=0.01)

    # Stale flags cleared at start; fresh APPROVED eventually found
    assert result is True
