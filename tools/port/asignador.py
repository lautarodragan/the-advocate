#!/usr/bin/env python3
"""Las primitivas del asignador: qué colores se pierden y cómo se agrupan.

Todo lo que está acá **cambia lo que se ve**: fusionar un color con otro,
decidir qué colores van juntos en una paleta, medir cuánto se mueve una imagen
si se le saca un color. Es la mitad artística del pipeline de gráficos, y por
eso no está en `tiles/`, que sólo convierte lo que ya entra y nunca toca un
pixel. Ver "El asignador corre primero" en ESTADO.md.

Quien lo usa todavía vive repartido en `snes_convert.py` —`repartir_encima`,
`build_palette`, `npcs_dibujables`— y en `titulo.py`. El día que el asignador
pase a Rust, esto es lo que se lleva primero.

Hasta el 2026-09-17 se llamaba `pixeles.py` y hacía también la parte que no
decide nada —indexar un tile en su paleta, probar sus espejados—, que pasó a
`tiles`. Antes todavía estaba adentro de `md_convert.py`, que es de donde salió
el port a Mega Drive.
"""

import collections
import sys

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
    """Distancia entre colores, pesada como la percibe el ojo.

    Los pesos son los de la luma de siempre —0,30 / 0,59 / 0,11— multiplicados
    por cien para que la cuenta sea **entera**. El orden que produce es el
    mismo que con los coeficientes fraccionarios, y a cambio dos distancias
    iguales comparan iguales: `merge_least_visible` multiplica esto por la
    cuenta de píxeles y después ordena, y ahí un empate resuelto por el último
    bit de un float es exactamente la clase de diferencia que separa a la ROM
    de la referencia sin que nadie haya tocado nada.
    """
    return (30 * (a[0] - b[0]) ** 2 + 59 * (a[1] - b[1]) ** 2
            + 11 * (a[2] - b[2]) ** 2)


def merge_least_visible(counts, keep, accept=None):
    """Fusiona el par de colores que menos se note, hasta que pase.

    "Lo que menos se note" es **cuántos píxeles se mueven por cuánto se
    mueven**: el costo de mandar el color `a` al color `b` es
    `pixeles(a) * luma_distance(a, b)`, que es el error que el cambio agrega a
    la imagen. Se fusiona el par más barato, se suman los píxeles del que se
    fue al que quedó, y se repite.

    Antes el criterio era sólo `pixeles(a)`: se mataba al color menos usado sin
    mirar a qué distancia estaba su vecino. Eso es lo que dejaba grises a Talan
    y al save point. Un color puede cubrir pocos píxeles y aun así **definir el
    dibujo** —un brillo, un ojo, el borde de un casco—, y mandarlo a diez de
    distancia se ve; mientras tanto dos grises casi iguales que cubren media
    lámina sobrevivían los dos porque ninguno era el menos usado. Con el costo
    de arriba pasa justo al revés: los dos grises se funden en uno —cuesta
    casi cero— y el brillo se queda, que es la entrada de CGRAM bien gastada.

    No inventa colores: el que queda es siempre uno de los que ya estaban, así
    que no hay que volver a cuantizar a 15 bits y no depende de la versión de
    PIL. Y es determinista: el costo es entero y el desempate es por el color.

    `accept` decide cuándo parar: para el mapa es "los tiles entran en las
    paletas", para el sprite es "quedan 15 colores o menos". Devuelve el mapeo
    de color viejo a color nuevo y la lista de fusiones hechas.
    """
    mapping = {c: c for c in counts}
    merged = []
    weight = collections.Counter(counts)
    alive = set(counts)
    # El vecino más barato de cada color vivo, y lo que cuesta mandarlo ahí.
    # Se recalcula sólo para los que lo tenían al muerto —y para el que
    # engordó—, que es lo que hace que esto no sea cúbico: las láminas del
    # fondo llegan a trescientos colores y fusionan cien.
    cerca = {}

    def recalcular(color):
        otros = alive - {color}
        if not otros:
            cerca.pop(color, None)
            return
        vecino = min(otros, key=lambda o: (luma_distance(color, o), o))
        cerca[color] = (weight[color] * luma_distance(color, vecino), vecino)

    for color in alive:
        recalcular(color)

    while True:
        if accept is None:
            if len(alive) <= keep:
                return mapping, merged
        else:
            result = accept(mapping)
            if result is not None:
                return mapping, merged, result

        if len(alive) <= 1:
            sys.exit("No se pudo reducir la paleta lo suficiente.")

        victim = min(alive, key=lambda c: (cerca[c][0], c, cerca[c][1]))
        target = cerca[victim][1]
        for original, current in mapping.items():
            if current == victim:
                mapping[original] = target
        merged.append((victim, target, weight[victim]))
        weight[target] += weight[victim]
        alive.discard(victim)
        del cerca[victim]
        recalcular(target)
        for color in alive:
            if color != target and cerca[color][1] == victim:
                recalcular(color)


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

    mapping, merged, (remap, groups) = merge_least_visible(counts, 0, accept)
    return ([[remap[tile] for tile in row] for row in grid],
            groups, merged, counts)
