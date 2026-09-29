"""The End Game screen of the pause menu: RM2k's `Scene_End`.

It is two windows over black: on top the question —the LDB term
`exit_game_message`, "End game?" in ABL— and below "Yes" and "No" —`yes` and
`no`—, with the System's bar over the one being chosen. The rules come from
easyrpg-player's `Scene_End::CreateCommandWindow` and `CreateHelpWindow`,
and the measurements were compared against the 2015 RPG_RT running under
Wine: with these same computations at 320x240, the windows, the text and the
bar land on the same pixels as in the capture of the original. What differs
are things of `window.py` and of the font, which apply to every window of
the port: the light band of the stretched background lands a few rows off,
and a couple of glyphs —the "g"— are not identical.

**It is drawn whole, as an image**, and not with the one-letter-per-cell
font of the item screen: it is a fixed screen of three words, so the letters
can go at the font's 6 pixels, as in RM2k, and the windows can measure what
they measure there. It goes on BG1 at 8bpp, which in mode 3 addresses all of
CGRAM.

**The cursor does not move tiles: it changes colors.** The two images —with
the bar on "Yes" and with the bar on "No"— share the tiles and the tilemap,
and what tells them apart are the pixels of the two bars. Each pair (color
with the cursor on Yes, color with the cursor on No) that appears in the
image is a CGRAM entry of its own: the pixels that do not change have the
same color in both, and those of the bars, a different one. Moving the
cursor is writing those few entries with the other image's palette, during
vblank. That way there is no second tilemap and no extra tiles.
"""

from port import constants
from port import window as window_mod

WIDTH, HEIGHT = constants.WIDTH, constants.HEIGHT
CELL = constants.CELL
BLACK = (0, 0, 0)

# `menu_item_height` of Window_Selectable and the borders of Window.
LINE = 16
BORDER = 8
# The two windows in RM2k, which is 320x240: the question at y=72 and the
# commands 48 further down, centered in x. Here the screen is 256x224, so
# they are centered on 256 and moved up 8, half of the 16 missing rows.
Y_QUESTION = 72
Y_COMMANDS = 72 + 48
Y_SHIFT = (240 - HEIGHT) // 2

# Which command the cursor marks on entering. The 2015 RPG_RT enters on
# "Yes", measured under Wine; easyrpg-player enters on "No" (`SetIndex(1)`).
# The original wins.
YES, NO = 0, 1
DEFAULT_CHOICE = YES


def texts(db):
    """The question and the two commands, from the LDB, with the same
    fallback texts as easyrpg if the term is empty."""
    t = db.terms
    def one(name, fallback):
        # Measured against A Blurred Line: an assumption of the engine, not a
        # fact of the game. See
        # `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
        value = t.get(name, b"").decode("cp1252")
        return value or fallback
    return (one("exit_game_message", "Do you really want to quit?"),
            one("yes", "Yes"), one("no", "No"))


def _width_of(text):
    from port import font
    return len(text) * font.WIDTH


def draw(sys_img, db, chosen, font_id=None, width=WIDTH, height=HEIGHT,
         y_shift=Y_SHIFT):
    """The screen in RGB, with the cursor on `chosen`. `width`, `height` and
    `y_shift` at 320, 240 and 0 give RM2k's, which is the one compared against
    the capture of the original."""
    from PIL import Image
    question, yes, no = texts(db)
    if _width_of(question) + 2 * BORDER > width:
        # RM2k would let it run off the screen; here it would be cut
        # without warning.
        raise SystemExit("the End Game question, %r, does not fit in %d "
                         "pixels" % (question, width))
    outside = Image.new("RGBA", (width, height), BLACK + (255,))

    def paste(image, x, y):
        outside.paste(image, (x, y), image)

    # The question: `Window_Help`, as wide as the text plus the borders, with
    # the text at (0, 2) of its contents.
    w = _width_of(question) + 2 * BORDER
    x, y = width // 2 - w // 2, Y_QUESTION - y_shift
    paste(window_mod.window(sys_img, w, 2 * LINE), x, y)
    window_mod.draw_line(outside, sys_img, x + BORDER, y + BORDER + 2,
                          question, font_id=font_id)

    # The commands: `Window_Command`, as wide as the longest plus the borders
    # and sixteen per command plus the borders tall. The bar is
    # `UpdateCursorRect`'s: four more on each side of the contents.
    commands = (yes, no)
    w = max(_width_of(o) for o in commands) + 2 * BORDER
    x, y = width // 2 - w // 2, Y_COMMANDS - y_shift
    paste(window_mod.window(sys_img, w, len(commands) * LINE + 2 * BORDER),
          x, y)
    paste(window_mod.cursor(sys_img, w - 2 * BORDER + 8, LINE),
          x + BORDER - 4, y + BORDER + chosen * LINE)
    for n, command in enumerate(commands):
        window_mod.draw_line(outside, sys_img, x + BORDER,
                              y + BORDER + n * LINE + LINE // 8, command,
                              font_id=font_id)
    return outside.convert("RGB")


