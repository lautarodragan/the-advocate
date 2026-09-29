"""The menus: the save slots, the pause menu, the item screen and the
choose-whom screen, with the font and the frames they share.
"""

import collections

import numpy

from port import adeleine
from port import experience
from port import font
from port.constants import HEIGHT, WIDTH, CELL, COLS, ROWS, MENU_CGRAM
from port.palette import BLACK
from port.rules import level_of, param_of


# --- the slot screen ---------------------------------------------------------
#
# Both ends use it: "Resume the Story" on the title, and the Lashe City save
# point. It is a screen of its own and not a layer over the title, so it has
# VRAM all to itself and everything can go at 4bpp.
#
# **The text that does not depend on the save is pre-rendered**, including
# the two variants of each slot —empty and taken— and the level term. What
# does depend on it —the leader's name and level— is composed one letter per
# cell with loose glyphs, like the timer digits; see "what depends on the
# actor" below. Until 2026-09-20 it was baked too, with one block per actor,
# and that made the bank grow with every actor that could be in the party.
#
# What the ROM does do on the fly is **choose which block of cells it writes
# on each row**: per slot there are four —empty or full, with cursor or
# without— and moving the cursor is rewriting two rows of 96 cells. There is
# no full tilemap per combination because there would be 64.
# The row is **48 pixels, six cells**, which is the size of a FaceSet face:
# `Window_SaveFile::Refresh` in easyrpg draws, per file, the file name, the
# leader's, the level and the hit points, and the faces of up to four of the
# party at 48x48. Here there are three lines of text on the left and up to
# three faces on the right: the fourth does not fit in 256 pixels without
# eating the border, which is not visible on a CRT. Four rows of 48 plus the
# header end at line 216 of the 224.
SLOT_Y = 24                   # where the first row starts, in pixels
# And how far apart the next one is. **A multiple of 8 on purpose**: each row
# is uploaded to the tilemap as a block of whole cells, so if the step did not
# land on a cell the text of one row would be written into the next row's
# block and get cut.
SLOT_STEP = 48
SLOT_ROWS = 6                # 8 px tall cells each one takes
SLOT_X = 56                   # where the text starts
LINE = 16                      # how far apart the text lines in the row are
HEADER_Y = 4
HEADER_ROWS = 2
# What a slot without a save says. RM2k has no term for this —its menu shows
# the empty gap— so the text is ours, and that is why it is written here and
# not taken from the LDB, so it shows that we made it up.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
EMPTY = "- Empty -"
# The faces: where the first one goes, in cells from the left edge, and how
# far apart the next one is. Six wide by six tall, touching.
FACE = 48
FACE_CELLS = FACE // CELL      # 6
FACE_COL = 14                   # that is x = 112
FACE_STEP = FACE_CELLS         # touching: 112, 160, 208
FACES_MAX = 3
# The leader's name, on the second line: seven cells wide, from the edge of
# the text to where the first face starts.
NAME_COL = SLOT_X // CELL   # 7
NAME_COLS = FACE_COL - NAME_COL     # 7
NAME_ROW = LINE // CELL     # 2: the second line starts at y+16
# And the third line, the level: the two digits after the term "L ", which
# is baked because it is the same for everyone.
LEVEL_ROW = 2 * LINE // CELL  # 4
LEVEL_DIGITS = 2                # "%2d", which is what RM2k shows
# Which cell the number starts at: the one after the term, which is two font
# characters wide. It is not `SLOT_X + 12` rounded by hand because the term
# comes from the LDB and its width is the font's.
LEVEL_COL = (SLOT_X + 2 * font.WIDTH) // CELL       # 8
# And which palette the faces use: 0 is the text's, and each face carries its
# own from 1. They are the palettes of BG2 at 4bpp, which are eight on the
# console.
FACE_PALETTES_MAX = 7
# How many tiles fit in the screen's bank: the converter checks it against
# the VRAM layout, see SLOT_MAP there.
SLOT_TILES_MAX = 448

# --- what depends on the actor, composed with glyphs ---------------------------
#
# The name, the level and the max HP **are composed one letter per cell** and
# not baked into one block per actor. The reason is that the bank is a single
# one and deduplicated: baked, each actor's text added some seven tiles it
# shares with nobody, so the bank grew with every actor that could be in the
# party and the whole game did not fit. With glyphs the text costs once —the
# letters the names use— and the only thing that keeps growing per actor is
# the faces.
#
# It is the same the gold digits, the current HP and the item screen already
# do. The price is the same they pay and it is declared: the letters go at an
# 8-pixel pitch and not at the font's 6, so the text that depends on the
# actor comes out a bit wider than before. What does not depend on it —"File
# 1", "- Empty -", the level term, "Normal", "HP"— is still baked with the
# font, so it comes out the same as always.
#
# The glyphs are drawn **in the same cell and with the same offset as the
# gold digits** —one in x, two in y—, so the ten digits come from here and the
# screen does not carry two sets of digits.
GLYPH_COL = 3                   # the column where the loose glyph is drawn
GLYPH_ROW = 25                 # and its row; both are arbitrary
GLYPH_DX = 1                    # centered in the cell: 6 px of font in 8
GLYPH_DY = 2


def _cell_block(layer, row0, rows, tiles, offset, index, col0=0,
                cols=COLS, palette=0):
    """The cells of a rectangle of `layer`, adding new tiles.

    Returns the list of tilemap words, `cols` per row: the tile index with
    the three bits of `palette` on top. The tiles are shared with everything
    else on the screen: there is a single bank and the blocks index it, so
    deduplicating separately would give indices that do not match. They are
    deduplicated by their indices and not by their colors, so a tile with the
    same drawing in two palettes is a single one.

    `index` maps a 15-bit color to a palette index; what is not there is an
    error and not a similar color, so that an extra color gets noticed.
    """
    px = layer.load()
    cells = []
    for row in range(rows):
        for col in range(col0, col0 + cols):
            cell = []
            for y in range(CELL):
                line = []
                for x in range(CELL):
                    sx = col * CELL + x
                    sy = (row0 + row) * CELL + y
                    if sy >= HEIGHT or sx >= WIDTH:
                        line.append(0)
                        continue
                    r, g, b, a = px[sx, sy]
                    line.append(index[(r >> 3, g >> 3, b >> 3)] if a else 0)
                cell.append(tuple(line))
            cell = tuple(cell)
            if cell not in offset:
                offset[cell] = len(tiles)
                tiles.append(cell)
            cells.append(offset[cell] | (palette << 10))
    return cells


def _slot_text(number, db, full):
    """The first two lines of a slot, with the game's terms. The second of a
    full slot is the leader's name, which goes separately because it depends
    on the save; the third is the level, which is written in two colors and
    also goes separately."""
    if not full:
        return ["%s %d" % (db.term_file, number + 1), EMPTY]
    return ["%s %d" % (db.term_file, number + 1), ""]


def _write_level_term(dest, sys_img, x, y, db, font_id):
    """The level term, like `Window_SaveFile::Refresh`: `lvl_short` padded
    to two characters and in system color 1. In ABL it is "L ". The hit
    points RM2k puts next to it do not go: this port does not have them.

    It is copied from the EasyRPG capture of 2026-09-10, not from the code
    alone.

    **The number does not go here**: the ROM composes it with glyphs,
    because it is the only thing on this line that depends on the actor
    —with Kersh as leader it says 20 and with Core 15—. The term is baked,
    since it is the same for everyone.
    """
    from port import window as window_mod
    window_mod.draw_line(dest, sys_img, x, y,
                          (db.term_lvl_short or "")[:2].ljust(2), color=1,
                          font_id=font_id)


def name_text(db, actor, cols=None):
    """The actor's name as the ROM composes it: one letter per cell, with the
    ones the font lacks turned into '?' and padded with spaces.

    The padding is not decoration: the ROM always writes the same cells, so
    what is left over on the right has to erase whatever was there."""
    cols = MENU_NAME_COLS if cols is None else cols
    name = db.actors[actor].name if actor in db.actors else ""
    return item_text(name, cols).ljust(cols)


