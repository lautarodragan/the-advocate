"""How the 64 KB of VRAM are laid out: the tilemap window, the six layouts
a map can get, the save slots screen, and the checks that every screen lands
where the ROM assumes in every layout.

The input is how many tiles each layer spends; the output, which layout the
map gets. The ROM chooses nothing: the layout travels in the `.inc`.
"""

from port import menus as menus_mod
from port import screens as screens_mod
from port.snes_format import BYTES_PER_TILE


# --- the tilemap window -----------------------------------------------------
# The PPU tilemap doesn't go beyond 64x64 cells, and on top of that VRAM has to
# be shared with the tiles, so the window left for it is 64x32: 512x256 pixels
# against the 256x224 of the screen. The game's maps reach 1000x80 cells, so
# the whole map is never in VRAM: the ROM keeps redrawing the column and the
# row that come in while the camera moves. What the ROM stores instead of the
# expanded tilemap is in `blocks.py`.
WINDOW_W, WINDOW_H = 64, 32     # the tilemap window that lives in VRAM
MAP_LAYOUT = 1                  # two 32x32 screens side by side, which is 64x32


# --- the VRAM layout --------------------------------------------------------
# The 64 KB can't be split any way one likes: the base of the sprite tiles
# goes in steps of 16 KB, that of each background in steps of 8 KB and that of
# each tilemap in steps of 2 KB. Which layout applies is decided by the
# converter and travels in the .inc: the ROM chooses nothing.
#
# Every map carries the message window —since 2026-09-17 it isn't optional; a
# map without a text window doesn't exist in practice— and there are three
# layouts that make room for it. Until that day there were three others
# without it. The window needs 8 KB of its own tiles —the text is 240 tiles
# and there is no way to lower that, because a 6 px glyph doesn't align to
# 8-pixel cells and it has to be composed pixel by pixel— plus **2 KB of its
# own tilemap**, and the 64 KB were already 100% allocated.
#
# What makes the tiles part possible is that `above` and `window` end up
# **adjacent**: BG2 has a single base and its tile indices are 10 bits, so 0
# to 255 fall in the first 8 KB bank and 256 to 511 in the next. That forces
# putting the sprites first, because the OBJ base goes in steps of 16 KB and
# a background's in steps of 8.
#
# And the tilemap of its own comes from trimming tiles from the sprites, which
# is where they are left over. Measured over the 318 maps that convert, the
# one that spends the most uses **380 sprite tiles**: 253 use 192 or fewer, 58
# between 193 and 256, and 7 between 257 and 380. With 448 none falls short,
# and the 2 KB freed land at word $1C00, which is a multiple of 1024 and
# therefore a valid tilemap base.
#
#   sprites   $0000  14 KB  448 4bpp tiles      OBJ base at 0
#   ventana_map $1C00 2 KB  the window's 32x32 tilemap
#   tiles     $2000  24 KB  384 8bpp tiles
#   encima    $5000   8 KB  256 tiles           <- the BG2 base
#   ventana   $6000   8 KB  256 tiles           <- indices 256..511
#   tilemaps  $7000   8 KB
#
# The second trades sprite tiles for background tiles, for the maps that
# spend more background, and there the 2 KB can't come from the sprites —those
# maps use up to 320— but from the background: 480 tiles instead of 512.
#
#   sprites     $0000   8 KB  256 tiles
#   tiles       $1000  30 KB  480 8bpp tiles
#   ventana_map $4C00   2 KB
#   encima      $5000   8 KB
#   ventana     $6000   8 KB
#   tilemaps    $7000   8 KB
#
# Measured over the 318 maps that convert: 309 fit in the first, 6 in the
# second and 3 didn't fit in either —8, 66 and 250—. **8 no longer**: on
# 2026-09-07, with the window moved to palette 0, its background tiles went
# down to 400 and it fits in the second layout. The number above is from
# before that and wasn't measured again over the 318.
#
# The old number written here was 2, and it was wrong for a reason worth
# stating: `vram_layout` didn't check that the background tiles fit in the
# bank of the chosen layout. `MAX_TILES` is 1024, which is the cap of the
# tilemap index and not of the bank, so maps 66 and 250 —518 and 620
# background tiles— took the 512 layout and spilled over the upper layer. It
# was never seen because no recipe asks for a window for them.
# The layout above gave 384 background tiles, and the one after it traded
# sprites for background. Both gave **256 tiles to the upper layer**, and
# measured that is a waste: over the 328 maps that convert, the median use is
# **1 tile** and 326 fit in 128. Lowering it to 128 frees 4 KB, which at 8bpp
# is 64 more background tiles.
#
# It was needed on 2026-09-07, when drawing all the events —see `fits`— took
# map 8 to 400 background tiles and 347 sprite ones, and there was no layout
# that gave it both.
#
# The puzzle is one of alignment and not of space: `BG12NBA` fixes the BG1 and
# BG2 bases at multiples of 8 KB, `OBSEL` that of the objects at multiples of
# 16 KB, and the tilemaps at multiples of 1 KB. The tilemaps moved to $5800
# and $7800, which are the only two gaps left aligned in the four layouts.
LAYOUT_WINDOW = {"sprites": (0x0000, 448), "ventana_map": (0x1C00, 1),
                 "tiles": (0x2000, 448), "mapa": (0x5800, 1),
                 "encima": (0x6000, 128), "ventana": (0x6800, 256)}
