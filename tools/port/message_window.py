"""The message window as the ROM carries it: its tiles, its palette, its
cells, and the font with the tables the ROM composes the text with.

The image comes from `window.py` and the glyphs from `font.py`; this turns
them into SNES bytes.
"""

from port import constants
from port.snes_format import COLORS_PER_PALETTE, cgram_word, pack_tile
from port.map_layers import CGRAM_RESERVED


# The window tiles live in the bank that follows the upper layer's, and BG2
# reaches them with the same base because they ended up adjacent: indices 0 to
# 255 are the upper layer's and 256 to 511 the window's.

# The window size in cells. It is fixed: 256x80 stuck to the bottom of the
# screen, the same numbers as `tools/port/window.py`.
WINDOW_COLS_INC, WINDOW_ROWS_INC = 32, 10

# The glyph, which is what the ROM composes. The same numbers as
# `tools/port/font.py`, which is generated from easyrpg-player.
FONT_WIDTH, FONT_HEIGHT = 6, 12


# The message window, split in two: what the ROM carries ready-made and what
# it composes on the fly.
#
# **Why it is composed on the fly.** A composed message page is about 240 4bpp
# tiles, that is 7.5 KB. The game has 18,808 lines of text: emitting one
# window per message doesn't come close to fitting in a 256 KB cartridge. The
# way out is FF6's —the font in the ROM and the text built from the 65816— and
# it is what `componer_mensaje` does in tools/runtime/.
#
# How the window's bank of 256 tiles is split:
#
#   0 .. 14       the empty window, deduplicated: frame and stretched background
#   15 .. 254     the text area, 30 columns by 8 rows of cells
#
# The 240 of the text area **are not deduplicated**: each cell has its fixed
# tile, because the ROM is going to rewrite them and can't go around looking
# for repeats. That is where the cap of 39 characters per line comes from: with
# 40 the shadow of the last one spills into column 31 and 8 more tiles than
# there are would be needed. Truncating to 39 loses 1.58% of the game's
# characters against 1.09% for truncating to 40.
WINDOW_TEXT_ROW = 1           # the first row of cells that carries text
WINDOW_TEXT_ROWS = 8
WINDOW_TEXT_COL = 1
WINDOW_TEXT_COLS = 30


def _columns():
    """How many characters fit on a line. It lives in `window.py` with the
    rest of the geometry, and the reason for the number is there."""
    from port import window as window_mod
    return constants.COLUMNS


def _to_15_bits(picture):
    """The pixels of an RGBA image as 15-bit colors, over black."""
    from PIL import Image
    plain = Image.alpha_composite(
        Image.new("RGBA", picture.size, (0, 0, 0, 255)), picture).convert("RGB")
    return [tuple(v >> 3 for v in p) for p in plain.get_flattened_data()]


