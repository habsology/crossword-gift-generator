"""Personalized crossword and word-search generator.

Usage:
  python3 crossword.py order.json out.pdf          # US Letter
  python3 crossword.py order.json out-a4.pdf a4    # A4

order.json:
{
  "title": "Happy 10th Anniversary, Sam & Priya",
  "subtitle": "A crossword made from your story",
  "footer": "Made with love, October 2026",
  "entries": [{"word": "Lisbon", "clue": "Where you got engaged"}, ...],
  "word_search": true
}

Words: letters only (spaces and hyphens are stripped), 3 to 15 letters, 8 to 20 entries work best.
Output: a print-ready PDF (US Letter) with the puzzle page, a clues page, an optional word search,
and a solutions page. Deterministic for a given order (seeded), so re-runs reproduce the same grid.
"""
import json, random, re, sys
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors

ACROSS, DOWN = "across", "down"

def clean(word):
    return re.sub(r"[^A-Z]", "", word.upper())

class Grid:
    def __init__(self, size):
        self.size = size
        self.cells = [[None] * size for _ in range(size)]
        self.placed = []  # (word, row, col, direction, clue)

    def fits(self, word, r, c, d):
        n = len(word)
        if d == ACROSS:
            if c < 0 or c + n > self.size or r < 0 or r >= self.size: return False
            if c > 0 and self.cells[r][c - 1]: return False
            if c + n < self.size and self.cells[r][c + n]: return False
            crosses = 0
            for i, ch in enumerate(word):
                cur = self.cells[r][c + i]
                if cur:
                    if cur != ch: return False
                    crosses += 1
                else:
                    if r > 0 and self.cells[r - 1][c + i]: return False
                    if r + 1 < self.size and self.cells[r + 1][c + i]: return False
            return crosses
        else:
            if r < 0 or r + n > self.size or c < 0 or c >= self.size: return False
            if r > 0 and self.cells[r - 1][c]: return False
            if r + n < self.size and self.cells[r + n][c]: return False
            crosses = 0
            for i, ch in enumerate(word):
                cur = self.cells[r + i][c]
                if cur:
                    if cur != ch: return False
                    crosses += 1
                else:
                    if c > 0 and self.cells[r + i][c - 1]: return False
                    if c + 1 < self.size and self.cells[r + i][c + 1]: return False
            return crosses

    def place(self, word, r, c, d, clue):
        for i, ch in enumerate(word):
            if d == ACROSS: self.cells[r][c + i] = ch
            else: self.cells[r + i][c] = ch
        self.placed.append((word, r, c, d, clue))

    def candidates(self, word):
        out = []
        for (pw, pr, pc, pd, _) in self.placed:
            for i, ch in enumerate(pw):
                for j, wch in enumerate(word):
                    if ch != wch: continue
                    if pd == ACROSS:
                        r, c, d = pr - j, pc + i, DOWN
                    else:
                        r, c, d = pr + i, pc - j, ACROSS
                    k = self.fits(word, r, c, d)
                    if k: out.append((k, r, c, d))
        return out

    def bounds(self):
        rows = [r for r in range(self.size) if any(self.cells[r])]
        cols = [c for c in range(self.size) if any(self.cells[r][c] for r in range(self.size))]
        return min(rows), max(rows), min(cols), max(cols)

def build(entries, seed=0, size=None, tries=60):
    """Try a few grid sizes; return the first layout that places every word, else the best."""
    words = [(clean(e["word"]), e["clue"]) for e in entries]
    words = [(w, c) for w, c in words if 3 <= len(w) <= 15]
    if not words: raise SystemExit("no usable words")
    base = size or max(15, max(len(w) for w, _ in words) + 4)
    overall = None
    for size in (base, base + 4, base + 8):
        g, left = _build_once(words, seed, size, tries)
        if overall is None or len(left) < len(overall[1]): overall = (g, left)
        if not left: break
    return overall

