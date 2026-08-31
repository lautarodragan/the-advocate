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
from render_map import (GAME_DIR, REPO, RTP_DIR, Renderer, build_passability,
                        find_resource, load_image)

# Los tiles viven entre 0x0000 y 0x7FFF de la VRAM, a 32 bytes cada uno. El
# tamaño del mapa no está acotado: la ROM va redibujando las filas y columnas
# del plano a medida que la cámara se mueve.
MAX_TILES = 1024

PALETTES = 4
# La última paleta queda para el sprite del personaje: un sprite usa una sola,
# y los 24 colores del CharSet no tienen nada que ver con los del mapa.
MAP_PALETTES = PALETTES - 1
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


def try_pack(sets, limit=None):
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
        elif len(groups) < (limit or MAP_PALETTES):
            groups.append(set(colors))
        else:
            return None
    return groups


def luma_distance(a, b):
    """Distancia entre colores de 9 bits, pesada como la percibe el ojo."""
    return (0.30 * (a[0] - b[0]) ** 2 + 0.59 * (a[1] - b[1]) ** 2
            + 0.11 * (a[2] - b[2]) ** 2)


def merge_least_used(counts, keep, accept=None):
    """Fusiona el color menos usado con su vecino más cercano, hasta que pase.

    `accept` decide cuándo parar: para el mapa es "los tiles entran en las
    paletas", para el sprite es "quedan 15 colores o menos". Devuelve el mapeo
    de color viejo a color nuevo y la lista de fusiones hechas.
    """
    mapping = {c: c for c in counts}
    merged = []

    while True:
        if accept is None:
            if len(set(mapping.values())) <= keep:
                return mapping, merged
        else:
            result = accept(mapping)
            if result is not None:
                return mapping, merged, result

        alive = set(mapping.values())
        if len(alive) <= 1:
            sys.exit("No se pudo reducir la paleta lo suficiente.")

        weight = collections.Counter()
        for original, current in mapping.items():
            weight[current] += counts[original]
        victim = min(alive, key=lambda c: (weight[c], c))
        target = min(alive - {victim}, key=lambda c: (luma_distance(c, victim), c))
        for original, current in mapping.items():
            if current == victim:
                mapping[original] = target
        merged.append((victim, target, weight[victim]))


def reduce_colors(grid):
    """Fusiona colores hasta que los tiles entren en las 4 paletas del VDP.

    El límite real no es la cantidad de colores sino cómo se reparten: un tile
    con 14 colores obliga a que esos 14 estén en la misma paleta. La cola de la
    distribución suele ser colores de uno o dos píxeles, así que fusionar el
    menos usado con su vecino más cercano y reintentar cuesta muy poco.

    El trabajo se hace sobre los tiles únicos, que son unos cientos, y no sobre
    las celdas del mapa, que en Lashe City son 22500.
    """
    counts = collections.Counter(p for row in grid for tile in row
                                 for line in tile for p in line)
    unique = {tile for row in grid for tile in row}

    def accept(mapping):
        remap = {tile: tuple(tuple(mapping[p] for p in line) for line in tile)
                 for tile in unique}
        sets = {frozenset(p for line in t for p in line) for t in remap.values()}
        groups = try_pack(sets)
        return (remap, groups) if groups is not None else None

    mapping, merged, (remap, groups) = merge_least_used(counts, 0, accept)
    return ([[remap[tile] for tile in row] for row in grid],
            groups, merged, counts)


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


# --- colisión ---------------------------------------------------------------
#
# Cada tile de RM2k tiene cuatro bits que dicen por qué lados se lo puede
# cruzar. Moverse de un tile al de al lado pide permiso a los dos: el de origen
# tiene que dejar salir por ese lado y el destino dejar entrar por el opuesto.
#
# La capa alta manda sobre la baja, salvo que tenga el bit "Above" —que
# significa "se dibuja por encima del héroe", o sea decorado— en cuyo caso la
# que decide es la baja. Puerto de Game_Map::IsPassableTile de EasyRPG.

