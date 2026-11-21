"""Tests for canonical names applied to an analyzer's Markdown."""



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


def test_derive_names_reads_guest_and_brand_from_the_episode_title():
    from podscribe.names import derive_names

    names = derive_names(TITLE, "Lee Atchison")

    assert names.guest == "Marcin Wyszynski"
    assert names.brand == "Spacelift"
    assert names.host == "Lee Atchison"


def test_derive_names_needs_a_with_phrase_to_find_a_guest():
    from podscribe.names import derive_names

    names = derive_names("An Episode Without Guests", "The Publisher")

    assert names.guest == ""
    assert names.brand == ""
    assert names.host == "The Publisher"


def test_derive_names_takes_configured_overrides_and_aliases():
    from podscribe.names import derive_names

    names = derive_names(
        TITLE,
        "Lee Atchison",
        {"guest": "Real Guest", "host": "Real Host", "aliases": {"Grzemski": "Wyszynski"}},
    )

    assert names.guest == "Real Guest"
    assert names.host == "Real Host"
    assert dict(names.aliases) == {"Grzemski": "Wyszynski"}


def test_correct_analysis_replaces_aliases_and_brand_casings():
    from podscribe.names import NameFix, correct_analysis

    fix = NameFix(brand="Spacelift", aliases=(("Grzemski", "Wyszynski"), ("Dzemski", "Wyszynski")))

    corrected = correct_analysis(ANALYSIS, fix)

    assert "Grzemski" not in corrected
    assert "Dzemski" not in corrected
    assert "SpaceLift" not in corrected
    assert corrected.count("Marcin Wyszynski") == 2
    assert corrected.count("Spacelift") == 1


def test_correct_analysis_leaves_unrelated_names_alone():
    from podscribe.names import NameFix, correct_analysis

    corrected = correct_analysis(
        "SpaceX and SpaceLift ship rockets; SpaceLiftoff is not the brand.", NameFix(brand="Spacelift")
    )

    assert corrected == "SpaceX and Spacelift ship rockets; SpaceLiftoff is not the brand."
