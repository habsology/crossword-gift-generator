import json
import crossword


def _order(clue, n=14):
    words = ["Lisbon", "Biscuit", "October", "Priya", "Tiramisu", "Pancakes", "Tofino", "Kayak",
             "Scrabble", "Leo", "Elm", "Main", "Sam", "Bike", "Honeymoon", "Sundays", "Apartment"][:n]
    return {"title": "Test", "subtitle": "", "word_search": True, "seed": 0,
            "entries": [{"word": w, "clue": clue} for w in words]}


def test_wrap_keeps_length_tag_with_last_word():
    crossword._register_fonts()
    lines = crossword._wrap("Where Sam popped the question, sparking joy (6)", crossword.FONTS["body"], 11.5, 150)
    assert all(not line.startswith("(") for line in lines)
    assert lines[-1].endswith("joy (6)")


def test_clues_share_page_one_with_grid(tmp_path):
    """Short, long and many clues all stay on page 1 (puzzle, word search, key, keepsake = 4 pages)."""
    from pypdf import PdfReader
    long_clue = ("The little seaside town on the west coast of the island where the two of them "
                 "spent a rainy honeymoon week")
    for clue, n in (("Hint", 14), (long_clue, 14), (long_clue, 17)):
        for paper in ("letter", "a4"):
            out = tmp_path / f"{n}-{paper}.pdf"
            crossword.render(_order(clue, n), str(out), paper)
            assert len(PdfReader(str(out)).pages) == 4


def test_helvetica_fallback_still_fits(tmp_path, monkeypatch):
    from pypdf import PdfReader
    monkeypatch.setattr(crossword, "FONT_DIRS", [])
    monkeypatch.setitem(crossword.FONTS, "body", "Helvetica")
    monkeypatch.setitem(crossword.FONTS, "bold", "Helvetica-Bold")
    out = tmp_path / "helv.pdf"
    crossword.render(_order("Took an unexpected turn during the Tofino honeymoon, with everyone watching"), str(out))
    assert len(PdfReader(str(out)).pages) == 4
