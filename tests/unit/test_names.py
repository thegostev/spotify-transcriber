"""Tests for canonical names applied to an analyzer's Markdown."""

import pytest

TITLE = "Navigating Cloud Infrastructure using AI with Marcin Wyszynski, Spacelift"
ANALYSIS = """---
title: "Cloud Infrastructure"
guest: "Marcin Grzemski"
host: "unknown"
topics: ["terraform"]
---

## Who is talking

- **Guest:** Marcin Grzemski, cofounder of SpaceLift.
- **Host:** unknown.
"""


@pytest.mark.xfail(strict=True, reason="LAG-1071")
def test_derive_names_reads_guest_and_brand_from_the_episode_title():
    from podscribe.names import derive_names

    names = derive_names(TITLE, "Lee Atchison")

    assert names.guest == "Marcin Wyszynski"
    assert names.brand == "Spacelift"
    assert names.host == "Lee Atchison"


@pytest.mark.xfail(strict=True, reason="LAG-1071")
def test_derive_names_needs_a_with_phrase_to_find_a_guest():
    from podscribe.names import derive_names

    names = derive_names("An Episode Without Guests", "The Publisher")

    assert names.guest == ""
    assert names.brand == ""
    assert names.host == "The Publisher"


@pytest.mark.xfail(strict=True, reason="LAG-1071")
def test_derive_names_takes_configured_overrides_and_aliases():
    from podscribe.names import derive_names

    names = derive_names(
        TITLE,
        "Lee Atchison",
        {
            "guest": "Marcin Wyszynski",
            "host": "Lee Atchison",
            "aliases": {"Grzemski": "Wyszynski", "Dzemski": "Wyszynski"},
        },
    )

    assert names.guest == "Marcin Wyszynski"
    assert names.host == "Lee Atchison"
    assert dict(names.aliases) == {"Grzemski": "Wyszynski", "Dzemski": "Wyszynski"}
