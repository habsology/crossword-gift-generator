# Crossword gift generator

Turn a paragraph of memories about someone into a printable, personalized crossword puzzle. The clues are written by a small open-weight model (Gemma 3 4B through Ollama) running on your own machine, so nothing you write about your family leaves your computer.

Two scripts:

- `clues.py` reads the memories, asks the local model for answer words and clues, and validates them (letters only, 3 to 15 letters, no duplicates, no answer hidden in its own clue, and every answer must actually appear in the memories).
- `crossword.py` lays the entries out on a grid and renders a print-ready PDF: puzzle page, clues page, optional word search, solutions page. Deterministic for a given order, so re-runs reproduce the same grid.

![Sample puzzle](docs/anniversary-1.jpg)

![What you get](docs/anniversary-2.jpg)

## Quick try (no model needed)

```
pip install -r requirements.txt
python3 clues.py samples/anniversary-memories.txt order.json --title "Happy 10th Anniversary" --mock
python3 crossword.py order.json puzzle.pdf
```

`--mock` only picks capitalized and long words with placeholder clues, so it proves the pipeline and PDF work; real clues need the model below. On Windows use `py` instead of `python3`.

## Requirements

- Python 3.10 or newer
- `pip install -r requirements.txt` (reportlab)
- [Ollama](https://ollama.com) with the model pulled: `ollama pull gemma3:4b` (about 3.4 GB, runs on an 8 GB GPU or on CPU)

Any OpenAI-compatible chat endpoint works instead of Ollama. Set `CLUE_ENDPOINT` and `CLUE_MODEL`.

## Usage

Write the memories as plain prose, one paragraph is enough:

```
Sam proposed in Lisbon. They adopted Biscuit the dog in October. Priya loves Tiramisu
and Pancakes on Sundays. Honeymoon in Tofino where the Kayak flipped. Scrabble nights.
```

Then:

```
python3 clues.py samples/anniversary-memories.txt order.json --title "Happy 10th Anniversary, Sam & Priya"
python3 crossword.py order.json puzzle.pdf          # US Letter
python3 crossword.py order.json puzzle-a4.pdf a4    # A4
```

`clues.py` prints the accepted entries, the rejected candidates with the reason, and the run time. The first call to a cold model can take a minute or more while Ollama loads it; the script sends a warm-up request first and allows 300 seconds.

To run without a model (for tests and demos): `python3 clues.py memories.txt order.json --title "..." --mock`.

You can also skip `clues.py` and write `order.json` by hand. See the docstring at the top of `crossword.py` for the format, or any file in `samples/`.

## Tests

```
pip install pytest
pytest
```

## How the validation works

Small models invent words and pad lists with generic answers. `clues.py` builds the set of words in the memories (plus adjacent pairs, so "New York" becomes NEWYORK) and rejects any answer outside it. On a 4B model that turns roughly 85 percent of the raw candidates into usable entries, which is why the script asks for a few more candidates than it needs.

## Samples

`samples/` holds fictional orders for ten occasions (anniversary, birthday, Christmas, graduation, housewarming, new baby, retirement, teacher, Valentine's, wedding) with the rendered PDFs.

## License

MIT, see `LICENSE`.
