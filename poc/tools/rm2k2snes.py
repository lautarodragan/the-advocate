#!/usr/bin/env python3
"""
rm2k2snes - convierte assets de RPG Maker 2000 al formato del PPU de la SNES.

La diferencia grande con la version de Mega Drive no es el formato de tile:
es que la SNES tiene 8 paletas de 16 colores para fondos en modo 1, contra
4 paletas compartidas del Mega Drive. Asi que en vez de aplastar todo el
chipset a 16 colores, se hace bin packing: cada tile de 16x16 va a la paleta
donde entra, y el numero de paleta viaja en el propio tilemap.

Emite blobs binarios listos para DMA:
    bg_pal.bin       8 paletas x 16 colores BGR555
    bg_tiles.bin     tiles de 8x8 en 4bpp planar
    tilemap.bin      64x32 entradas ya armadas (tile + paleta)
    obj_pal.bin      1 paleta para el personaje
    obj_tiles.bin    12 frames de 32x32 en grilla de 16 tiles de ancho
"""
import argparse
import os
import struct
import sys
from collections import Counter
from PIL import Image

LOWER_X, LOWER_COLS, LOWER_ROWS = 192, 6, 16
CHAR_W, CHAR_H, CELL_W, CELL_H = 72, 128, 24, 32
DIRS, FRAMES = 4, 3
NUM_BG_PALS = 8
OBJ_CELL = 32          # el frame de 24x32 se paddea a un sprite de 32x32
OBJ_GRID_W = 16        # la VRAM de sprites es una grilla de 16 tiles de ancho


def bgr555(rgb):
    """RGB de 8 bits -> BGR555. La SNES tiene 5 bits por canal."""
    r, g, b = rgb[:3]
    return ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)


def tile_colors(px, ox, oy, w, h):
    return {bgr555(px[ox + x, oy + y]) for y in range(h) for x in range(w)}


def pack_palettes(tiles_colors, shared, npals, per_pal):
    """
    Bin packing de conjuntos de colores en `npals` paletas de `per_pal` colores
    (sin contar el compartido, que va en el indice 0 de todas).

    Devuelve (lista de paletas, asignacion tile->paleta, lista de tiles que
    no entraron en ninguna).
    """
    order = sorted(range(len(tiles_colors)),
                   key=lambda i: -len(tiles_colors[i]))
    pals, assign, overflow = [], [0] * len(tiles_colors), []

    for t in order:
        need = tiles_colors[t] - {shared}
        if len(need) > per_pal:
            overflow.append(t)
            continue
        best, best_growth = -1, None
        for i, p in enumerate(pals):
            union = p | need
            if len(union) <= per_pal:
                growth = len(union) - len(p)
                if best_growth is None or growth < best_growth:
                    best, best_growth = i, growth
        if best >= 0:
            pals[best] |= need
            assign[t] = best
        elif len(pals) < npals:
            pals.append(set(need))
            assign[t] = len(pals) - 1
        else:
            overflow.append(t)
    return pals, assign, overflow


def nearest(c, pal):
    tr, tg, tb = c & 31, (c >> 5) & 31, (c >> 10) & 31
    best, bd = 0, 1 << 30
    for i, p in enumerate(pal):
        dr, dg, db = (p & 31) - tr, ((p >> 5) & 31) - tg, ((p >> 10) & 31) - tb
        d = dr * dr * 3 + dg * dg * 6 + db * db
        if d < bd:
            best, bd = i, d
    return best


def encode_4bpp(idx):
    """
    Tile de 8x8 (indices 0-15) -> 32 bytes en el formato de la SNES:
    planos 0 y 1 intercalados por fila en los bytes 0-15,
    planos 2 y 3 intercalados por fila en los bytes 16-31.
    """
    out = bytearray(32)
    for y in range(8):
        b0 = b1 = b2 = b3 = 0
        for x in range(8):
            v = idx[y][x] & 0xF
            bit = 7 - x
            b0 |= (v & 1) << bit
            b1 |= ((v >> 1) & 1) << bit
            b2 |= ((v >> 2) & 1) << bit
            b3 |= ((v >> 3) & 1) << bit
        out[y * 2] = b0
        out[y * 2 + 1] = b1
        out[16 + y * 2] = b2
        out[16 + y * 2 + 1] = b3
    return bytes(out)


