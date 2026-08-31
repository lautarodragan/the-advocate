#!/usr/bin/env python3
"""
rm2k2md - convierte assets de RPG Maker 2000 al formato del VDP del Mega Drive.

    python3 tools/rm2k2md.py ChipSet.png CharSet.png -o src/assets

Que hace:
  * ChipSet  -> toma el bloque "lower layer" (x=192..287, 6x16 tiles de 16x16)
                cada tile de 16x16 se parte en 4 tiles de 8x8 (TL, TR, BL, BR)
  * CharSet  -> toma el personaje 0 (bloque 72x128) = 4 direcciones x 3 frames
                cada frame de 24x32 = 1 sprite de hardware de 3x4 tiles
  * Cuantiza cada set a 16 colores en el espacio de 9 bits del Mega Drive
  * Emite assets.c / assets.h

Limites del hardware que esto choca de frente:
  - 16 colores por paleta, 4 paletas, 3 bits por canal (512 colores posibles)
  - un chipset de RM2k trae hasta 256 colores; la perdida es real y se avisa
"""
import argparse
import sys
from PIL import Image

# Layout del ChipSet de RM2k (480x256)
LOWER_X, LOWER_Y, LOWER_COLS, LOWER_ROWS = 192, 0, 6, 16
# Layout del CharSet de RM2k (288x256)
CHAR_W, CHAR_H = 72, 128
CELL_W, CELL_H = 24, 32
DIRS, FRAMES = 4, 3


def md_color(rgb):
    """RGB de 8 bits por canal -> palabra de color del VDP: 0000 BBB0 GGG0 RRR0"""
    r, g, b = rgb[:3]
    return ((b >> 5) << 9) | ((g >> 5) << 5) | ((r >> 5) << 1)


def quantize(img_rgb, ncolors, reserve_index0=None):
    """
    Devuelve (imagen indexada, lista de colores RGB).
    Si la imagen tiene pocos colores usa la paleta exacta; si no, mediana.
    reserve_index0: color RGB que debe quedar SIEMPRE en el indice 0
                    (el transparente de los charsets de RM2k).
    """
    colors = img_rgb.getcolors(maxcolors=1 << 24) or []
    uniq = [c for _, c in colors]
    if reserve_index0 is not None:
        uniq = [c for c in uniq if c != reserve_index0]

    budget = ncolors - (1 if reserve_index0 is not None else 0)

    if len(uniq) <= budget:
        pal = ([reserve_index0] if reserve_index0 is not None else []) + uniq
        lossy = False
    else:
        q = img_rgb.quantize(colors=budget, method=Image.MEDIANCUT)
        raw = q.getpalette()[: budget * 3]
        pal = [tuple(raw[i * 3:i * 3 + 3]) for i in range(budget)]
        if reserve_index0 is not None:
            pal = [reserve_index0] + pal
        lossy = True

    pal = pal[:ncolors]
    while len(pal) < ncolors:
        pal.append((0, 0, 0))

    # Mapeo final por vecino mas cercano, pero comparando ya en 9 bits:
    # asi el error que medimos es el que va a ver la consola, no el del PC.
    md_pal = [md_color(c) for c in pal]
    lut = {}

    def index_of(rgb):
        if rgb in lut:
            return lut[rgb]
        if reserve_index0 is not None and rgb == reserve_index0:
            lut[rgb] = 0
            return 0
        target = md_color(rgb)
        tr, tg, tb = (target >> 1) & 7, (target >> 5) & 7, (target >> 9) & 7
        best, bestd = 0, 1 << 30
        start = 1 if reserve_index0 is not None else 0
        for i in range(start, ncolors):
            c = md_pal[i]
            dr, dg, db = ((c >> 1) & 7) - tr, ((c >> 5) & 7) - tg, ((c >> 9) & 7) - tb
            d = dr * dr * 3 + dg * dg * 6 + db * db
            if d < bestd:
                best, bestd = i, d
        lut[rgb] = best
        return best

    w, h = img_rgb.size
    px = img_rgb.load()
    idx = [[index_of(px[x, y][:3]) for x in range(w)] for y in range(h)]
    return idx, md_pal, lossy, len(uniq)


def tile8(idx, ox, oy):
    """Extrae un tile de 8x8 -> 8 longwords (4bpp, nibble alto = pixel izquierdo)."""
    out = []
    for row in range(8):
        v = 0
        for col in range(8):
            v = (v << 4) | (idx[oy + row][ox + col] & 0xF)
        out.append(v & 0xFFFFFFFF)
    return out


def convert_chipset(path):
    img = Image.open(path).convert("RGB")
    if img.size != (480, 256):
        print(f"  aviso: {path} mide {img.size}, se esperaba (480, 256)",
              file=sys.stderr)
    block = img.crop((LOWER_X, LOWER_Y,
                      LOWER_X + LOWER_COLS * 16, LOWER_Y + LOWER_ROWS * 16))
    idx, pal, lossy, nuniq = quantize(block, 16)
    if lossy:
        print(f"  chipset: {nuniq} colores -> 16. Hay perdida de color.")
    else:
        print(f"  chipset: {nuniq} colores, entran en la paleta sin perdida.")

    ntiles = LOWER_COLS * LOWER_ROWS
    tiles = []
    for t in range(ntiles):
        col, row = t % LOWER_COLS, t // LOWER_COLS
        ox, oy = col * 16, row * 16
        # orden TL, TR, BL, BR: asi el tile N de RM2k vive en 4*N del VRAM
        tiles += tile8(idx, ox, oy)
        tiles += tile8(idx, ox + 8, oy)
        tiles += tile8(idx, ox, oy + 8)
        tiles += tile8(idx, ox + 8, oy + 8)
    return pal, tiles, ntiles