def level_text(db, actor, level=None):
    """The two digits of the level, as RM2k says them: right-aligned. Without
    `level`, the starting one; the ROM composes the current one with the
    same, `text_level`."""
    if level is None:
        level = level_of(db.actors[actor]) if actor in db.actors else 0
    return ("%*d" % (LEVEL_DIGITS, level))[-LEVEL_DIGITS:]


def max_text(db, actor, level=None):
    """The actor's max HP after its slash: "/168". They go next to the
    current HP, which the ROM writes with the same glyphs. Without `level`,
    those of the starting one; the ROM composes those of the current one,
    `text_max`."""
    maximum = (param_of(db.actors[actor], "maxhp", level)
               if actor in db.actors else 0)
    return ("/%d" % maximum).ljust(MENU_MAX_DIGITS)[:MENU_MAX_DIGITS]


def exp_text(db, actor, level=None, exp=None):
    """The experience as `DrawActorExp` writes it: `"%6d/%6d"`, the current
    one and the one the next level asks for —`GetNextExp`—, or dashes at the
    cap. Without `level` or `exp`, the starting ones, like
    `level_text`."""
    a = db.actors[actor]
    if level is None:
        level = experience.initial_level(a)
    if exp is None:
        exp = experience.initial_exp(a)
    next_exp = experience.next_exp(a, level)
    if next_exp == -1:
        return "-" * MENU_EXP_DIGITS + "/" + "-" * MENU_EXP_DIGITS
    return "%*d/%*d" % (MENU_EXP_DIGITS, exp, MENU_EXP_DIGITS, next_exp)


def glyphs_of(db, actors, extra=""):
    """Which letters the bank needs: those of what is composed, plus the ten
    digits, which always go because the gold and the current HP use them,
    and those of `extra` —the names of the medicines, which the actor choice
    writes: see `TARGET_WINDOWS`—.

    It comes from the texts themselves and not from an alphabet written by
    hand: a cartridge with three actors does not pay for the others'
    letters."""
    letters = set("0123456789 ") | set(extra)
    letters |= set("/-")         # the experience's, which it always has
    for actor in actors:
        letters |= set(name_text(db, actor) + level_text(db, actor)
                       + max_text(db, actor))
    return sorted(letters)


def face_of(db, actor, game_dir):
    """The actor's face, 48x48 in RGBA, or None if it has none.

    It goes through `render_map.load_image` and not `Image.open`, like the
    skin: in RM2k palette index 0 is transparent in a FaceSet too, and in
    `ABLFaces` it is a red that fills almost the whole face. Drawn opaque,
    each face was a red square with a figure inside.
    """
    import os
    from render import render_map
    a = db.actors[actor]
    if not a.face_name:
        return None
    sheet = render_map.load_image(os.path.join(game_dir, "FaceSet",
                                               a.face_name + ".png"))
    col, row = a.face_index % 4, a.face_index // 4
    return sheet.crop((col * FACE, row * FACE, (col + 1) * FACE,
                       (row + 1) * FACE))


def _face_palette(face):
    """Fifteen colors for a face, and where each color of the image goes.

    ABL's faces use between 22 and 29 15-bit colors, and a 4bpp palette fits
    15. Index 0 is the transparent one, and black goes there: over the
    screen's black background it makes no difference and does not spend an
    entry.

    The reduction is `adeleine.merge_least_visible` and **not** `palette.reduce`,
    which is what the title image uses. `palette.reduce` keeps the fifteen most
    used colors and sends the rest to the nearest, and at 48x48 pixels that
    flattens everything: a face has a handful of skin tones covering almost
    all of it and a dozen details of two or three pixels each —the glint of
    an eye, the edge of a lock of hair—, so the fifteen winners were fifteen
    variants of the same tone and the face came out flat. taro reported it
    as "Talan and Core look gray".

    On the title the difference does not exist —it is 240 colors out of
    369, and the ones merged barely appear— and it costs the quadratic, so
    `palette.reduce` stays there.
    """
    face_pixels = [(r >> 3, g >> 3, b >> 3) if a else BLACK
                   for r, g, b, a in face.get_flattened_data()]
    used = collections.Counter(p for p in face_pixels if p != BLACK)
    if len(used) > 15:
        mapping = adeleine.merge_least_visible(used, 15)[0]
        palette = sorted(set(mapping.values()))
        dest = mapping
    else:
        palette = sorted(used, key=lambda c: (-used[c], c))
        dest = {c: c for c in used}
    colors = [BLACK] + list(palette)
    index = {BLACK: 0}
    for color, target_color in dest.items():
        index[color] = colors.index(target_color)
    return colors, index


def _lent_face(colors, face_index, palettes):
    """Which of the existing palettes a face that did not get its own hangs
    on to, and for each color of the face which index of that palette it
    goes to.

    The palette missing the fewest colors is chosen —counting distinct
    colors and not pixels, which is what can be known here without walking
    the image again— and each color goes to the nearest by luma, which is
    exactly what `picture.fits` does in the converter with the sprites.

    The first two palettes are the text's and are not touched: painting the
    face over the text would make it illegible, which is worse than a face
    with its tone changed.
    """
    candidates = list(range(2, len(palettes)))
    which = min(candidates,
                key=lambda n: (sum(1 for c in colors if c not in palettes[n]), n))
    dest = palettes[which]
    offset = {}
    for color in colors:
        if color in dest:
            offset[color] = dest.index(color)
        else:
            offset[color] = dest.index(
                min(dest, key=lambda p, c=color: (
                    adeleine.luma_distance(p, c), p)))
    return which, {c: offset[colors[k]] for c, k in face_index.items()}


