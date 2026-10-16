import json
import clues


def test_parse_handles_fences_and_prose():
    txt = 'Sure! Here you go:\n```json\n[{"word": "Lisbon", "clue": "City of the proposal"}]\n```'
    assert clues.parse(txt) == [("Lisbon", "City of the proposal")]


def test_validate_rules():
    pairs = [
        ("Lisbon", "City of the proposal"),
        ("New York", "First apartment, two words"),
        ("ab", "too short"),
        ("Lisbon", "duplicate"),
        ("Biscuit", "Biscuit the dog"),  # answer inside clue
        ("Kayak", "The one that flipped."),
    ]
    entries, rejected = clues.validate(pairs)
    assert [e["word"] for e in entries] == ["Lisbon", "Newyork", "Kayak"]
    assert entries[-1]["clue"] == "The one that flipped"
    assert {r[1] for r in rejected} == {"length", "duplicate", "answer in clue"}


def test_mock_pipeline_builds_a_puzzle(tmp_path):
    memories = (
        "Sam proposed in Lisbon. They adopted Biscuit the dog in October. Priya loves Tiramisu and "
        "Pancakes on Sundays. Honeymoon in Tofino, kayak flipped. Scrabble nights, Leo both. Elm street."
    )
    order = clues.build_order(memories, "Happy 10th, Sam & Priya", "anniversary", n=10, mock=True)
    assert 8 <= len(order["entries"]) <= 10
    import crossword
    out = tmp_path / "p.pdf"
    grid, leftover, _ = crossword.render(order, str(out))
    assert out.stat().st_size > 1000
    assert len(grid.placed) + len(leftover) == len(order["entries"])


def test_chat_is_called_with_prompt(monkeypatch):
    seen = {}

    def fake_chat(prompt, **kw):
        if "ready" in prompt:  # warm-up call
            return "ready"
        seen["prompt"] = prompt
        names = ["Lisbon", "Tofino", "Biscuit", "Kayak", "Scrabble", "Pancakes", "Elm", "Bike", "Leo", "Tiramisu", "Main", "Sunday"]
        return json.dumps([{"word": w, "clue": f"clue number {i}"} for i, w in enumerate(names)])

    monkeypatch.setattr(clues, "chat", fake_chat)
    memories = "Dad proposed in Lisbon, honeymoon in Tofino, Biscuit the dog, the Kayak, Scrabble, Pancakes, Elm street, the Bike shop on Main, Leo, Tiramisu, Sunday."
    order = clues.build_order(memories, "Dad Turns 60", "birthday", n=10)
    assert "Occasion: birthday" in seen["prompt"] and "Dad proposed" in seen["prompt"]
    assert len(order["entries"]) == 10


def test_validate_rejects_answers_not_in_memories():
    # recorded from the 2026-10-16 gemma3:4b run on Matt's PC: PRAMA, YEARS and LOVE are not in the text
    memories = "Sam proposed in Lisbon. Priya loves Tiramisu and Pancakes on Sundays. Scrabble nights."
    pairs = [("Lisbon", "Where Sam popped the question"), ("PRAMA", "Priya's sweet Sunday treat"),
             ("YEARS", "Celebrating this milestone"), ("LOVE", "The foundation"), ("Scrabble", "Word nights"),
             ("Sunday", "Pancake day"), ("New York", "Two words")]
    entries, rejected = clues.validate(pairs, source=memories + " They live in New York.")
    assert [e["word"] for e in entries] == ["Lisbon", "Scrabble", "Newyork"]
    assert {r[0] for r in rejected} == {"PRAMA", "YEARS", "LOVE", "Sunday"}  # LOVE != loves, Sunday != Sundays
    assert all(r[1] == "not in memories" for r in rejected)


def test_mock_clues_are_fill_in_the_blank():
    pairs = clues.mock_pairs("Sam proposed in Lisbon. They adopted Biscuit the dog in October.")
    d = dict(pairs)
    assert d["Lisbon"] == "Sam proposed in ____"
    assert all(w.upper() not in clues.clean(c) for w, c in pairs)
    assert "They" not in d and "THEY" not in {clues.clean(w) for w in d}