PASS_DOWN = 0x01
PASS_LEFT = 0x02
PASS_RIGHT = 0x04
PASS_UP = 0x08
PASS_ABOVE = 0x10
PASS_WALL = 0x20
PASS_ALL = PASS_DOWN | PASS_LEFT | PASS_RIGHT | PASS_UP

# Las combinaciones de un autotile de terreno que son la cara de una pared.
# Con el bit Wall puesto, esas se cruzan siempre.
WALL_FACES = frozenset(list(range(20, 24)) + list(range(33, 38))
                       + [42, 43, 45, 46])


def lower_passable(flags, raw, bit):
    if 4000 <= raw < 5000 and (flags[raw] & PASS_WALL):
        if (raw - 4000) % 50 in WALL_FACES:
            return True
    return bool(flags[raw] & bit)


def passability_map(game_map, flags):
    """Un byte por tile del mapa con los cuatro bits de dirección ya resueltos.

    Toda la lógica de RM2k se resuelve acá; la ROM sólo mira la tabla.
    """
    result = bytearray(game_map.width * game_map.height)
    for i in range(len(result)):
        lower = game_map.lower_layer[i]
        upper = game_map.upper_layer[i]
        byte = 0
        for bit in (PASS_DOWN, PASS_LEFT, PASS_RIGHT, PASS_UP):
            if not (flags[upper] & bit):
                continue                       # la capa alta bloquea
            if not (flags[upper] & PASS_ABOVE):
                byte |= bit                    # la capa alta manda, y deja
            elif lower_passable(flags, lower, bit):
                byte |= bit                    # es decorado: manda la baja
        result[i] = byte
    return bytes(result)


def hero_start(passable, width, height):
    """El tile abierto por los cuatro lados más cercano al centro del mapa."""
    cx, cy = width // 2, height // 2
    best = None
    for y in range(height):
        for x in range(width):
            if passable[y * width + x] & PASS_ALL == PASS_ALL:
                distance = (x - cx) ** 2 + (y - cy) ** 2
                if best is None or distance < best[0]:
                    best = (distance, x, y)
    if best is None:
        sys.exit("El mapa no tiene ningún tile abierto por los cuatro lados.")
    return best[1], best[2]


def walk(passable, width, height, start, dx, dy):
    """Hasta dónde llega el personaje caminando en una dirección sin soltar.

    Mismas reglas que la ROM, para poder predecir dónde va a terminar y
    comparar contra eso.
    """
    leaving = {(1, 0): PASS_RIGHT, (-1, 0): PASS_LEFT,
               (0, 1): PASS_DOWN, (0, -1): PASS_UP}[(dx, dy)]
    entering = {(1, 0): PASS_LEFT, (-1, 0): PASS_RIGHT,
                (0, 1): PASS_UP, (0, -1): PASS_DOWN}[(dx, dy)]

    x, y = start
    while True:
        nx, ny = x + dx, y + dy
        if not (0 <= nx < width and 0 <= ny < height):
            return x, y
        if not passable[y * width + x] & leaving:
            return x, y
        if not passable[ny * width + nx] & entering:
            return x, y
        x, y = nx, ny


# --- el sprite del personaje ----------------------------------------------
#
# Un CharSet de RM2k son 4 personajes de ancho por 2 de alto; cada uno ocupa
# 72x128 y tiene 12 poses: 3 columnas de caminata por 4 direcciones. Cada pose
# mide 24x32, o sea 3x4 celdas del VDP, que es un tamaño legal de sprite.

SPRITE_CELLS_W = 3
SPRITE_CELLS_H = 4
SPRITE_POSES = 12
POSE_W = SPRITE_CELLS_W * CELL
POSE_H = SPRITE_CELLS_H * CELL