LAYOUT_WINDOW_BG = {"sprites": (0x0000, 256), "tiles": (0x1000, 480),
                    "ventana_map": (0x4C00, 1), "mapa": (0x5800, 1),
                    "encima": (0x6000, 128), "ventana": (0x6800, 256)}

# And the third, which does the opposite of the second: it trades background
# tiles for sprite tiles. Delcentric Factory asked for it —map 17, the road to
# the auditorium—, which spends **217 background tiles and 475 sprite ones**
# and didn't fit in either of the two: 28 character slots are exactly 448
# tiles, and on top of that go the 8 timer glyphs and the 19 raindrops. That
# is 27 tiles too many over the 448 of the first layout, and the rain can't be
# removed because the weather persists across map changes and it rains in the
# opening.
#
#   sprites     $0000  16 KB  512 4bpp tiles      OBJ base at 0
#   tiles       $2000  24 KB  384 8bpp tiles      <- the BG1 base
#   ventana_map $5000   2 KB  the window's 32x32 tilemap
#   (free)      $5400   2 KB
#   tilemap     $5800   4 KB
#   encima      $6000   8 KB  128 tiles           <- the BG2 base
#   ventana     $6800   8 KB  256 tiles           <- indices 128..383
#   tilemap     $7800   4 KB
#
# 512 is the hardware cap and not a choice: the OAM name field is nine bits,
# and with `OBSEL`'s name select at zero both tables end up adjacent, which is
# exactly what `OBSEL_VALUE` emits. That is, this layout gives the sprites all
# the console can address.
#
# The 2 KB free at $5400 are the price of alignment: the BG1 base goes in
# steps of 8 KB, so lowering the background from 448 to 384 tiles frees 8 KB
# and the window needs 2. They can't be used for anything because there is
# nothing else to place.
#
# **It goes last on purpose.** `vram_layout` returns the first one that fits,
# so no map that already had a layout changes layout because of this: only
# the ones that didn't fit in the other two take it.
LAYOUT_WINDOW_SPRITE = {"sprites": (0x0000, 512), "tiles": (0x2000, 384),
                        "ventana_map": (0x5000, 1), "mapa": (0x5800, 1),
                        "encima": (0x6000, 128), "ventana": (0x6800, 256)}

