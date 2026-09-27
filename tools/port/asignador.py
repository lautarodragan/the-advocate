#!/usr/bin/env python3
"""Las primitivas del asignador: qué colores se pierden y cómo se agrupan.

Todo lo que está acá **cambia lo que se ve**: fusionar un color con otro,
decidir qué colores van juntos en una paleta, medir cuánto se mueve una imagen
si se le saca un color. Es la mitad artística del pipeline de gráficos, y por
eso no está en `tools/voodoo/`, que sólo convierte lo que ya entra y nunca toca un
pixel: ver "`tools/voodoo/` no decide colores" en `AGENTS.md`.

Quien lo usa todavía vive repartido en `snes_convert.py` —`repartir_encima`,
`build_palette`, `npcs_dibujables`— y en `titulo.py`. El día que el asignador
pase a Rust, esto es lo que se lleva primero.

Hasta el 2026-09-17 se llamaba `pixeles.py` y hacía también la parte que no
decide nada —indexar un tile en su paleta, probar sus espejados—, que pasó a
Voodoo.
"""

import collections
import sys

import numpy

CELL = 8

# Cuántos colores entra en una paleta de cuatro bits, menos el índice 0 que es
# transparente: el de los sprites y la capa de encima. El fondo va en ocho bits
# y pasa su propio límite por parámetro.
COLORS_PER_PALETTE = 16
USABLE_COLORS = COLORS_PER_PALETTE - 1


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
    bit de un float es exactamente la clase de diferencia que cambia la ROM
    sin que nadie haya tocado nada.
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

    Sin `accept` se recuerda: el mismo personaje se cuantiza igual en cada mapa
    donde aparece, y la cuenta es pura. La clave lleva los colores **en su
    orden**, porque el mapeo sale en ese orden, y se devuelven copias, porque
    hay quien completa el mapeo que recibe.
    """
    if accept is None:
        clave = (tuple(counts.items()), keep)
        if clave not in _fusionados:
            _fusionados[clave] = _merge_least_visible(counts, keep, None)
        mapping, merged = _fusionados[clave]
        return dict(mapping), list(merged)
    return _merge_least_visible(counts, keep, accept)


_fusionados = {}


def _merge_least_visible(counts, keep, accept):
    mapping = {c: c for c in counts}
    merged = []
    # Con numpy, y cada color por su puesto en el orden de las tuplas: así el
    # desempate por color de los `min` —el vecino por `(distancia, color)`,
    # la víctima por `(costo, color)`— es el desempate por puesto, entero y
    # sin floats. `luma_distance` y el costo son los de siempre.
    colores = sorted(counts)
    puesto = {c: i for i, c in enumerate(colores)}
    n = len(colores)
    rojo, verde, azul = (numpy.array([c[k] for c in colores], dtype=numpy.int64)
                         for k in range(3))
    orden = numpy.arange(n, dtype=numpy.int64)
    peso = numpy.array([counts[c] for c in colores], dtype=numpy.int64)
    vivo = numpy.ones(n, dtype=bool)
    nunca = numpy.iinfo(numpy.int64).max
    # Qué colores originales están hoy en cada uno, para no recorrer el
    # mapeo entero en cada fusión.
    adentro = [[c] for c in colores]
    # El vecino más barato de cada color vivo, y lo que cuesta mandarlo ahí.
    # Se recalcula sólo para los que lo tenían al muerto —y para el que
    # engordó—, que es lo que hace que esto no sea cúbico: las láminas del
    # fondo llegan a trescientos colores y fusionan cien.
    costo = numpy.zeros(n, dtype=numpy.int64)
    vecino = numpy.full(n, -1, dtype=numpy.int64)

    def recalcular(i):
        distancia = (30 * (rojo - rojo[i]) ** 2 + 59 * (verde - verde[i]) ** 2
                     + 11 * (azul - azul[i]) ** 2)
        clave = numpy.where(vivo, distancia * n + orden, nunca)
        clave[i] = nunca
        j = int(clave.argmin())
        if clave[j] == nunca:
            vecino[i] = -1
            return
        costo[i] = peso[i] * distancia[j]
        vecino[i] = j

    for i in range(n):
        recalcular(i)
    vivos = n

    while True:
        if accept is None:
            if vivos <= keep:
                return mapping, merged
        else:
            result = accept(mapping)
            if result is not None:
                return mapping, merged, result

        if vivos <= 1:
            sys.exit("No se pudo reducir la paleta lo suficiente.")

        candidatos = numpy.where(vivo, costo, nunca)
        victima = int(numpy.flatnonzero(vivo & (candidatos
                                                == candidatos.min()))[0])
        blanco = int(vecino[victima])
        victim, target = colores[victima], colores[blanco]
        for original in adentro[victima]:
            mapping[original] = target
        adentro[blanco] += adentro[victima]
        merged.append((victim, target, int(peso[victima])))
        peso[blanco] += peso[victima]
        vivo[victima] = False
        vivos -= 1
        recalcular(blanco)
        for i in numpy.flatnonzero(vivo & (vecino == victima)).tolist():
            if i != blanco:
                recalcular(i)


def reduce_colors(grid, budget):
    """Fusiona colores hasta que los tiles entren en `budget` paletas.

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
