#!/usr/bin/env python3
"""Convierte un mapa de A Blurred Line a datos que consume el VDP de la Mega Drive.

Toma el ChipSet del mapa, arma los tiles ya combinados (autotiles resueltos y
las dos capas compuestas) y saca lo que el VDP necesita: tiles de 8x8 a 4 bits
por pixel, paletas de 16 colores, y un tilemap.

Las tres restricciones del hardware que mandan acá:

  * El color es de 9 bits, 3 por canal. Los 74 colores del render de Map0007
    quedan en 33.
  * Hay 4 paletas de 16 colores, y cada tile de 8x8 usa una sola. El índice 0
    de cada paleta es transparente, así que quedan 15 colores útiles: hay que
    repartir los colores en grupos tales que ningún tile necesite dos grupos.
  * Los tiles son de 8x8, no de 16x16 como los de RM2k. Cada celda del mapa son
    cuatro tiles del VDP.

Uso:
    python3 tools/md_convert.py --map-id 7 -o md/src/mapdata
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
from render_map import GAME_DIR, REPO, RTP_DIR, Renderer

# El plano del VDP admite como máximo 64x64 celdas de 8x8, o sea 32x32 tiles de
# RM2k. Un mapa más grande necesita ir redibujando filas y columnas a medida que
# se scrollea, que es otro problema.
PLANE_CELLS = 64
# Los tiles viven entre 0x0000 y 0x7FFF de la VRAM, a 32 bytes cada uno.
MAX_TILES = 1024

PALETTES = 4
COLORS_PER_PALETTE = 16
USABLE_COLORS = COLORS_PER_PALETTE - 1   # el 0 es transparente
CELL = 8


def quantize(image):
    """La imagen como filas de colores de 9 bits, que es lo que el VDP muestra."""
    pixels = list(image.convert("RGB").get_flattened_data())
    quantized = [(r >> 5, g >> 5, b >> 5) for r, g, b in pixels]
    return [quantized[y * image.width:(y + 1) * image.width]
            for y in range(image.height)]


def cut_tiles(rows):
    """La imagen partida en celdas de 8x8, como tuplas de filas."""
    height, width = len(rows), len(rows[0])
    grid = []
    for ty in range(height // CELL):
        line = []
        for tx in range(width // CELL):
            line.append(tuple(tuple(rows[ty * CELL + y][tx * CELL:(tx + 1) * CELL])
                              for y in range(CELL)))
        grid.append(line)
    return grid


def color_sets(grid):
    unique = {tile for row in grid for tile in row}
    return unique, {frozenset(p for row in t for p in row) for t in unique}


def try_pack(sets):
    """Reparte los colores en paletas de forma que cada tile use una sola.

    Los colores pueden repetirse entre paletas: lo que hay que lograr es que el
    conjunto de colores de cada tile quede contenido en alguna. Best-fit, los
    tiles con más colores primero, cada uno al grupo que menos crezca.
    """
    groups = []
    for colors in sorted(sets, key=lambda s: -len(s)):
        best = None
        for index, group in enumerate(groups):
            size = len(group | colors)
            if size <= USABLE_COLORS and (best is None or size < best[1]):
                best = (index, size)
        if best is not None:
            groups[best[0]] |= colors
        elif len(groups) < PALETTES:
            groups.append(set(colors))
        else:
            return None
    return groups


def luma_distance(a, b):
    """Distancia entre colores de 9 bits, pesada como la percibe el ojo."""
    return (0.30 * (a[0] - b[0]) ** 2 + 0.59 * (a[1] - b[1]) ** 2
            + 0.11 * (a[2] - b[2]) ** 2)


def reduce_colors(grid):
    """Fusiona colores hasta que los tiles entren en las 4 paletas del VDP.

    Map0007 usa 32 colores de 9 bits y necesitaría 6 paletas, porque el límite
    real no es la cantidad de colores sino cómo se reparten entre los tiles.
    La cola de la distribución son colores de uno o dos píxeles: fusionar el
    menos usado con su vecino más cercano, y repetir, cuesta casi nada.
    """
    counts = collections.Counter(p for row in grid for tile in row
                                 for line in tile for p in line)
    mapping = {c: c for c in counts}
    merged = []

    while True:
        remapped = [[tuple(tuple(mapping[p] for p in line) for line in tile)
                     for tile in row] for row in grid]
        _, sets = color_sets(remapped)
        groups = try_pack(sets)
        if groups is not None:
            return remapped, groups, merged, counts

        alive = {mapping[c] for c in mapping}
        if len(alive) <= 1:
            sys.exit("No se pudo reducir la paleta lo suficiente.")

        # El color vivo menos usado se va con su vecino más cercano.
        weight = collections.Counter()
        for original, current in mapping.items():
            weight[current] += counts[original]
        victim = min(alive, key=lambda c: (weight[c], c))
        target = min(alive - {victim}, key=lambda c: (luma_distance(c, victim), c))
        for original, current in mapping.items():
            if current == victim:
                mapping[original] = target
        merged.append((victim, target, weight[victim]))


def to_indices(tile, palette):
    """El tile como índices dentro de su paleta. El 0 queda sin usar."""
    lookup = {color: i + 1 for i, color in enumerate(palette)}
    return tuple(tuple(lookup[p] for p in row) for row in tile)


def flips(indices):
    """Las cuatro orientaciones, para reusar tiles espejados."""
    horizontal = tuple(tuple(reversed(row)) for row in indices)
    vertical = tuple(reversed(indices))
    both = tuple(reversed(horizontal))
    return ((indices, 0, 0), (horizontal, 1, 0), (vertical, 0, 1), (both, 1, 1))


def pack_tile(indices):
    """Formato del VDP: 8 filas de 4 bytes, dos pixeles por byte, el alto primero."""
    data = bytearray()
    for row in indices:
        for x in range(0, CELL, 2):
            data.append((row[x] << 4) | row[x + 1])
    return bytes(data)


# El índice 0 de cada paleta es transparente y ningún tile lo usa, así que ahí
# va el color de fondo. Magenta, que no aparece en ningún mapa: si se ve dentro
# de la pantalla, algún tile está usando el índice 0 y hay un bug.
BACKDROP = 0x0E0E


def cram_word(color):
    """Palabra de CRAM: 0000 BBB0 GGG0 RRR0."""
    red, green, blue = color
    return (blue << 9) | (green << 5) | (red << 1)


def convert(image):
    grid, groups, merged, counts = reduce_colors(cut_tiles(quantize(image)))
    palettes = [sorted(group) for group in groups]
    unique, _ = color_sets(grid)

    assignment = {}
    for tile in unique:
        colors = {p for row in tile for p in row}
        assignment[tile] = next(i for i, g in enumerate(groups) if colors <= g)

    # Cada tile único ya tiene paleta; ahora se deduplican también los
    # espejados, que el VDP puede dibujar dados vuelta sin gastar VRAM.
    catalogue = {}
    tile_data = []
    entries = {}
    for tile in sorted(unique):
        palette_index = assignment[tile]
        indices = to_indices(tile, palettes[palette_index])
        for variant, hflip, vflip in flips(indices):
            key = (palette_index, variant)
            if key in catalogue:
                entries[tile] = (catalogue[key], hflip, vflip, palette_index)
                break
        else:
            catalogue[(palette_index, indices)] = len(tile_data)
            entries[tile] = (len(tile_data), 0, 0, palette_index)
            tile_data.append(pack_tile(indices))

    tilemap = []
    for row in grid:
        for tile in row:
            index, hflip, vflip, palette_index = entries[tile]
            # El tile 0 de la VRAM se deja en blanco, así que todo corre uno.
            tilemap.append((palette_index << 13) | (vflip << 12) | (hflip << 11)
                           | (index + 1))

    cram = []
    for i in range(PALETTES):
        colors = palettes[i] if i < len(palettes) else []
        cram.append([BACKDROP] + [cram_word(c) for c in colors]
                    + [0] * (COLORS_PER_PALETTE - 1 - len(colors)))

    lost = sum(pixels for _, _, pixels in merged)
    total = sum(counts.values())
    stats = {"merged": merged, "lost": lost, "total": total,
             "palettes": [len(p) for p in palettes]}
    return tile_data, cram, tilemap, len(grid[0]), len(grid), stats


def emit(path, name, tile_data, cram, tilemap, width, height):
    with open(path + ".h", "w") as handle:
        handle.write(
            "/* Generado por tools/md_convert.py. No editar. */\n"
            "#ifndef MAPDATA_H\n#define MAPDATA_H\n\n"
            "#define MAP_NAME       \"%s\"\n"
            "#define MAP_CELLS_W    %d\n"
            "#define MAP_CELLS_H    %d\n"
            "#define MAP_TILE_COUNT %d\n\n"
            "extern const unsigned short md_palette[%d];\n"
            "extern const unsigned int   md_tiles[%d * 8];\n"
            "extern const unsigned short md_tilemap[%d];\n\n"
            "#endif\n"
            % (name, width, height, len(tile_data),
               PALETTES * COLORS_PER_PALETTE, len(tile_data), width * height))

    with open(path + ".c", "w") as handle:
        handle.write("/* Generado por tools/md_convert.py. No editar. */\n"
                     "#include \"mapdata.h\"\n\n")

        handle.write("const unsigned short md_palette[%d] = {\n"
                     % (PALETTES * COLORS_PER_PALETTE))
        for palette in cram:
            handle.write("    " + " ".join("0x%04X," % c for c in palette) + "\n")
        handle.write("};\n\n")

        handle.write("const unsigned int md_tiles[%d * 8] = {\n" % len(tile_data))
        for i, data in enumerate(tile_data):
            longs = ["0x%08X," % int.from_bytes(data[j:j + 4], "big")
                     for j in range(0, 32, 4)]
            handle.write("    " + " ".join(longs) + "  /* %d */\n" % i)
        handle.write("};\n\n")

        handle.write("const unsigned short md_tilemap[%d] = {\n" % len(tilemap))
        for y in range(height):
            row = tilemap[y * width:(y + 1) * width]
            handle.write("    " + " ".join("0x%04X," % c for c in row) + "\n")
        handle.write("};\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=7)
    parser.add_argument("--maps-dir", default=os.path.join(REPO, "Maps"))
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--rtp-dir", default=RTP_DIR)
    parser.add_argument("-o", "--output", default=os.path.join(REPO, "md/src/mapdata"),
                        help="base de los archivos .c/.h a generar")
    parser.add_argument("--reference", help="PNG con lo que el VDP debería mostrar")
    args = parser.parse_args()

    renderer = Renderer(args.game_dir, args.rtp_dir)
    game_map = lcf.Map(os.path.join(args.maps_dir, "Map%04d.lmu" % args.map_id))
    image, _ = renderer.render(game_map, draw_events_too=False)
    if image is None:
        sys.exit("Falta el chipset del mapa %d" % args.map_id)

    tile_data, cram, tilemap, width, height, stats = convert(image)
    palette_sizes = stats["palettes"]
    name = renderer.tree.map_names.get(args.map_id, "Map%04d" % args.map_id)

    if width > PLANE_CELLS or height > PLANE_CELLS:
        sys.exit("El mapa mide %dx%d celdas y el plano del VDP llega a %dx%d. "
                 "Para uno más grande hay que redibujar el plano al scrollear."
                 % (width, height, PLANE_CELLS, PLANE_CELLS))
    if len(tile_data) > MAX_TILES:
        sys.exit("%d tiles distintos: no entran en los %d que hay de VRAM."
                 % (len(tile_data), MAX_TILES))
    emit(args.output, name, tile_data, cram, tilemap, width, height)

    print("Mapa %d %r: %dx%d celdas de 8x8" % (args.map_id, name, width, height))
    print("  %dx%d px, %d tiles distintos de %d (%.0f%% de la VRAM de tiles)"
          % (width * CELL, height * CELL, len(tile_data), width * height,
             100.0 * len(tile_data) / MAX_TILES))
    print("  paletas: %s colores de %d" % (palette_sizes, USABLE_COLORS))
    print("  colores fusionados: %d (%d px de %d, %.3f%%)"
          % (len(stats["merged"]), stats["lost"], stats["total"],
             100.0 * stats["lost"] / stats["total"]))
    print("  -> %s.c / %s.h" % (args.output, args.output))

    if args.reference:
        write_reference(args.reference, image, tile_data, cram, tilemap, width, height)


def write_reference(path, image, tile_data, cram, tilemap, width, height):
    """Reconstruye desde los datos generados lo que el VDP tiene que mostrar.

    Es la referencia contra la que se compara el screenshot del emulador: si
    esto y la captura no coinciden, el error está en la ROM o en el conversor,
    no en la cuantización de color.
    """
    from PIL import Image

    # Niveles del DAC del Mega Drive para los 8 valores de 3 bits.
    levels = [0, 52, 87, 116, 144, 172, 206, 255]
    out = Image.new("RGB", (width * CELL, height * CELL))
    pixels = out.load()

    for cell in range(width * height):
        entry = tilemap[cell]
        palette = cram[(entry >> 13) & 3]
        vflip, hflip = (entry >> 12) & 1, (entry >> 11) & 1
        data = tile_data[(entry & 0x7FF) - 1]
        base_x, base_y = (cell % width) * CELL, (cell // width) * CELL

        for y in range(CELL):
            for x in range(CELL):
                sx = CELL - 1 - x if hflip else x
                sy = CELL - 1 - y if vflip else y
                byte = data[sy * 4 + sx // 2]
                index = (byte >> 4) if sx % 2 == 0 else (byte & 0x0F)
                word = palette[index]
                pixels[base_x + x, base_y + y] = (
                    levels[(word >> 1) & 7], levels[(word >> 5) & 7],
                    levels[(word >> 9) & 7])

    out.save(path)
    print("  referencia -> %s" % path)


if __name__ == "__main__":
    main()