# And the fourth, the only one that **moves the map's tilemap**: `Sector 34
# With Car` asked for it, map 38, which spends **476 background tiles and 347
# sprite ones** and didn't fit in any of the three —it lacked 28 background
# tiles in the first and 91 sprite ones in the second—. In bytes it did fit;
# what didn't allow it was the tilemap fixed at $5800, which cut the BG1 bank
# at 448 tiles. Moving it down to the 2 KB left free between the sprites and
# the background:
#
#   sprites     $0000  12 KB  384 4bpp tiles      OBJ base at 0
#   mapa        $1800   4 KB  the BG1 tilemap     <- down here, not at $5800
#   tiles       $2000  30 KB  480 8bpp tiles      <- the BG1 base
#   ventana_map $5C00   2 KB  the window's 32x32 tilemap
#   encima      $6000   8 KB  128 tiles           <- the BG2 base
#   ventana     $6800   8 KB  256 tiles           <- indices 128..383
#   tilemap     $7800   4 KB  the upper layer's, which doesn't move
#
# 480 is the ceiling with 347 sprites even if the tilemap could go anywhere
# —measured by enumerating every base the hardware allows—: the BG1 bank
# starts at $2000 because the sprites go past $1000, and the window's tilemap
# needs a base that is a multiple of 1024 words after the background.
#
# The tilemap moving is paid for by `build_column` and `build_row`, which add
# `FAR_VRAM_MAP` instead of a constant, and by the step to the upper layer in
# `push_strips`, which masks instead of adding a fixed distance. That is why
# **both bases have to be multiples of 2048 words**, and the map's can't be
# zero: `col_addr` at zero means "no column". `_check_splits` checks it.
#
# **It goes last on purpose**, for the same reason as the previous one: no
# map that already fit changes layout.
LAYOUT_WINDOW_BOTH = {"sprites": (0x0000, 384), "mapa": (0x1800, 1),
                      "tiles": (0x2000, 480), "ventana_map": (0x5C00, 1),
                      "encima": (0x6000, 128), "ventana": (0x6800, 256)}

# And the fifth, the ceiling of "+fondo": the world asked for it, map 66,
# which spends **527 background tiles and 222 sprite ones** and didn't fit in
# any of the four —the one that gives the most background with 222 sprites is
# the 480 of "+fondo" and "+ambos"—. With 256 sprites the hardware gives 544
# (see docs/port/vram.md, "Dónde está el techo"), and "+fondo" stays 64 below
# only because raising it would change the layout of the maps that already
# use it. It is "+fondo" with the ventana_map and the tilemap shifted behind
# the background:
#
#   sprites     $0000   8 KB  256 4bpp tiles      OBJ base at 0
#   tiles       $1000  34 KB  544 8bpp tiles      <- the BG1 base
#   ventana_map $5400   2 KB  the window's 32x32 tilemap
#   tilemap     $5800   4 KB
#   encima      $6000   8 KB  128 tiles           <- the BG2 base
#   ventana     $6800   8 KB  256 tiles           <- indices 128..383
#   tilemap     $7800   4 KB
#
# 544 8bpp tiles are 34 KB, more than the LZ2 buffer: that is why the
# background goes in two streams —see `compressed_parts`—.
#
# **It goes last on purpose**, for the same reason as the two previous ones.
LAYOUT_WINDOW_BG_CEILING = {"sprites": (0x0000, 256), "tiles": (0x1000, 544),
                            "ventana_map": (0x5400, 1), "mapa": (0x5800, 1),
                            "encima": (0x6000, 128), "ventana": (0x6800, 256)}

# And the sixth, the only one that **moves the BG2 base**: Sorbe Village asked
# for it, map 69, which spends **329 background tiles, 157 upper ones and 283
# sprite ones**. The other five give the upper layer 128 tiles, because the
# window starts at BG2 index 128 and the upper tilemap is fixed at $7800. With
# the BG2 base at $5000 the upper layer has 256, and the window goes after it:
#
#   sprites     $0000  12 KB  384 4bpp tiles      OBJ base at 0
#   mapa        $1800   4 KB  the BG1 tilemap, as in "+ambos"
#   tiles       $2000  24 KB  384 8bpp tiles      <- the BG1 base
#   encima      $5000   8 KB  256 tiles           <- the BG2 base
#   ventana     $6000   8 KB  256 tiles           <- indices 256..511
#   ventana_map $7000   2 KB  the window's 32x32 tilemap
#   (free)      $7400   2 KB
#   tilemap     $7800   4 KB  the upper layer's, which doesn't move
#
# What it costs is that the window starts at index 256 and not 128, and its
# cells carry that index baked in: that is why there are **two layouts** of
# the window, one for each base the VRAM layouts use —see `ventana_bases`—,
# and `stamp_window` picks its own by looking at where the window ended up
# relative to the BG2 base.
#
# **It goes last on purpose**, for the same reason as the previous ones:
# `vram_layout` now also looks at the upper layer, and since all the maps that
# already converted fit in 128, none changes layout.
LAYOUT_WINDOW_ABOVE = {"sprites": (0x0000, 384), "mapa": (0x1800, 1),
                       "tiles": (0x2000, 384), "encima": (0x5000, 256),
                       "ventana": (0x6000, 256), "ventana_map": (0x7000, 1)}

