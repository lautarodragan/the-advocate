"""The formats of the SNES PPU: a tile, a CGRAM color and a tilemap cell,
as bytes or words ready for the console.
"""

BYTES_PER_TILE = 64                      # 8 bit planes, 8 rows each
COLORS_PER_PALETTE = 16            # what each sprite palette takes in CGRAM


def pack_tile(indices, planes=8):
    """The PPU format: bitplanes, not two pixels per byte.

    Each plane holds one bit of each pixel, one row per byte, with the
    leftmost pixel in the highest bit. Planes come in pairs, 16 bytes per
    pair: 0 and 1 first, then 2 and 3, and so on. That is why a 4-bit tile is
    exactly the first half of an 8-bit one, and the same code serves both by
    changing only how many planes it walks.
    """
    data = bytearray(planes * 8)
    for y, row in enumerate(indices):
        for x, value in enumerate(row):
            bit = 1 << (7 - x)
            for plane in range(planes):
                if (value >> plane) & 1:
                    data[(plane // 2) * 16 + y * 2 + (plane % 2)] |= bit
    return bytes(data)


def cgram_word(color):
    """A CGRAM word: 0BBB BBGG GGGR RRRR."""
    red, green, blue = color
    return (blue << 10) | (green << 5) | red


def entry(tile, horizontal, vertical, priority=0):
    """A tilemap cell: vhop ppcc cccc cccc.

    The three palette bits are not set here: at 8 bits per pixel the index
    already reaches all of CGRAM and the PPU ignores them. The cells of the
    slot screen, which is BG2 at 4bpp, already come from `rm2k-snes-screens`
    with the palette set in `tile`, and this lets it through.
    """
    return (tile | (priority << 13) | (horizontal << 14) | (vertical << 15))
