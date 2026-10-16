"""Turn a buyer's memories into crossword entries with a local open-weight model.

The buyer rarely writes "WORD - clue" pairs; they write a paragraph about the person. This script
asks a local model (Gemma via Ollama by default, any OpenAI-compatible endpoint works) to pull out
8 to 20 answer words and write a short clue for each, then validates the result for the grid
builder: letters only, 3 to 15 letters, no duplicates, no clue that contains its own answer.

Usage:
  python3 clues.py memories.txt order.json --title "Happy 60th, Dad" [--occasion birthday] [--n 14]
  python3 clues.py memories.txt order.json --title "..." --mock        # no model, for tests and demos
  python3 crossword.py order.json puzzle.pdf

Environment: CLUE_ENDPOINT (default http://localhost:11434/v1/chat/completions, Ollama's
OpenAI-compatible route), CLUE_MODEL (default gemma3:4b). Nothing leaves the machine.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = os.environ.get("CLUE_ENDPOINT", "http://localhost:11434/v1/chat/completions")
MODEL = os.environ.get("CLUE_MODEL", "gemma3:4b")

SYSTEM = (
    "You write crossword clues for a personalized gift puzzle. From the memories you are given, "
    "choose answer words (names, places, pets, foods, hobbies, dates as words, inside jokes) and write "
    "one short, warm, specific clue for each. Rules: answers are single words of 3 to 15 letters, "
    "A to Z only (join two-word names: NEWYORK); every answer must be a word that appears in the memories, "
    "never an invented or generic word; never put the answer inside its clue; clues are under 12 words, "
    "written in the third person about the people named (no 'you' or 'your'); no two clues may describe "
    "the same fact; no generic clues like 'a city'. Return ONLY a JSON array of objects with keys "
    '"word" and "clue", nothing else.'
)


def clean(word):
    return re.sub(r"[^A-Z]", "", str(word).upper())


def warm_up(endpoint=ENDPOINT, model=MODEL, timeout=300):
    """One throwaway call so the model is loaded before the timed run (Ollama unloads idle models
    after about 5 minutes; the first call after that can take 1 to 2 minutes on a cold GPU)."""
    try:
        chat("Reply with the single word ready.", system="You reply briefly.", endpoint=endpoint, model=model, timeout=timeout)
    except Exception as e:  # noqa: BLE001 - warm-up failures are not fatal; the real call reports them
        print(f"warm-up failed: {e}", file=sys.stderr)


def chat(prompt, system=SYSTEM, endpoint=ENDPOINT, model=MODEL, timeout=300):
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.4,
            "stream": False,
        }
    ).encode()
    req = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"]


def parse(text):
    """Pull the first JSON array out of a model reply (models often wrap it in prose or fences)."""
    m = re.search(r"\[.*\]", text, flags=re.S)
    if not m:
        raise ValueError("no JSON array in model output")
    items = json.loads(m.group(0))
    return [(str(i.get("word", "")), str(i.get("clue", "")).strip()) for i in items if isinstance(i, dict)]


def _source_words(text):
    """Words of the memories text, plus each pair of adjacent words joined (so "New York" allows NEWYORK)."""
    toks = [clean(t) for t in re.findall(r"[A-Za-z][A-Za-z'-]*", text)]
    toks = [t for t in toks if t]
    return set(toks) | {a + b for a, b in zip(toks, toks[1:])}


def validate(pairs, n=14, source=None):
    """Keep entries the grid builder can use. Returns (entries, rejected_with_reason).
    With `source` (the buyer's memories), an answer must appear in that text: small models
    sometimes invent answers ("PRAMA") or pad with generic ones ("LOVE", "YEARS")."""
    out, seen, rejected = [], set(), []
    allowed = _source_words(source) if source else None
    for word, clue in pairs:
        w = clean(word)
        if not 3 <= len(w) <= 15:
            rejected.append((word, "length")); continue
        if allowed is not None and w not in allowed:
            rejected.append((word, "not in memories")); continue
        if w in seen:
            rejected.append((word, "duplicate")); continue
        if not clue or len(clue.split()) > 16:
            rejected.append((word, "clue")); continue
        if w in clean(clue):
            rejected.append((word, "answer in clue")); continue
        seen.add(w)
        out.append({"word": w.title(), "clue": clue.rstrip(".")})
        if len(out) == n:
            break
    return out, rejected


_STOP = set(
    "THE AND BUT FOR WITH THAT THIS THEY THEM THEIR THEN THAN WHEN WHERE WHILE WHICH WHOSE WHAT WHO HAS HAVE HAD "
    "WAS WERE ARE BEEN BOTH EACH EVERY FIRST ALSO ONLY JUST VERY FROM INTO OVER AFTER BEFORE ABOUT ONCE SOME "
    "MANY MUCH MOST SUCH THESE THOSE ALWAYS NEVER STILL EVEN YEAR YEARS DAY DAYS TIME".split()
)


def mock_pairs(memories, n=14, per_sentence=2):
    """Deterministic stand-in for the model. Picks names and distinctive words from the text and
    writes fill-in-the-blank clues from the sentence each one appears in, so a demo run reads like
    a real puzzle: 'Sam proposed in ____'. Proper nouns first, then longer plain words."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", memories) if s.strip()]
    cands = []  # (priority, order, word, sentence index)
    seen = set()
    for si, sent in enumerate(sentences):
        for m in re.finditer(r"[A-Za-z][A-Za-z'-]*", sent):
            tok = m.group(0)
            w = clean(tok)
            if w in seen or w in _STOP or not 3 <= len(w) <= 15:
                continue
            capital = tok[0].isupper()
            if not capital and len(w) < 5:
                continue
            seen.add(w)
            cands.append((0 if capital else 1, len(cands), tok, si))
    cands.sort(key=lambda c: (c[0], c[1]))
    used, pairs = {}, []
    for _, _, tok, si in cands:
        if used.get(si, 0) >= per_sentence:
            continue
        used[si] = used.get(si, 0) + 1
        blank = re.sub(r"\b" + re.escape(tok) + r"\b", "____", sentences[si], flags=re.I).rstrip(".!? ")
        words = blank.split()
        if len(words) > 12:  # keep a window around the blank
            k = next(i for i, x in enumerate(words) if "____" in x)
            lo = max(0, min(k - 5, len(words) - 12))
            blank = " ".join(words[lo:lo + 12])
        pairs.append((tok, blank))
        if len(pairs) == n:
            break
    return pairs


