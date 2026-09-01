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
import itertools
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


def try_pack(sets, limit):
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
        elif len(groups) < limit:
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


def reduce_colors(grid, budget):
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
        groups = try_pack(sets, budget)
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


def hero_start(passable, width, height, blocked=()):
    """El tile abierto por los cuatro lados más cercano al centro del mapa."""
    cx, cy = width // 2, height // 2
    best = None
    for y in range(height):
        for x in range(width):
            if (passable[y * width + x] & PASS_ALL == PASS_ALL
                    and (x, y) not in blocked):
                distance = (x - cx) ** 2 + (y - cy) ** 2
                if best is None or distance < best[0]:
                    best = (distance, x, y)
    if best is None:
        sys.exit("El mapa no tiene ningún tile abierto por los cuatro lados.")
    return best[1], best[2]


def walk(passable, width, height, start, dx, dy, blocked=()):
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
        if (nx, ny) in blocked:
            return x, y             # hay un NPC parado ahí
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


def charset_colors(image, index):
    """Los colores de un personaje del CharSet, con cuántos píxeles usa cada uno."""
    base_x = (index % 4) * POSE_W * 3
    base_y = (index // 4) * POSE_H * 4
    counts = collections.Counter()
    for y in range(POSE_H * 4):
        for x in range(POSE_W * 3):
            red, green, blue, alpha = image.getpixel((base_x + x, base_y + y))
            if alpha:
                counts[(red >> 5, green >> 5, blue >> 5)] += 1
    return (base_x, base_y), counts


def pack_charsets(counters, budget):
    """Reparte varios personajes en `budget` paletas de 15 colores.

    Cada sprite del VDP usa una sola paleta, así que los personajes que
    comparten paleta tienen que compartir colores. Con pocos personajes se
    prueban todos los repartos; con muchos, uno por uno al grupo que menos
    crezca.

    Devuelve, por personaje, en qué paleta cayó, y por paleta, sus colores y el
    mapeo de color original a color final.
    """
    count = len(counters)
    if count == 0:
        return [], [], []

    def cost(group):
        merged_total = collections.Counter()
        for index in group:
            merged_total.update(counters[index])
        if not merged_total:
            return 0, {}, []
        mapping, merged = merge_least_used(merged_total, USABLE_COLORS)
        return sum(px for _, _, px in merged), mapping, merged

    if count <= 8 and budget > 1:
        best = None
        for assignment in itertools.product(range(budget), repeat=count):
            if len(set(assignment)) != min(budget, count):
                continue                   # no dejar paletas sin usar de gusto
            groups = [[i for i, g in enumerate(assignment) if g == p]
                      for p in range(budget)]
            total = sum(cost(g)[0] for g in groups if g)
            if best is None or total < best[0]:
                best = (total, assignment)
        assignment = best[1]
    else:
        # Greedy: cada personaje al grupo con el que más colores comparte.
        assignment = [0] * count
        groups = [[] for _ in range(budget)]
        for index in sorted(range(count), key=lambda i: -len(counters[i])):
            pick = min(range(budget),
                       key=lambda p: cost(groups[p] + [index])[0])
            groups[pick].append(index)
            assignment[index] = pick

    palettes = []
    mappings = []
    merged_all = []
    for palette_index in range(budget):
        members = [i for i, g in enumerate(assignment) if g == palette_index]
        lost, mapping, merged = cost(members)
        palettes.append(sorted(set(mapping.values())) if mapping else [])
        mappings.append(mapping)
        merged_all.append(merged)
        del lost
    return assignment, palettes, mappings


def pose_tiles(image, origin, pose, palette, mapping):
    """Los 12 tiles de una pose.

    El VDP lee las celdas de un sprite por columnas, de arriba a abajo, así que
    hay que emitirlas en ese orden y no por filas como el fondo.
    """
    base_x, base_y = origin
    lookup = {color: i + 1 for i, color in enumerate(palette)}
    pose_x = base_x + (pose % 3) * POSE_W
    pose_y = base_y + (pose // 3) * POSE_H
    tiles = []

    for col in range(SPRITE_CELLS_W):
        for row in range(SPRITE_CELLS_H):
            indices = []
            for y in range(CELL):
                line = []
                for x in range(CELL):
                    red, green, blue, alpha = image.getpixel(
                        (pose_x + col * CELL + x, pose_y + row * CELL + y))
                    if not alpha:
                        line.append(0)      # transparente: se ve el fondo
                    else:
                        line.append(lookup[mapping[(red >> 5, green >> 5,
                                                    blue >> 5)]])
                indices.append(tuple(line))
            tiles.append(pack_tile(tuple(indices)))
    return tiles


def sprite_tiles(image, index, origin, palette, mapping):
    """Las 12 poses de un personaje, una atrás de la otra."""
    tiles = []
    for pose in range(SPRITE_POSES):
        tiles += pose_tiles(image, origin, pose, palette, mapping)
    return tiles


# --- los NPCs ---------------------------------------------------------------
#
# Son los eventos del mapa que tienen CharSet, en la página que el motor
# mostraría al empezar una partida: la de número más alto sin condiciones. No se
# evalúan sus scripts, así que cada uno se queda quieto en la pose que declara
# su página. Los eventos sin CharSet —puertas, cofres, disparadores— quedan
# afuera por ahora.

# Las tres capas de un evento. El orden de dibujado de RM2k es primero por
# capa y recién después por Y: un evento "below" queda debajo del héroe aunque
# esté más adelante en la pantalla, y uno "above" lo tapa siempre. Sale de
# Game_Character::GetScreenZ, donde el z es L- YY XX II con la capa en el byte
# más alto.
FACE_DOWN = 2      # la fila del CharSet con la que arranca el héroe

LAYER_BELOW = 0
LAYER_SAME = 1     # la del héroe, y la única que le choca
LAYER_ABOVE = 2


def collect_npcs(game_map):
    """Los eventos visibles, con su pose y si bloquean el paso."""
    npcs = []
    for event in game_map.events:
        page = event.active_page()
        if page is None or not page.character_name:
            continue
        # La caminata son cuatro fases sobre tres columnas: la del medio va dos
        # veces, así que la cuarta dibuja la misma que la segunda.
        column = 1 if page.character_pattern == 3 else page.character_pattern
        npcs.append({
            "x": event.x, "y": event.y,
            "charset": page.character_name,
            "index": page.character_index,
            "pose": page.character_direction * 3 + column,
            "layer": page.layer,
            "blocks": page.layer == LAYER_SAME,
        })
    return npcs


def allocate(image, counters):
    """Decide cuántas de las 4 paletas se lleva el fondo y cuántas los sprites.

    Se prueban todos los repartos y gana el que minimiza el peor de los dos
    errores. Se compara la *fracción* de píxeles que cambia de cada lado, no la
    cantidad: el fondo tiene mil veces más píxeles que un sprite, y sumar
    píxeles pelados haría que los sprites nunca importaran.

    El fondo suele usar menos paletas de las que se le dan —a Lashe City le
    alcanza con dos— y lo que sobra se lo quedan los sprites.
    """
    grid = cut_tiles(quantize(image))
    sprite_pixels = sum(sum(c.values()) for c in counters)
    options = []

    for budget in range(1, PALETTES):
        reduced, groups, merged, counts = reduce_colors(grid, budget)
        used = len(groups)
        for_sprites = PALETTES - used
        if for_sprites < 1 and counters:
            continue

        map_error = sum(px for _, _, px in merged) / sum(counts.values())
        assignment, palettes, mappings = pack_charsets(counters, for_sprites)

        sprite_error = 0.0
        if counters:
            lost = 0
            for index, counter in enumerate(counters):
                mapping = mappings[assignment[index]]
                lost += sum(n for color, n in counter.items()
                            if mapping[color] != color)
            sprite_error = lost / sprite_pixels

        options.append(((max(map_error, sprite_error), map_error + sprite_error),
                        used, for_sprites, reduced, groups, merged, counts,
                        assignment, palettes, mappings))

    if not options:
        sys.exit("No hay reparto de paletas posible.")
    return min(options, key=lambda o: o[0])


def convert(image, counters):
    """Del render del mapa a lo que consume el VDP, con las paletas ya repartidas."""
    (_, map_palettes, sprite_palettes, grid, groups, merged, counts,
     assignment, palettes, mappings) = allocate(image, counters)

    background = [sorted(group) for group in groups]
    unique, _ = color_sets(grid)

    tile_palette = {}
    for tile in unique:
        colors = {p for row in tile for p in row}
        tile_palette[tile] = next(i for i, g in enumerate(groups) if colors <= g)

    # Cada tile único ya tiene paleta; ahora se deduplican también los
    # espejados, que el VDP puede dibujar dados vuelta sin gastar VRAM.
    catalogue = {}
    tile_data = []
    entries = {}
    for tile in sorted(unique):
        palette_index = tile_palette[tile]
        indices = to_indices(tile, background[palette_index])
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

    # Las paletas del fondo van primero y las de los sprites después.
    cram = []
    for i in range(PALETTES):
        colors = background[i] if i < len(background) else (
            palettes[i - map_palettes] if i - map_palettes < len(palettes) else [])
        cram.append([BACKDROP] + [cram_word(c) for c in colors]
                    + [0] * (COLORS_PER_PALETTE - 1 - len(colors)))

    lost = sum(pixels for _, _, pixels in merged)
    stats = {"merged": merged, "lost": lost, "total": sum(counts.values()),
             "palettes": [len(p) for p in background],
             "map_palettes": map_palettes, "sprite_palettes": sprite_palettes,
             "assignment": assignment, "sprite_colors": palettes,
             "sprite_mappings": mappings}
    return tile_data, cram, tilemap, len(grid[0]), len(grid), stats


def npc_table(npcs, hero_tiles, sprite_base):
    """Los NPCs listos para el VDP, ordenados de adelante hacia atrás.

    El VDP dibuja los sprites en el orden de la lista y los primeros tapan a
    los últimos, así que van de mayor a menor Y: el que está más abajo en
    pantalla se ve adelante, como en RM2k.

    La posición ya viene en píxeles y con el ancla del sprite aplicada: mide
    24x32 sobre una celda de 16x16, o sea centrado a lo ancho y apoyado por los
    pies.
    """
    entries = []
    for npc in sorted(npcs, key=lambda n: (-n["layer"], -n["y"], -n["x"])):
        tile = sprite_base + hero_tiles + npc["slot"] * (SPRITE_CELLS_W
                                                         * SPRITE_CELLS_H)
        entries.append({
            "x": npc["x"] * 16 - (SPRITE_CELLS_W * CELL - 16) // 2,
            "y": npc["y"] * 16 - (SPRITE_CELLS_H * CELL - 16),
            "attr": (npc["palette"] << 13) | tile,
            "layer": npc["layer"],
            "tx": npc["x"], "ty": npc["y"], "blocks": npc["blocks"],
        })
    return entries


def emit(path, name, tile_data, cram, tilemap, width, height, sprite,
         passable, start, hero_palette, npc_tiles, npcs):
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
            "#define NPC_COUNT      %d\n"
            "#define NPC_BLOCKS     %d\n\n"
            "/* Un NPC ya listo para la tabla de sprites del VDP. */\n"
            "typedef struct {\n"
            "    short x, y;            /* esquina del sprite, en píxeles */\n"
            "    unsigned short attr;   /* paleta y primer tile */\n"
            "    short layer;           /* 0 debajo, 1 a la altura, 2 encima */\n"
            "} Npc;\n\n"
            "extern const unsigned short md_palette[%d];\n"
            "extern const unsigned int   md_tiles[%d * 8];\n"
            "extern const unsigned short md_tilemap[%d];\n"
            "extern const unsigned int   md_sprite_tiles[%d * 8];\n"
            "extern const unsigned char  md_passable[%d];\n"
            "extern const unsigned int   md_npc_tiles[%d * 8];\n"
            "extern const Npc            md_npcs[%d];\n"
            "extern const short          md_npc_blocks[%d][2];\n\n"
            "#endif\n"
            % (name, width, height, width // 2, height // 2, len(tile_data),
               SPRITE_POSES, SPRITE_CELLS_W, SPRITE_CELLS_H, tiles_per_pose,
               hero_palette, start[0], start[1],
               len(npcs), sum(1 for n in npcs if n["blocks"]),
               PALETTES * COLORS_PER_PALETTE, len(tile_data), width * height,
               len(sprite), len(passable), max(1, len(npc_tiles)),
               max(1, len(npcs)), max(1, sum(1 for n in npcs if n["blocks"]))))

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
        handle.write("};\n\n")

        write_tiles("md_npc_tiles", npc_tiles or [bytes(32)])

        handle.write("const Npc md_npcs[%d] = {\n" % max(1, len(npcs)))
        for npc in npcs or [{"x": 0, "y": -64, "attr": 0, "layer": 1}]:
            handle.write("    { %d, %d, 0x%04X, %d },\n"
                         % (npc["x"], npc["y"], npc["attr"], npc["layer"]))
        handle.write("};\n\n")

        blocks = [n for n in npcs if n["blocks"]] or [{"tx": -1, "ty": -1}]
        handle.write("const short md_npc_blocks[%d][2] = {\n" % len(blocks))
        for npc in blocks:
            handle.write("    { %d, %d },\n" % (npc["tx"], npc["ty"]))
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
    parser.add_argument("--hero-tile", nargs=2, type=int, metavar=("TX", "TY"),
                        help="arrancar al héroe en este tile en vez del centro; "
                             "para mirar situaciones puntuales")
    parser.add_argument("--reference", help="PNG con lo que el VDP debería mostrar")
    args = parser.parse_args()

    renderer = Renderer(args.game_dir, args.rtp_dir)
    game_map = lcf.Map(os.path.join(args.maps_dir, "Map%04d.lmu" % args.map_id))
    image, _ = renderer.render(game_map, draw_events_too=False)
    if image is None:
        sys.exit("Falta el chipset del mapa %d" % args.map_id)

    # Los personajes que van a aparecer: Talan primero y después los CharSets
    # de los eventos del mapa. Todos entran en el reparto de paletas.
    npcs = collect_npcs(game_map)
    actors = [(args.charset, args.charset_index)]
    for npc in npcs:
        key = (npc["charset"], npc["index"])
        if key not in actors:
            actors.append(key)

    images = {}
    origins = []
    counters = []
    for name, index in actors:
        if name not in images:
            path = find_resource(renderer.search_dirs, "CharSet", name)
            if not path:
                sys.exit("No encuentro el CharSet %r" % name)
            images[name] = load_image(path)
        origin, counter = charset_colors(images[name], index)
        origins.append(origin)
        counters.append(counter)

    tile_data, cram, tilemap, width, height, stats = convert(image, counters)
    palette_sizes = stats["palettes"]
    name = renderer.tree.map_names.get(args.map_id, "Map%04d" % args.map_id)

    if len(tile_data) > MAX_TILES:
        sys.exit("%d tiles distintos: no entran en los %d que hay de VRAM."
                 % (len(tile_data), MAX_TILES))

    def palette_of(actor):
        """En qué paleta del VDP quedó cada personaje, y con qué colores."""
        group = stats["assignment"][actor]
        return (stats["map_palettes"] + group,
                stats["sprite_colors"][group], stats["sprite_mappings"][group])

    # Talan necesita sus 12 poses porque camina; cada NPC, sólo la que declara.
    hero_palette, palette, mapping = palette_of(0)
    sprite = sprite_tiles(images[args.charset], args.charset_index, origins[0],
                          palette, mapping)

    npc_tiles = []
    pose_slot = {}
    for npc in npcs:
        actor = actors.index((npc["charset"], npc["index"]))
        key = (actor, npc["pose"])
        if key not in pose_slot:
            pose_slot[key] = len(npc_tiles) // (SPRITE_CELLS_W * SPRITE_CELLS_H)
            _, colors, remap = palette_of(actor)
            npc_tiles += pose_tiles(images[npc["charset"]], origins[actor],
                                    npc["pose"], colors, remap)
        npc["slot"] = pose_slot[key]
        npc["palette"] = palette_of(actor)[0]

    sprite_lost = sum(
        n for actor, counter in enumerate(counters)
        for color, n in counter.items()
        if stats["sprite_mappings"][stats["assignment"][actor]][color] != color)
    sprite_pixels = sum(sum(c.values()) for c in counters)

    # Colisión: se resuelve acá y la ROM sólo mira la tabla.
    flags = build_passability(renderer.database.chipsets[game_map.chipset_id])
    passable = passability_map(game_map, flags)
    blocked = {(n["x"], n["y"]) for n in npcs if n["blocks"]}
    start = (tuple(args.hero_tile) if args.hero_tile
             else hero_start(passable, game_map.width, game_map.height, blocked))

    entries = npc_table(npcs, len(sprite), 1 + len(tile_data))
    emit(args.output, name, tile_data, cram, tilemap, width, height, sprite,
         passable, start, hero_palette, npc_tiles, entries)

    print("Mapa %d %r: %dx%d celdas de 8x8" % (args.map_id, name, width, height))
    print("  %dx%d px, %d tiles distintos de %d (%.0f%% de la VRAM de tiles)"
          % (width * CELL, height * CELL, len(tile_data), width * height,
             100.0 * len(tile_data) / MAX_TILES))
    print("  paletas: %d para el fondo %s, %d para sprites"
          % (stats["map_palettes"], palette_sizes, stats["sprite_palettes"]))
    print("  colores fusionados: %d (%d px de %d, %.3f%%)"
          % (len(stats["merged"]), stats["lost"], stats["total"],
             100.0 * stats["lost"] / stats["total"]))
    blocked = sum(1 for b in passable if b & PASS_ALL != PASS_ALL)
    print("  colisión: %d de %d tiles con algún lado cerrado (%.0f%%), "
          "arranca en (%d, %d)"
          % (blocked, len(passable), 100.0 * blocked / len(passable),
             start[0], start[1]))
    print("  %d personajes (%s en la paleta %d) en %d paletas: %d tiles, "
          "%d px de %d fusionados (%.1f%%)"
          % (len(actors), args.charset, hero_palette, stats["sprite_palettes"],
             len(sprite) + len(npc_tiles), sprite_lost, sprite_pixels,
             100.0 * sprite_lost / sprite_pixels))
    blocking = sum(1 for n in npcs if n["blocks"])
    print("  %d NPCs, %d bloquean el paso, %d poses distintas"
          % (len(npcs), blocking, len(pose_slot)))
    print("  -> %s.c / %s.h" % (args.output, args.output))

    if args.reference:
        # El héroe también va en la referencia, en su tile y su pose de
        # arranque: mirando abajo y con el frame del medio. Así la comparación
        # cubre en qué orden se dibuja respecto de los NPCs, que es justo lo
        # que se escapaba cuando quedaba enmascarado.
        hero_pose = FACE_DOWN * 3 + 1
        with_hero = entries + [{
            "x": start[0] * 16 - (SPRITE_CELLS_W * CELL - 16) // 2,
            "y": start[1] * 16 - (SPRITE_CELLS_H * CELL - 16),
            "attr": (hero_palette << 13) | (1 + len(tile_data)
                                            + hero_pose * SPRITE_CELLS_W
                                            * SPRITE_CELLS_H),
            "layer": LAYER_SAME,
        }]
        write_reference(args.reference, image, tile_data, cram, tilemap,
                        width, height, with_hero, sprite + npc_tiles,
                        1 + len(tile_data))


def write_reference(path, image, tile_data, cram, tilemap, width, height,
                    npcs=(), npc_tiles=(), npc_base=0):
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

    # Mismo orden que en la ROM pero al revés, porque acá se dibuja de atrás
    # hacia adelante: primero por capa y después por Y.
    for npc in sorted(npcs, key=lambda n: (n["layer"], n["y"], n["x"])):
        palette = cram[(npc["attr"] >> 13) & 3]
        first = (npc["attr"] & 0x7FF) - npc_base
        for cell in range(SPRITE_CELLS_W * SPRITE_CELLS_H):
            data = npc_tiles[first + cell]
            # El VDP ordena las celdas de un sprite por columnas.
            base_x = npc["x"] + (cell // SPRITE_CELLS_H) * CELL
            base_y = npc["y"] + (cell % SPRITE_CELLS_H) * CELL
            for y in range(CELL):
                for x in range(CELL):
                    byte = data[y * 4 + x // 2]
                    index = (byte >> 4) if x % 2 == 0 else (byte & 0x0F)
                    if index == 0:
                        continue            # transparente
                    px, py = base_x + x, base_y + y
                    if 0 <= px < out.width and 0 <= py < out.height:
                        word = palette[index]
                        pixels[px, py] = (
                            levels[(word >> 1) & 7], levels[(word >> 5) & 7],
                            levels[(word >> 9) & 7])

    out.save(path)
    print("  referencia -> %s" % path)


if __name__ == "__main__":
    main()
