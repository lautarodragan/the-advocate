"""An image that fills the whole screen, compressed into one LZ2 stream.

It is the path of the Game Over and title screens: the image is converted
with `palette.convert` —scaled to 256x224, at 8 bits per pixel on BG1,
which in mode 3 addresses all of CGRAM— and what goes into the cartridge is
**a single stream** with the three things the ROM uploads, one after the
other:

    the tiles, 64 bytes each
    the 32x32 tilemap, which is 2048 bytes
    the colors, two bytes each

The ROM decompresses it whole into WRAM and uploads it with three DMAs: see
`pantalla_subir` in tools/runtime/game_over.s, which reads from
`pantallas_tabla` where each stream is and how long each part is.

**Why compressed, and not a light one in the ROM with the quality one in the
`.msu`**, like the battle backdrops: measured on 2026-09-28 with the RTP's
Game Over image, at full quality it is 36,224 B of raw tiles and 11,530 with
LZ2; a light one at 128x112 and 16 colors, doubled in size like the backdrop
fallback, is 2,901 compressed. The light one saves about 9 KB of cartridge,
and it would cost a second path in the ROM —doubling, reading from the
`.msu`, waiting for the seek— that no core in the suite exercises in full.
Compressed, the quality image goes on every console. The title one was
decided the same way, on 2026-09-28: the numbers are in
`workflow/tasks/*/la-pantalla-de-game-over.md` and in
`workflow/tasks/*/la-pantalla-de-titulo-comprimida.md`.
"""

from port import compress
from port.snes_format import cgram_word, entry, pack_tile
from port.palette import convert

# The tilemap the ROM uploads: 32x32 entries of two bytes, even though the
# screen shows 28 rows. It is the size the PPU reads, and the same as the
# title.
TILEMAP_BYTES = 32 * 32 * 2


def comprimida(imagen, primer_color=0, tope=256, debajo=()):
    """The image as a dict: `flujo` is the LZ2 with the three parts, and
    `tiles`, `colores` and `primer_color` are what the ROM needs to split
    it.

    `primer_color` and `tope` are those of `palette.convert`: by default the
    image takes all of CGRAM, from 0. Index 0 is also the PPU's backdrop
    color, and `palette.reduce` leaves black there.

    `debajo` are colors that are not the image's and go in CGRAM right before
    its own —on the title, the menu's—: they travel in the same stream and
    are uploaded with the same DMA, so the stream's `primer_color` drops by
    as many as they take. It is to avoid spending another DMA in bank 0.
    """
    if len(debajo) > primer_color:
        raise ValueError("%d colors below the image, and the image starts "
                         "at %d" % (len(debajo), primer_color))
    tiles, paleta, tilemap = convert(imagen, primer_color, tope)
    datos = bytearray()
    for celda in tiles:
        datos += pack_tile(celda, planes=8)
    plano = bytearray()
    for indice in range(32 * 32):
        numero = tilemap[indice] if indice < len(tilemap) else 0
        plano += entry(numero, False, False).to_bytes(2, "little")
    colores = list(debajo) + list(paleta)
    crudo = (bytes(datos) + bytes(plano)
             + b"".join(cgram_word(c).to_bytes(2, "little") for c in colores))
    return {"flujo": compress.compress(crudo), "crudo": len(crudo),
            "tiles": len(tiles), "colores": len(colores),
            "primer_color": primer_color - len(debajo)}