# --- the pause menu ----------------------------------------------------------
#
# It is RM2k's `Scene_Menu` at 256x224 and not 320x240, so the geometry is
# ours and not theirs: the command column on the left, the gold at the bottom
# left and the party on the right, **without the windows** —black background,
# like the slot screen— and without what does not fit: the actor's title, the
# experience and the SP. Of the party one sees the face, the name, the level,
# the status and the HP. It is cosmetic and declared: it looks right or it
# does not, and taro says which by playing.
#
# It lives in the **same tile bank and the same palette** as the slot screen:
# the faces are the same, and the save screen is opened from the menu.
# Everything is aligned to 8-pixel cells so the blocks work on any row.
MENU_OPTIONS = 5
MENU_OPT_Y = 8                  # the first command, in pixels
MENU_OPT_STEP = 16             # and how far apart the next one is
MENU_OPT_COL = 3                # the command's text, x = 24
MENU_OPT_COLS = 9               # up to x = 96, where the party starts
MENU_CURSOR_COL = 1             # the ">", x = 8
# Which commands do something. The others are drawn in the "cannot" color,
# which is system color 3, the way RM2k draws "Save" when it is forbidden:
# today that is only techniques. Using items opens the item screen since
# 2026-09-11. Number 3, saving, depends on `ChangeSaveAccess`. Number 4, End
# Game, opens the end_game.py screen since 2026-09-28: until then it was
# gray because "ending the game requires going back to the title without
# resetting the SPC700", and that stopped being needed when Game Over started
# going back to the title with a reset.
MENU_ITEMS = 0
MENU_EQUIPMENT = 2
MENU_SAVE = 3
MENU_END = 4
MENU_DONE = (MENU_ITEMS, MENU_EQUIPMENT, MENU_SAVE, MENU_END)
# The gold, at the bottom left: up to six digits **one cell each** —not at the
# font's 6 pixels, so the ROM writes them one at a time without rebuilding
# tiles— and the currency term after them, in color 1.
MENU_GOLD_Y = 200
MENU_GOLD_COL = 3
MENU_GOLD_DIGITS = 6
MENU_CURRENCY_COL = MENU_GOLD_COL + MENU_GOLD_DIGITS    # 9, x = 72
MENU_CURRENCY_COLS = 3
# The party: a row of seven cells per actor, with the face on the left and
# the text beside it. Four rows are exactly 224 pixels.
MENU_ACTOR_COL = 12             # x = 96
MENU_ACTOR_COLS = COLS - MENU_ACTOR_COL
MENU_ACTOR_ROWS = 7
MENU_TEXT_X = MENU_ACTOR_COL * CELL + FACE + 8     # 152
MENU_STATUS_DX = 42             # "Normal" goes 42 from the level, as in RM2k
MENU_PARTY_ROWS = 4
# The current HP: three digits **one cell each**, for the same reason as the
# gold —so the ROM writes them one at a time without rebuilding tiles—. They
# go on the third line of the actor's row, that is rows 4 and 5 of the block,
# which is where the gold digits land aligned: both are drawn two pixels from
# the top edge of their cell. The maximum goes after, with the slash, and
# that one is baked: it never changes.
MENU_HP_DIGITS = 3              # no actor in the game goes past 999
MENU_HP_COL = 21                # x = 168, right after the "HP" on the left
MENU_HP_ROW = 4                # the third line, inside the block
MENU_MAX_X = (MENU_HP_COL + MENU_HP_DIGITS) * CELL      # 192
# And where, inside the actor's row, the three strips that depend on it and
# that the ROM composes with glyphs land: the name on the first line, the two
# level digits after the term on the second, and the maximum after the
# current HP on the third. See "what depends on the actor" up there.
MENU_NAME_COL = MENU_TEXT_X // CELL                  # 19
MENU_NAME_COLS = COLS - MENU_NAME_COL               # 13
MENU_NAME_ROW = 0
MENU_LEVEL_COL = (MENU_TEXT_X + 2 * font.WIDTH) // CELL      # 20
MENU_LEVEL_ROW = LINE // CELL                         # 2
MENU_MAX_COL = MENU_MAX_X // CELL                       # 24
MENU_MAX_DIGITS = 4             # the slash and up to three digits: "/168"
# The experience, which is the third line of `Window_MenuStatus`: the term
# —"Ex" in ABL— in color 1, and twelve pixels on the current one and the next
# level's, six digits each with the slash in between, `"%6d/%6d"` like
# `DrawActorExp`. With the level at the cap both are dashes, which is what
# easyrpg's comment says RPG_RT does.
#
# **It goes in sprites, not in the tilemap**, and it is the only line on this
# screen that is not on the grid. It did not fit anywhere else: RM2k puts the
# HP to the right of the level and the experience below, in two columns that
# do not fit in 256 pixels, and a fourth line of cells does not fit in the
# row's 56 pixels. In sprites it goes wherever needed: twelve pixels below
# the HP, which is the font's pitch, and at the font's six pixels and not the
# cells' eight —at eight, the thirteen letters went off the screen—. The
# tiles are the bank's own glyphs: the sprites read VRAM from `SLOT_VRAM`,
# so a glyph's tile is the same number.
#
# Twelve and not sixteen pixels below the HP leaves one pixel of space above
# and two below, and on the fourth row the digits' shadow lands exactly on
# the last line of the screen.
MENU_EXP_X = MENU_TEXT_X
MENU_EXP_Y = 2 + 2 * LINE + 11         # where the letter starts, in the row
MENU_EXP_NUM_DX = 12
MENU_EXP_DIGITS = 6
MENU_EXP_LETTERS = 2 * MENU_EXP_DIGITS + 1
MENU_EXP_TERM_CELLS = 2        # "Ex": twelve pixels, two cells wide


# --- the item screen ---------------------------------------------------------
#
# `Scene_Item`: on top the description of the marked item and below the
# inventory list with how many there are. In RM2k the list goes in two
# 144-pixel columns; here they do not fit and it goes in **one**, with the
# quantity on the right, and the description is split into two lines.
#
# The text does not go pre-drawn but **one letter per cell**: the screen
# carries its own tile bank with each font character in two cells —white and
# gray—, and names and descriptions go as text in the ROM, which writes two
# tilemap words per letter. The first attempt drew each item's text into the
# bank shared with the slots and the menu, and with a dozen items it no longer
# fit: four of the suite's ROMs stopped building. This way the cost does not
# depend on how many items there are, and the price is that the letters go at
# 8 pixels and not the font's 6, like the menu's gold digits. It is cosmetic
# and declared.
ITEM_DESC_Y = 8
ITEM_DESC_COL = 1
ITEM_DESC_WIDTH = 30            # letters per line, one per cell
ITEM_DESC_LINES = 2
# The list starts one cell lower and has one row less than until 2026-09-28,
# when the windows arrived —see `ITEM_WINDOWS`—: with eleven rows from 48 the
# last one touched the bottom frame, and the top one was stuck to the
# window's. This way both windows leave the same spacing as RM2k.
ITEM_LIST_Y = 56
ITEM_ROWS = 10                 # 56 + 10 * 16 = 216, and the frame at 222
ITEM_CURSOR_COL = 1
ITEM_NAME_COL = 3             # x = 24, like the menu's commands
ITEM_NAME_WIDTH = 20          # the longest name in the game
ITEM_COLON_COL = 27
ITEM_DIGITS_COL = 28            # two digits, 28 and 29
ITEM_FIRST_CHAR = 32       # the ones the font has: from the space
ITEM_CHARS = 95            # to the tilde, which is what the items use
# The font variants: the index is what the ROM carries in `temp + 1`, and
# also its palette. Number 2 is system color 2, `Window_EquipStatus`'s "goes
# up" one, and only the equipment screen uses it for a parameter's new value,
# so it carries **only the digits**: the whole font in one more color was
# about 150 tiles, and the battle's bank does not have them —see
# `ITEMS_TILES_MAX`—. Number 3 is color 1, the red of the terms of
# `Window_EquipStatus` and `Window_EquipLeft`, and that one does go **whole**:
# measured on 2026-09-28, the font in that color is ten more tiles and not a
# hundred-odd, because tiles are deduplicated by index and the red's gradient
# lands on the same indices as the white's. Only the letters of the terms
# were thirty-five: with fewer letters the palette order —by frequency— comes
# out different and no longer matches.
ITEM_WHITE, ITEM_GRAY, ITEM_UP, ITEM_RED = range(4)
ITEM_UP_CHARS = "0123456789 "
# How far the font bank can grow: the battle uploads it and then writes its
# scene's tilemap at VRAM word $3800, which is tile 384 counting from
# `SLOT_VRAM`. Whatever goes past there would be overwritten.
ITEMS_TILES_MAX = (0x3800 - 0x2000) // 16

# The screen's windows, like `Scene_Item`: the help one on top and the list
# one below, each with the stretched background and the System's frame
# —`window.window`, the same as the message's—. RM2k puts them right
# against each other, so the separator is the two frames together: four
# pixels. The help one is taller than RM2k's —32— because here the
# description goes on two lines.
#
# They go on **BG1**, which was off on this screen, and the text stays on BG2
# as before: that way the text does not have to know anything about the
# windows, and the description, which is uploaded in whole rows, does not
# erase the frame. The glyphs already carry the priority bit —see
# `item_glyph_cells` in the converter—, so the text stays above the band of
# the background that crosses it, as in RM2k. At 8bpp a pixel is directly its
# CGRAM entry: the frame's colors go from `ITEM_BORDER_CGRAM`, after the four
# text palettes, and black is 0, the transparent one, which lets the backdrop
# color show through, which is black.
ITEM_HELP_HEIGHT = 48
ITEM_WINDOWS = ((0, 0, WIDTH, ITEM_HELP_HEIGHT),
                (0, ITEM_HELP_HEIGHT, WIDTH, HEIGHT - ITEM_HELP_HEIGHT))
ITEM_BORDER_CGRAM = 4 * MENU_CGRAM
# The frame's tiles go in the font's bank, after it: BG1's base is the same as
# BG2's, and an 8bpp tile is the size of two 4bpp ones. Everything has to fit
# before BG1's tilemap, which goes at $3800 —where the battle puts its
# scene's, so nothing of this screen is there—.
ITEM_BORDER_MAP = 0x3800
# The list's cursor is the System's —RM2k's red bar— and not the ">": four
# pixels wider than the text on each side, which is what RM2k leaves.
ITEM_BAR_X = ITEM_NAME_COL * CELL - 4
ITEM_BAR_WIDTH = (ITEM_DIGITS_COL + 2 - ITEM_NAME_COL) * CELL + 8


