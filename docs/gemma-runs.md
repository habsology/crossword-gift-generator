# Gemma clue-writer test runs, 2026-10-16

Hardware: a laptop with an Intel i9-14900HX, 32 GB RAM, NVIDIA RTX 4060 Laptop GPU (8 GB), Windows, Ollama 0.40.5, gemma3:4b (Q4_K_M, 3.4 GB), Python 3.12.7. `pytest -q test_clues.py`: 4 passed.

First cold call before the warm-up fix: the model loaded onto the GPU in 115 s and the first request then took 2m57s and returned HTTP 500 (prompt eval 0.26 tokens/s). Second call: first token at 0.9 s, 49 tokens/s generation. Cause not proven; treated as cold start. Fix: a throwaway warm-up call and a 300 s timeout.

Input: `samples/anniversary-memories.txt` (fictional couple), title "Happy 10th, Sam & Priya", 14 entries requested.

| Run | Wall time | Entries | Rejected by validator | Problems found by eye |
|---|---|---|---|---|
| seed 0 | 24.2 s (incl. warm-up) | 14 | 0 | SAM clue duplicates the LISBON clue |
| seed 1 | 14.3 s | 14 | 0 | PRAMA (not a word); YEARS, LOVE not in the memories |
| seed 2 | 14.2 s | 14 | 0 | PRAMA, YEARS, LOVE again; two clues use "your" |

`crossword.py order0.json puzzle0.pdf`: placed 14 words, none left out.

## Run 0 (verbatim)
```
model: gemma3:4b at http://localhost:11434/v1/chat/completions; 23.8 s including warm-up
14 entries -> order0.json; rejected 0: []
  LISBON          Where Sam popped the question
  BISCUIT         Their furry, happy addition
  OCTOBER         The month of their new family member
  PRIYA           The sweet one who loves dessert
  TIRAMISU        Priya's Sunday treat obsession
  PANCAKES        Another Sunday morning favorite
  TOFINO          Honeymoon waters where they capsized
  KAYAK           The vessel that turned upside down
  SCRABBLE        Their competitive nights of words
  LEO             One of their shared names
  ELM             The street of their first home
  MAIN            Where they first met, cycling
  BIKE            The shop where their paths converged
  SAM             The proposer, forever loved
```

## Run 1 (verbatim)
```
model: gemma3:4b at http://localhost:11434/v1/chat/completions; 14.0 s including warm-up
14 entries -> order1.json; rejected 0: []
  LISBON          Where Sam popped the question
  BISCUIT         Their furry, happy addition
  OCTOBER         The month of new beginnings
  PRAMA           Priya's sweet Sunday treat
  PANCAKES        A Sunday morning favorite
  TOFINO          Honeymoon waters where they flipped
  KAYAK           A watery adventure in BC
  SCRABBLE        Their competitive nights of fun
  LEO             Both of them share this name
  ELM             Their first home's charming street
  MAIN            Where they first met, cycling
  BIKE            The shop where their story began
  YEARS           Celebrating this special milestone
  LOVE            The foundation of their journey
```

## Run 2 (verbatim)
```
model: gemma3:4b at http://localhost:11434/v1/chat/completions; 13.9 s including warm-up
14 entries -> order2.json; rejected 0: []
  LISBON          Where Sam popped the question
  BISCUIT         Their furry, happy addition
  OCTOBER         The month of new beginnings
  PRAMA           Priya's sweet Sunday treat
  PANCAKES        A Sunday morning favorite
  TOFINO          Honeymoon waters where they flipped
  KAYAK           A paddle adventure gone wrong
  SCRABBLE        Their competitive night in
  LEO             One of their shared names
  ELM             Their first home's street name
  MAIN            Where their love story started
  BIKE            The shop where they first met
  YEARS           Celebrating your anniversary
  LOVE            The foundation of your journey
```

## What changed after the run
- `validate()` now rejects any answer that is not a word in the memories text (or two adjacent words joined). On the recorded run 1 and 2 output this rejects PRAMA, YEARS and LOVE (test `test_validate_rejects_answers_not_in_memories`). The runs above predate this rule.
- The prompt now says: answers must come from the memories; third person only; no two clues for the same fact.
- Score, by eye, across 42 entries: 36 usable as written (86%), 3 invented or generic answers (now caught), 3 weak clues (duplicate fact, "your").