def convert_chipset(path, outdir, mp):
    img = Image.open(path).convert("RGB")
    block = img.crop((LOWER_X, 0, LOWER_X + LOWER_COLS * 16, LOWER_ROWS * 16))
    px = block.load()
    ntiles = LOWER_COLS * LOWER_ROWS

    freq = Counter()
    for y in range(block.size[1]):
        for x in range(block.size[0]):
            freq[bgr555(px[x, y])] += 1
    shared = freq.most_common(1)[0][0]      # va al indice 0 y al backdrop

    tcolors = []
    for t in range(ntiles):
        ox, oy = (t % LOWER_COLS) * 16, (t // LOWER_COLS) * 16
        tcolors.append(tile_colors(px, ox, oy, 16, 16))

    pals, assign, overflow = pack_palettes(tcolors, shared, NUM_BG_PALS, 15)

    total = len(freq)
    print(f"  chipset: {total} colores unicos, {ntiles} tiles")
    print(f"  empaquetado en {len(pals)} paletas de {NUM_BG_PALS} disponibles")
    if overflow:
        print(f"  {len(overflow)} tiles no entraron y se cuantizan (perdida)")
    else:
        print(f"  0 tiles con perdida de color")

    # materializar paletas: indice 0 = color compartido
    full = []
    for p in pals:
        e = [shared] + sorted(p)
        full.append(e + [0] * (16 - len(e)))
    while len(full) < NUM_BG_PALS:
        full.append([shared] + [0] * 15)

    # tiles -> 4bpp, orden TL TR BL BR por tile de RM2k
    tiles = bytearray()
    for t in range(ntiles):
        pal = full[assign[t]]
        ox, oy = (t % LOWER_COLS) * 16, (t // LOWER_COLS) * 16
        lut = {}
        for sx, sy in ((0, 0), (8, 0), (0, 8), (8, 8)):
            idx = []
            for y in range(8):
                row = []
                for x in range(8):
                    c = bgr555(px[ox + sx + x, oy + sy + y])
                    if c not in lut:
                        lut[c] = pal.index(c) if c in pal else nearest(c, pal)
                    row.append(lut[c])
                idx.append(row)
            tiles += encode_4bpp(idx)

    # tilemap 64x32: (paleta << 10) | numero de tile
    #
    # OJO: la SNES NO guarda un tilemap de 64x32 como un array lineal de 64 de
    # ancho. Lo guarda como DOS pantallas de 32x32 pegadas: las columnas 0-31
    # ocupan las primeras 1024 palabras y las columnas 32-63 las siguientes.
    # El Mega Drive si es lineal, por eso el mismo codigo no sirve para los dos.
    entries = [0] * 2048
    for row in range(32):
        my, half = row >> 1, row & 1
        for col in range(64):
            mx = col >> 1
            if my >= len(mp) or mx >= len(mp[0]):
                continue
            t = mp[my][mx]
            base = t * 4 + half * 2 + (col & 1)
            screen = 1024 if col >= 32 else 0
            entries[screen + row * 32 + (col & 31)] = (assign[t] << 10) | base
    tmap = b"".join(struct.pack("<H", e) for e in entries)

    pal_blob = b"".join(struct.pack("<H", c) for p in full for c in p)
    open(os.path.join(outdir, "bg_pal.bin"), "wb").write(pal_blob)
    open(os.path.join(outdir, "bg_tiles.bin"), "wb").write(bytes(tiles))
    open(os.path.join(outdir, "tilemap.bin"), "wb").write(bytes(tmap))
    return shared, len(tiles) // 32


def convert_charset(path, outdir, char=0):
    img = Image.open(path).convert("RGB")
    cx, cy = (char % 4) * CHAR_W, (char // 4) * CHAR_H
    block = img.crop((cx, cy, cx + CHAR_W, cy + CHAR_H))
    px = block.load()
    key = bgr555(px[0, 0])

    colors = sorted(tile_colors(px, 0, 0, CHAR_W, CHAR_H) - {key})
    lossy = len(colors) > 15
    if lossy:
        colors = colors[:15]
    pal = [0] + colors + [0] * (15 - len(colors))
    print(f"  charset: {len(colors)} colores + transparente"
          f"{' (recortado)' if lossy else ''}")

    # grilla de la VRAM de sprites: 16 tiles de ancho, 4 frames por fila
    grid_rows = (DIRS * FRAMES + 3) // 4 * 4     # 4 filas de tiles por frame
    grid = [[None] * OBJ_GRID_W for _ in range(grid_rows)]
    for f in range(DIRS * FRAMES):
        d, fr = f // FRAMES, f % FRAMES
        gx, gy = (f % 4) * 4, (f // 4) * 4
        for ty in range(4):
            for tx in range(4):
                idx = []
                for y in range(8):
                    row = []
                    for x in range(8):
                        # el frame de 24x32 se centra en la celda de 32x32
                        sx = tx * 8 + x - 4
                        sy = ty * 8 + y
                        if 0 <= sx < CELL_W and 0 <= sy < CELL_H:
                            c = bgr555(px[fr * CELL_W + sx, d * CELL_H + sy])
                            row.append(0 if c == key else
                                       (pal.index(c) if c in pal
                                        else nearest(c, pal[1:]) + 1))
                        else:
                            row.append(0)
                    idx.append(row)
                grid[gy + ty][gx + tx] = encode_4bpp(idx)

    blank = bytes(32)
    tiles = b"".join(t if t else blank for r in grid for t in r)
    open(os.path.join(outdir, "obj_pal.bin"), "wb").write(
        b"".join(struct.pack("<H", c) for c in pal))
    open(os.path.join(outdir, "obj_tiles.bin"), "wb").write(tiles)
    return len(tiles) // 32


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chipset")
    ap.add_argument("charset")
    ap.add_argument("-o", "--outdir", default="assets/snes")
    ap.add_argument("--char", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    print("convirtiendo para SNES:")
    mp = demo_map(32, 16)
    shared, nbg = convert_chipset(a.chipset, a.outdir, mp)
    nobj = convert_charset(a.charset, a.outdir, a.char)

    with open(os.path.join(a.outdir, "sizes.inc"), "w") as f:
        f.write(f".DEFINE BG_TILES_BYTES {nbg * 32}\n")
        f.write(f".DEFINE OBJ_TILES_BYTES {nobj * 32}\n")
        f.write(f".DEFINE BACKDROP ${shared:04X}\n")

    vram = (nbg + nobj) * 32 + 4096
    print(f"  tiles BG {nbg}  tiles OBJ {nobj}")
    print(f"  VRAM usada: {vram} bytes de 65536 ({vram*100//65536}%)")


if __name__ == "__main__":
    main()