def item_windows(sys_img, bar=None):
    """The item screen's windows, in RGBA and the size of the screen: what
    BG1 draws. With `bar`, the cursor on that row of the list."""
    from PIL import Image
    from port import window as window_mod
    outside = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    for x, y, width, height in ITEM_WINDOWS:
        image = window_mod.window(sys_img, width, height)
        outside.paste(image, (x, y), image)
    if bar is not None:
        image = window_mod.cursor(sys_img, ITEM_BAR_WIDTH, 2 * CELL)
        outside.paste(image, (ITEM_BAR_X, ITEM_LIST_Y + 2 * CELL * bar), image)
    return outside


def item_layers(sys_img):
    """What `borders` needs from the item screen: the windows without a
    cursor, and with the cursor on each row of the list together with the
    first cell row it takes."""
    return (item_windows(sys_img),
            [(item_windows(sys_img, k), ITEM_LIST_Y // CELL + 2 * k)
             for k in range(ITEM_ROWS)])


def borders(sys_img, first_tile, screens, cgram=None, cap=256):
    """The windows of several screens as the ROM uploads them: 8bpp tiles,
    one 32x28 tilemap per screen, their cursors and the colors.

    `screens` is a list of `(ventanas, barras)`, as `item_layers` gives
    them: the screen-sized image without a cursor, and that of each cursor
    position with the first cell row it takes and, if it is not two, how
    many. The tiles and the colors are **a single set for all**: the screens
    are never open at the same time and upload their tiles to the same place
    in VRAM, so each one uploads the whole set and each one's tilemap indexes
    it the same way.

    `first_tile` is the 8bpp tile number of the first one, counted from
    BG1's base. Returns `(tiles, colores, mapas)`: `tiles[i][y][x]` is the
    CGRAM entry of that pixel; `colors` the 15-bit ones from `cgram`
    —`ITEM_BORDER_CGRAM` if not given—, which cannot go past `cap`; and
    `mapas[p]` is `(mapa, barras)` of screen `p`, with `mapping` the tilemap
    words row by row and `barras[k]` the two cell rows of cursor `k` with
    the cursor on top, which is what the ROM copies over `mapping` to paint it.

    The tiles are also deduplicated mirrored, with the tilemap's flip bits:
    the frame is symmetric, and without that the windows and the cursor did
    not fit in what is left of VRAM —see `_check_items_border`—.
    """
    cgram = ITEM_BORDER_CGRAM if cgram is None else cgram
    pictures = [image for background, bars in screens
                for image in [background] + [b[0] for b in bars]]
    counts = collections.Counter()
    for image in pictures:
        pixels = numpy.asarray(image).reshape(-1, 4)
        rgb = pixels[pixels[:, 3] != 0, :3].astype(numpy.int32) >> 3
        for r, g, b in rgb.tolist():
            if (r, g, b) != BLACK:
                counts[(r, g, b)] += 1
    colors = sorted(counts, key=lambda c: (-counts[c], c))
    if cgram + len(colors) > cap:
        raise SystemExit("the windows use %d colors and from %d there is room "
                         "for %d"
                         % (len(colors), cgram, cap - cgram))
    index = {c: cgram + i for i, c in enumerate(colors)}
    empty = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, offset = [empty], {empty: 0}

    def words(image, rows):
        px = image.load()
        out = []
        for row in rows:
            for col in range(COLS):
                cell = []
                for y in range(CELL):
                    line = []
                    for x in range(CELL):
                        r, g, b, a = px[col * CELL + x, row * CELL + y]
                        color = (r >> 3, g >> 3, b >> 3)
                        line.append(index[color]
                                    if a and color != BLACK else 0)
                    cell.append(tuple(line))
                cell = tuple(cell)
                h = tuple(tuple(reversed(r)) for r in cell)
                for flip, shape in ((0, cell), (0x4000, h),
                                    (0x8000, tuple(reversed(cell))),
                                    (0xC000, tuple(reversed(h)))):
                    if shape in offset:
                        out.append((first_tile + offset[shape]) | flip)
                        break
                else:
                    offset[cell] = len(tiles)
                    tiles.append(cell)
                    out.append(first_tile + offset[cell])
        return out

    tilemaps = []
    for background, bars in screens:
        tilemaps.append((words(background, range(ROWS)),
                         [words(b[0], range(b[1], b[1] + (b[2] if len(b) > 2
                                                         else 2)))
                          for b in bars]))
    return tiles, colors, tilemaps


def item_usable(item):
    """Whether the item goes in white and A does something with it on the
    map: it is `Game_Party::IsItemUsable` outside battle. The switch ones
    with `occasion_field2`, and the medicines, which open the actor choice.
    Books, materials and specials not yet: they go in gray."""
    from rpgmaker import lcf
    return ((item.type == lcf.ITEM_TYPE_SWITCH and item.occasion_field2)
            or item.type == lcf.ITEM_TYPE_MEDICINE)


def item_needs_actor(item):
    """Whether using it opens `Scene_ActorTarget`: the medicines."""
    from rpgmaker import lcf
    return item.type == lcf.ITEM_TYPE_MEDICINE


def item_text(text, width):
    """What the screen can write: the characters the font has, with a '?'
    instead of the others, and cut to the width."""
    return "".join(c if ITEM_FIRST_CHAR <= ord(c)
                   < ITEM_FIRST_CHAR + ITEM_CHARS else "?"
                   for c in text)[:width]


def split_description(text, width=ITEM_DESC_WIDTH):
    """The description in two lines, cut at a space. What does not fit in
    two is lost."""
    rows, current = [], ""
    for word in text.split(" "):
        candidate = (current + " " + word) if current else word
        if len(candidate) <= width:
            current = candidate
            continue
        rows.append(current)
        current = word[:width]
    rows.append(current)
    rows = [item_text(r, width) for r in rows]
    return (rows + ["", ""])[:ITEM_DESC_LINES]


def item_list(items, inventory):
    """The items the screen shows, in number order like `Game_Party`: the
    ones there are and that the ROM knows."""
    return [i for i in sorted(items) if inventory.get(i, 0) > 0]


def items_screen(sys_img, font_id=None):
    """The item screen's bank: each font character in two cells, one above
    the other, in white, in gray and in red, and the digits also in the
    "goes up" color —see `ITEM_UP`—.

    Returns `(tiles, paletas, glifos)`: `paletas[v]` and
    `glifos[v][caracter]` —the two tilemap words— per variant: 0 the text, 1
    the gray, 2 the "goes up" one, which only has `ITEM_UP_CHARS`,
    and 3 the red. The space is two blank cells: it is the one the cursor
    erases.
    """
    from PIL import Image
    from port import window as window_mod
    colors = {ITEM_WHITE: 0, ITEM_GRAY: 3, ITEM_UP: 2, ITEM_RED: 1}
    layers = []
    for gray in (ITEM_WHITE, ITEM_GRAY, ITEM_UP, ITEM_RED):
        for n in range(ITEM_CHARS):
            c = chr(ITEM_FIRST_CHAR + n)
            if gray == ITEM_UP and c not in ITEM_UP_CHARS:
                continue
            image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            window_mod.draw_line(image, sys_img, 1, 2, c,
                                  color=colors[gray], font_id=font_id)
            layers.append((gray, n, image))
    # The colors of each set, with numpy: it is one screen-sized image per
    # character and per color, with the letter in a corner, and walking them
    # pixel by pixel was almost all this screen cost. The order they are
    # counted in does not matter: the palette comes out sorted.
    seen = [collections.Counter() for _ in colors]
    for gray, _, image in layers:
        pixels = numpy.asarray(image).reshape(-1, 4)
        rgb = pixels[pixels[:, 3] != 0, :3].astype(numpy.int32) >> 3
        codes, count = numpy.unique(
            (rgb[:, 0] << 10) | (rgb[:, 1] << 5) | rgb[:, 2],
            return_counts=True)
        for c, k in zip(codes.tolist(), count.tolist()):
            seen[gray][(c >> 10, (c >> 5) & 31, c & 31)] += k
    palettes, indices = [], []
    for counts in seen:
        if len(counts) > 15:
            raise SystemExit("the item screen's font uses %d colors and 4bpp "
                             "fits 15" % len(counts))
        palette = [BLACK] + sorted(counts, key=lambda c: (-counts[c], c))
        palettes.append(palette)
        indices.append({color: i for i, color in enumerate(palette)})
    empty = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, offset = [empty], {empty: 0}
    glyphs = [{} for _ in colors]
    for gray, n, image in layers:
        glyphs[gray][chr(ITEM_FIRST_CHAR + n)] = _cell_block(
            image, 0, 2, tiles, offset, indices[gray], 0, 1, gray)
    if len(tiles) > ITEMS_TILES_MAX:
        raise SystemExit("the item screen's font gathers %d tiles and its "
                         "bank fits %d" % (len(tiles), ITEMS_TILES_MAX))
    return tiles, palettes, glyphs


def _write_menu_row(dest, sys_img, db, font_id):
    """The text of a party row that **does not depend on the actor**: the
    level term, the status and the HP term.

    It is a single block for the four rows and for all actors, and that is
    the difference with before: the name, the level number and the maximum
    —the only things that changed from one actor to another— are composed by
    the ROM with glyphs, so this block is not multiplied by the number of
    actors.

    The current HP does not go here either, and that is the fix of
    2026-09-13: this block is baked when converting and uploaded as is, so
    whatever number it carried could never change. taro reported it while
    playing —"HP goes down in battle, but the menu always shows 40"—; the 40
    is the maximum of Talan, who leads the intro.
    """
    from port import window as window_mod

    def write(x, y, text, color=0):
        return window_mod.draw_line(dest, sys_img, x, y, text,
                                     color=color, font_id=font_id)

    _write_level_term(dest, sys_img, MENU_TEXT_X, 2 + LINE, db,
                      font_id)
    write(MENU_TEXT_X + MENU_STATUS_DX, 2 + LINE, db.term_normal_status)
    write(MENU_TEXT_X, 2 + 2 * LINE, db.term_hp_short, color=1)


def digits_of(value, how_many):
    """The digits of a number capped at `how_many`, without leading zeros.

    It is `gold_digits` generalized: the menu's gold and each actor's HP
    use it, which the ROM writes with the same one-cell blocks.
    """
    return [int(c) for c in str(max(0, min(value, 10 ** how_many - 1)))]


def menu_hp(db, actor, hp=None):
    """The HP the actor's row has to show: those in `hp` if present, and
    otherwise the maximum for its level, which is what the game starts
    with."""
    if hp is not None and actor in hp:
        return hp[actor]
    return param_of(db.actors[actor], "maxhp")


def _paste_hp(paste, menu, row, how_much):
    """The HP digits of a party row, right-aligned.

    It is what the ROM does in `menu_hp_write`, with the same cells and in
    the same columns; what is left over on the left stays blank.
    """
    digits = digits_of(how_much, MENU_HP_DIGITS)
    _paste_text(paste, menu, "".join(str(c) for c in digits),
                row * MENU_ACTOR_ROWS + MENU_HP_ROW,
                MENU_HP_COL + MENU_HP_DIGITS - len(digits))


def gold_digits(gold):
    """The digits that get written, without leading zeros: 0 is "0"."""
    return digits_of(gold, MENU_GOLD_DIGITS)


def slots_screen(sys_img, db, slots, font_id=None, actors=(),
                 game_dir=None, letters=""):
    """The slot screen's tiles, its palettes and its cell blocks.

    Returns `(tiles, paletas, cabeceras, filas, caras, menu)`:

    * `paletas[0]` is the text's, `paletas[1]` that of the menu's disabled
      commands, and the ones after, one per face.
    * `cabeceras[modo]` are the cells of the screen's title, with `mode` 0
      for loading and 1 for saving. Both texts come from the LDB
      —`load_game_message` and `save_game_message`, which in ABL say "Load
      which slot?" and "Save in which slot?"—.
    * `filas[ranura][llena][cursor]` are the cells of a whole row, with the
      face, name and level cells blank.
    * `caras[actor]` are the 36 cells of the face, with its palette set, for
      the `actors` that have one. The ROM writes it over the row according
      to the party the save stored, and `render_slots` does the same.

    * `menu` are the pause menu's blocks, which shares bank and palette:
      `opciones[orden][deshabilitada]`, `cursor`, `moneda`, `row` —the text
      of a party row, a single one for all— and `glifos[letra]`, the two
      cells of each letter the ROM composes. The ten digits are there: they
      are the ones that write the gold and the HP.

    All the variants are drawn before deduplicating, for the usual reason:
    there is a single tile bank.
    """
    from PIL import Image
    from port import window as window_mod

    def layer():
        return Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

    def write(dest, x, y, text):
        if text:
            window_mod.draw_line(dest, sys_img, x, y, text,
                                  font_id=font_id)

    # First all the text layers, so the colors can be gathered at once.
    layers = []
    for mode, text in enumerate((db.term_load_message, db.term_save_message)):
        image = layer()
        write(image, SLOT_X, HEADER_Y, text)
        layers.append(("cabecera", mode, image))
    for number in range(slots):
        for full in (0, 1):
            for cursor in (0, 1):
                image = layer()
                y = SLOT_Y + number * SLOT_STEP
                if cursor:
                    write(image, SLOT_X - 16, y + 2, ">")
                for n, line in enumerate(_slot_text(number, db, full)):
                    write(image, SLOT_X, y + 2 + n * LINE, line)
                if full:
                    # The level term goes in the row and not in the actor's
                    # layer: it is the same for everyone, and a slot without a
                    # save does not show it.
                    _write_level_term(image, sys_img, SLOT_X,
                                      y + 2 + 2 * LINE, db, font_id)
                layers.append(("fila", (number, full, cursor), image))
    # The pause menu's, in the same bank. Each on the topmost row it gets: the
    # blocks work on any other because they are aligned.
    from port import window as window_mod
    for option, text in enumerate(db.term_menu):
        for disabled in (0, 1):
            image = layer()
            window_mod.draw_line(
                image, sys_img, MENU_OPT_COL * CELL,
                MENU_OPT_Y + option * MENU_OPT_STEP + 2, text,
                color=3 if disabled else 0, font_id=font_id)
            layers.append(("menu_option", (option, disabled), image))
    image = layer()
    write(image, MENU_CURSOR_COL * CELL, MENU_OPT_Y + 2, ">")
    layers.append(("menu_cursor", None, image))
    for letter in glyphs_of(db, actors, letters):
        image = layer()
        write(image, GLYPH_COL * CELL + GLYPH_DX,
              GLYPH_ROW * CELL + GLYPH_DY, letter)
        layers.append(("menu_glifo", letter, image))
    image = layer()
    window_mod.draw_line(image, sys_img, MENU_CURRENCY_COL * CELL,
                          MENU_GOLD_Y + 2, db.term_gold, color=1,
                          font_id=font_id)
    layers.append(("menu_currency", None, image))
    image = layer()
    _write_menu_row(image, sys_img, db, font_id)
    layers.append(("menu_row", None, image))
    # The experience term, loose like a glyph: sprites draw it. Up to two
    # letters, which are the twelve pixels `DrawActorExp` leaves it before
    # the digits.
    image = layer()
    window_mod.draw_line(image, sys_img, GLYPH_COL * CELL,
                          GLYPH_ROW * CELL + GLYPH_DY,
                          (db.term_exp_short or "")[:2], color=1,
                          font_id=font_id)
    layers.append(("menu_exp_finished", None, image))

    # The disabled commands go in **their own palette**, number 1: system
    # color 3 is a gradient that, added to the text's, gives 18 colors, and
    # 4bpp fits 15. It costs the faces one palette.
    def gray(kind, key):
        return kind == "menu_option" and key[1]

    seen, seen_gray = collections.Counter(), collections.Counter()
    for kind, key, image in layers:
        counts = seen_gray if gray(kind, key) else seen
        for r, g, b, a in image.get_flattened_data():
            if a:
                counts[(r >> 3, g >> 3, b >> 3)] += 1
    for count, what in ((len(seen), "the text of the slots and the menu"),
                        (len(seen_gray), "the disabled commands")):
        if count > 15:
            raise SystemExit("%s uses %d colors and 4bpp fits 15"
                             % (what, count))
    palette = [BLACK] + sorted(seen, key=lambda c: (-seen[c], c))
    index = {color: i for i, color in enumerate(palette)}
    gray_palette = [BLACK] + sorted(seen_gray,
                                    key=lambda c: (-seen_gray[c], c))
    gray_index = {color: i for i, color in enumerate(gray_palette)}

    empty = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, offset = [empty], {empty: 0}
    headers = [None, None]
    rows = [[[None, None], [None, None]] for _ in range(slots)]
    menu = {"opciones": [[None, None] for _ in range(MENU_OPTIONS)],
            "cursor": None, "glifos": {}, "moneda": None, "fila": None}
    for kind, key, image in layers:
        if kind == "menu_option":
            option, disabled = key
            menu["opciones"][option][disabled] = _cell_block(
                image, (MENU_OPT_Y + option * MENU_OPT_STEP) // CELL, 2, tiles,
                offset, gray_index if disabled else index,
                MENU_OPT_COL, MENU_OPT_COLS, 1 if disabled else 0)
        elif kind == "menu_cursor":
            menu["cursor"] = _cell_block(
                image, MENU_OPT_Y // CELL, 2, tiles, offset, index,
                MENU_CURSOR_COL, 1)
        elif kind == "menu_glifo":
            menu["glifos"][key] = _cell_block(
                image, GLYPH_ROW, 2, tiles, offset, index, GLYPH_COL, 1)
        elif kind == "menu_currency":
            menu["moneda"] = _cell_block(
                image, MENU_GOLD_Y // CELL, 2, tiles, offset, index,
                MENU_CURRENCY_COL, MENU_CURRENCY_COLS)
        elif kind == "menu_row":
            menu["fila"] = _cell_block(
                image, 0, MENU_ACTOR_ROWS, tiles, offset, index,
                MENU_ACTOR_COL, MENU_ACTOR_COLS)
        elif kind == "menu_exp_finished":
            menu["exp_termino"] = _cell_block(
                image, GLYPH_ROW, 2, tiles, offset, index, GLYPH_COL,
                MENU_EXP_TERM_CELLS)
        elif kind == "cabecera":
            headers[key] = _cell_block(
                image, HEADER_Y // CELL, HEADER_ROWS, tiles, offset, index)
        else:
            number, full, cursor = key
            row0 = (SLOT_Y + number * SLOT_STEP) // CELL
            rows[number][full][cursor] = _cell_block(
                image, row0, SLOT_ROWS, tiles, offset, index)

    # And the faces, each with its palette, pasted at the top left of the
    # first row to cut them into cells with the same function.
    palettes, faces = [palette, gray_palette], {}
    # Which faces had to borrow a palette: it shows in the converter's
    # report, same as with the sprites.
    face_lent = set()
    for actor in actors:
        face = face_of(db, actor, game_dir)
        if face is None:
            continue
        colors, face_index = _face_palette(face)
        if len(palettes) > FACE_PALETTES_MAX:
            # No BG2 palette left: **one is lent to it**, which is the same
            # rule `picture.fits` runs with the sprites and the same reason of taro's
            # —if we cannot include everyone, the whole project falls apart—.
            # Each color of the face goes to the nearest by luma in the
            # palette it is missing the fewest from, and the face shows with
            # colors that are not its own.
            #
            # It was needed when putting in the whole of Lashe City: the faces
            # are one palette each, six are left, and from map 20 on Arden,
            # Saldra, the Rat Tracks Gang Member and AG7-17 can join the party,
            # that is eight. The alternative was leaving out Rat Tracks B2 and
            # the whole car chain, which are the path of the story.
            which, face_index = _lent_face(colors, face_index, palettes)
            face_lent.add(actor)
        else:
            which = len(palettes)
            palettes.append(colors)
        image = layer()
        image.paste(face, (FACE_COL * CELL, SLOT_Y))
        faces[actor] = _cell_block(
            image, SLOT_Y // CELL, FACE_CELLS, tiles, offset, face_index,
            FACE_COL, FACE_CELLS, which)
    if face_lent:
        print("  faces without a palette of their own, drawn with another's: %s"
              % ", ".join(db.actors[a].name for a in sorted(face_lent)))
    if len(tiles) > SLOT_TILES_MAX:
        raise SystemExit(
            "the slot screen and the menu gather %d tiles and their bank "
            "fits %d" % (len(tiles), SLOT_TILES_MAX))
    return tiles, palettes, headers, rows, faces, menu


def _painter(outside, tiles, palettes):
    """A function that pastes a block of cells onto `outside`, as the ROM does:
    tile and palette of each tilemap word."""
    px = outside.load()

    def paste(cells, row0, col0=0, cols=COLS):
        for i, word in enumerate(cells):
            tx = (col0 + i % cols) * CELL
            ty = (row0 + i // cols) * CELL
            cell = tiles[word & 0x3FF]
            palette = palettes[(word >> 10) & 7]
            for y in range(CELL):
                if ty + y >= HEIGHT:
                    break
                for x in range(CELL):
                    value = cell[y][x]
                    if value:
                        px[tx + x, ty + y] = tuple(v << 3 for v in palette[value])
    return paste


def _paste_sprite(outside, tiles, palettes, word, x, y):
    """An 8x8 tile at any pixel, like a sprite: what is transparent lets
    what was there show through. The palette is the word's, which the ROM
    copies to the sprites'."""
    px = outside.load()
    cell = tiles[word & 0x3FF]
    palette = palettes[(word >> 10) & 7]
    for dy in range(CELL):
        for dx in range(CELL):
            value = cell[dy][dx]
            if value and 0 <= x + dx < WIDTH and 0 <= y + dy < HEIGHT:
                px[x + dx, y + dy] = tuple(v << 3 for v in palette[value])


def _paste_exp(outside, tiles, palettes, menu, row, text):
    """The experience line of a party row, in sprites: the term and the
    thirteen letters of `text`, at six pixels. It is what `menu_exp_paint`
    does in the ROM; spaces get no sprite."""
    y = row * MENU_ACTOR_ROWS * CELL + MENU_EXP_Y - GLYPH_DY
    for n, word in enumerate(menu["exp_termino"]):
        _paste_sprite(outside, tiles, palettes, word,
                      MENU_EXP_X + (n % MENU_EXP_TERM_CELLS) * CELL,
                      y + (n // MENU_EXP_TERM_CELLS) * CELL)
    for n, letter in enumerate(text):
        if letter == " ":
            continue
        x = MENU_EXP_X + MENU_EXP_NUM_DX + n * font.WIDTH - GLYPH_DX
        top, bottom = menu["glifos"][letter]
        _paste_sprite(outside, tiles, palettes, top, x, y)
        _paste_sprite(outside, tiles, palettes, bottom, x, y + CELL)


def _paste_text(paste, menu, text, row, col):
    """A text composed one letter per cell, as the ROM writes it."""
    for n, letter in enumerate(text):
        paste(menu["glifos"][letter], row, col + n, 1)


def _paste_actor_row(paste, menu, faces, db, row, actor, hp=None,
                     levels=None):
    """A row of the party panel: the fixed block, the face and the three
    strips that depend on the actor. It is what `menu_party_paint` does, in
    the same order, and that is why the menu and the actor choice share
    it."""
    row0 = row * MENU_ACTOR_ROWS
    paste(menu["fila"], row0, MENU_ACTOR_COL, MENU_ACTOR_COLS)
    if actor in faces:
        paste(faces[actor], row0, MENU_ACTOR_COL, FACE_CELLS)
    _paste_text(paste, menu, name_text(db, actor),
                row0 + MENU_NAME_ROW, MENU_NAME_COL)
    level = (levels or {}).get(actor)
    _paste_text(paste, menu, level_text(db, actor, level),
                row0 + MENU_LEVEL_ROW, MENU_LEVEL_COL)
    _paste_text(paste, menu, max_text(db, actor, level),
                row0 + MENU_HP_ROW, MENU_MAX_COL)
    _paste_hp(paste, menu, row, menu_hp(db, actor, hp))


def render_menu(sys_img, db, slots, party, gold, chosen=0,
                save_allowed=True, font_id=None, actors=None,
                game_dir=None, hp=None, levels=None, exps=None):
    """The pause menu as the console has to show it.

    `party` are the actors in order, `gold` the gold, `chosen` the command
    with the cursor and `save_allowed` what `ChangeSaveAccess` left.
    `actors` is the ROM's list —those who can join the party,
    `possible_members` in the converter—, which decides the tile bank;
    without it, the party. It is built with the same blocks the ROM uploads,
    like `render_slots`.

    `hp` is what the save has in `FAR_HP`, from actor to HP: without it they
    are assumed full, which is what the game starts with. It goes apart from
    the actor's block because the block is baked and this changes with every
    battle. `levels`, from actor to level, is the same for the level and the
    maximum: without it, the starting ones. `exps`, from actor to experience,
    the same for the experience line, which also looks at the level.
    """
    from PIL import Image
    actors = sorted(set(actors if actors is not None else party))
    tiles, palettes, _, _, faces, menu = slots_screen(
        sys_img, db, slots, font_id, actors, game_dir)
    outside = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    paste = _painter(outside, tiles, palettes)
    for option in range(MENU_OPTIONS):
        done = option in MENU_DONE and (option != MENU_SAVE
                                        or save_allowed)
        paste(menu["opciones"][option][0 if done else 1],
              (MENU_OPT_Y + option * MENU_OPT_STEP) // CELL, MENU_OPT_COL,
              MENU_OPT_COLS)
    paste(menu["cursor"], (MENU_OPT_Y + chosen * MENU_OPT_STEP) // CELL,
          MENU_CURSOR_COL, 1)
    digits = gold_digits(gold)
    _paste_text(paste, menu, "".join(str(c) for c in digits),
                MENU_GOLD_Y // CELL, MENU_CURRENCY_COL - len(digits))
    paste(menu["moneda"], MENU_GOLD_Y // CELL, MENU_CURRENCY_COL,
          MENU_CURRENCY_COLS)
    for row, actor in enumerate(list(party)[:MENU_PARTY_ROWS]):
        if actor in actors:
            _paste_actor_row(paste, menu, faces, db, row, actor, hp,
                             levels)
    # The experience goes on top of everything, like sprites over the
    # background, and only in the menu: `Window_ActorTarget` does not show
    # it.
    for row, actor in enumerate(list(party)[:MENU_PARTY_ROWS]):
        if actor in actors:
            _paste_exp(outside, tiles, palettes, menu, row, exp_text(
                db, actor, (levels or {}).get(actor),
                (exps or {}).get(actor)))
    return outside


# The actor choice, `Scene_ActorTarget`: the menu's party panel, and as in
# RM2k, three System windows on BG1 —like the item and equipment ones, see
# `ITEM_WINDOWS`— and the red bar over the marked row. RM2k puts the help
# with the item's name on the left and "Owned Items" in red with the quantity
# below it, and the party on the right. Here the left column reaches x = 104:
# the bank's faces are 48 wide but what shows of them starts twelve pixels in,
# at x = 108, so the party window can start left of the menu row (x = 96)
# without covering them. At 104 eleven 8-pixel letters fit, and the name goes
# on two lines: eleven is what "Sandwich-HP" needs.
#
# The name is written with the menu bank's glyphs —one letter per cell, like
# the actor's name—, so the bank also carries the medicines' letters. "Owned
# Items" does not: it is **baked into BG1**, in red and at the font's six
# pixels, because at eight its eleven letters fill the window and leave no
# room for the quantity, and because the red has no free palette on BG2. The
# quantity does, with the glyphs, on the right.
#
# To choose whom to equip, the screen is the same without the two windows on
# the left: there is no item.
#
# A uses the medicine on the marked row and the screen stays, with that row's
# HP and the quantity up to date: see `medicine_use` in
# tools/runtime/medicine.s. This draws the HP passed in `hp`, so after healing
# it is enough to pass the new ones.
TARGET_LEFT = 104
TARGET_NAME_HEIGHT = 48
TARGET_COUNT_HEIGHT = 32
TARGET_PARTY = (TARGET_LEFT, 0, WIDTH - TARGET_LEFT, HEIGHT)
TARGET_WINDOWS = ((0, 0, TARGET_LEFT, TARGET_NAME_HEIGHT),
                  (0, TARGET_NAME_HEIGHT, TARGET_LEFT,
                   TARGET_COUNT_HEIGHT),
                  TARGET_PARTY)
TARGET_NAME_COL = 1
TARGET_NAME_ROW = 1        # y = 8, and the second line at y = 24
TARGET_NAME_WIDTH = (TARGET_LEFT - 8) // CELL - TARGET_NAME_COL  # 11
TARGET_COUNT_ROW = (TARGET_NAME_HEIGHT + 8) // CELL                # 7
TARGET_COUNT_COL = TARGET_NAME_COL + TARGET_NAME_WIDTH - 2    # 10
# The bar goes over the row's three lines of text, as in RM2k, and not over
# the face: four pixels before the text and up to four from the edge, and
# from two pixels inside the row, so as not to touch the top frame. It ends at
# 48, on a cell boundary, and not at 50, which is where the third line ends:
# with the bottom tip mid-cell it was 64 tiles, which is exactly what fits
# before the tilemap, and this way it is 60. What is left out is the shadow of
# the HP letters.
TARGET_BAR = (MENU_TEXT_X - 4, 2, WIDTH - MENU_TEXT_X, 3 * LINE - 2)
# BG1's colors go in 128..143: they are those of sprite palette 0, which on
# this screen are off, and which `menu_exp_close` restores on closing the
# menu. There is no room in 0..127: they are the menu bank's palettes.
TARGET_CGRAM = 128
TARGET_COLORS_MAX = 16
# BG1's tiles and tilemap, after the menu's tilemap ($3C00..$4000): BG1 has
# its own base at $4000, so they do not touch BG2's bank. What matters is that
# everything stays in the layouts' BG1 bank, which is what `load_map`
# restores on the way back: see `_check_target` in the converter.
TARGET_VRAM = 0x4000
TARGET_MAP = 0x4800


def name_in_lines(name, width=TARGET_NAME_WIDTH, rows=2):
    """The name split into lines of `width`, by words; a word that does not
    fit is cut where it reaches. Padded with spaces, which are what erase
    whatever was there."""
    out, line = [], ""
    for word in name.strip().split():
        while len(word) > width:
            if line:
                out.append(line)
                line = ""
            out.append(word[:width])
            word = word[width:]
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    return [r.ljust(width) for r in (out + [""] * rows)[:rows]]


def target_windows(sys_img, db, with_item=True, bar=None, font_id=None):
    """The actor choice's windows, in RGBA and the size of the screen: what
    BG1 draws. With `with_item`, the two on the left with "Owned Items"; with
    `bar`, the cursor on that party row."""
    from PIL import Image
    from port import window as window_mod
    outside = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    for x, y, width, height in (TARGET_WINDOWS if with_item
                                else (TARGET_PARTY,)):
        image = window_mod.window(sys_img, width, height)
        outside.paste(image, (x, y), image)
    if with_item:
        window_mod.draw_line(
            outside, sys_img, TARGET_NAME_COL * CELL + GLYPH_DX,
            TARGET_COUNT_ROW * CELL + GLYPH_DY,
            lcf_owned_term(db), color=1, font_id=font_id)
    if bar is not None:
        x, y, width, height = TARGET_BAR
        image = window_mod.cursor(sys_img, width, height)
        outside.paste(image, (x, bar * MENU_ACTOR_ROWS * CELL + y), image)
    return outside


def lcf_owned_term(db):
    """"Owned Items": `possessed_items` from the LDB terms."""
    from rpgmaker import lcf
    return lcf.to_string(db.terms["possessed_items"])


def target_layers(sys_img, db, font_id=None):
    """What `borders` needs from the actor choice: with an item and without,
    each without a cursor and with the cursor on each party row, from the
    first cell row of the actor's row."""
    return [(target_windows(sys_img, db, with_item, None, font_id),
             [(target_windows(sys_img, db, with_item, k, font_id),
               k * MENU_ACTOR_ROWS, MENU_ACTOR_ROWS)
              for k in range(MENU_PARTY_ROWS)])
            for with_item in (True, False)]


def compact_target(tilemaps):
    """What the ROM stores of the tilemaps of
    `borders(target_layers(...))`, which is much less than what `borders`
    returns.

    * **A single tilemap**, the with-item one: the without-item one is the
      same with the cells of the two left windows at zero —the columns left
      of `TARGET_LEFT`, down to the bottom of the "Owned Items" one—, and
      the ROM erases them when uploading it.
    * **The bar, only where it changes**: the rectangle covering what differs
      between each party row with the bar and without it, the same for the
      four rows, and which has to be the same with and without an item.

    Returns `(mapa, barras, fila0, filas, col0, cols, borrar_filas,
    borrar_cols)`: `barras[k]` are the `filas` by `cols` words of party row
    `k`, from row `row0` of the actor's row and column `col0`. If any of
    that does not hold, it is an error and not a different tilemap: the ROM
    assumes both things.
    """
    (with_map, bars_with), (without_map, bars_without) = tilemaps
    erase_cols = TARGET_LEFT // CELL
    erase_rows = (TARGET_NAME_HEIGHT + TARGET_COUNT_HEIGHT) // CELL
    expected = [0 if (i // COLS < erase_rows and i % COLS < erase_cols)
                else p for i, p in enumerate(with_map)]
    if expected != without_map:
        raise SystemExit("the actor choice's without-item tilemap is not the "
                         "with-item one with the left windows erased")
    distinct = set()
    for k, bar in enumerate(bars_with):
        base = with_map[k * MENU_ACTOR_ROWS * COLS:
                        (k + 1) * MENU_ACTOR_ROWS * COLS]
        distinct |= {(i // COLS, i % COLS)
                     for i, (a, b) in enumerate(zip(base, bar)) if a != b}
    row0 = min(f for f, _ in distinct)
    rows = max(f for f, _ in distinct) + 1 - row0
    col0 = min(c for _, c in distinct)
    cols = max(c for _, c in distinct) + 1 - col0
    if col0 < erase_cols:
        raise SystemExit("the actor choice's bar reaches column %d, which "
                         "belongs to the item windows" % col0)

    def clip(bar):
        return [bar[(row0 + f) * COLS + col0 + c]
                for f in range(rows) for c in range(cols)]

    bars = [clip(b) for b in bars_with]
    if bars != [clip(b) for b in bars_without]:
        raise SystemExit("the actor choice's bar is not the same with and "
                         "without an item")
    return with_map, bars, row0, rows, col0, cols, erase_rows, erase_cols


def render_target(sys_img, db, slots, party, chosen=0, font_id=None,
                  actors=None, game_dir=None, hp=None, item=None,
                  amount=0):
    """The actor choice as the console has to show it.

    It shares the party panel with the menu, so it also writes the HP:
    `menu_party_paint` paints them, which is the same routine on both
    sides. `item` is the medicine being used, with `amount` how many are
    left; without it, it is the choice of whom to equip.
    """
    from PIL import Image
    actors = sorted(set(actors if actors is not None else party))
    name = db.items[item].name if item else ""
    tiles, palettes, _, _, faces, menu = slots_screen(
        sys_img, db, slots, font_id, actors, game_dir, name)
    outside = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    windows = target_windows(sys_img, db, bool(item), chosen, font_id)
    outside.paste(windows, (0, 0), windows)
    paste = _painter(outside, tiles, palettes)
    for row, actor in enumerate(list(party)[:MENU_PARTY_ROWS]):
        if actor in actors:
            _paste_actor_row(paste, menu, faces, db, row, actor, hp)
    if item:
        for n, line in enumerate(name_in_lines(name)):
            _paste_text(paste, menu, line, TARGET_NAME_ROW + 2 * n,
                        TARGET_NAME_COL)
        _paste_text(paste, menu, "%2d" % min(amount, 99),
                    TARGET_COUNT_ROW, TARGET_COUNT_COL)
    return outside


def render_items(sys_img, db, inventory, chosen=0, top=0, font_id=None,
                 items=None):
    """The item screen as the console has to show it.

    `inventory` maps item number to how many there are; `items` are the
    ones the ROM knows —without it, the inventory's—; `chosen` is the
    cursor's position in the list and `top` the first visible one. It is
    built with the same cells the ROM writes.
    """
    from PIL import Image
    items = sorted(items if items is not None
                   else [i for i, n in inventory.items() if n > 0])
    tiles, palettes, glyphs = items_screen(sys_img, font_id)
    outside = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    listed = item_list(items, inventory)
    # The cursor is part of the windows: see `ITEM_BAR_X`.
    windows = item_windows(sys_img, chosen - top if listed else None)
    outside.paste(windows, (0, 0), windows)
    paste = _painter(outside, tiles, palettes)

    def write(text, row0, col0, gray=0):
        for n, c in enumerate(text):
            paste(glyphs[gray][c], row0, col0 + n, 1)

    if listed:
        for n, line in enumerate(split_description(
                db.items[listed[chosen]].description)):
            write(line, ITEM_DESC_Y // CELL + 2 * n, ITEM_DESC_COL)
    for row in range(ITEM_ROWS):
        k = top + row
        if k >= len(listed):
            break
        item = db.items[listed[k]]
        row0 = ITEM_LIST_Y // CELL + 2 * row
        gray = 0 if item_usable(item) else 1
        write(item_text(item.name, ITEM_NAME_WIDTH), row0,
              ITEM_NAME_COL, gray)
        write(":%2d" % min(inventory[listed[k]], 99), row0,
              ITEM_COLON_COL, gray)
    return outside


def render_slots(sys_img, db, slots, full_slots, chosen, mode=0, font_id=None,
                 parties=None, game_dir=None, levels=None):
    """The slot screen as the console has to show it.

    `full_slots` is a sequence of booleans, one per slot; `chosen`, where the
    cursor is; `mode`, 0 for loading and 1 for saving; `parties`, per full
    slot, the actors of the saved party, which set the first one's name and
    the faces of up to FACES_MAX; `levels`, per slot, the level the leader
    had in that save —without it, the starting one—.

    It is built with **the same cell blocks the ROM uploads**, not drawing
    the text again nor pasting the face: if it were drawn here with the font
    and there with the tiles, exactly the step that can go wrong would be
    left out.
    """
    from PIL import Image
    parties = parties or {}
    actors = sorted({a for g in parties.values() for a in g})
    tiles, palettes, headers, rows, faces, menu = slots_screen(
        sys_img, db, slots, font_id, actors, game_dir)
    outside = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    paste = _painter(outside, tiles, palettes)

    paste(headers[mode], HEADER_Y // CELL)
    for number in range(slots):
        row0 = (SLOT_Y + number * SLOT_STEP) // CELL
        full = bool(full_slots[number]) or number in parties
        paste(rows[number][1 if full else 0][
            1 if number == chosen else 0], row0)
        if not full:
            continue
        party = list(parties.get(number, ()))
        # The leader's name and level, composed with glyphs over the row, and
        # the faces, which are blocks. An actor without a face draws nothing,
        # which is what `DrawFace` does with an empty name.
        if party and party[0] in actors:
            _paste_text(paste, menu,
                        name_text(db, party[0], NAME_COLS),
                        row0 + NAME_ROW, NAME_COL)
            _paste_text(paste, menu,
                        level_text(db, party[0],
                                   (levels or {}).get(number)),
                        row0 + LEVEL_ROW, LEVEL_COL)
        for place, actor in enumerate(party[:FACES_MAX]):
            if actor in faces:
                paste(faces[actor], row0, FACE_COL + place * FACE_STEP,
                      FACE_CELLS)
    return outside