def sprite_palette(image, index):
    """Los colores del personaje, reducidos a los 15 que entran en una paleta.

    El índice 0 de la paleta es transparente —para un sprite eso significa que
    se ve el fondo— así que quedan 15 para el dibujo.
    """
    base_x = (index % 4) * POSE_W * 3
    base_y = (index // 4) * POSE_H * 4

    counts = collections.Counter()
    for y in range(POSE_H * 4):
        for x in range(POSE_W * 3):
            red, green, blue, alpha = image.getpixel((base_x + x, base_y + y))
            if alpha:
                counts[(red >> 5, green >> 5, blue >> 5)] += 1

    mapping, merged = merge_least_used(counts, USABLE_COLORS)
    return (base_x, base_y), sorted(set(mapping.values())), mapping, merged


def sprite_tiles(image, index, origin, palette, mapping):
    """Las 12 poses, cada una en 12 tiles del VDP.

    El VDP lee las celdas de un sprite por columnas, de arriba a abajo, así que
    hay que emitirlas en ese orden y no por filas como el fondo.
    """
    base_x, base_y = origin
    lookup = {color: i + 1 for i, color in enumerate(palette)}
    tiles = []

    for pose in range(SPRITE_POSES):
        pose_x = base_x + (pose % 3) * POSE_W
        pose_y = base_y + (pose // 3) * POSE_H
        for col in range(SPRITE_CELLS_W):
            for row in range(SPRITE_CELLS_H):
                indices = []
                for y in range(CELL):
                    line = []
                    for x in range(CELL):
                        red, green, blue, alpha = image.getpixel(
                            (pose_x + col * CELL + x, pose_y + row * CELL + y))
                        if not alpha:
                            line.append(0)      # transparente
                        else:
                            line.append(lookup[mapping[(red >> 5, green >> 5,
                                                        blue >> 5)]])
                    indices.append(tuple(line))
                tiles.append(pack_tile(tuple(indices)))
    return tiles


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
    # La última paleta la llena el sprite; acá queda vacía.

    lost = sum(pixels for _, _, pixels in merged)
    total = sum(counts.values())
    stats = {"merged": merged, "lost": lost, "total": total,
             "palettes": [len(p) for p in palettes]}
    return tile_data, cram, tilemap, len(grid[0]), len(grid), stats


def emit(path, name, tile_data, cram, tilemap, width, height, sprite,
         passable, start):
    tiles_per_pose = SPRITE_CELLS_W * SPRITE_CELLS_H
    with open(path + ".h", "w") as handle:
        handle.write(
            "/* Generado por tools/md_convert.py. No editar. */\n"
            "#ifndef MAPDATA_H\n#define MAPDATA_H\n\n"
            "#define MAP_NAME       \"%s\"\n"
            "#define MAP_CELLS_W    %d\n"
            "#define MAP_CELLS_H    %d\n"
            "/* Los tiles de RM2k son de 16x16, o sea 2x2 celdas del VDP. */\n"
            "#define MAP_TILES_W    %d\n"
            "#define MAP_TILES_H    %d\n"
            "#define MAP_TILE_COUNT %d\n\n"
            "#define SPRITE_POSES     %d\n"
            "#define SPRITE_CELLS_W   %d\n"
            "#define SPRITE_CELLS_H   %d\n"
            "#define SPRITE_POSE_TILES %d\n"
            "#define SPRITE_PALETTE   %d\n\n"
            "/* Bits de paso: 1 abajo, 2 izquierda, 4 derecha, 8 arriba. */\n"
            "#define HERO_START_TX  %d\n"
            "#define HERO_START_TY  %d\n\n"
            "extern const unsigned short md_palette[%d];\n"
            "extern const unsigned int   md_tiles[%d * 8];\n"
            "extern const unsigned short md_tilemap[%d];\n"
            "extern const unsigned int   md_sprite_tiles[%d * 8];\n"
            "extern const unsigned char  md_passable[%d];\n\n"
            "#endif\n"
            % (name, width, height, width // 2, height // 2, len(tile_data),
               SPRITE_POSES, SPRITE_CELLS_W, SPRITE_CELLS_H, tiles_per_pose,
               PALETTES - 1, start[0], start[1],
               PALETTES * COLORS_PER_PALETTE, len(tile_data), width * height,
               len(sprite), len(passable)))

    with open(path + ".c", "w") as handle:
        handle.write("/* Generado por tools/md_convert.py. No editar. */\n"
                     "#include \"mapdata.h\"\n\n")

        handle.write("const unsigned short md_palette[%d] = {\n"
                     % (PALETTES * COLORS_PER_PALETTE))
        for palette in cram:
            handle.write("    " + " ".join("0x%04X," % c for c in palette) + "\n")
        handle.write("};\n\n")

        def write_tiles(name, data):
            handle.write("const unsigned int %s[%d * 8] = {\n" % (name, len(data)))
            for i, tile in enumerate(data):
                longs = ["0x%08X," % int.from_bytes(tile[j:j + 4], "big")
                         for j in range(0, 32, 4)]
                handle.write("    " + " ".join(longs) + "  /* %d */\n" % i)
            handle.write("};\n\n")

        write_tiles("md_tiles", tile_data)

        handle.write("const unsigned short md_tilemap[%d] = {\n" % len(tilemap))
        for y in range(height):
            row = tilemap[y * width:(y + 1) * width]
            handle.write("    " + " ".join("0x%04X," % c for c in row) + "\n")
        handle.write("};\n\n")

        write_tiles("md_sprite_tiles", sprite)

        handle.write("const unsigned char md_passable[%d] = {\n" % len(passable))
        for y in range(height // 2):
            row = passable[y * (width // 2):(y + 1) * (width // 2)]
            handle.write("    " + " ".join("0x%02X," % c for c in row) + "\n")
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
    parser.add_argument("--charset", default="Future1",
                        help="CharSet del personaje (default: el de Talan)")
    parser.add_argument("--charset-index", type=int, default=0,
                        help="cuál de los 8 personajes del CharSet")
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

    if len(tile_data) > MAX_TILES:
        sys.exit("%d tiles distintos: no entran en los %d que hay de VRAM."
                 % (len(tile_data), MAX_TILES))
    # El personaje: su paleta va en la última, que el mapa dejó libre.
    charset_path = find_resource(renderer.search_dirs, "CharSet", args.charset)
    if not charset_path:
        sys.exit("No encuentro el CharSet %r" % args.charset)
    charset = load_image(charset_path)
    origin, palette, mapping, sprite_merged = sprite_palette(charset,
                                                             args.charset_index)
    sprite = sprite_tiles(charset, args.charset_index, origin, palette, mapping)
    cram[PALETTES - 1] = ([BACKDROP] + [cram_word(c) for c in palette]
                          + [0] * (COLORS_PER_PALETTE - 1 - len(palette)))

    # Colisión: se resuelve acá y la ROM sólo mira la tabla.
    flags = build_passability(renderer.database.chipsets[game_map.chipset_id])
    passable = passability_map(game_map, flags)
    start = hero_start(passable, game_map.width, game_map.height)

    emit(args.output, name, tile_data, cram, tilemap, width, height, sprite,
         passable, start)

    print("Mapa %d %r: %dx%d celdas de 8x8" % (args.map_id, name, width, height))
    print("  %dx%d px, %d tiles distintos de %d (%.0f%% de la VRAM de tiles)"
          % (width * CELL, height * CELL, len(tile_data), width * height,
             100.0 * len(tile_data) / MAX_TILES))
    print("  paletas: %s colores de %d" % (palette_sizes, USABLE_COLORS))
    print("  colores fusionados: %d (%d px de %d, %.3f%%)"
          % (len(stats["merged"]), stats["lost"], stats["total"],
             100.0 * stats["lost"] / stats["total"]))
    blocked = sum(1 for b in passable if b & PASS_ALL != PASS_ALL)
    print("  colisión: %d de %d tiles con algún lado cerrado (%.0f%%), "
          "arranca en (%d, %d)"
          % (blocked, len(passable), 100.0 * blocked / len(passable),
             start[0], start[1]))
    print("  sprite %s[%d]: %d tiles, %d colores, %d fusionados"
          % (args.charset, args.charset_index, len(sprite), len(palette),
             len(sprite_merged)))
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