def convert_window(sys_img, font_id=None):
    """The message window: tiles, palette, cells and what the font needs.

    The image is built by `window.py`, which follows easyrpg-player's rules
    and is verified against a capture of the original game running in
    EasyRPG.
    Here it is cut into 8x8 cells and the fixed part is separated from what
    the ROM composes.

    The palette carries the colors of the empty window **plus** those of the
    text and the shadow, even though the empty window doesn't use them: they
    are the ones the ROM is going to write. Index 0 is left free on purpose,
    which is BG2's transparent and no window tile uses it.

    Returns a dict with:
        tiles     those of the empty window, deduplicated
        cram      the 16 words of the palette
        celdas    the 32x10 tilemap, with the text tiles already numbered
        fondo     the 240 tiles of the text area, without text, in order
        color     the palette index of each of the glyph's 12 rows
        sombra    the index of the shadow
    """
    from port import font as font_mod
    from port import window as window_mod

    if font_id is None:
        font_id = font_mod.MINCHO
    empty = window_mod.window(sys_img)
    pixels = _to_15_bits(empty)
    width, height = empty.width, empty.height

    # The text colors come from the System's 16x16 block, and they are the
    # ones `Font::Render` uses as a mask. Each row of the glyph takes a single
    # one —it is measured: the gradient is horizontally uniform— so they are
    # twelve colors, not a block, and the shadow is a single one.
    block = window_mod.text_color(sys_img, 0)
    shadow_img = window_mod.shadow_color(sys_img)
    ox, oy = window_mod.TEXT_OFFSET
    color_row = []
    for py in range(font_mod.HEIGHT):
        row = {tuple(v >> 3 for v in block.getpixel((ox + px, oy + py))[:3])
               for px in range(font_mod.WIDTH)}
        if len(row) != 1:
            raise SystemExit(
                "row %d of the text color has %d distinct colors; the "
                "ROM composes it with a single one" % (py, len(row)))
        color_row.append(row.pop())
    shadow = tuple(v >> 3 for v in shadow_img.getpixel((0, 0))[:3])

    colors = sorted(set(pixels) | set(color_row) | {shadow})
    if len(colors) > COLORS_PER_PALETTE - 1:
        raise SystemExit("the window uses %d colors and %d fit"
                         % (len(colors), COLORS_PER_PALETTE - 1))
    index = {c: i + 1 for i, c in enumerate(colors)}

    def cell_at(tx, ty):
        return tuple(tuple(index[pixels[(ty * 8 + y) * width + tx * 8 + x]]
                           for x in range(8)) for y in range(8))

    # The cells without text are deduplicated as always; the ones in the text
    # area are numbered consecutively from there.
    tiles, cells = {}, []
    for ty in range(height // 8):
        row = []
        for tx in range(width // 8):
            if (WINDOW_TEXT_ROW <= ty < WINDOW_TEXT_ROW + WINDOW_TEXT_ROWS
                    and WINDOW_TEXT_COL <= tx < WINDOW_TEXT_COL + WINDOW_TEXT_COLS):
                row.append(None)       # numbered below, once it is known how many
                continue
            cell = cell_at(tx, ty)
            if cell not in tiles:
                tiles[cell] = len(tiles)
            row.append(tiles[cell])
        cells.append(row)

    base = len(tiles)
    background = []
    for n, ty in enumerate(range(WINDOW_TEXT_ROW,
                                WINDOW_TEXT_ROW + WINDOW_TEXT_ROWS)):
        for m, tx in enumerate(range(WINDOW_TEXT_COL,
                                     WINDOW_TEXT_COL + WINDOW_TEXT_COLS)):
            cells[ty][tx] = base + n * WINDOW_TEXT_COLS + m
            background.append(cell_at(tx, ty))
    if base + len(background) > 256:
        raise SystemExit("the window needs %d tiles and the bank has 256"
                         % (base + len(background)))

    data = b"".join(pack_tile(cell, planes=4)
                    for cell, _ in sorted(tiles.items(), key=lambda kv: kv[1]))
    cram = [0] + [cgram_word(c) for c in colors]
    cram += [0] * (COLORS_PER_PALETTE - len(cram))
    # The background starts where this ends, so if the window grew it would
    # step on it and the ROM would draw the text with a map color. The highest
    # index really used is checked —the shadow's or that of some row of the
    # glyph— and not how many words are nonzero: a black color has word zero
    # and wouldn't be counted.
    height = max([index[c] for c in color_row] + [index[shadow]])
    if height >= CGRAM_RESERVED:
        raise SystemExit(
            "the message window uses CGRAM entry %d and the background "
            "starts at %d: raise CGRAM_RESERVED" % (height, CGRAM_RESERVED))
    return {"tiles": data, "cram": cram, "celdas": cells,
            "base": base,
            "fondo": b"".join(pack_tile(c, planes=4) for c in background),
            "color": [index[c] for c in color_row],
            "sombra": index[shadow]}


def font_bytes(font_id):
    """The 95 ASCII glyphs, twelve rows of six bits each.

    It is the same table as `tools/port/font.py`, which is generated from
    easyrpg-player, but **with the bits reversed**: there bit 0 is the
    leftmost pixel and in the console's tile format the leftmost is bit 7.
    Reversing them here and not in the ROM comes for free: it is a 1140-byte
    table generated once.
    """
    from port import font as font_mod
    out = bytearray()
    for code in range(32, 127):
        for row in font_mod.rows(chr(code), font_id):
            inverted = 0
            for px in range(FONT_WIDTH):
                if row >> px & 1:
                    inverted |= 1 << (7 - px)
            out.append(inverted)
    return bytes(out)


# The window glyphs already composed, for each of the four phases a character
# can land on: x is `WINDOW_BORDER + 6 * column`, so modulo 8 it gives 0, 6, 4
# or 2 and never anything else. Per glyph and phase go the cell rows of
# `FONT_PRE_ROWS` it touches —the glyph's twelve from `TEXT_OFS_Y`, and
# one more of shadow— and per row the two cells it can step on, each with
# three words: what is kept from the buffer, and what is set in planes 0-1
# and in 2-3. The ROM does `buf = buf & conservar | prender`, which is what it
# used to compute on each row with `pintar`, twice —shadow and glyph— and with
# a one-bit-at-a-time shift. See `compose_char`.
#
# The shadow and the glyph come already combined, with the ordering rule of
# `Font::Render`: on a row lands the glyph from two rows up and the shadow
# from three, shifted one pixel, and where they overlap the glyph wins.
FONT_PRE_ROWS = FONT_HEIGHT + 1
FONT_PRE_CHAR = FONT_PRE_ROWS * 2 * 6


def font_prerender(source, colors, shadow):
    """The four tables, one per phase (0, 2, 4 and 6), in that order."""
    n = len(source) // FONT_HEIGHT
    tables = []
    for phase in (0, 2, 4, 6):
        out = bytearray()
        for c in range(n):
            rows = source[c * FONT_HEIGHT:(c + 1) * FONT_HEIGHT]
            run = [(f << 8) >> phase for f in rows]
            for k in range(FONT_PRE_ROWS):
                glyph = run[k] if k < FONT_HEIGHT else 0
                color = colors[k] if k < FONT_HEIGHT else 0
                shadow_m = (run[k - 1] >> 1) if k >= 1 else 0
                shadow_m &= ~glyph & 0xFFFF
                for cell in (0, 1):
                    g = (glyph >> (8 if cell == 0 else 0)) & 0xFF
                    s = (shadow_m >> (8 if cell == 0 else 0)) & 0xFF
                    keep = ~((g | s) * 0x0101) & 0xFFFF
                    turn_on = []
                    for bits in (0, 2):
                        word = 0
                        for m, col in ((g, color), (s, shadow)):
                            if col >> bits & 1:
                                word |= m
                            if col >> (bits + 1) & 1:
                                word |= m << 8
                        turn_on.append(word)
                    for word in [keep] + turn_on:
                        out += bytes([word & 0xFF, word >> 8])
        tables.append(bytes(out))
    return tables
