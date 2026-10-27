"""Offline tests of the scraper's cleaning rules (no network)."""
from app.scraper import _clean_text, _is_fiction


def test_clean_text_strips_links_and_footers():
    raw = {"value": "A [great](https://x.org) book.\n\n----------\nSource: https://example.com"}
    assert _clean_text(raw) == "A great book."


def test_fiction_detection_ignores_nonfiction_tag():
    assert _is_fiction(["Science fiction", "Robots"])
    assert not _is_fiction(["Nonfiction", "Computer programming"])
    assert not _is_fiction(None)