# --- what goes into the cartridge ---------------------------------------------
#
# BG2, at 4bpp and with palette 0: the tiles from `RANURA_VRAM` and the tilemap
# at `RANURA_MAP`, which are the VRAM places the menu and the slot screen
# already write —see `back_to_map`—, so the map comes back without anything
# else having to be restored. The palette is entries 0 to 15, which the menu
# also restores on the way back.
COLORS_MAX = 16
# How many frames the fade to black of "Yes" lasts, and how long the song's:
# the screen's measured on the 2015 RPG_RT —about 330 ms—, and the song's is
# `Scene_End`'s `BgmFade(400)`.
FADE_FRAMES = 20
SONG_FADE_MS = 400


def ramp():
    """The INIDISP brightness on each frame of the fade to black: a straight
    line from 15 to 0 in `FADE_FRAMES` steps, the last one black."""
    last = FADE_FRAMES - 1
    return [15 * (last - n) // last for n in range(FADE_FRAMES)]


def convert(sys_img, db, font_id=None):
    """The screen as the ROM uploads it: `(tiles, filas, fila0, paletas)`.

    `tiles[i][y][x]` are indices from 0 to 15, and 0 is the empty tile;
    `rows` the tilemap words of the cell rows that have something, from
    `row0`; the rest of the tilemap is zero. `palettes` are two lists of 16
    15-bit colors: the one with the bar on "Yes" and the one with the bar on
    "No". See the header: one index per pair of colors.
    """
    colors15 = [[tuple(v >> 3 for v in p) for p in
                 draw(sys_img, db, n, font_id).get_flattened_data()]
                for n in (YES, NO)]
    pairs = sorted(set(zip(*colors15)))
    pairs.remove((BLACK, BLACK))
    pairs.insert(0, (BLACK, BLACK))     # 0: transparent, the black background
    if len(pairs) > COLORS_MAX:
        raise SystemExit("the End Game screen uses %d pairs of colors and "
                         "a 4bpp palette has %d" % (len(pairs),
                                                           COLORS_MAX))
    index = {pair: i for i, pair in enumerate(pairs)}
    pixels = [index[pair] for pair in zip(*colors15)]
    empty = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, where, mapping = [empty], {empty: 0}, []
    for row in range(HEIGHT // CELL):
        for col in range(WIDTH // CELL):
            cell = tuple(tuple(pixels[(row * CELL + y) * WIDTH
                                      + col * CELL:(row * CELL + y) * WIDTH
                                      + col * CELL + CELL])
                         for y in range(CELL))
            # Mirrored too, with the tilemap's flip bits: the window frame is
            # symmetric.
            h = tuple(tuple(reversed(r)) for r in cell)
            for flip, shape in ((0, cell), (0x4000, h),
                                (0x8000, tuple(reversed(cell))),
                                (0xC000, tuple(reversed(h)))):
                if shape in where:
                    mapping.append(where[shape] | flip)
                    break
            else:
                where[cell] = len(tiles)
                tiles.append(cell)
                mapping.append(where[cell])
    cols = WIDTH // CELL
    used = [f for f in range(HEIGHT // CELL) if any(mapping[f * cols:(f + 1) * cols])]
    row0, row1 = used[0], used[-1] + 1
    palettes = [[pair[n] for pair in pairs] + [BLACK] * (COLORS_MAX - len(pairs))
                for n in (YES, NO)]
    return tiles, mapping[row0 * cols:row1 * cols], row0, palettes


def render(sys_img, db, chosen, font_id=None):
    """What the ROM has to show, rebuilt from `convert` and not from
    `draw`: the tiles, the tilemap and the palette, at 15 bits. That way
    the drawing the ROM is compared against goes through the same color-pair
    math as the ROM does."""
    from PIL import Image
    tiles, rows, row0, palettes = convert(sys_img, db, font_id)
    palette = palettes[chosen]
    outside = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    px = outside.load()
    cols = WIDTH // CELL
    for n, word in enumerate(rows):
        cell = tiles[word & 0x3FF]
        if word & 0x4000:
            cell = tuple(tuple(reversed(r)) for r in cell)
        if word & 0x8000:
            cell = tuple(reversed(cell))
        row, col = row0 + n // cols, n % cols
        for y in range(CELL):
            for x in range(CELL):
                r, g, b = palette[cell[y][x]]
                px[col * CELL + x, row * CELL + y] = (r << 3, g << 3, b << 3)
    return outside
