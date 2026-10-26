"""Personalized crossword and word-search generator (Code Red line C).

Usage:
  python3 crossword.py order.json out.pdf          # US Letter
  python3 crossword.py order.json out-a4.pdf a4    # A4
  python3 crossword.py order.json poster.pdf 18x24 # poster: puzzle page + keepsake page, 18x24 in
                                                   # (also 24x36, a2, a1, a0)

order.json:
{
  "title": "Happy 10th Anniversary, Sam & Priya",
  "subtitle": "A crossword made from your story",
  "footer": "Made with love, October 2026",
  "entries": [{"word": "Lisbon", "clue": "Where you got engaged"}, ...],
  "word_search": true
}

Words: letters only (spaces and hyphens are stripped), 3 to 15 letters, 8 to 20 entries work best.
Output: a print-ready PDF (US Letter) with the puzzle page (grid and clues), an optional word search, the answer key
and a frame-ready keepsake page (the solved grid alone, larger, no clues or footer). Deterministic for a given order (seeded), so re-runs reproduce the same grid.
Everything is vector (text, lines, grid; no images) with all fonts embedded, so every page prints sharp at any
size. Poster sizes scale the Letter layout (inch sizes) or the A4 layout (ISO sizes) onto the bigger sheet,
centred, and keep only the puzzle page and the keepsake page.
"""
import json
import os, random, re, sys, unicodedata
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors

ACROSS, DOWN = "across", "down"

def clean(word):
    """Upper-case A-Z only; accents are folded (Québec -> QUEBEC), not dropped."""
    folded = unicodedata.normalize("NFD", str(word)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z]", "", folded.upper())

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

FONT_DIRS = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
             "/usr/share/fonts/truetype/crosextra"]  # bundled copies first, then the Debian package
