"""Una imagen llevada a N colores de 15 bits, o a pantalla completa en 8 bpp.

`reducir` y `convertir` son de la pantalla de título de nacimiento, y hoy los
usan también los carteles, las animaciones, los fondos de la pelea y las
pantallas completas.
"""

import collections

from port.constantes import ALTO, ANCHO, CELL, COLORES, COLS, FILAS, MENU_CGRAM

NEGRO = (0, 0, 0)


def _distancia(a, b):
    """Lo lejos que están dos colores de 15 bits, al cuadrado.

    Euclídea y sin pesos por canal: la alternativa —ponderar por luma, que es
    lo que hace `merge_least_visible` para las paletas de dieciséis— acá no
    cambiaría nada visible y sí haría falta explicar por qué los pesos son esos.
    Los colores que se fusionan son los que casi no aparecen, y el vecino que
    les toca está a un paso de distancia.
    """
    return sum((x - y) ** 2 for x, y in zip(a, b))


def reducir(pixeles, tope=COLORES):
    """Los colores de la imagen llevados a `tope`, y el mapa de a dónde fue cada uno.

    Se queda con los más usados y manda cada uno de los que sobran a su vecino
    más cercano de los que quedaron. **No es mediancut**: no promedia colores,
    así que no puede inventar uno que no estuviera en la imagen y no hay que
    volver a cuantizar a 15 bits después. Y no depende de qué versión de PIL
    esté instalada, que es lo que hace que la ROM salga igual byte por byte en
    cualquier máquina.

    El desempate es por el color, no por el orden en que aparecieron: dos
    colores con la misma cuenta tienen que caer siempre del mismo lado o la
    ROM cambia sin que nadie haya tocado nada.
    """
    cuenta = collections.Counter(pixeles)
    # El negro se queda con el índice 0 aunque no fuera de los más usados: es
    # el color del fondo, y así lo que el PPU pinta donde no hay nada coincide
    # con lo que la imagen tiene ahí.
    orden = sorted(cuenta, key=lambda c: (-cuenta[c], c))
    if NEGRO in orden:
        orden.remove(NEGRO)
    paleta = [NEGRO] + orden[:tope - 1]
    quedan = set(paleta)
    mapa = {c: c for c in quedan}
    for color in orden[tope - 1:]:
        mapa[color] = min(paleta, key=lambda p: (_distancia(color, p), p))
    return paleta, mapa


def _quince(imagen):
    """La imagen escalada a la pantalla y con los colores a 15 bits.

    El escalado es LANCZOS, que es el que menos ensucia los bordes del texto
    del título; el original tiene mucho degradé y poco detalle fino, así que la
    diferencia contra bicúbico se ve en los créditos y en ningún otro lado.
    """
    from PIL import Image
    chica = imagen.convert("RGB").resize((ANCHO, ALTO), Image.LANCZOS)
    return [(r >> 3, g >> 3, b >> 3) for r, g, b in chica.get_flattened_data()]


def convertir(imagen, primer_color=MENU_CGRAM, tope=COLORES):
    """Una imagen de pantalla completa como (tiles, paleta, tilemap).

    `tiles` son los tiles únicos de 8 bits por pixel; `paleta` sus colores, que
    van en CGRAM **a partir de `primer_color`** —en el título, `MENU_CGRAM`,
    porque las de abajo son del menú—; `tilemap` las 32x28 entradas, en el
    tilemap de 32x32 que el PPU espera. `tope` es cuántos colores le quedan.

    Los índices que los tiles llevan ya vienen corridos, así que quien los emita
    no tiene que acordarse de sumar nada: el corrimiento se escribe una sola vez
    y acá.
    """
    pixeles = _quince(imagen)
    paleta, mapa = reducir(pixeles, tope)
    indice = {color: i + primer_color for i, color in enumerate(paleta)}
    # La imagen como índices de paleta, fila por fila.
    filas = []
    for y in range(ALTO):
        filas.append([indice[mapa[pixeles[y * ANCHO + x]]] for x in range(ANCHO)])

    tiles, donde, tilemap = [], {}, []
    for ty in range(FILAS):
        for tx in range(COLS):
            celda = tuple(tuple(filas[ty * CELL + y][tx * CELL:(tx + 1) * CELL])
                          for y in range(CELL))
            if celda not in donde:
                donde[celda] = len(tiles)
                tiles.append(celda)
            tilemap.append(donde[celda])
    return tiles, paleta, tilemap