def _build_once(words, seed, size, tries):
    best = None
    rng = random.Random(seed)
    for t in range(tries):
        order = sorted(words, key=lambda x: -len(x[0]))
        if t: rng.shuffle(order)
        g = Grid(size)
        w0, c0 = order[0]
        g.place(w0, size // 2, (size - len(w0)) // 2, ACROSS, c0)
        leftover = []
        for w, c in order[1:]:
            cands = g.candidates(w)
            if not cands:
                leftover.append((w, c)); continue
            cands.sort(key=lambda x: (-x[0], rng.random()))
            k, r, cc, d = cands[0]
            g.place(w, r, cc, d, c)
        # second pass for leftovers
        for w, c in list(leftover):
            cands = g.candidates(w)
            if cands:
                k, r, cc, d = max(cands, key=lambda x: x[0])
                g.place(w, r, cc, d, c); leftover.remove((w, c))
        r0, r1, c0_, c1 = g.bounds()
        score = (len(g.placed), -max(r1 - r0, c1 - c0_))
        if best is None or score > best[0]:
            best = (score, g, leftover)
    return best[1], best[2]

def number(grid):
    """Assign clue numbers in reading order."""
    starts = {}
    for (w, r, c, d, clue) in grid.placed:
        starts.setdefault((r, c), []).append((d, w, clue))
    nums, n = {}, 0
    for r in range(grid.size):
        for c in range(grid.size):
            if (r, c) in starts:
                n += 1; nums[(r, c)] = n
    across = sorted([(nums[(r, c)], w, clue) for (r, c), lst in starts.items() for d, w, clue in lst if d == ACROSS])
    down = sorted([(nums[(r, c)], w, clue) for (r, c), lst in starts.items() for d, w, clue in lst if d == DOWN])
    return nums, across, down

def word_search(words, seed=0, size=15):
    rng = random.Random(seed + 7)
    g = [[None] * size for _ in range(size)]
    dirs = [(0, 1), (1, 0), (1, 1), (-1, 1), (0, -1), (-1, 0), (-1, -1), (1, -1)]
    placed = []
    for w in sorted(words, key=len, reverse=True):
        if len(w) > size: continue
        for _ in range(400):
            dr, dc = rng.choice(dirs)
            r, c = rng.randrange(size), rng.randrange(size)
            rr, cc = r + dr * (len(w) - 1), c + dc * (len(w) - 1)
            if not (0 <= rr < size and 0 <= cc < size): continue
            ok = all(g[r + dr * i][c + dc * i] in (None, w[i]) for i in range(len(w)))
            if ok:
                for i, ch in enumerate(w): g[r + dr * i][c + dc * i] = ch
                placed.append((w, r, c, dr, dc)); break
    for r in range(size):
        for c in range(size):
            if g[r][c] is None: g[r][c] = rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return g, placed

FONT_DIR = "/usr/share/fonts/truetype/crosextra"
FONTS = {"title": "Helvetica-Bold", "body": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique"}

def _register_fonts():
    """Use Caladea (serif) for titles and Carlito (sans) for text when installed; fall back to Helvetica."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        pdfmetrics.registerFont(TTFont("Caladea-Bold", f"{FONT_DIR}/Caladea-Bold.ttf"))
        pdfmetrics.registerFont(TTFont("Caladea-Italic", f"{FONT_DIR}/Caladea-Italic.ttf"))
        pdfmetrics.registerFont(TTFont("Carlito", f"{FONT_DIR}/Carlito-Regular.ttf"))
        pdfmetrics.registerFont(TTFont("Carlito-Bold", f"{FONT_DIR}/Carlito-Bold.ttf"))
        FONTS.update(title="Caladea-Bold", body="Carlito", bold="Carlito-Bold", italic="Caladea-Italic")
    except Exception:
        pass

def draw_grid(cv, grid, nums, x0, y0, cell, solution=False, ws=None, accent=None):
    if ws is not None:
        for r, row in enumerate(ws):
            for c, ch in enumerate(row):
                cv.setFont(FONTS["body"], cell * 0.6)
                cv.drawCentredString(x0 + c * cell + cell / 2, y0 - r * cell - cell * 0.7, ch)
        return
    r0, r1, c0, c1 = grid.bounds()
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            ch = grid.cells[r][c]
            if not ch: continue
            x, y = x0 + (c - c0) * cell, y0 - (r - r0 + 1) * cell
            cv.setFillColor(colors.white); cv.setStrokeColor(colors.HexColor("#222222")); cv.setLineWidth(0.9)
            cv.rect(x, y, cell, cell, fill=1)
            cv.setFillColor(colors.black)
            if (r, c) in nums:
                cv.setFont(FONTS["body"], cell * 0.3)
                cv.drawString(x + 1.6, y + cell - cell * 0.33, str(nums[(r, c)]))
            if solution:
                cv.setFont(FONTS["bold"], cell * 0.56)
                cv.setFillColor(accent or colors.black)
                cv.drawCentredString(x + cell / 2, y + cell * 0.24, ch)
                cv.setFillColor(colors.black)

def _wrap(text, font, size, width):
    from reportlab.lib.utils import simpleSplit
    return simpleSplit(text, font, size, width)

def _clue_columns(cv, across, down, x_left, y_top, col_w, gap, size=11.5, lead=15):
    """Draw ACROSS and DOWN clue lists in two columns. Returns the lowest y reached."""
    lowest = y_top
    for i, (label, lst) in enumerate((("ACROSS", across), ("DOWN", down))):
        x = x_left + i * (col_w + gap)
        y = y_top
        cv.setFont(FONTS["bold"], 11); cv.drawString(x, y, label); y -= lead * 1.25
        for n, w, clue in lst:
            lines = _wrap(f"{n}.  {clue} ({len(w)})", FONTS["body"], size, col_w - 4)
            for j, line in enumerate(lines):
                cv.setFont(FONTS["body"], size)
                cv.drawString(x + (14 if j else 0), y, line); y -= lead
        lowest = min(lowest, y)
    return lowest

def render(order, out, pagesize=None):
    """Render an order to `out`. pagesize: None/"letter" (default) or "a4"; the order's
    "paper" key ("letter" or "a4") is used when pagesize is not given.
    Page 1 holds the puzzle grid and the clues together; then the optional word search; then the answer key."""
    _register_fonts()
    entries = order["entries"]
    grid, leftover = build(entries, seed=order.get("seed", 0))
    nums, across, down = number(grid)
    paper = (pagesize or order.get("paper") or "letter").lower()
    W, H = A4 if paper == "a4" else letter
    accent = colors.HexColor(order.get("accent", "#8C2F39"))
    cv = canvas.Canvas(out, pagesize=(W, H))
    cv.setTitle(order.get("title", "Custom crossword"))
    title, sub, foot = order.get("title", ""), order.get("subtitle", ""), order.get("footer", "")
    M = 0.6 * inch  # page margin

    def frame():
        cv.setStrokeColor(accent); cv.setLineWidth(1.2)
        cv.rect(M * 0.6, M * 0.6, W - M * 1.2, H - M * 1.2)
        cv.setLineWidth(0.4)
        cv.rect(M * 0.6 + 4, M * 0.6 + 4, W - M * 1.2 - 8, H - M * 1.2 - 8)

    def header(page_label):
        frame()
        cv.setFillColor(colors.black)
        size = 24 if len(title) <= 34 else 19
        cv.setFont(FONTS["title"], size); cv.drawCentredString(W / 2, H - 1.15 * inch, title)
        cv.setFillColor(accent); cv.setFont(FONTS["italic"], 12)
        cv.drawCentredString(W / 2, H - 1.42 * inch, sub if sub else page_label)
        cv.setStrokeColor(accent); cv.setLineWidth(0.8)
        cv.line(W / 2 - 1.1 * inch, H - 1.56 * inch, W / 2 + 1.1 * inch, H - 1.56 * inch)
        cv.setFillColor(colors.HexColor("#555555")); cv.setFont(FONTS["body"], 8.5)
        cv.drawRightString(W - M - 2, M * 0.6 + 10, page_label.upper())
        if foot:
            cv.setFont(FONTS["italic"], 9); cv.drawCentredString(W / 2, M * 0.6 + 10, foot)
        cv.setFillColor(colors.black)

    r0, r1, c0, c1 = grid.bounds()
    rows, cols = r1 - r0 + 1, c1 - c0 + 1
    # Page 1: grid sized so the clues fit underneath (two columns)
    n_clues = len(across) + len(down)
    clue_rows = max(len(across), len(down)) + 1
    clue_h = clue_rows * 15 + 0.35 * inch
    avail_h = H - 1.85 * inch - clue_h - M
    cell = min(0.4 * inch, avail_h / rows, (W - 2 * M) / cols)
    gx = (W - cols * cell) / 2
    gy = H - 1.8 * inch
    header("Puzzle")
    draw_grid(cv, grid, nums, gx, gy, cell)
    col_gap = 0.35 * inch
    col_w = (W - 2 * M - col_gap) / 2
    y_top = gy - rows * cell - 0.42 * inch
    low = _clue_columns(cv, across, down, M, y_top, col_w, col_gap)
    if low < M * 0.6 + 24:  # very long clue lists spill to a second page
        cv.showPage(); header("Clues")
        _clue_columns(cv, across, down, M, H - 1.85 * inch, col_w, col_gap)
    cv.showPage()

    # Optional word search
    ws_placed = []
    if order.get("word_search"):
        words = [w for (w, *_rest) in grid.placed] + [w for w, _ in leftover]
        ws, ws_placed = word_search(words, seed=order.get("seed", 0))
        header("Bonus word search")
        wcell = 0.4 * inch
        wx, wy = (W - 15 * wcell) / 2, H - 1.95 * inch
        cv.setStrokeColor(accent); cv.setLineWidth(0.8)
        cv.rect(wx - 6, wy - 15 * wcell - 6, 15 * wcell + 12, 15 * wcell + 12)
        draw_grid(cv, None, None, wx, wy, wcell, ws=ws)
        cv.setFont(FONTS["bold"], 10.5)
        y = wy - 15 * wcell - 0.45 * inch
        cv.drawCentredString(W / 2, y, "FIND THESE WORDS"); y -= 0.26 * inch
        cv.setFont(FONTS["body"], 10.5)
        ws_words = [w for w, *_ in ws_placed]
        for i in range(0, len(ws_words), 6):
            cv.drawCentredString(W / 2, y, "     ".join(ws_words[i:i + 6])); y -= 0.21 * inch
        cv.showPage()

    # Last page: answer key
    header("Answer key")
    draw_grid(cv, grid, nums, gx, gy, cell, solution=True, accent=accent)
    low = _clue_columns(cv, across, down, M, y_top, col_w, col_gap)
    cv.save()
    return grid, leftover, ws_placed

if __name__ == "__main__":
    order = json.load(open(sys.argv[1], encoding="utf-8"))
    grid, leftover, _ = render(order, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print(f"placed {len(grid.placed)} words; left out: {[w for w, _ in leftover]}")