FONTS = {"title": "Helvetica-Bold", "body": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique"}

def _register_fonts():
    """Use Caladea (serif) for titles and Carlito (sans) for text; both ship in fonts/ (SIL Open Font
    License). Fall back to Helvetica only if the files are missing; the layout measures whichever font
    is in use, so clues fit either way."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for d in FONT_DIRS:
        try:
            pdfmetrics.registerFont(TTFont("Caladea-Bold", os.path.join(d, "Caladea-Bold.ttf")))
            pdfmetrics.registerFont(TTFont("Caladea-Italic", os.path.join(d, "Caladea-Italic.ttf")))
            pdfmetrics.registerFont(TTFont("Carlito", os.path.join(d, "Carlito-Regular.ttf")))
            pdfmetrics.registerFont(TTFont("Carlito-Bold", os.path.join(d, "Carlito-Bold.ttf")))
            FONTS.update(title="Caladea-Bold", body="Carlito", bold="Carlito-Bold", italic="Caladea-Italic")
            return
        except Exception:
            continue

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
    """Greedy word wrap with reportlab's string widths. A trailing "(n)" length tag is glued to the
    word before it so it never sits alone on a line."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words = text.split()
    if len(words) >= 2 and re.fullmatch(r"\(\d+\)", words[-1]):
        words[-2:] = [words[-2] + " " + words[-1]]
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and stringWidth(trial, font, size) > width:
            lines.append(cur); cur = w
        else:
            cur = trial
    if cur: lines.append(cur)
    return lines or [""]

CLUE_SIZES = (11.5, 10.5, 9.5, 8.5)  # body sizes tried, largest first, until the clues fit the page

def _clue_layout(across, down, col_w, size):
    """Wrap every clue at `size`. Returns (lines per column, line height, text indent):
    each column is a list of (number_or_None, text) rows ready to draw."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    lead = round(size * 1.3, 1)
    indent = stringWidth("88.", FONTS["body"], size) + 5  # room for a two-digit number plus a gap
    cols = []
    for lst in (across, down):
        rows = []
        for n, w, clue in lst:
            lines = _wrap(f"{clue} ({len(w)})", FONTS["body"], size, col_w - indent)
            rows.append((n, lines[0]))
            rows.extend((None, line) for line in lines[1:])
        cols.append(rows)
    return cols, lead, indent

def _clue_height(cols, lead):
    """Height of the taller clue column, label included."""
    return lead * 1.6 + max(len(c) for c in cols) * lead

def _clue_columns(cv, across, down, x_left, y_top, col_w, gap, size=11.5):
    """Draw ACROSS and DOWN clue lists in two columns with a hanging indent. Returns the lowest y reached."""
    cols, lead, indent = _clue_layout(across, down, col_w, size)
    lowest = y_top
    for i, (label, rows) in enumerate(zip(("ACROSS", "DOWN"), cols)):
        x = x_left + i * (col_w + gap)
        y = y_top
        cv.setFont(FONTS["bold"], size - 0.5); cv.drawString(x, y, label); y -= lead * 1.6
        cv.setFont(FONTS["body"], size)
        for n, text in rows:
            if n is not None:
                cv.drawRightString(x + indent - 5, y, f"{n}.")
            cv.drawString(x + indent, y, text); y -= lead
        lowest = min(lowest, y + lead)
    return lowest

def render(order, out, pagesize=None):
    """Render an order to `out`. pagesize: None/"letter" (default) or "a4"; the order's
    "paper" key ("letter" or "a4") is used when pagesize is not given.
    Page 1 holds the puzzle grid and the clues together; then the optional word search; then the answer key;
    then (unless "keepsake" is false) a keepsake page: the solved grid alone, larger and centred, no clues or footer."""
    _register_fonts()
    entries = order["entries"]
    grid, leftover = build(entries, seed=order.get("seed", 0))
    nums, across, down = number(grid)
    paper = (pagesize or order.get("paper") or "letter").lower()
    W, H = A4 if paper == "a4" else letter
    accent = colors.HexColor(order.get("accent", "#8C2F39"))
    # initialFontName: without it reportlab declares an unembedded Helvetica on every page, which print-shop
    # preflight flags even though no text uses it.
    cv = canvas.Canvas(out, pagesize=(W, H), initialFontName=FONTS["body"], initialFontSize=10)
    cv.setTitle(order.get("title", "Custom crossword"))
    title, sub, foot = order.get("title", ""), order.get("subtitle", ""), order.get("footer", "")
    M = 0.6 * inch  # page margin

    def frame():
        cv.setStrokeColor(accent); cv.setLineWidth(1.2)
        cv.rect(M * 0.6, M * 0.6, W - M * 1.2, H - M * 1.2)
        cv.setLineWidth(0.4)
        cv.rect(M * 0.6 + 4, M * 0.6 + 4, W - M * 1.2 - 8, H - M * 1.2 - 8)

    def header(page_label, working=True):
        """Title block and frame. Pages carry no corner label; working=False also drops the footer (keepsake page)."""
        frame()
        cv.setFillColor(colors.black)
        size = 24 if len(title) <= 34 else 19
        cv.setFont(FONTS["title"], size); cv.drawCentredString(W / 2, H - 1.15 * inch, title)
        cv.setFillColor(accent); cv.setFont(FONTS["italic"], 12)
        if sub:
            cv.drawCentredString(W / 2, H - 1.42 * inch, sub)
        cv.setStrokeColor(accent); cv.setLineWidth(0.8)
        cv.line(W / 2 - 1.1 * inch, H - 1.56 * inch, W / 2 + 1.1 * inch, H - 1.56 * inch)
        if working and foot:
            cv.setFillColor(colors.HexColor("#555555"))
            cv.setFont(FONTS["italic"], 9); cv.drawCentredString(W / 2, M * 0.6 + 10, foot)
        cv.setFillColor(colors.black)

    r0, r1, c0, c1 = grid.bounds()
    rows, cols_n = r1 - r0 + 1, c1 - c0 + 1
    # Page 1: grid and both clue columns together. Measure the wrapped clues first, shrink the clue
    # text (never below CLUE_SIZES[-1]) until grid and clues share the page; only if the smallest size
    # still cannot fit do the clues move to their own page.
    col_gap = 0.35 * inch
    col_w = (W - 2 * M - col_gap) / 2
    top, bottom = H - 1.8 * inch, M * 0.6 + 26   # grid top; lowest baseline above the page label
    gap_grid_clues = 0.38 * inch
    min_cell = 0.26 * inch
    clue_size, cell, clues_on_page1 = CLUE_SIZES[-1], min_cell, False
    for size in CLUE_SIZES:
        cols, lead, _ = _clue_layout(across, down, col_w, size)
        avail_h = top - bottom - _clue_height(cols, lead) - gap_grid_clues
        c = min(0.4 * inch, avail_h / rows, (W - 2 * M) / cols_n)
        if c >= min_cell:
            clue_size, cell, clues_on_page1 = size, c, True
            break
    if not clues_on_page1:
        cell = min(0.4 * inch, (top - bottom) / rows, (W - 2 * M) / cols_n)
    gx = (W - cols_n * cell) / 2
    gy = top
    y_top = gy - rows * cell - gap_grid_clues
    header("Puzzle")
    draw_grid(cv, grid, nums, gx, gy, cell)
    if clues_on_page1:
        _clue_columns(cv, across, down, M, y_top, col_w, col_gap, size=clue_size)
    else:
        cv.showPage(); header("Clues")
        _clue_columns(cv, across, down, M, H - 1.85 * inch, col_w, col_gap, size=clue_size)
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

    # Answer key
    header("Answer key")
    draw_grid(cv, grid, nums, gx, gy, cell, solution=True, accent=accent)
    if clues_on_page1:
        _clue_columns(cv, across, down, M, y_top, col_w, col_gap, size=clue_size)
    # Last page: keepsake, the solved puzzle with no page label or footer, ready to frame
    if order.get("keepsake", True):
        cv.showPage()
        header("Keepsake", working=False)
        k_top, k_bottom = top, M * 0.6 + 0.45 * inch
        k_cell = min(0.5 * inch, (k_top - k_bottom) / rows, (W - 2 * M) / cols_n)
        kx = (W - cols_n * k_cell) / 2
        ky = k_top - ((k_top - k_bottom) - rows * k_cell) / 2
        draw_grid(cv, grid, nums, kx, ky, k_cell, solution=True, accent=accent)
    cv.save()
    return grid, leftover, ws_placed

POSTER_SIZES = {  # name: (width, height, base layout)
    "18x24": (18 * inch, 24 * inch, "letter"),
    "24x36": (24 * inch, 36 * inch, "letter"),
    "a2": (420 / 25.4 * inch, 594 / 25.4 * inch, "a4"),
    "a1": (594 / 25.4 * inch, 841 / 25.4 * inch, "a4"),
    "a0": (841 / 25.4 * inch, 1189 / 25.4 * inch, "a4"),
}

def render_poster(order, out, size="18x24"):
    """Poster PDF: the puzzle page and the keepsake page of the base layout, scaled up (vector, lossless)
    to fill the poster sheet and centred. Needs pypdf."""
    import io
    from pypdf import PdfReader, PdfWriter, PageObject, Transformation
    Wp, Hp, base = POSTER_SIZES[size.lower()]
    buf = io.BytesIO()
    result = render(order, buf, base)
    src = PdfReader(io.BytesIO(buf.getvalue()))
    keep = [src.pages[0]] + ([src.pages[-1]] if order.get("keepsake", True) else [])
    writer = PdfWriter()
    for page in keep:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        k = min(Wp / w, Hp / h)
        blank = PageObject.create_blank_page(width=Wp, height=Hp)
        blank.merge_transformed_page(page, Transformation().scale(k).translate((Wp - w * k) / 2, (Hp - h * k) / 2))
        writer.add_page(blank)
    writer.add_metadata({"/Title": order.get("title", "Custom crossword")})
    with open(out, "wb") as f:
        writer.write(f)
    return result

if __name__ == "__main__":
    order = json.load(open(sys.argv[1]))
    size = sys.argv[3] if len(sys.argv) > 3 else None
    if size and size.lower() in POSTER_SIZES:
        grid, leftover, _ = render_poster(order, sys.argv[2], size)
    else:
        grid, leftover, _ = render(order, sys.argv[2], size)
    print(f"placed {len(grid.placed)} words; left out: {[w for w, _ in leftover]}")
