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

    assert 'guest: "Marcin Wyszynski"' in corrected
    assert "SpaceLift" not in corrected
    assert corrected.count("Marcin Wyszynski") == 2
    assert corrected.count("Spacelift") == 1


def test_correct_analysis_leaves_unrelated_names_alone():
    from podscribe.names import NameFix, correct_analysis

    corrected = correct_analysis(
        "SpaceX and SpaceLift ship rockets; SpaceLiftoff is not the brand.", NameFix(brand="Spacelift")
    )

    assert corrected == "SpaceX and Spacelift ship rockets; SpaceLiftoff is not the brand."


def test_correct_analysis_replaces_unknown_guest_and_host_statements():
    from podscribe.names import NameFix, correct_analysis

    fix = NameFix(guest="Marcin Wyszynski", host="Lee Atchison")
    text = "- **Guest:** unknown.\n- **Host:** unknown (not given in the inputs).\n"

    corrected = correct_analysis(text, fix)

    assert corrected == "- **Guest:** Marcin Wyszynski.\n- **Host:** Lee Atchison.\n"


def test_correct_analysis_fixes_a_name_inside_a_direct_quote():
    from podscribe.names import NameFix, correct_analysis

    text = '> "I asked Marcin Grzemski about the provider."\n'

    corrected = correct_analysis(text, NameFix(aliases=(("Grzemski", "Wyszynski"),)))

    assert corrected == '> "I asked Marcin Wyszynski about the provider."\n'


def test_correct_analysis_keeps_a_quoted_transcript_spelling():
    from podscribe.names import NameFix, correct_analysis

    text = '- **Guest:** Marcin Grzemski (the transcript also shows "Dzemski").\n'

    corrected = correct_analysis(text, NameFix(aliases=(("Grzemski", "Wyszynski"), ("Dzemski", "Wyszynski"))))

    assert corrected == '- **Guest:** Marcin Wyszynski (the transcript also shows "Dzemski").\n'


def test_correct_analysis_keeps_the_source_side_of_a_correction():
    from podscribe.names import NameFix, correct_analysis

    text = '- **Fixes:** "Marcin Grzemski" -> "Grzemski".\n'

    corrected = correct_analysis(text, NameFix(aliases=(("Grzemski", "Wyszynski"),)))

    assert corrected == '- **Fixes:** "Marcin Grzemski" -> "Wyszynski".\n'