# In the order `vram_layout` tries them. **New ones are added at the end**,
# never in the middle: that way a new layout doesn't change any map's.
LAYOUTS = (("VENTANA", LAYOUT_WINDOW),
           ("VENTANA_FONDO", LAYOUT_WINDOW_BG),
           ("VENTANA_SPRITE", LAYOUT_WINDOW_SPRITE),
           ("VENTANA_AMBOS", LAYOUT_WINDOW_BOTH),
           ("VENTANA_FONDO_TECHO", LAYOUT_WINDOW_BG_CEILING),
           ("VENTANA_ENCIMA", LAYOUT_WINDOW_ABOVE))
# How many save slots the cartridge has. The same number is in
# `tools/runtime/save_game.s` as `SRAM_SLOTS`, and the ROM checks it: if they
# didn't match, the screen would show one number of slots and the SRAM would
# have another.
SLOTS = 4

# Where the tilemap and the tiles of the slots screen live, in words. The same
# numbers are in the `.inc` as SLOT_MAP and SLOT_VRAM.
#
# **They don't share with the title menu**, although until 2026-09-10 they
# did: the save point opens this screen with a map loaded and when closing it
# whatever it overwrote has to be restored, and that is cheap only if what it
# overwrote is the BG1 tile bank, which `load_map` uploads whole again. The
# menu's addresses —$4400 and $5000— fell on the sprites of a layout without
# a window that no longer exists: the NPCs came back from the menu with broken
# poses and the hero too if it wasn't the one in block 0. The ones here are in
# the intersection of the BG1 bank of the five layouts, which is $2000..$4000:
#
#   LAYOUT_WINDOW        $2000..$5800
#   LAYOUT_WINDOW_BG  $1000..$4C00
#   LAYOUT_WINDOW_SPRITE $2000..$5000
#   LAYOUT_WINDOW_BOTH  $2000..$5C00
#   LAYOUT_WINDOW_BG_CEILING $1000..$5400
#
# A BG's tile base goes in steps of 4096 words and the tilemap in steps of
# 1024: the tiles at $2000, which with the party's faces are about 300 and can
# reach 448 —up to $3C00—, and the tilemap at $3C00. The title screen
# overwrites them —its image reaches $3E00— and it doesn't matter: coming back
# from the slots the title is uploaded whole. `_check_slots` checks it
# against the real layouts, so that moving one doesn't leave this written
# wrong.
SLOT_VRAM = 0x2000
# The row of `slot_actor_text`: an actor's name, the two digits of the
# level and max HP, one after the other. Its size is a power of two even if
# bytes are left over, so that the actor's index comes out of five `asl` and
# not of a multiplication written in assembly.
SLOT_TEXT_WIDTH = 32
SLOT_TEXT_LEVEL = 16         # the name fits in thirteen, and three are left over
SLOT_TEXT_MAX = SLOT_TEXT_LEVEL + menus_mod.LEVEL_DIGITS
SLOT_MAP = 0x3C00

# The upper layer's tilemap is fixed: the background's is chosen by the layout
# —see LAYOUT_WINDOW_BOTH—.
VRAM_ABOVE_MAP = 0x7800

# Where the window's bank starts **counted from the BG2 base**, which is where
# the upper layer begins. It comes from the layout and not from a written
# number: with the upper layer at 128 tiles, the window starts at index 128
# and not 256, and writing it by hand was the first thing that broke when the
# layout moved.
def window_base(layout):
    """The BG2 index of the window's first tile in that layout."""
    return (layout["ventana"][0] - layout["encima"][0]) // 16


# The bases the layouts use, in the order of their layouts in the `.inc`: the
# first one's is `window_cells` —the usual one— and the second's,
# `window_cells_256`. The ROM picks between the two by the distance between
# the window and the BG2 base, so **there can't be a third** without touching
# `stamp_window`; `_check_splits` enforces it.
WINDOW_TILE_BASE = window_base(LAYOUT_WINDOW)
WINDOW_BASES = (WINDOW_TILE_BASE, 256)


