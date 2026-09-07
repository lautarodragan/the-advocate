#!/usr/bin/env python3
"""De una imagen a tiles y paletas: lo que las dos consolas hacen igual.

Cortar en celdas de 8x8, contar colores, repartirlos en paletas, fusionar los
que sobran y reconocer un tile espejado son la misma operación en la Mega Drive
y en la Super Nintendo. Lo que cambia es la profundidad —nueve bits contra
quince—, cuántas paletas hay y cómo se empaquetan los pixeles, y eso vive en el
conversor de cada consola.

Esto estaba adentro de `md_convert.py`, que es de donde salió el port a Mega
Drive. El port a SNES lo venía importando de ahí, así que "el conversor de Mega
Drive" era en realidad media lógica compartida con un nombre que mentía.
"""

import collections

CELL = 8

# Cuántos colores entra en una paleta de cuatro bits, menos el índice 0 que es
# transparente. Es el caso que las dos consolas comparten —los tiles de fondo de
# la Mega Drive y los sprites de la Super Nintendo—, y por eso vive acá; el
# fondo de la SNES va en ocho bits y pasa su propio límite por parámetro.
COLORS_PER_PALETTE = 16
USABLE_COLORS = COLORS_PER_PALETTE - 1


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


def tile_colors(tile):
    """Los colores de un tile, sin contar los píxeles transparentes."""
    return frozenset(p for row in tile for p in row if p is not None)


def color_sets(grid):
    unique = {tile for row in grid for tile in row}
    return unique, {tile_colors(t) for t in unique}


def try_pack(sets, limit, por_paleta=USABLE_COLORS):
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
            if size <= por_paleta and (best is None or size < best[1]):
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
                                 for line in tile for p in line
                                 if p is not None)
    unique = {tile for row in grid for tile in row}

    def accept(mapping):
        remap = {tile: tuple(tuple(mapping.get(p) for p in line)
                             for line in tile)
                 for tile in unique}
        sets = {tile_colors(t) for t in remap.values()}
        groups = try_pack(sets, budget)
        return (remap, groups) if groups is not None else None

    mapping, merged, (remap, groups) = merge_least_used(counts, 0, accept)
    return ([[remap[tile] for tile in row] for row in grid],
            groups, merged, counts)


def to_indices(tile, palette, base=1):
    """El tile como índices dentro de su paleta.

    El 0 es el transparente: en la capa de abajo no se usa nunca —de ahí que
    sirva de canario— y en la de arriba es todo lo que no es el tile.

    `base` es en qué entrada de CGRAM arranca la paleta. Para la capa de encima
    es 1, que es el índice 1 de su paleta de 16. Para el fondo, que va a 8 bits
    y direcciona CGRAM en directo, es donde termina lo que está reservado abajo:
    ver `CGRAM_RESERVADAS` en snes_convert.py.
    """
    lookup = {color: i + base for i, color in enumerate(palette)}
    lookup[None] = 0
    return tuple(tuple(lookup[p] for p in row) for row in tile)


def flips(indices):
    """Las cuatro orientaciones, para reusar tiles espejados."""
    horizontal = tuple(tuple(reversed(row)) for row in indices)
    vertical = tuple(reversed(indices))
    both = tuple(reversed(horizontal))
    return ((indices, 0, 0), (horizontal, 1, 0), (vertical, 0, 1), (both, 1, 1))


