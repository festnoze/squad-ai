"""What actually gets read aloud out of a full answer.

This is the most audible logic in the bridge: everything else only decides how
the sentence is spoken, this decides which sentence. The contract is the one in
`pick_spoken_part`: an explicit <voix> block wins, otherwise the closing
paragraph, otherwise a cut on a sentence boundary.

Run with:  uvx --with pytest --python 3.14 pytest tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import speak  # noqa: E402

MAX = 260


def spoken(text: str, max_chars: int = MAX) -> str:
    return speak.pick_spoken_part(text, max_chars)


# --------------------------------------------------------------------------
# The <voix> block wins
# --------------------------------------------------------------------------


def test_the_voice_block_wins_over_everything_else() -> None:
    answer = """# Rapport

Trois fichiers changes, dix-huit tests passent.

<voix>Les tests passent.</voix>"""
    assert spoken(answer) == "Les tests passent."


def test_the_voice_block_is_found_anywhere_and_in_any_case() -> None:
    assert spoken("<VOIX>En majuscules.</VOIX>\n\nSuite.") == "En majuscules."
    assert spoken("Avant. <voix>Au milieu.</voix> Apres.") == "Au milieu."


def test_a_voice_block_spanning_several_lines_is_joined_as_written() -> None:
    assert spoken("<voix>Premiere phrase.\nSeconde phrase.</voix>") == (
        "Premiere phrase.\nSeconde phrase."
    )


def test_the_voice_block_is_cleaned_of_markdown() -> None:
    assert spoken("<voix>Les **tests** passent, voir `speak.py`.</voix>") == (
        "Les tests passent, voir speak.py."
    )


def test_a_long_voice_block_is_not_truncated() -> None:
    """The model was asked for one sentence; if it writes more, read it.

    Truncating here would cut the model off mid-word, and the caller already
    splits long text into chunks for the daemon.
    """
    line = "Une phrase de reference qui revient plusieurs fois. " * 8
    assert spoken(f"<voix>{line}</voix>") == line.strip()


def test_an_empty_voice_block_falls_back_to_the_body() -> None:
    """An empty tag must not silence the answer entirely."""
    assert spoken("<voix></voix>\n\nLe rapport tient en une ligne.") == (
        "Le rapport tient en une ligne."
    )


# --------------------------------------------------------------------------
# No <voix> block: the conclusion, at the end
# --------------------------------------------------------------------------


def test_a_short_answer_is_read_whole() -> None:
    assert spoken("Trois fichiers changes.") == "Trois fichiers changes."


def test_nothing_to_say_returns_nothing() -> None:
    assert spoken("") == ""
    assert spoken("   \n\n  ") == ""
    assert spoken("```\ncode only\n```") == "(bloc de code)"


def test_a_long_answer_is_read_from_its_closing_paragraph() -> None:
    opening = "Voici ce que j'ai trouve en parcourant le depot. " * 6
    closing = "Conclusion: les dix-huit tests passent et rien n'est commite."
    assert spoken(f"{opening}\n\n{closing}") == closing


def test_the_closing_paragraph_is_skipped_when_it_is_a_scrap() -> None:
    """A one-word last line is not the conclusion; keep looking backwards."""
    opening = "Voici ce que j'ai trouve en parcourant le depot. " * 6
    closing = "Conclusion: les dix-huit tests passent et rien n'est commite."
    assert spoken(f"{opening}\n\n{closing}\n\nVoila.") == closing


def test_a_long_answer_of_short_lines_is_read_from_the_end() -> None:
    """The conclusion lives at the end even when no paragraph is substantial.

    Without this, an answer made only of short bullet lines was truncated from
    the top, so the opening was read out instead of the outcome.
    """
    lines = "\n\n".join(f"Point numero {n}." for n in range(1, 40))
    result = spoken(lines)
    assert len(result) <= MAX
    assert result.endswith("Point numero 39.")
    assert "Point numero 1." not in result


def test_a_cut_lands_on_a_sentence_boundary() -> None:
    para = "Cette phrase fait partie d'un paragraphe unique et tres long. " * 8
    result = spoken(para)
    assert len(result) <= MAX
    assert result.endswith("."), "the cut fell mid-sentence"


def test_a_cut_with_no_boundary_to_find_says_so() -> None:
    """A wall of text with no full stop is marked as unfinished, not faked."""
    result = spoken("mot " * 200)
    assert len(result) <= MAX + 3
    assert result.endswith("...")


@pytest.mark.parametrize("length", [MAX - 1, MAX, MAX + 1])
def test_the_limit_is_respected_around_its_boundary(length: int) -> None:
    text = "a" * length
    result = spoken(text)
    assert len(result) <= MAX + 3, "over the limit, cut marker included"


# --------------------------------------------------------------------------
# Markdown that would be unpleasant to hear
# --------------------------------------------------------------------------


def test_markdown_furniture_is_dropped() -> None:
    assert speak.clean_markdown("## Titre") == "Titre"
    assert speak.clean_markdown("- premier point") == "premier point"
    assert speak.clean_markdown("1. premier point") == "premier point"
    assert speak.clean_markdown("**gras** et _italique_") == "gras et italique"


def test_a_link_keeps_its_words_and_loses_its_target() -> None:
    assert speak.clean_markdown("voir [le fichier](voice_bridge/speak.py)") == (
        "voir le fichier"
    )


def test_a_code_block_is_announced_rather_than_spelled_out() -> None:
    cleaned = speak.clean_markdown("Lance ceci:\n```\npytest -q\n```\nvoila.")
    assert "pytest" not in cleaned
    assert "bloc de code" in cleaned


def test_a_path_becomes_a_spoken_phrase() -> None:
    cleaned = speak.clean_markdown("edite C:\\Dev\\squad-ai\\voice_bridge\\speak.py")
    assert "Dev" not in cleaned
    assert "ce fichier" in cleaned


def test_blank_lines_are_collapsed_but_paragraphs_survive() -> None:
    assert speak.clean_markdown("un\n\n\n\n\ndeux") == "un\n\ndeux"


def test_cleaning_a_bulleted_answer_keeps_its_paragraphs_apart() -> None:
    """Regression: the bullet pattern used to eat the blank line before it.

    With the paragraphs merged into one block, picking the closing paragraph
    could never work on a bulleted answer, which is most of them.
    """
    cleaned = speak.clean_markdown("- premier point\n\n- second point")
    assert cleaned == "premier point\n\nsecond point"
    assert len(cleaned.split("\n\n")) == 2


def test_cleaning_a_heading_keeps_the_paragraph_break() -> None:
    assert speak.clean_markdown("Fin du texte.\n\n## Titre") == "Fin du texte.\n\nTitre"


def test_a_bulleted_answer_is_read_from_its_last_substantial_point() -> None:
    points = "\n\n".join(
        f"- Point numero {n} du rapport, avec assez de mots pour compter."
        for n in range(1, 12)
    )
    assert spoken(points) == "Point numero 11 du rapport, avec assez de mots pour compter."