def convert_charset(path, char=0):
    img = Image.open(path).convert("RGB")
    if img.size != (288, 256):
        print(f"  aviso: {path} mide {img.size}, se esperaba (288, 256)",
              file=sys.stderr)
    cx, cy = (char % 4) * CHAR_W, (char // 4) * CHAR_H
    block = img.crop((cx, cy, cx + CHAR_W, cy + CHAR_H))
    key = block.getpixel((0, 0))
    idx, pal, lossy, nuniq = quantize(block, 16, reserve_index0=key)
    print(f"  charset: {nuniq} colores + transparente"
          f"{' -> 15, con perdida' if lossy else ', sin perdida'}")

    # 12 frames (4 direcciones x 3 pasos), cada uno 3x4 tiles.
    # El VDP lee los tiles de un sprite en orden COLUMNA, no fila.
    tiles = []
    for d in range(DIRS):
        for f in range(FRAMES):
            ox, oy = f * CELL_W, d * CELL_H
            for tc in range(CELL_W // 8):
                for tr in range(CELL_H // 8):
                    tiles += tile8(idx, ox + tc * 8, oy + tr * 8)
    return pal, tiles


def demo_map(w, h):
    GRASS, PATH, WATER, STONE, BRICK, TREE, FLOWER = range(7)
    ICE, LAVA, WOOD, SAND, CAVE, ROOF = range(7, 13)
    m = [[GRASS] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if (x * 7 + y * 13) % 23 == 0:
                m[y][x] = FLOWER
    for x in range(w):
        m[h // 2][x] = PATH
        m[h // 2 + 1][x] = PATH
    for y in range(h):
        m[y][w - 6] = WATER
        m[y][w - 5] = WATER
    for y in (h // 2, h // 2 + 1):
        m[y][w - 6] = WOOD
        m[y][w - 5] = WOOD
    for x in range(3, 11):
        m[2][x] = ROOF
        m[3][x] = ROOF
        m[4][x] = BRICK
        m[5][x] = STONE
    for x in range(18, 24):          # parche de arena y hielo
        m[9][x] = SAND
        m[10][x] = SAND
    for x in range(18, 22):
        m[12][x] = ICE
    for x in range(2, 6):            # cueva con lava
        m[12][x] = CAVE
        m[13][x] = CAVE
    m[13][3] = LAVA
    m[13][4] = LAVA
    for x, y in ((14, 2), (26, 3), (5, 9), (9, 13), (28, 12)):
        m[y][x] = TREE
    for x in range(w):
        m[0][x] = WATER
        m[h - 1][x] = WATER
    return m


def emit(out, cpal, ctiles, ntiles, spal, stiles, mp):
    mh, mw = len(mp), len(mp[0])
    with open(out + ".h", "w") as f:
        f.write(f"""/* Generado por tools/rm2k2md.py - no editar a mano */
#ifndef ASSETS_H
#define ASSETS_H

#define RM2K_TILES      {ntiles}
#define MAP_W           {mw}
#define MAP_H           {mh}
#define SPR_FRAMES      {DIRS * FRAMES}
#define SPR_TILES_FRAME {(CELL_W // 8) * (CELL_H // 8)}
#define SPR_W           {CELL_W}
#define SPR_H           {CELL_H}

extern const unsigned short tileset_pal[16];
extern const unsigned int   tileset_tiles[{len(ctiles)}];
extern const unsigned short sprite_pal[16];
extern const unsigned int   sprite_tiles[{len(stiles)}];
extern const unsigned char  map_data[MAP_H][MAP_W];

#endif
""")

    def arr(name, vals, typ, per, fmt):
        s = [f"const {typ} {name}[{len(vals)}] = {{"]
        for i in range(0, len(vals), per):
            s.append("    " + ", ".join(fmt % v for v in vals[i:i + per]) + ",")
        s.append("};\n")
        return "\n".join(s)

    with open(out + ".c", "w") as f:
        f.write('/* Generado por tools/rm2k2md.py - no editar a mano */\n')
        f.write('#include "assets.h"\n\n')
        f.write(arr("tileset_pal", cpal, "unsigned short", 8, "0x%04X") + "\n")
        f.write(arr("tileset_tiles", ctiles, "unsigned int", 4, "0x%08X") + "\n")
        f.write(arr("sprite_pal", spal, "unsigned short", 8, "0x%04X") + "\n")
        f.write(arr("sprite_tiles", stiles, "unsigned int", 4, "0x%08X") + "\n")
        f.write(f"const unsigned char map_data[MAP_H][MAP_W] = {{\n")
        for row in mp:
            f.write("    { " + ", ".join(str(v) for v in row) + " },\n")
        f.write("};\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chipset")
    ap.add_argument("charset")
    ap.add_argument("-o", "--out", default="src/assets")
    ap.add_argument("--char", type=int, default=0)
    ap.add_argument("--map-w", type=int, default=32)
    ap.add_argument("--map-h", type=int, default=16)
    a = ap.parse_args()

    print("convirtiendo:")
    cpal, ctiles, ntiles = convert_chipset(a.chipset)
    spal, stiles = convert_charset(a.charset, a.char)
    mp = demo_map(a.map_w, a.map_h)
    emit(a.out, cpal, ctiles, ntiles, spal, stiles, mp)

    vram = (len(ctiles) + len(stiles)) * 4
    print(f"  tiles chipset: {len(ctiles)//8}  tiles sprite: {len(stiles)//8}")
    print(f"  VRAM de tiles: {vram} bytes de 65536 ({vram*100//65536}%)")
    print(f"  -> {a.out}.c / {a.out}.h")


if __name__ == "__main__":
    main()