def vram_layout(tiles, sprites=0, above=0):
    """Which VRAM layout a map gets, according to what it spends.

    The three numbers are checked in every layout, and the first one that
    fits is returned. The upper layer is checked since the sixth layout, the
    one that gives it 256: with the five before it always fit, because a map
    that went over 128 didn't convert.
    """
    # The two numbers are checked in both layouts. The background used to be
    # checked in one and the sprites in the other, and that let a map with 620
    # background tiles into a bank of 512: see the comment on
    # LAYOUT_WINDOW_BG.
    for _name, layout in LAYOUTS:
        if (tiles <= layout["tiles"][1] and sprites <= layout["sprites"][1]
                and above <= layout["encima"][1]):
            return layout
    raise SystemExit(
        "this map can't carry a message window: it spends %d background tiles, "
        "%d sprite tiles and %d upper tiles, and there is no layout that leaves "
        "8 KB of tiles plus 2 KB of tilemap for the window" % (tiles, sprites, above))


def _check_slots(slot_tiles):
    """That the slots screen lands in the BG1 bank of every layout.

    It is what lets `back_to_map` restore the map with `load_map` and
    nothing else; see the comment on SLOT_MAP.
    """
    end_tiles = SLOT_VRAM + slot_tiles * 16
    end_map = SLOT_MAP + 32 * 32
    if not (end_tiles <= SLOT_MAP or end_map <= SLOT_VRAM):
        raise SystemExit(
            "the %d tiles of the slots screen reach $%04X and overwrite its "
            "tilemap at $%04X" % (slot_tiles, end_tiles, SLOT_MAP))
    for name, layout in LAYOUTS:
        base, count = layout["tiles"]
        cap = base + count * (BYTES_PER_TILE // 2)
        for what, first, last in (("the tiles", SLOT_VRAM, end_tiles),
                                  ("the tilemap", SLOT_MAP, end_map)):
            if first < base or last > cap:
                raise SystemExit(
                    "the slots screen puts %s at $%04X..$%04X and the "
                    "BG1 bank of LAYOUT_%s is $%04X..$%04X: when coming back "
                    "from the menu `load_map` wouldn't restore it"
                    % (what, first, last, name, base, cap))


def items_border_first(source):
    """The first 8bpp tile of the item and equipment windows, counted from
    `SLOT_VRAM`, which is the BG1 base and the BG2 one: the first free one
    after the `source` tiles of the font, which are 4bpp and half the size."""
    return (source + 1) // 2


def _check_items_border(source, border):
    """That the font and the windows of the item and equipment screens, one
    after the other, don't reach the BG1 tilemap, and that everything stays
    in the BG1 bank of the layouts, like the rest of the screen —see
    `_check_slots`—."""
    end = SLOT_VRAM + (items_border_first(source) + border) * 32
    if end > menus_mod.ITEM_BORDER_MAP:
        raise SystemExit(
            "the item screen's font (%d 4bpp tiles) and the item and "
            "equipment windows (%d 8bpp ones) reach $%04X and the windows' "
            "tilemap is at $%04X" % (source, border, end, menus_mod.ITEM_BORDER_MAP))
    end_map = menus_mod.ITEM_BORDER_MAP + 32 * 32
    for name, layout in LAYOUTS:
        base, count = layout["tiles"]
        cap = base + count * (BYTES_PER_TILE // 2)
        if SLOT_VRAM < base or end_map > cap:
            raise SystemExit(
                "the item and equipment windows reach $%04X and the BG1 "
                "bank of LAYOUT_%s is $%04X..$%04X" % (end_map, name, base,
                                                       cap))


def _check_target(tiles):
    """That the tiles and the tilemap of the actor-choice windows fit between
    their BG1 base and their tilemap, and that everything lands in the BG1
    bank of every layout, which is what `load_map` restores when closing the
    menu —like `_check_slots`—, and outside what the menu already uses:
    its tiles and its tilemap end at `SLOT_MAP` + 1024."""
    T = menus_mod
    end_tiles = T.TARGET_VRAM + tiles * 32
    end_map = T.TARGET_MAP + 32 * 32
    if end_tiles > T.TARGET_MAP:
        raise SystemExit(
            "the actor-choice windows are %d 8bpp tiles and "
            "reach $%04X, and their tilemap is at $%04X"
            % (tiles, end_tiles, T.TARGET_MAP))
    if T.TARGET_VRAM < SLOT_MAP + 32 * 32:
        raise SystemExit("the actor-choice windows overwrite the "
                         "menu's tilemap")
    for name, layout in LAYOUTS:
        base, count = layout["tiles"]
        cap = base + count * (BYTES_PER_TILE // 2)
        if T.TARGET_VRAM < base or end_map > cap:
            raise SystemExit(
                "the actor-choice windows go at $%04X..$%04X and "
                "the BG1 bank of LAYOUT_%s is $%04X..$%04X: when closing the "
                "menu `load_map` wouldn't restore them"
                % (T.TARGET_VRAM, end_map, name, base, cap))


def _check_shop(tiles):
    """That the tiles of the shop windows, from their BG1 base, don't reach
    beyond what `load_map` restores when closing in any layout —like
    `_check_target`—, nor what the screen uses: the font and the BG2
    tilemap end at `SLOT_MAP` + 1024. The tilemap is the item and equipment
    one, which `_check_items_border` already checks."""
    P = screens_mod
    end_tiles = P.TI_VRAM + tiles * 32
    if P.TI_VRAM < SLOT_MAP + 32 * 32:
        raise SystemExit("the shop windows overwrite the text "
                         "tilemap")
    for name, layout in LAYOUTS:
        base, count = layout["tiles"]
        cap = base + count * (BYTES_PER_TILE // 2)
        if P.TI_VRAM < base or end_tiles > cap:
            raise SystemExit(
                "the shop windows are %d 8bpp tiles, at "
                "$%04X..$%04X, and the BG1 bank of LAYOUT_%s is "
                "$%04X..$%04X: when closing the shop `load_map` wouldn't "
                "restore them" % (tiles, P.TI_VRAM, end_tiles, name, base,
                                  cap))


def _check_splits():
    """That each layout respects the hardware and what the ROM assumes of it.

    None of this depends on the map, so it is checked once per conversion.
    """
    for name, layout in LAYOUTS:
        # In words: what each thing takes, and the step its base goes in. The
        # sprite and upper-layer tiles are 4bpp, 16 words.
        pieces = {
            "sprites": (layout["sprites"][1] * 16, 0x2000),
            "tiles": (layout["tiles"][1] * (BYTES_PER_TILE // 2), 0x1000),
            "encima": (layout["encima"][1] * 16, 0x1000),
            "ventana": (layout["ventana"][1] * 16, 1),
            "ventana_map": (32 * 32, 0x400),
            # 2048 and not 1024, which is what `BG1SC` asks for: `push_strips`
            # steps to the upper layer by masking eleven bits. See
            # `push_one_column`.
            "mapa": (WINDOW_W * WINDOW_H, 0x800),
        }
        stretches = [("upper map", VRAM_ABOVE_MAP, VRAM_ABOVE_MAP
                      + WINDOW_W * WINDOW_H)]
        for piece, (length, step) in pieces.items():
            base = layout[piece][0]
            if base % step:
                raise SystemExit("LAYOUT_%s: %s at $%04X, and its base goes in "
                                 "steps of $%X words" % (name, piece, base, step))
            stretches.append((piece, base, base + length))
        if layout["mapa"][0] == 0:
            raise SystemExit("LAYOUT_%s: the tilemap at $0000, and `col_addr` "
                             "at zero means there is no column" % name)
        if window_base(layout) not in WINDOW_BASES:
            raise SystemExit("LAYOUT_%s: the window starts at BG2 tile %d, "
                             "and there are layouts for %s: see WINDOW_BASES"
                             % (name, window_base(layout), WINDOW_BASES))
        # And the window has to land inside what BG2 reaches from its base: the
        # tilemap index is ten bits.
        if window_base(layout) + layout["ventana"][1] > 1024:
            raise SystemExit("LAYOUT_%s: the window goes past BG2 index "
                             "1023" % name)
        stretches.sort(key=lambda t: t[1])
        for (a, _, end), (b, first, _) in zip(stretches, stretches[1:]):
            if end > first:
                raise SystemExit("LAYOUT_%s: %s ends at $%04X and %s starts "
                                 "at $%04X" % (name, a, end, b, first))
        if stretches[-1][2] > 0x8000:
            raise SystemExit("LAYOUT_%s: %s goes past VRAM"
                             % (name, stretches[-1][0]))