def build_order(memories, title, occasion="gift", n=14, mock=False, subtitle=None, footer=None, seed=0):
    prompt = (
        f"Occasion: {occasion}. Make {n} entries (give {n + 6} candidates so the best {n} survive validation).\n"
        f"Memories:\n{memories.strip()}"
    )
    if mock:
        pairs = mock_pairs(memories, n + 6)
    else:
        warm_up()
        pairs = parse(chat(prompt))
    entries, rejected = validate(pairs, n, source=memories)
    if len(entries) < 8:
        raise SystemExit(f"only {len(entries)} usable entries; rejected: {rejected}")
    return {
        "title": title,
        "subtitle": subtitle or "A crossword made from your story",
        "footer": footer or "",
        "word_search": True,
        "seed": seed,
        "entries": entries,
        "_rejected": rejected,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("memories"); ap.add_argument("out")
    ap.add_argument("--title", required=True); ap.add_argument("--occasion", default="gift")
    ap.add_argument("--n", type=int, default=14); ap.add_argument("--mock", action="store_true")
    ap.add_argument("--subtitle"); ap.add_argument("--footer"); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    with open(a.memories, encoding="utf-8") as f:
        memories = f.read()
    t0 = time.time()
    try:
        order = build_order(memories, a.title, a.occasion, a.n, a.mock, a.subtitle, a.footer, a.seed)
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach the model at {ENDPOINT} ({e.reason}).\n"
                 "Start Ollama and run `ollama pull gemma3:4b`, set CLUE_ENDPOINT/CLUE_MODEL, "
                 "or add --mock to try the pipeline without a model.")
    print(f"model: {MODEL} at {ENDPOINT}; {time.time() - t0:.1f} s including warm-up")
    rejected = order.pop("_rejected")
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(order, f, indent=1)
    print(f"{len(order['entries'])} entries -> {a.out}; rejected {len(rejected)}: {rejected}")
    for e in order["entries"]:
        print(f"  {e['word'].upper():15} {e['clue']}")


if __name__ == "__main__":
    main()
