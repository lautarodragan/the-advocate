#!/usr/bin/env python3
"""Convierte un mapa de A Blurred Line a datos que consume el PPU de la SNES.

Comparte con el resto de las herramientas todo lo que no depende del
chip: el reparto de colores en paletas, la fusión de los menos usados cuando no
entran, y el reuso de tiles espejados. Esos problemas son los mismos en las dos
consolas y el código vive allá.

Lo que cambia es el hardware, y para mejor:

  * **El color es de 15 bits, cinco por canal**, contra los 9 de la Mega Drive.
    De los 72 colores del render de Map0007 sobreviven 60; en la Mega Drive
    quedaban 32.
  * **El fondo va en modo 3, con 8 bits por pixel.** Ahí cada pixel es un índice
    directo a CGRAM y no hay paleta por tile, así que el problema de repartir
    los colores en grupos —el que dominaba todo el conversor de la Mega Drive—
    simplemente no existe. Con 4 bits y 8 paletas, Map0007 perdía 32 de sus 60
    colores; con 8 bits no pierde ninguno.

    Cuesta el doble de VRAM por tile, 64 bytes en vez de 32. Con 92 tiles son
    5,8 KB de los 64 disponibles, así que no es una restricción real.
  * **El formato de tile es por planos**, no por nibbles: cada bit de un pixel
    vive en un mapa de bits distinto, de a pares y de a 16 bytes. Por eso un
    tile de 4 bits es exactamente la primera mitad de uno de 8.

Los índices se limitan a la mitad baja de CGRAM. Los sprites usan siempre las
paletas 8 a 15, o sea los índices 128 a 255, y en 8 bits el fondo llega hasta el
255: quedarse abajo evita pisarlos.

Uso:
    python3 tools/port/snes_convert.py --map-id 7 -o rom/build/inc/mapdata.inc

Con una página de prueba, que es la lista de comandos de RM2k de un archivo
de `pruebas/casos/`; varias en un cartucho, cada una detrás de un `--caso`, y
los flags del cartucho antes del primero. El arnés elige cuál corre con
`Partida(caso=k)`:
    python3 tools/port/snes_convert.py -o … --map-id 6 \
        --comandos-de-prueba pruebas/casos/pan.json \
        --caso --comandos-de-prueba pruebas/casos/pan-vuelve.json
"""

import argparse
import collections
import json
import os
import sys

# Corrido como script —que es como lo corren las recetas—, Python pone en el
# `sys.path` la carpeta de este archivo y no `tools/`, que es de donde se
# importan los paquetes. Se la reemplaza en vez de sumar `tools/` al lado: con
# las dos, un `import eventos` suelto andaría y cargaría una segunda copia del
# módulo, distinta de `port.eventos`.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from ensamblado import bancos
from port import tiles_bin
from rpgmaker import event_codes
from port import eventos
from rpgmaker import lcf
from rpgmaker import rm2k

# Los eventos translúcidos llevan su propio gráfico: ver
# `rm2k.decorar_translucido` —horneado contra el fondo, tramado, u opaco—.
lcf.DECORAR_TRANSLUCIDO = rm2k.decorar_translucido
from port import animacion as animacion_mod
from port import imagen
from port import asignador
from port import titulo as titulo_mod
from port import pantallas as pantallas_mod
from port import batalla as batalla_mod
from port import escena as escena_mod
from audio import snes_music
from port.asignador import CELL, cut_tiles, tile_colors
from rpgmaker.rm2k import collect_npcs, hero_start, passability_map
from render.render_map import (GAME_DIR, REPO, RTP_DIR, Renderer, build_passability,
                               find_resource, load_image)

# El PPU direcciona 1024 tiles por capa: diez bits en cada celda del tilemap.
MAX_TILES = 1024

# CGRAM tiene 256 entradas. La mitad de arriba es de los sprites; la de abajo la
# comparten el fondo, que va en 8 bits por pixel y direcciona CGRAM en directo,
# y la capa que va por encima del héroe, que va en 4 bits y por lo tanto cuenta
# su índice dentro de una paleta de 16.
#
# Dónde cae el corte entre las dos no es fijo: lo decide el conversor mapa por
# mapa, en convert_layers(). Con una paleta arriba el fondo tiene 111 colores;
# con tres, 79. Antes eran dos siempre, y 27 mapas no entraban —los tres
# primeros del juego entre ellos— mientras el fondo dejaba colores sin usar.
#
# El tope de acá abajo no es una decisión de calidad sino la forma del hardware:
# al fondo tiene que quedarle al menos una paleta. Cuántas se lleva de verdad la
# capa de encima sale de lo que el fondo no necesita.
BG_PALETTES = 8                          # la mitad baja de CGRAM, en paletas
MAX_ABOVE_PALETTES = BG_PALETTES - 1
BYTES_PER_TILE = 64                      # 8 planos de bits, 8 filas cada uno


def above_split(palettes):
    """En qué paleta arranca la capa de encima si se lleva tantas."""
    return BG_PALETTES - palettes


# Las entradas de CGRAM que el fondo **no** puede usar, abajo de todo: la 0, que
# es el color de fondo de la pantalla, y las siete de la ventana de mensaje.
#
# La ventana va en la **paleta 0** y no flotando debajo de la capa de encima, y
# eso es lo que le devuelve al fondo todo lo que antes se tiraba. BG1 va a 8 bits
# por pixel y direcciona CGRAM en directo: no necesita paletas de 16, le alcanza
# con que nadie le pise las entradas. Poniendo la ventana abajo de todo, el fondo
# queda contiguo desde la 8 hasta donde arranque la capa de encima, sin huecos.
#
# Antes la ventana iba en la paleta más baja de toda la ROM —`paleta_de_la
# ventana`— y al fondo se le daba sólo el bloque de abajo. En la ROM de la
# apertura eso lo dejaba en 47 colores mientras las paletas 4, 5 y 6 no las usaba
# **nadie**: 57 entradas tiradas en el mapa 7. Los nueve mapas del PoC fusionaban
# 97 colores entre todos y ahora fusionan 8.
#
# Y hay una propiedad que sale gratis de ponerla abajo: `aplicar_tinte` tiñe
# desde donde arranca el fondo, así que la ventana queda fuera del rango sin que
# nadie tenga que acordarse. En RM2k el tono se aplica al mapa y no a la ventana.
# **Ocho y no siete.** Contarlos con `sum(1 for w in cram if w)` da siete
# porque uno de los colores de la ventana es negro puro y su palabra de CGRAM
# es cero. Con siete, la ROM dibujaba el texto con un color que nadie había
# subido y la tanda cobró 79 pixeles en los renglones de texto. Lo que manda es
# el índice más alto que la ventana usa, y de eso se asegura `convert_ventana`.
VENTANA_COLORES = 8
CGRAM_RESERVADAS = 1 + VENTANA_COLORES


def bg_budget(first):
    """Los colores que le quedan al fondo debajo de la capa de encima.

    No cuentan las de abajo de todo: el color de fondo de la pantalla y los de
    la ventana de mensaje. Ver `CGRAM_RESERVADAS`.
    """
    return first * COLORS_PER_PALETTE - CGRAM_RESERVADAS


# El orden de prioridades del modo 3, de adelante hacia atrás, es:
#
#     objetos 3 / BG1 1 / objetos 2 / BG2 1 / objetos 1 / BG1 0 / objetos 0
#
# que es justo lo que hace falta: el mapa en BG1 con prioridad 0, el héroe y los
# NPCs comunes en objetos con prioridad 1, la capa de encima en BG2 con
# prioridad 1, y los eventos marcados "above" en objetos con prioridad 2. El
# orden de RM2k sale del hardware sin trucos.
PRIORITY_ABOVE = 1                       # para las celdas de BG2

# Los tiles de la ventana viven en el banco que sigue al de la capa de encima,
# y BG2 los alcanza con la misma base porque quedaron pegados: del índice 0 al
# 255 cae el de encima y del 256 al 511 el de la ventana.

# El tamaño de la ventana en celdas. Es fijo: 256x80 pegada al pie de la
# pantalla, los mismos números que `tools/port/ventana.py`.
VENTANA_COLS_INC, VENTANA_FILAS_INC = 32, 10

# El glifo, que es lo que la ROM compone. Los mismos números que
# `tools/port/fuente.py`, que se genera desde easyrpg-player.
FUENTE_ANCHO, FUENTE_ALTO = 6, 12

# Y las de los objetos, ya corridas a su lugar en el byte vhoopppN: la
# prioridad son los bits 5 y 4, no los 0 y 1: escribir $20 creyendo que es
# prioridad 1 da prioridad 2, y en el orden de más arriba ese lugar de más cruza
# justo la capa de encima. No falla nada y el sprite se sigue viendo: sólo que
# del lado equivocado de una capa, o sea tapando el techo por el que debería
# caminar por debajo.
#
# Estos dos valores son los únicos del programa: la ROM recibe el del héroe en
# HERO_PRIORITY y el de cada NPC viene armado en su byte de atributos. Tenerlos
# escritos también en `main.s` fue lo que dejó que este error sobreviviera a la
# primera comparación: los dos lados se equivocaron igual y dio cero.
OBJ_PRIORITY = 0x10                      # prioridad 1: debajo de BG2 1
OBJ_PRIORITY_ABOVE = 0x20                # prioridad 2: por encima

# El color 0 de CGRAM es el fondo: se ve donde ninguna capa dibuja, y también
# donde un tile usa el índice 0. Negro, que es lo que RM2k dibuja donde el mapa
# no tiene nada y más allá de sus bordes, y desde el 2026-09-05 eso se ve: la
# sacudida de pantalla asoma lo que hay a los costados. Antes era magenta, un
# centinela para el ojo —"si asoma dentro de la pantalla es que algo está
# mal"—; la comparación contra la referencia no lo necesita, porque los dos
# lados lo pintan con esta misma constante.
BACKDROP = (0, 0, 0)


def quantize(image):
    """La imagen como filas de colores de 15 bits, que es lo que el PPU muestra.

    Un pixel transparente queda como None y va a parar al índice 0 de la
    paleta, que el PPU no dibuja.
    """
    pixels = list(image.convert("RGBA").get_flattened_data())
    quantized = [None if a == 0 else (r >> 3, g >> 3, b >> 3)
                 for r, g, b, a in pixels]
    return [quantized[y * image.width:(y + 1) * image.width]
            for y in range(image.height)]


def pack_tile(indices, planes=8):
    """Formato del PPU: planos de bits, no dos pixeles por byte.

    Cada plano guarda un bit de cada pixel, una fila por byte y el pixel de más
    a la izquierda en el bit más alto. Los planos van de a pares y de a 16
    bytes: 0 y 1 primero, después 2 y 3, y así. Por eso un tile de 4 bits es
    exactamente la primera mitad de uno de 8, y el mismo código sirve para los
    dos con sólo cambiar cuántos planos recorre.
    """
    data = bytearray(planes * 8)
    for y, row in enumerate(indices):
        for x, value in enumerate(row):
            bit = 1 << (7 - x)
            for plane in range(planes):
                if (value >> plane) & 1:
                    data[(plane // 2) * 16 + y * 2 + (plane % 2)] |= bit
    return bytes(data)


def cgram_word(color):
    """Palabra de CGRAM: 0BBB BBGG GGGR RRRR."""
    red, green, blue = color
    return (blue << 10) | (green << 5) | red


def repartir_encima(grid, limite):
    """Qué paletas se lleva la capa de encima, con `limite` como tope.

    Es la decisión, separada de la emisión: cuántas paletas usa esta capa es
    lo que decide dónde arranca en CGRAM, y eso a su vez le dice al fondo hasta
    dónde puede llegar. Por eso la toma `_convert_layers`, que es el único que
    ve las dos capas, y `convert_above` recibe el resultado.

    Si no alcanzan, fusiona. Devuelve (grilla, paletas, fusionados): la grilla
    es otra si hubo que fusionar.
    """
    sets = {tile_colors(t) for row in grid for t in row}
    sets = {s for s in sets if s}
    groups = asignador.try_pack(sets, limite) if sets else []
    merged = []
    if sets and groups is None:
        # Repartiendo no entra. Hay dos motivos y se confundían en uno solo:
        # que los colores sean muchos para las paletas concedidas, o que un
        # tile suelto tenga más de 15, que no entra en ninguna paleta por
        # muchas que se le den. El segundo no lo arregla ningún reparto.
        #
        # Los dos los arregla lo mismo: fusionar el color menos usado con su
        # vecino más cercano y reintentar. Es lo que la Mega Drive ya hacía con
        # el fondo, y el código vive allá.
        grid, groups, merged, _ = asignador.reduce_colors(grid, limite)
    return grid, [sorted(g) for g in groups], merged


def imagen_encima(grid, palettes, above_first):
    """La capa de encima como la deja el asignador: un PNG indexado.

    Sus índices son **entradas de CGRAM**: el color `k` de la paleta `i` de esta
    capa es la entrada `(above_first + i) * 16 + k + 1`, y lo transparente es la
    0. Así lo que se decidió —qué paleta lleva cada celda y dónde arranca cada
    una— queda escrito en la imagen, y se puede mirar sin armar la ROM.
    """
    columnas, filas = len(grid[0]), len(grid)
    ancho = columnas * CELL
    pixeles = [0] * (ancho * filas * CELL)
    posicion = [{color: k + 1 for k, color in enumerate(p)} for p in palettes]
    for cy, row in enumerate(grid):
        for cx, tile in enumerate(row):
            colors = tile_colors(tile)
            if not colors:
                continue
            # La primera paleta que tenga todos sus colores, que es la misma
            # cuenta que hizo `repartir_encima` al armarlas.
            i = next(i for i, pal in enumerate(palettes) if colors <= set(pal))
            base = (above_first + i) * COLORS_PER_PALETTE
            for y, line in enumerate(tile):
                fila = (cy * CELL + y) * ancho + cx * CELL
                for x, color in enumerate(line):
                    if color is not None:
                        pixeles[fila + x] = base + posicion[i][color]
    colores = [None] * 256
    for i, palette in enumerate(palettes):
        base = (above_first + i) * COLORS_PER_PALETTE
        colores[base] = BACKDROP
        for k in range(COLORS_PER_PALETTE - 1):
            colores[base + k + 1] = palette[k] if k < len(palette) else (0, 0, 0)
    return tiles_bin.png_indexado(
        ancho, filas * CELL, pixeles, colores,
        [e % COLORS_PER_PALETTE == 0 for e in range(256)])


def convert_above(grid, palettes, above_first, merged=0):
    """La capa que va por encima del héroe: tiles de 4 bits y su tilemap.

    Es mucho más chica que la de abajo —en Map0073 son 419 celdas de 900, con
    siete colores— así que casi siempre entra en una o dos paletas. Las celdas
    vacías apuntan al tile 0, que se deja transparente a propósito.

    **No decide nada**: las paletas las eligió `repartir_encima`, y en cuál de
    CGRAM arranca, `above_first`, lo eligió `_convert_layers`. Con eso se
    escribe la imagen indexada y la convierte `tiles`.

    Devuelve (tiles, palabras de CGRAM, tilemap, primera paleta, fusionados,
    la imagen del asignador).
    """
    png = imagen_encima(grid, palettes, above_first)
    tiles, cgram, tilemap, _ = tiles_bin.convertir(
        png, 4, len(grid[0]), prioridad=PRIORITY_ABOVE)
    # Las paletas de esta capa, y nada más: el resto de la CGRAM de la imagen
    # es de otras capas.
    cram = cgram[2 * above_first * COLORS_PER_PALETTE:
                 2 * (above_first + len(palettes)) * COLORS_PER_PALETTE]
    # Nunca cero: en la consola un DMA de tamaño cero transfiere 65536 bytes, no
    # ninguno. Un mapa sin capa de encima mandaba una paleta vacía y arrasaba
    # CGRAM entera, paletas de sprites incluidas. Se emite una paleta vacía.
    if not cram:
        cram = bytes(2 * COLORS_PER_PALETTE)
    return tiles, cram, tilemap, above_first, merged, png


def entry(tile, horizontal, vertical, priority=0):
    """Una celda del tilemap: vhop ppcc cccc cccc.

    Los tres bits de paleta no se ponen acá: en 8 bits por pixel el índice ya
    alcanza CGRAM entero y el PPU los ignora. Las celdas de la pantalla de
    ranuras, que es BG2 a 4bpp, ya vienen de `titulo.py` con la paleta puesta
    en `tile`, y esto la deja pasar.
    """
    return (tile | (priority << 13) | (horizontal << 14) | (vertical << 15))


# --- el sprite del personaje ------------------------------------------------
#
# Un CharSet de RM2k son 4 personajes de ancho por 2 de alto; cada uno ocupa
# 72x128 y tiene 12 poses de 24x32: 3 frames de caminata por 4 direcciones.
#
# La SNES no tiene sprites de 24x32. El más chico que cubre esa pose es 32x32,
# así que se rellena con transparente a los costados y se pierde una cuarta
# parte de los tiles. La alternativa era partir cada pose en varios objetos de
# 16x32, que gasta lo mismo y multiplica las entradas de OAM.
#
# Los sprites son siempre de 4 bits por pixel, sin excepción: no hay un modo 3
# para ellos. O sea que Talan tiene que entrar en 15 colores, y son 36.

SPRITE_W, SPRITE_H = 24, 32
OBJ_W = OBJ_H = 32                 # el tamaño real del objeto en pantalla
OBJ_COLORS = 15                    # 4 bits por pixel, y el 0 es transparente
COLORS_PER_PALETTE = 16            # lo que ocupa cada paleta de sprite en CGRAM
SPRITE_POSES = 12
POSE_INICIAL = 2 * 3 + 1           # mirando abajo, el frame del medio
OBJ_PALETTES = 8                   # de la 8 a la 15, con cronómetro o sin él

# La tabla de nombres de OAM tiene 16 tiles de ancho, así que un objeto de
# 32x32 no ocupa 16 tiles seguidos sino un bloque de 4x4 dentro de esa grilla.
OBJ_ROW = 16


def pose_origin(index, pose):
    """Dónde empieza una pose dentro del CharSet."""
    return ((index % 4) * SPRITE_W * 3 + (pose % 3) * SPRITE_W,
            (index // 4) * SPRITE_H * 4 + (pose // 3) * SPRITE_H)


TODAS_LAS_POSES = frozenset(range(SPRITE_POSES))


def sprite_colors(image, index, poses=None):
    """Los colores del personaje, con cuántos pixeles usa cada uno.

    `poses` son las que el evento puede llegar a mostrar. **Contar las doce
    cuando se ve una es regalar entradas de CGRAM**: el save point de Lashe
    City anima mirando para arriba y nada más, y sus doce poses juntas tienen
    41 colores contra los 13 de esos tres cuadros. Los 26 de diferencia se
    fusionaban todos, y lo primero que caía era el azul y el blanco del brillo
    —pocos píxeles cada uno— contra los grises que cubren el resto del bloque.

    Quién puede mostrar qué lo decide `poses_del_mapa`, que es la misma pasada
    que ya elegía a quién le van las doce poses al cartucho: la optimización
    existía en tiles y en VRAM desde el 2026-09-05 y nunca había bajado al
    conteo de colores. `None` es "las doce", que es lo que corresponde a quien
    camina, anima quieto, gira hacia el héroe o cambia de gráfico con la 34.
    """
    base_x = (index % 4) * SPRITE_W * 3
    base_y = (index // 4) * SPRITE_H * 4
    counts = collections.Counter()
    for pose in (sorted(TODAS_LAS_POSES) if poses is None else sorted(poses)):
        ox = base_x + (pose % 3) * SPRITE_W
        oy = base_y + (pose // 3) * SPRITE_H
        for y in range(SPRITE_H):
            for x in range(SPRITE_W):
                red, green, blue, alpha = image.getpixel((ox + x, oy + y))
                if alpha:
                    counts[(red >> 3, green >> 3, blue >> 3)] += 1
    return counts


# --- los NPCs ---------------------------------------------------------------
#
# Son los eventos del mapa que tienen CharSet, quietos en la pose que declara su
# página. No se evalúan sus scripts. Cada uno es un objeto de OAM más.
#
# Dos límites de la consola mandan acá. Uno es cuántos tiles de sprite entran en
# VRAM: 512 direccionables, y cada pose son 16. El otro, más duro, es que en una
# misma línea de pantalla no puede haber más de 34 tiles de 8x8 de sprite; un
# objeto de 32x32 aporta 4, así que a partir de nueve personajes juntos la
# consola empieza a no dibujar los últimos.

BLOCKS_PER_ROW = 4              # bloques de 4x4 tiles que entran en la grilla


def block_tile(block):
    """El número de tile donde arranca un bloque de 32x32."""
    return (block // BLOCKS_PER_ROW) * 64 + (block % BLOCKS_PER_ROW) * 4


def paleta_del_personaje(image, index, tope=None, poses=None):
    """La paleta de un personaje, y cómo mapear cada color a su índice.

    Es la misma cuenta para la imagen que va a VRAM y para el banco de poses
    del cartucho, y tiene que serlo: una pose subida en caliente se dibuja con
    la paleta que ya está en CGRAM.

    `tope` baja el número de colores por debajo de los quince, y existe para
    hacerle lugar al cronómetro: sus dígitos son dos colores y el negro suele
    estar ya, así que le alcanza con una entrada. **Quién lo paga y cuánto lo
    decide `npcs_dibujables`**, que es el único que ve todas las paletas del
    mapa; acá sólo se obedece. Si el conversor lo eligiera acá, dos llamadas
    para el mismo personaje podrían dar paletas distintas y las poses del
    cartucho no coincidirían con la CGRAM.

    `poses` son las que el evento puede mostrar: **los quince colores se
    eligen mirando sólo ésas**, que es de donde sale casi toda la ganancia de
    color del save point. Lo mismo que `tope`, lo decide `npcs_dibujables` y
    acá sólo se obedece.

    El `mapping` que se devuelve cubre igual **todos** los colores del bloque
    de doce poses, no sólo los de `poses`: los que quedaron afuera del conteo
    van al más cercano de los que sobrevivieron. No es adorno defensivo —es lo
    que hace que `pose_tiles` no se caiga con un KeyError si alguien pide una
    pose de más—, y cuesta una cuenta por color.
    """
    tope = OBJ_COLORS if tope is None else tope
    counts = sprite_colors(image, index, poses)
    if len(counts) <= tope:
        mapping = {c: c for c in counts}
    else:
        mapping, _ = asignador.merge_least_visible(counts, tope)
    palette = sorted(set(mapping.values()))
    if poses is not None and palette:
        for color in sprite_colors(image, index):
            if color not in mapping:
                mapping[color] = min(
                    palette, key=lambda p, c=color: (asignador.luma_distance(p, c), p))
    lookup = {color: i + 1 for i, color in enumerate(palette)}
    return palette, lookup, mapping


def pose_tiles(image, index, pose, lookup, mapping):
    """Los dieciséis tiles de una pose, por filas: cuatro filas de cuatro.

    Es el orden en que la PPU lee un objeto de 32x32 —cada fila son cuatro
    tiles seguidos de la grilla de nombres, y las filas van de a dieciséis— y
    por eso una pose se sube con cuatro DMA de 128 bytes.
    """
    ox, oy = pose_origin(index, pose)
    out = []
    for ty in range(4):
        for tx in range(4):
            cell = []
            for y in range(CELL):
                row = []
                for x in range(CELL):
                    sx = tx * CELL + x - (OBJ_W - SPRITE_W) // 2
                    sy = ty * CELL + y
                    if 0 <= sx < SPRITE_W and 0 <= sy < SPRITE_H:
                        r, g, b, a = image.getpixel((ox + sx, oy + sy))
                        row.append(lookup[mapping[(r >> 3, g >> 3,
                                                   b >> 3)]] if a else 0)
                    else:
                        row.append(0)
                cell.append(tuple(row))
            out.append(pack_tile(tuple(cell), planes=4))
    return out


def cambia_de_grafico(evento):
    """Si alguna página del evento dibuja algo distinto de otra.

    Es lo que separa un descarte molesto de uno que rompe el juego. Un evento
    decorativo de una sola página que no se dibuja se pierde y ya —el `CoreBlood`
    del mapa 3, los cuatro `Link`—. Uno que **cambia de gráfico** es un mecanismo:
    una puerta que se abre, una máquina que se enciende. Si no se dibuja, el
    cambio no se ve nunca, y como el evento igual cierra el paso, lo que queda es
    una pared invisible que el jugador esperaba que se abriera.
    """
    graficos = {((getattr(p, "character_name", "") or "").strip(),
                 p.character_index) for p in evento.pages}
    return len(graficos) > 1


def aviso_de_descarte(texto, peligroso):
    """Un evento que no se dibuja. Si es de los que rompen, corta la conversión.

    **Y corta a propósito.** Esto era un `print` entre otros cincuenta, y el
    2026-09-07 costó una tarde: `demo-apertura` se armó con el cronómetro, el
    mapa 2 perdió el evento 30 —la celda del medio de la puerta que Core rompe—
    y el aviso pasó de largo en la salida del build. taro llegó a la cinemática,
    la puerta no cambió de tile y no pudo pasar.

    Es el mismo criterio que `entrar_en_panico` en la ROM: algo que no debería
    pasar no se descarta en silencio. La diferencia es dónde se hace ruido. Un
    descarte se decide **al convertir**, y para cuando la ROM corre el evento ya
    no está en ninguna tabla: no queda nada que la consola pueda mirar. Hacerla
    explotar al cargar el mapa sería lo mismo que no armar la ROM, pero más tarde
    y sin poder decir cuál evento.

    Cortar con **todos** los descartes tampoco sirve: hoy hay decorativos que no
    entran en varios mapas, así que todas las recetas tendrían que pedir seguir y
    el corte no protegería de nada. Por eso el tope es `cambia_de_grafico`, que
    es exactamente la clase a la que pertenecía el evento 30.

    No hay forma de pedirle que siga: hubo un `--descartar-eventos`, y se fue
    en el paso 9e, cuando ningún cartucho descartaba ya nada que lo necesitara.
    """
    if not peligroso:
        print("  " + texto)
        return
    sys.exit(
        "%s\n\n"
        "No se arma la ROM: ese evento **cambia de gráfico entre sus páginas**, o\n"
        "sea que es un mecanismo y no un adorno. Sin dibujarse, el cambio no se ve\n"
        "nunca, y como el evento igual cierra el paso y dispara, lo que queda es\n"
        "una pared invisible donde el juego esperaba una puerta." % texto)


# --- el peso de un gráfico --------------------------------------------------
#
# Cuando un mapa tiene más personajes que paletas de sprite, el que llega
# último **no se queda sin dibujar**: se le presta una ajena y se lo dibuja con
# los colores de otro (ver `cabe`). Quién llega último era el orden de los
# eventos del mapa, o sea el azar: en Lashe City el save point es el evento 66
# de 68 y por eso salía con la paleta de otro. taro lo describió como "en
# algún momento perdió uno o dos colores y pasó de azul/celeste/blanco a gris",
# y no era la fusión: era que no tenía paleta propia.
#
# Así que un gráfico puede pesar, y el que pesa se sirve primero. Es una tabla
# escrita a mano y corta a propósito: no hay una medida automática de "cuánto
# se ve" que no sea inventarse una —un evento decorativo puede estar en pantalla
# todo el juego y un personaje central aparecer un minuto—, y una tabla de dos
# renglones se revisa de un vistazo. Lo que la llena es lo que taro reporta
# jugando.
#
# El sufijo `~trama` de los translúcidos no cuenta: el peso es del dibujo.
PESO_DE_GRAFICO = {
    # El save point: está en cada ciudad, es con lo que se guarda la partida, y
    # su azul contra el blanco del brillo es todo lo que tiene.
    "savept": 2,
    # Los cuatro de Future1 —Talan, Core, Manta, Kersh—. Casi siempre son
    # líderes, y al líder ya se le fuerza paleta; esto los cubre en los mapas
    # donde además andan como NPC.
    "Future1": 1,
}


def peso_de_grafico(charset):
    """Cuánto pesa un CharSet a la hora de repartir las paletas de sprite."""
    return PESO_DE_GRAFICO.get((charset or "").split(rm2k.TRAMA_SUFIJO)[0], 0)


def fila_de_pose(pose):
    """Los tres cuadros del ciclo de caminata de la dirección de `pose`.

    Un evento que anima quieto cambia de columna y **nunca de fila**: la ROM
    arma su pose como `mirada_de_fila * 3 + columna` en `animar_quietos`, así
    que de las doce sólo puede mostrar estas tres.
    """
    return frozenset(range(pose // 3 * 3, pose // 3 * 3 + 3))


def poses_del_mapa(renderer, game_map, lideres, movibles=(), giran=(),
                   graficos_de_ruta=(), anima_quieto=()):
    """Qué poses puede llegar a mostrar cada (CharSet, índice) en este mapa.

    De acá sale la paleta de cada personaje: quince colores elegidos sobre lo
    que se ve y no sobre las doce poses del bloque. La lista de quién necesita
    las doce es **la misma** que ya decidía qué poses van al cartucho y a la
    VRAM —ver `eventos_movibles` y el armado de `ranuras` en `convertir`—, y
    tiene que serlo: una pose que la ROM sube y la paleta no contó se dibuja
    con colores que no son los suyos.

    Llevan las doce:

    * los candidatos a líder, porque el héroe camina;
    * los eventos de `movibles` que **caminan**;
    * los gráficos de `giran`, porque el que se da vuelta hacia el héroe puede
      terminar en cualquiera de las cuatro direcciones;
    * los gráficos de la orden 34, que después del cambio siguen caminando.

    El que **anima quieto** se queda con los tres cuadros de su dirección, que
    es lo único que `animar_quietos` puede poner en pantalla: cambia de columna
    y no de fila. Ahí está el save point de Lashe City, que taro vio gris: sus
    doce poses tienen 41 colores y los tres cuadros que muestra, 13. `savept`
    es un CharSet **editado** —el dibujo original de RPG Maker en casi todo el
    bloque y un dibujo nuevo, con colores propios, en un rincón—, y en ésos las
    doce poses no comparten paleta. En uno normal contar doce o contar tres da
    casi lo mismo.

    El resto se queda con la pose que declara su página, más la de cada página
    si el gráfico las sigue: son exactamente las ranuras de VRAM que el mapa le
    reserva, ni una más.

    Un mismo (CharSet, índice) puede ser de un quieto y de uno que camina a la
    vez —y entre mapas de la misma ROM, también—: se acumula la unión, que es
    lo que hace que la cuenta no dependa del orden en que se recorran.
    """
    poses = {}

    def sumar(clave, cuales):
        anterior = poses.get(clave)
        poses[clave] = TODAS_LAS_POSES if (anterior is TODAS_LAS_POSES
                                           or cuales is TODAS_LAS_POSES) \
            else frozenset(anterior or ()) | frozenset(cuales)

    for actor in lideres:
        a = renderer.database.actors[actor]
        sumar((a.charset, a.charset_index), TODAS_LAS_POSES)
    for pares in (giran.values() if hasattr(giran, "values") else giran):
        for par in pares:
            sumar(tuple(par), TODAS_LAS_POSES)
    for par in graficos_de_ruta:
        sumar(tuple(par), TODAS_LAS_POSES)
    for npc in collect_npcs(game_map):
        clave = (npc["charset"], npc["index"])
        # Anima quieto y no camina: los tres cuadros de su fila. Si además está
        # en `giran` ya se llevó las doce más arriba, así que el giro no se
        # queda sin colores.
        quieto_animado = (npc["evento"] in anima_quieto
                          and npc["evento"] in movibles)
        if quieto_animado:
            propias = fila_de_pose(npc["pose"])
        elif npc["evento"] in movibles:
            propias = TODAS_LAS_POSES
        else:
            propias = frozenset((npc["pose"],))
        sumar(clave, propias)
        if npc["cambia"]:
            for grafico in npc["graficos"]:
                if grafico is not None:
                    # Un evento que camina y además cambia de gráfico pierde el
                    # cambio —gana caminar, ver `convertir`—, pero el gráfico de
                    # la página igual pide paleta acá, así que se le cuenta la
                    # pose que declara.
                    sumar(grafico[:2],
                          fila_de_pose(grafico[2]) if quieto_animado
                          else TODAS_LAS_POSES if npc["evento"] in movibles
                          else (grafico[2],))
    return poses


def npcs_dibujables(renderer, game_map, lideres, tope, graficos_de_ruta=(),
                    timer_colores=(), solo_aqui=None, poses=None):
    """Los NPCs del mapa que se dibujan: todos los que tienen CharSet, y los
    dibujados con un tile del chipset **que entren** en las paletas de sprite.

    Un evento con gráfico de tile es un personaje más para la consola, con su
    paleta, y las paletas de sprite son ocho. Los
    CharSets del juego usan quince colores cada uno y no comparten ninguna, así
    que en un mapa con siete personajes de CharSet queda una sola paleta para
    todos los tiles, y dos tiles que no compartan colores no entran. Pasó en el
    mapa 8: nueve personajes en nueve paletas. Antes de esto los eventos de
    tile directamente no se dibujaban en ningún mapa —la puerta del mapa 2 era
    un portal negro—, así que dibujar los que entran y avisar de los que no es
    estrictamente mejor.

    La regla es una sola y la corren los dos lados con esta función: primero
    se reparten los líderes posibles, los NPCs con CharSet y los gráficos a los
    que las rutas cambian con la orden 34 —que son un personaje más, con su
    paleta—, en el orden del mapa y con el mismo primer-lugar-que-entre de
    `build_characters`; después los tiles, en el orden del mapa, cada uno
    mientras quepa. Devuelve la lista
    de NPCs que se dibujan y la de los (evento, tile) que quedaron afuera.
    Un tile que quedó afuera no se dibuja, pero su evento sigue ahí: cierra el
    paso y dispara igual.
    """
    paletas = []
    paleta_de = {}
    # A quiénes hubo que prestarles una paleta ajena. Salen en el informe del
    # conversor: no rompen nada, pero se ven con colores que no son los suyos.
    prestadas = set()
    # Las paletas de los líderes posibles. **Nadie más se mete ahí**, y no es
    # por prolijidad: el destello de un evento —`FlashSprite`— en la consola es
    # un tinte de CGRAM, así que tiñe la paleta entera y con ella todo lo que la
    # comparta. La referencia, en cambio, lo aplica sobre la imagen del sprite,
    # que es lo que hace RM2k; o sea que compartir la paleta del héroe es una
    # diferencia real entre los dos lados y no un detalle de empaquetado.
    #
    # taro lo vio el 2026-09-07 en el Emitter Room: cuando Talan absorbe el
    # enojo de Core y destella en rojo, dos tiles negros encima de unos cofres
    # —invisibles, porque son todo negro— se ponían rojos con él. Compartían la
    # paleta 0 con `Future1:0`.
    #
    # Se protege al líder y no a "el que destella" porque el blanco de un
    # destello puede ser cualquier evento y se decide en tiempo de ejecución; el
    # héroe es el que destella en este juego y es el único que se puede saber
    # acá. Si aparece un destello sobre otro evento, va a filtrar igual.
    de_lider = set()
    # Qué poses puede mostrar cada gráfico, que es sobre lo que se eligen sus
    # quince colores. Sin él —la referencia vieja, o un llamador que no lo
    # pase— son las doce de siempre.
    poses = dict(poses or {})

    def cabe(charset, index, forzar, lider=False):
        palette, _, _ = paleta_del_personaje(renderer.charsets.get(charset),
                                             index,
                                             poses=poses.get((charset, index)))
        for numero, existente in enumerate(paletas):
            if numero in de_lider and not lider:
                continue
            union = existente + [c for c in palette if c not in existente]
            if len(union) <= OBJ_COLORS:
                paletas[numero] = union
                paleta_de[(charset, index)] = numero
                return True
        if forzar or len(paletas) < tope:
            if lider:
                de_lider.add(len(paletas))
            paleta_de[(charset, index)] = len(paletas)
            paletas.append(list(palette))
            return True
        # No hay paleta para él, así que **se le presta una**: cada color va al
        # más cercano de los que hay. Se ve mal, pero se ve.
        #
        # Antes se lo descartaba, y taro cortó esa discusión con el argumento
        # que la cierra: si no podemos incluir todos los eventos, el proyecto
        # entero se cae. Y un sprite con colores raros es un error **visible**;
        # uno invisible es una trampa, y ya nos costó una tarde con la puerta
        # que Core rompe.
        #
        # Cuánto se ve depende del salto de color, no de cuántos pixeles
        # cambian: la puerta del pad cambia el 42% de los suyos con un salto de
        # 1 sobre 31 y queda casi igual, mientras que `Future3:1` cambia el 49%
        # con saltos de 17 y sí se nota.
        cuenta = sprite_colors(renderer.charsets.get(charset), index)
        mejor = None
        for numero, existente in enumerate(paletas):
            if numero in de_lider:
                continue        # ésas las pisa la ROM con los colores del líder
            costo = sum(v for c, v in cuenta.items() if c not in existente)
            if mejor is None or costo < mejor[0]:
                mejor = (costo, numero)
        if mejor is None:
            return False        # no hay ni una paleta que no sea de líder
        paleta_de[(charset, index)] = mejor[1]
        prestadas.add((charset, index))
        return True

    npcs = collect_npcs(game_map)

    def claves(npc):
        """Las (CharSet, índice) que el NPC puede llegar a dibujar: la de su
        fila y, si el gráfico sigue a la página, las de todas sus páginas."""
        salida = [(npc["charset"], npc["index"])]
        if npc["cambia"]:
            salida += [g[:2] for g in npc["graficos"] if g is not None]
        return salida

    # Los líderes posibles, que son los que el héroe puede llegar a dibujar.
    #
    # **Comparten una sola ranura de CGRAM**, porque lidera uno a la vez: la ROM
    # le sube los quince colores del que esté liderando cuando cambia el grupo y
    # al cargar el mapa. Antes se le reservaba una paleta a cada uno, y eso es
    # una paleta ocupada por alguien que no está en pantalla: el mapa 8 —la
    # calle a la que da el pad de Talan— pedía nueve de las ocho por eso, con
    # Talan y Kersh reservados en una calle donde no aparece ninguno.
    #
    # **Salvo el que además está como NPC en este mapa.** Ése se lleva paleta
    # propia, porque su fila la usa al mismo tiempo que el héroe: compartiendo
    # la ranura, con Talan liderando, el Kersh parado en el mapa se dibujaría
    # con los colores de Talan. Pasa en los mapas 1 y 6 con Kersh y en el 3 con
    # Talan; en los otros seis del PoC no pasa, y ahí es donde se gana.
    de_npc = {c for npc in npcs for c in claves(npc)}
    vistos, ranura_lider, propios = set(), None, set()
    for actor in lideres:
        a = renderer.database.actors[actor]
        clave = (a.charset, a.charset_index)
        if clave in vistos or not sprite_colors(
                renderer.charsets.get(a.charset), a.charset_index):
            continue
        vistos.add(clave)
        if clave in de_npc or ranura_lider is None:
            cabe(a.charset, a.charset_index, True, lider=True)
            if clave not in de_npc:
                ranura_lider = paleta_de[clave]
        else:
            # A la ranura compartida, y con **sus propios** colores: sus poses
            # se empaquetan con su paleta ordenada, que es la que la ROM sube
            # cuando le toca liderar.
            paleta_de[clave] = ranura_lider
            propios.add(clave)

    # Los CharSets de las páginas **ya no se fuerzan**. Se los forzaba para que
    # un personaje nunca se quedara sin paleta, y el precio era que un mapa con
    # más personajes que paletas no convertía: el 8 pedía nueve de las ocho y el
    # Hover-Tram pide once. Con el préstamo de `cabe` eso ya no hace falta —el
    # que no entra se dibuja con una ajena— y ningún mapa se cae por esto.
    #
    # El único que sigue forzado es el líder: el héroe está en pantalla todo el
    # tiempo y es a quien más se le notaría.
    #
    # El orden es el del mapa, **salvo los que tienen peso**: ver `PESO_DE_GRAFICO`.
    for npc in sorted(npcs, key=lambda n: -peso_de_grafico(n["charset"])):
        for clave in claves(npc):
            if clave not in vistos and not clave[0].startswith(rm2k.TILE_PREFIX):
                vistos.add(clave)
                cabe(clave[0], clave[1], False)
    # Y los de la orden 34, después de los NPCs y antes de los tiles.
    # **Mientras quepan**, como los tiles y no como los CharSets de una página:
    # forzarlos rompía tres mapas del juego —el 108, el 114 y el 207 pedían
    # nueve paletas de las ocho— y romper un mapa que hoy convierte es peor que
    # no dibujar un cambio de gráfico. El que no entra no se dibuja, que es lo
    # mismo que ya pasa con una página cuyo gráfico no entró. Los transparentes
    # ni siquiera piden paleta.
    for clave in graficos_de_ruta:
        if clave not in vistos and sprite_colors(
                renderer.charsets.get(clave[0]), clave[1]):
            vistos.add(clave)
            cabe(clave[0], clave[1], False)
    # El cronómetro **antes que los eventos dibujados con un tile del chipset**.
    # Sus dos colores van a la primera paleta con lugar y quedan reservados ahí;
    # `digitos_del_timer` después los encuentra puestos y no agrega nada.
    #
    # El orden importa y hasta ahora era el revés por accidente. Un evento de
    # tile entra "mientras quepa" —así está escrito unas líneas más abajo, y el
    # que no entra no se dibuja—, mientras que el cronómetro es HUD y está en
    # pantalla siempre. En el mapa 8 el tile 118 del chipset, que son dos
    # colores, se metía en la paleta del save point y la dejaba en catorce: el
    # cronómetro ya no entraba en ninguna y había que bajarle un color a un
    # personaje entero para hacerle lugar. Sirviéndolo antes, no se fusiona
    # nada y el tile se acomoda en otra paleta.
    if timer_colores:
        for numero, existente in enumerate(paletas):
            if numero in de_lider:
                continue        # ésas las pisa la ROM con los colores del líder
            union = existente + [c for c in timer_colores if c not in existente]
            if len(union) <= OBJ_COLORS:
                paletas[numero] = union
                break

    entran, afuera, salida, descartados = set(), set(), [], []
    for npc in npcs:
        for clave in claves(npc):
            if clave in vistos or clave in entran or clave in afuera:
                continue
            if cabe(clave[0], clave[1], False):
                entran.add(clave)
            else:
                afuera.add(clave)
        # Las que quedaron afuera no se dibujan, de ningún lado: la fila se
        # esconde si es la suya, y la página que la pida sale sin gráfico.
        npc["afuera"] = {c for c in claves(npc) if c in afuera}
        descartados += [(npc["evento"], c[0]) for c in sorted(npc["afuera"])]
        if (npc["charset"], npc["index"]) in afuera:
            npc["visible"] = False
            npc["tile_pasa"] = None
            if not npc["cambia"]:
                continue
            # La fila queda por las otras páginas, escondida, y sus campos
            # pasan a la primera de ellas que entre: es la ranura con la que
            # nace. Si ninguna entra, el evento no se dibuja nunca.
            otra = next((g for g in npc["graficos"]
                         if g is not None and g[:2] not in afuera), None)
            if otra is None:
                continue
            npc["charset"], npc["index"], npc["pose"] = otra
        salida.append(npc)
    # Y por último, el cronómetro. Sus dígitos son dos colores y el negro suele
    # estar ya en casi todas, así que le alcanza con **una entrada libre**; el
    # problema aparece en un mapa que llene las ocho paletas a quince, que es el
    # 8 —Lashe City, la calle a la que da el pad de Talan—.
    #
    # Ahí se le hace lugar bajando a un personaje de quince colores a catorce, y
    # se elige **el que menos pixeles mueva**. Sólo se miran paletas de un
    # personaje solo: bajar una que comparten dos obligaría a recuantizar a los
    # dos contra la paleta nueva, y eso es bastante más código para un caso que
    # no aparece. Tampoco se miran las de líder: la ROM las pisa.
    #
    # Medido en el mapa 8: `BLVehicles:5` mueve 105 pixeles de 4648, el 2,26%,
    # con un salto de 4 sobre 31. El siguiente candidato cuesta 11,84%.
    topes = {}
    # Sólo si de verdad no tiene dónde: ni una paleta con lugar **ni una ranura
    # libre**. Sin mirar las ranuras libres, esto le bajaba dos colores a
    # `People4:5` en el mapa 5 —16,85% de sus pixeles— cuando el mapa usa cuatro
    # paletas de las ocho y al cronómetro le sobraba una entera.
    if timer_colores and len(paletas) >= OBJ_PALETTES and not any(
            n not in de_lider
            and len(set(p) | set(timer_colores)) <= OBJ_COLORS
            for n, p in enumerate(paletas)):
        solos = collections.Counter()
        for clave, n in paleta_de.items():
            solos[n] += 1
        mejor = None
        for clave, n in paleta_de.items():
            if n in de_lider or solos[n] != 1 or clave[0].startswith(
                    rm2k.TILE_PREFIX):
                continue
            # Los que están en otro mapa de la ROM van **últimos**, no afuera:
            # el banco de poses es global, así que cuantizarlo distinto acá que
            # allá le cuesta al cartucho un banco más, 6 KB. Hasta el
            # 2026-09-12 quedaban excluidos y alcanzaba, porque en el mapa 8
            # siempre había un candidato de un solo mapa; al servir primero a
            # los gráficos con peso —el save point— el reparto se reacomodó, no
            # quedó ninguno, y la ROM con cronómetro dejó de armarse. Seis kilos
            # es peor que nada y mejor que no tener cronómetro.
            ajeno = solo_aqui is not None and clave not in solo_aqui
            cuenta = sprite_colors(renderer.charsets.get(clave[0]), clave[1],
                                   poses.get(clave))
            if not cuenta:
                continue
            faltan = len([c for c in timer_colores if c not in paletas[n]])
            nuevo_tope = OBJ_COLORS - faltan
            m, _ = asignador.merge_least_visible(cuenta, nuevo_tope)
            movidos = sum(v for c, v in cuenta.items() if m[c] != c)
            costo = (ajeno, movidos / float(sum(cuenta.values())), clave)
            if mejor is None or costo < mejor[0]:
                mejor = (costo, clave, n, nuevo_tope, sorted(set(m.values())))
        if mejor is not None:
            _costo, clave, n, nuevo_tope, paleta_nueva = mejor
            print("  para que entre el cronómetro, %s:%d baja a %d colores "
                  "(%.2f%% de sus pixeles)%s"
                  % (clave[0], clave[1], nuevo_tope, 100 * _costo[1],
                     ", y con un banco de poses propio" if _costo[0] else ""))
            paletas[n] = paleta_nueva
            topes[clave] = nuevo_tope

    # El reparto se devuelve para que `build_characters` lo use tal cual: un
    # segundo primer-lugar-que-entre en otro orden puede dar otra cuenta, y
    # dio: el mapa 8 entraba acá en ocho paletas y allá pedía nueve.
    return salida, descartados, (paletas, paleta_de, propios, de_lider,
                                 topes, prestadas, poses)


def build_characters(images, personajes, ranuras, reparto):
    """El banco de sprites que va a VRAM: una pose por ranura.

    `personajes` es la lista de (charset, índice) que necesitan paleta, en el
    orden en que se las reparte; `ranuras` la de (clave, charset, índice,
    pose), un bloque de 16 tiles por cada una y en ese orden. Desde el
    2026-09-05 acá va **una pose por ranura** y nada más: las doce de los que
    caminan viven en el cartucho —ver `banco_de_poses`— y se suben en caliente.
    Antes iban todas acá, y la escena de apertura pedía 768 tiles de los 512
    que direcciona la PPU.

    **Las paletas no se deciden acá**: llegan en `reparto`, que es lo que
    decidió `npcs_dibujables` para el mapa entero. Acá sólo se arma el índice
    de cada color adentro de la suya. Hasta el 2026-09-17 había además un
    reparto propio, primero-que-entre, para cuando no llegaba ninguno; no lo
    usaba nadie, y un segundo reparto en otro orden ya había dado otra cuenta
    —el mapa 8 entraba allá en ocho paletas y acá pedía nueve—.

    Devuelve (tiles, paletas, ubicación, paleta_de): ubicación mapea la clave
    de la ranura a (bloque, paleta), y paleta_de cada (charset, índice) a su
    paleta.
    """
    tiles = bytearray()
    colores = {}
    palettes = [list(p) for p in reparto[0]]
    paleta_de = dict(reparto[1])
    # Los que comparten la ranura del líder: su `lookup` sale de **su** paleta y
    # no de la de la ranura, porque la ROM va a subir sus colores ahí cuando le
    # toque liderar. Ver `npcs_dibujables`.
    propios = set(reparto[2])
    # Y a quién se le bajó el número de colores para que entrara el cronómetro.
    # Tiene que ser el mismo número que usó `npcs_dibujables`: si acá se
    # cuantizara con quince, las poses del cartucho no coincidirían con la
    # paleta que la ROM sube a CGRAM.
    topes = dict(reparto[4])
    # Y qué poses puede mostrar cada uno, que es sobre lo que se eligieron sus
    # quince colores allá. Tiene que ser el mismo conjunto: con otro, la paleta
    # que la ROM sube a CGRAM y los tiles que se empaquetan acá saldrían de dos
    # cuentas distintas.
    poses_de = dict(reparto[6])
    for charset, index in personajes:
        if (charset, index) in colores:
            continue
        palette, lookup, mapping = paleta_del_personaje(
            images[charset], index, topes.get((charset, index)),
            poses=poses_de.get((charset, index)))
        if (charset, index) not in paleta_de:
            sys.exit("%s:%d no está en el reparto de paletas" % (charset, index))
        if (charset, index) in propios:
            colores[(charset, index)] = (lookup, mapping)
            continue
        union = palettes[paleta_de[(charset, index)]]
        # Los colores que no estén en la paleta que le tocó van al más cercano
        # de los que hay. Pasa cuando el mapa se quedó sin paletas y
        # `npcs_dibujables` le prestó una ajena: se ve mal, pero se ve. La
        # cuenta de "más cercano" es la misma de allá, así que los dos lados
        # eligen igual.
        lookup = {}
        for color in palette:
            if color in union:
                lookup[color] = union.index(color) + 1
            else:
                cerca = min(union,
                            key=lambda p, c=color: asignador.luma_distance(p, c))
                lookup[color] = union.index(cerca) + 1
        colores[(charset, index)] = (lookup, mapping)

    where = {}
    for block, (clave, charset, index, pose) in enumerate(ranuras):
        lookup, mapping = colores[(charset, index)]
        where[clave] = (block, paleta_de[(charset, index)])
        first = block_tile(block)
        # El bloque no ocupa 16 tiles seguidos: es un cuadrado de 4x4 dentro
        # de una grilla de 16 de ancho, así que hay que dejar el hueco.
        needed = (first + 3 * OBJ_ROW + 4) * 32
        if len(tiles) < needed:
            tiles += bytes(needed - len(tiles))
        for i, tile in enumerate(pose_tiles(images[charset], index, pose,
                                            lookup, mapping)):
            number = first + (i // 4) * OBJ_ROW + (i % 4)
            tiles[number * 32:(number + 1) * 32] = tile
    return bytes(tiles), palettes, where, paleta_de, colores


# Una pose en el cartucho: los 16 tiles seguidos, por filas.
POSE_BYTES = 16 * 32


def banco_de_poses(images, personajes, colores):
    """Las doce poses de cada personaje que cambia de pose, para el cartucho.

    Un bloque por personaje —doce poses de 512 bytes, 6 KB— y no uno para
    todos: cada uno va con `.bloque`, así que ningún DMA de una pose cruza de
    banco. Y **de la ROM entera, no del mapa**: los mapas 1 y 2 comparten a
    Core, a Manta y a Kersh, y con una copia por mapa la ROM del arranque con
    ventana se pasaba del cartucho por 19 KB. La pose `p` del personaje `g`
    está en `sprite_poses_g + p * 512`, con `g` el índice de la ROM; el mapa
    lleva sus personajes animados en orden y `emit` traduce.
    """
    bancos = {}
    for charset, index in personajes:
        # Con el lookup de `build_characters`, que es el de la paleta en la
        # que quedó empaquetado: una pose subida en caliente se dibuja con la
        # paleta que ya está en CGRAM.
        lookup, mapping = colores[(charset, index)]
        datos = bytearray()
        for pose in range(SPRITE_POSES):
            for tile in pose_tiles(images[charset], index, pose, lookup,
                                   mapping):
                datos += tile
        bancos[(charset, index)] = bytes(datos)
    return bancos


# El cronómetro: once glifos de 8x16 en el System, a partir de (32, 32). Diez
# dígitos y los dos puntos, que es todo lo que `Sprite_Timer::Draw` dibuja.
TIMER_GLIFOS = 11
TIMER_GLIFO_W, TIMER_GLIFO_H = 8, 16
TIMER_ORIGEN = (32, 32)
# Dónde se dibuja en pantalla. `Sprite_Timer` lo pone en
# `menu_offset_x + 4` y `menu_offset_y + 4`, y con una pantalla más angosta que
# el menú los dos desplazamientos dan cero.
TIMER_X, TIMER_Y = 4, 4


def colores_del_timer(sys_img):
    """Los colores que usan los once glifos del cronómetro.

    Hace falta **antes** de repartir las paletas y no sólo al empaquetar los
    dígitos: si un mapa llena las ocho, hay que decidir a quién bajarle un color
    para hacerle lugar, y esa decisión cambia cómo se cuantiza a ese personaje.
    """
    colores = collections.Counter()
    for i in range(TIMER_GLIFOS):
        for y in range(TIMER_GLIFO_H):
            for x in range(TIMER_GLIFO_W):
                r, g, b, a = sys_img.getpixel((TIMER_ORIGEN[0] + i * 8 + x,
                                               TIMER_ORIGEN[1] + y))
                if a:
                    colores[(r >> 3, g >> 3, b >> 3)] += 1
    return colores


def digitos_del_timer(sys_img, tiles, palettes, de_lider=(),
                     tope=OBJ_PALETTES):
    """Los once glifos del cronómetro, al final del banco de sprites.

    Van como dos tiles de 8x8 apilados cada uno, y los once entran en una fila
    de dieciséis: el glifo i ocupa el tile `base + i` y el `base + 16 + i`. La
    base se redondea a una fila para que esa cuenta valga.

    Devuelve (tiles, base, número de paleta). **No se lleva una paleta propia si
    no hace falta**: son dos colores —negro y rojo puro— y entran de sobra en la
    de cualquier personaje que tenga trece o menos, exactamente como entran los
    eventos dibujados con un tile del chipset. Sólo se agrega una si ninguna
    tiene lugar.

    Reservársela de entrada costaba una paleta de las ocho, y eso no es
    contabilidad: `npcs_dibujables` decide con ese número **qué eventos se
    dibujan**. El 2026-09-07, al armar `demo-apertura` con el cronómetro, el
    mapa 2 perdió dos eventos, y uno era el del medio de la puerta que Core
    rompe: taro llegó a la cinemática, la puerta no cambió de tile y no pudo
    pasar. Un evento que no se dibuja **igual ocupa**, así que la pérdida no es
    sólo visual.
    """
    colores = colores_del_timer(sys_img)
    if len(colores) > OBJ_COLORS:
        raise SystemExit("los dígitos del cronómetro usan %d colores y entran %d"
                         % (len(colores), OBJ_COLORS))
    quiere = sorted(colores)
    # La primera paleta en la que entren sus colores sin fusionar nada. Es el
    # mismo primer-ajuste de `build_characters` y por la misma razón.
    #
    # **Menos las ranuras de líder.** Ésas las pisa la ROM con los quince
    # colores del que esté liderando cada vez que cambia el grupo o se carga un
    # mapa, así que un dígito metido ahí se quedaría sin su rojo en cuanto Talan
    # le pase el liderazgo a Kersh. En los siete mapas de `demo-apertura` hoy no
    # cae en ninguna, que es justo lo que hace que el error fuera invisible.
    for numero, existente in enumerate(palettes):
        if numero in de_lider:
            continue
        union = list(existente) + [c for c in quiere if c not in existente]
        if len(union) <= OBJ_COLORS:
            palettes[numero] = union
            paleta, cual = union, numero
            break
    else:
        if len(palettes) >= tope:
            raise SystemExit(
                "el cronómetro no entra: el mapa ya usa las %d paletas de "
                "sprite que le tocan y ninguna tiene lugar para sus %d colores"
                % (tope, len(quiere)))
        paleta, cual = list(quiere), len(palettes)
        palettes.append(paleta)
    indice = {color: paleta.index(color) + 1 for color in quiere}

    tiles = bytearray(tiles)
    # La base se redondea a una **fila de bloques**, 64 tiles, y no a una fila
    # de la grilla: los bloques de 4x4 de la última fila de bloques ocupan
    # cuatro filas de la grilla, y con la imagen de VRAM chica que hay desde
    # las poses en caliente, redondear a 16 dejaba los glifos encima de la
    # última fila del bloque del héroe. Ahí no se veía nada hasta que la pose
    # del héroe subía y pisaba el 0 y los dos puntos.
    base = -(-(len(tiles) // 32) // 64) * 64
    if (base + 16 + TIMER_GLIFOS) * 32 > len(tiles):
        tiles += bytes((base + 16 + TIMER_GLIFOS) * 32 - len(tiles))
    for i in range(TIMER_GLIFOS):
        for mitad in (0, 1):
            celda = []
            for y in range(CELL):
                fila = []
                for x in range(CELL):
                    r, g, b, a = sys_img.getpixel(
                        (TIMER_ORIGEN[0] + i * 8 + x,
                         TIMER_ORIGEN[1] + mitad * CELL + y))
                    fila.append(indice[(r >> 3, g >> 3, b >> 3)] if a else 0)
                celda.append(tuple(fila))
            numero = base + mitad * 16 + i
            tiles[numero * 32:(numero + 1) * 32] = pack_tile(tuple(celda),
                                                             planes=4)
    return bytes(tiles), base, cual


def gotas_de_lluvia(tiles, palettes, de_lider=(), timer_base=None,
                   tope=OBJ_PALETTES):
    """Los seis tiles de las gotas —arriba y abajo de la raya, en los tres
    grises— y la paleta donde entran sus colores. Ver OP_WEATHER en eventos.py.

    Es lo mismo que `digitos_del_timer`: los colores van en la primera paleta
    de personaje con lugar, menos las de líder, y los tiles al final del
    banco. Si el cronómetro está, en su misma fila de dieciséis, que le sobran
    cinco lugares; si no, en una fila de bloques propia. El tono `t` arriba es
    el tile `base + t` y abajo el `base + 16 + t`. Devuelve (tiles, base,
    número de paleta).
    """
    quiere = [c for c in eventos.LLUVIA_COLORES]
    cual = _primer_lugar(palettes, de_lider, quiere, tope)
    if cual is None:
        # No hay lugar: este mapa no dibuja lluvia. No se le baja un color a
        # nadie para hacerle lugar, como al cronómetro: eso cambiaría el
        # reparto, y el reparto es lo que decide qué colores tiene cada mapa.
        return bytes(tiles), 0, 0
    paleta = palettes[cual]
    tiles = bytearray(tiles)
    if timer_base:
        base = timer_base + TIMER_GLIFOS
    else:
        base = -(-(len(tiles) // 32) // 64) * 64
    if (base + 16 + 3) * 32 > len(tiles):
        tiles += bytes((base + 16 + 3) * 32 - len(tiles))
    raya = set(eventos.lluvia_pixeles(0, 0))
    for tono, color in enumerate(quiere):
        indice = paleta.index(color) + 1
        for mitad in (0, 1):
            celda = tuple(tuple(indice if (x, mitad * CELL + y) in raya else 0
                                for x in range(CELL)) for y in range(CELL))
            numero = base + mitad * 16 + tono
            tiles[numero * 32:(numero + 1) * 32] = pack_tile(celda, planes=4)
    return bytes(tiles), base, cual


def cartel_de_imagen(info, tiles, palettes, base_previa=None):
    """El cartel del `ShowPicture` al final del banco de sprites: sus tiles y
    **una paleta entera para él solo**.

    No comparte paleta con nadie, a diferencia del cronómetro y de las gotas, y
    no es por falta de lugar: el fundido del cartel es un tinte de sus quince
    entradas de CGRAM cuadro a cuadro, así que un personaje metido en esa
    paleta se apagaría y se prendería con él.

    Y va **arriba de `SPRITE_CGRAM`**, o sea afuera del rango que recorren
    `aplicar_tinte` y `subir_paletas`. Eso no es acomodar números: en RM2k las
    imágenes tienen `affected_by_tint` apagado de fábrica —`Priority_PictureOld`
    es 120 y `Priority_Screen` 90—, así que el tinte de pantalla no las toca.
    Quedando fuera del rango, no hay que acordarse de saltearlas.

    Devuelve (tiles, base, número de paleta), o (tiles, 0, 0) si el mapa ya usa
    las ocho paletas de sprite: ahí este mapa no dibuja el cartel, y la
    referencia lo sabe con la misma cuenta.
    """
    if len(palettes) >= OBJ_PALETTES:
        return bytes(tiles), 0, 0
    cual = len(palettes)        # la primera libre, sin agregarla a la lista
    tiles = bytearray(tiles)
    if base_previa:
        base = -(-(base_previa + 2 * 16) // 64) * 64
    else:
        base = -(-(len(tiles) // 32) // 64) * 64
    cuantos = imagen.tiles_reservados(info)
    if (base + cuantos) * 32 > len(tiles):
        tiles += bytes((base + cuantos) * 32 - len(tiles))
    for numero, celda in imagen.celdas(info).items():
        tiles[(base + numero) * 32:(base + numero + 1) * 32] = pack_tile(
            celda, planes=4)
    return bytes(tiles), base, cual


def mapa_muestra_animacion(game_map, renderer, comandos=()):
    """Si alguna página de este mapa puede dibujar una animación de batalla.

    Se mira sobre los comandos crudos y no sobre el bytecode ya compilado, y a
    propósito: la VRAM hay que reservarla al convertir el mapa y las páginas se
    compilan después. Es un superconjunto —una página que al final no compile
    deja 64 tiles reservados sin usar— y tiene que serlo: si el bytecode
    mostrara una animación que el mapa no reservó, la ROM escribiría los tiles
    encima de los de un personaje.

    `comandos` son los de las páginas de prueba, que no salen del mapa.
    """
    numeros = set()
    for cmd in list(comandos) + [cmd for evento in game_map.events
                                 for page in evento.pages
                                 for cmd in page.commands]:
        if (cmd.code == eventos.SHOW_BATTLE_ANIMATION
                and len(cmd.parameters) >= 3):
            numeros.add(cmd.parameters[0])
    return any(animacion_mod.de_numero(renderer, n) is not None
               for n in numeros)


def animacion_de_mapa(tiles, palettes, usadas=0):
    """La caja de la animación de batalla al final del banco de sprites: sus
    64 tiles y **una paleta entera para ella sola**.

    No comparte paleta con nadie por lo mismo que el cartel: los quince colores
    son de la animación, se suben cuando empieza y se pisan cuando empieza otra,
    y un personaje metido ahí cambiaría de color con ella. Y va **arriba de
    `SPRITE_CGRAM`**, o sea afuera del rango que recorren `aplicar_tinte` y
    `subir_paletas`, que además es lo fiel: en `Spriteset_Map::Update` el tono
    del mapa va al tilemap, a los personajes, al panorama y a las sombras, y a
    las animaciones no.

    Los tiles se reservan **en blanco**: lo que va adentro lo sube la ROM por
    DMA cuadro a cuadro, desde el cartucho. Ver `animacion.py`.

    Devuelve (tiles, base, número de paleta), o (tiles, 0, 0) si el mapa ya usa
    las ocho paletas de sprite. `usadas` son las que ya se llevó el cartel.
    """
    cual = len(palettes) + usadas
    if cual >= OBJ_PALETTES:
        return bytes(tiles), 0, 0
    tiles = bytearray(tiles)
    # Después de todo lo demás: el cronómetro, las gotas y el cartel ya
    # agrandaron `tiles` hasta cubrir lo suyo, así que el final del banco es el
    # largo. Redondeado a una **fila de bloques**, que es lo que la aritmética
    # de los objetos de 32x32 necesita entera.
    base = -(-(len(tiles) // 32) // 64) * 64
    if (base + animacion_mod.TILES) * 32 > len(tiles):
        tiles += bytes((base + animacion_mod.TILES) * 32 - len(tiles))
    return bytes(tiles), base, cual


def tope_de_paletas_del_mapa(renderer, game_map, lideres, graficos,
                             timer_colores, solos, poses, muestra_animacion):
    """Cuántas paletas de sprite puede repartirse este mapa entre sus
    personajes: las ocho, o **siete** si muestra animaciones de batalla.

    La caja de la animación necesita una paleta entera para ella sola, y los
    dos mapas de la intro —el 2 y el 3, que son los que la escena usa— llenaban
    las ocho. Sacarle una a los personajes es lo que hace que la escena del
    Emitter Room tenga dibujo; lo que cuesta son colores fusionados, y lo dice
    el informe de cada mapa.

    **Salvo que con siete no entre el cronómetro**, que no es negociable: sin
    sus dos colores no hay cronómetro en toda la ROM. Ahí se vuelve a ocho y
    este mapa no dibuja animaciones, que es lo que le pasa al mapa 9.

    Vive suelta y no adentro de `convertir` porque **la referencia tiene que
    tomar la misma decisión**: si los dos lados repartieran las paletas
    distinto, no estarían dibujando el mismo mapa. La referencia se fue el
    2026-09-16 y esto quedó donde estaba: sigue siendo una decisión de
    reparto y no un detalle de `convertir`.
    """
    if not muestra_animacion:
        return OBJ_PALETTES
    menos = OBJ_PALETTES - 1
    if timer_colores:
        reparto = npcs_dibujables(renderer, game_map, lideres, menos, graficos,
                                  timer_colores, solos, poses)[2]
        copia = [list(p) for p in reparto[0]]
        if _primer_lugar(copia, reparto[3], list(timer_colores),
                         menos) is None:
            return OBJ_PALETTES
    return menos


def _primer_lugar(palettes, de_lider, colores, tope=OBJ_PALETTES):
    """La primera paleta —menos las de líder— donde entran `colores` sin
    fusionar nada, o una nueva si queda ranura; la agrega o la agranda y
    devuelve su número, o None si no hay lugar.

    `tope` es cuántas paletas de sprite puede usar este mapa, que **no siempre
    son las ocho**: un mapa que muestra animaciones de batalla reserva una para
    la caja de la animación, y ni el cronómetro ni las gotas se la pueden
    llevar. Ver `tope_de_paletas` en `convertir`.
    """
    for numero, existente in enumerate(palettes):
        if numero in de_lider:
            continue
        union = list(existente) + [c for c in colores if c not in existente]
        if len(union) <= OBJ_COLORS:
            palettes[numero] = union
            return numero
    if len(palettes) < tope:
        palettes.append(list(colores))
        return len(palettes) - 1
    return None


def mapas_por_personaje(renderer, map_ids, game_dir):
    """En cuántos mapas de la ROM aparece cada (CharSet, índice)."""
    cuenta = collections.Counter()
    for otro in map_ids:
        gm = renderer.cargar_mapa(os.path.join(game_dir, "Map%04d.lmu" % otro))
        suyos = set()
        for evento in gm.events:
            for pagina in evento.pages:
                nombre = (getattr(pagina, "character_name", "") or "").strip()
                if nombre:
                    suyos.add((nombre, pagina.character_index))
        cuenta.update(suyos)
    return cuenta


def hay_lluvia(map_ids, extra=()):
    """Si alguna página de estos mapas pone lluvia: entonces cada mapa de la
    ROM lleva las gotas, porque el clima sigue al cambiar de mapa. `extra`
    son los comandos de las páginas de prueba."""
    def llueve(cmd):
        return (cmd.code == eventos.WEATHER_EFFECTS
                and cmd.parameters[:1] == [eventos.CLIMA_LLUVIA])
    if any(llueve(cmd) for cmd in extra):
        return True
    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(args_game_dir[0],
                                        "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                for cmd in page.commands:
                    if llueve(cmd):
                        return True
    return False


def npc_table(npcs, where, movibles=(), indice_animado=None, anima_quieto=()):
    """Los NPCs listos para la ROM, ya ordenados como los dibuja RM2k.

    El orden de dibujado es primero por capa y recién después por Y: uno "below"
    queda debajo del héroe aunque esté más adelante en pantalla. En la consola,
    el objeto con índice más bajo de OAM es el que se ve encima, así que la
    tabla va del frente hacia el fondo.

    **Este orden inicial es parte del contrato con la referencia.** Los que
    caminan cambian de Y y la ROM los reacomoda de a uno, con una inserción que
    respeta el orden de los empatados; la referencia ordena de nuevo con un
    `sorted` estable sobre esta misma lista. Las dos cosas dan lo mismo sólo si
    las dos arrancan de acá.

    Los de `movibles` llevan además en qué banco de poses del cartucho están
    sus doce, para que la ROM las suba en caliente mientras caminan.
    """
    rows = []
    for npc in sorted(npcs, key=orden_de_dibujo, reverse=True):
        camina = npc["evento"] in movibles
        clave = (("ev", npc["evento"]) if camina
                 else (npc["charset"], npc["index"], npc["pose"]))
        block, slot = where[clave]
        rows.append({
            "x": npc["x"] * 16, "y": npc["y"] * 16,
            "tile": block_tile(block), "palette": slot,
            "layer": npc["layer"], "blocks": npc["blocks"],
            "evento": npc["evento"], "dir": npc["pose"] // 3,
            "pose": npc["pose"],
            "poses": (indice_animado[(npc["charset"], npc["index"])]
                      if camina else None),
            "velocidad": npc.get("velocidad", 3),
            # Los quietos con animación continua: su columna sale del reloj del
            # juego. Los que caminan la llevan en su ranura de ruta, así que el
            # flag no vale para ellos aunque su página también la pida.
            "anima": npc["evento"] in anima_quieto,
            "visible": npc.get("visible", True),
            "tile_pasa": npc.get("tile_pasa"),
        })
    return rows


# --- conversión -------------------------------------------------------------

def build_palette(grid, bg_colors, otras=()):
    """Los colores del mapa, en una sola tabla, fusionando sólo si sobran.

    Con 8 bits por pixel el único límite es cuántas entradas de CGRAM quedan
    libres debajo de la capa de encima. Map0007 usa 60, así que no se fusiona
    nada; el camino de fusión existe para mapas más cargados y es el mismo de
    la Mega Drive.

    `otras` son las grillas de los otros dibujos de la animación del ChipSet.
    Cuentan para la paleta como el dibujo de siempre —el agua del mapa 5 trae
    tres colores que no están en su paso 0, y sin ellos el paso 1 no se podría
    escribir con esta paleta— y salen fusionadas con el mismo `mapping`, que
    es lo que las deja comparables entre sí.
    """
    counts = collections.Counter(p for g in (grid,) + tuple(otras)
                                 for row in g for tile in row
                                 for line in tile for p in line
                                 if p is not None)
    if len(counts) <= bg_colors:
        return sorted(counts), grid, list(otras), []

    mapping, merged = asignador.merge_least_visible(counts, bg_colors)

    def fusionar(g):
        return [[tuple(tuple(mapping.get(p) for p in line) for line in tile)
                 for tile in row] for row in g]

    return (sorted({c for c in mapping.values()}), fusionar(grid),
            [fusionar(g) for g in otras], merged)


def _huella_de_imagen(img):
    """Lo que hace a una imagen: modo, tamaño y pixeles."""
    return b"%s %dx%d " % (img.mode.encode(), img.size[0], img.size[1]) \
        + img.tobytes()


_VERSION_CAPAS = None


def convert_layers(base, above_img, variantes=None):
    """`_convert_layers`, recordado en disco.

    Es lo más caro del conversor —cuantizar y cortar en tiles las capas y sus
    dibujos animados, y repartir CGRAM: unos 25 de los 39 s de `demo-ciudad`,
    medido el 2026-09-10— y es una función pura de sus argumentos. La clave son
    **los pixeles de las imágenes** y no el `.lmu` ni el ChipSet: así entra
    todo lo que las produce, el renderer incluido, sin tener que enumerarlo. Y
    lleva el hash de este archivo y de `rm2k.py`, que es de donde salen las
    constantes del reparto: tocar el conversor invalida lo suyo solo.

    Verificado con `SIN_CACHE=1`: el `.sfc` es el mismo byte por byte.
    """
    global _VERSION_CAPAS
    from comun import cache_disco
    if _VERSION_CAPAS is None:
        # Y el binario de `tiles`, que es el que emite: recompilarlo sin tocar
        # nada de acá tiene que invalidar lo guardado.
        # Y el asignador, que decide qué colores quedan: hasta el 2026-09-17
        # no estaba, así que cambiar cómo se fusiona no invalidaba nada.
        _VERSION_CAPAS = (cache_disco.version_de("port/snes_convert.py",
                                                 "rpgmaker/rm2k.py",
                                                 "port/asignador.py")
                          + tiles_bin.version())
    partes = [_VERSION_CAPAS, _huella_de_imagen(base),
              _huella_de_imagen(above_img)]
    for familia in sorted(variantes or {}):
        partes.append("familia %s" % familia)
        for img in variantes[familia]:
            partes.append(_huella_de_imagen(img))
    en_disco = cache_disco.clave(*partes)
    hecho = cache_disco.leer("capas", en_disco)
    if hecho is None:
        hecho = _convert_layers(base, above_img, variantes)
        cache_disco.guardar("capas", en_disco, hecho)
    return hecho


def _convert_layers(base, above_img, variantes=None):
    """Las dos capas juntas, que es la única forma de repartir CGRAM bien.

    El corte entre el fondo y la capa de encima no lo puede decidir ninguna de
    las dos por su cuenta, así que se decide acá y hay un solo lugar donde está
    escrito. Antes cada llamador convertía una y después la otra, y que las tres
    copias del orden coincidieran era cuestión de suerte.

    La regla es que el fondo tiene la primera opción: se queda con las paletas
    que le hacen falta para los colores que realmente usa, porque va en 8 bits
    y no puede repartirlos en grupos. La capa de encima se lleva las que sobren
    —hasta las que pida, nunca más— y si no le alcanzan, fusiona.

    Va en ese orden y no al revés porque son 300 mapas cuya capa de encima pide
    una o dos paletas contra un puñado que pediría siete: dejar que el de
    encima se sirva primero le sacaría colores al fondo en todos para que unos
    pocos no fusionen.

    Hasta el 2026-09-07 la ventana de mensaje se llevaba además la paleta que
    queda justo debajo de la capa de encima, y **la pagaba el fondo**. La
    elección de a quién cobrarle era medida y no de gusto. El fondo va en 8
    bits, así que sus paletas son un pozo común: una menos le saca 16 entradas
    de CGRAM y lo obliga a fusionar sólo el excedente. La capa de encima va en
    4 y empaqueta por tile, así que una paleta menos le puede costar muchísimo
    más. En el mapa 1 —el que descubrió esto— el fondo usa 49 colores y la capa
    de encima 64 justos en 4 paletas: quitándole una al fondo se fusionan 2
    colores, y quitándosela a la capa de encima habría que fusionar 16.

    Hoy la ventana vive en la paleta 0, abajo de todo —ver
    `paleta_de_la_ventana`—, así que no le cobra a ninguna de las dos capas.

    Devuelve (lo de convert(), lo de convert_above()).
    """
    base_grid = cut_tiles(quantize(base))
    above_grid = cut_tiles(quantize(above_img))
    # Los otros dibujos de la animación del ChipSet, cortados igual que el
    # fondo. Ver `convert`.
    grillas = {familia: [cut_tiles(quantize(img)) for img in imagenes]
               for familia, imagenes in (variantes or {}).items()}

    # Lo que el fondo usa, y por lo tanto las paletas de 16 que necesita. El
    # +1 es el color de fondo de la pantalla, que ocupa la entrada 0.
    #
    # Cuentan **todos los dibujos**: el agua del mapa 5 trae tres colores que no
    # están en el dibujo que se ve al entrar, y si el reparto se decidiera sin
    # ellos no habría dónde ponerlos cuando el agua se mueva.
    usados = len({p for g in [base_grid] + [g for gs in grillas.values()
                                            for g in gs]
                  for row in g for tile in row
                  for line in tile for p in line if p is not None})
    pide = -(-(usados + CGRAM_RESERVADAS) // COLORS_PER_PALETTE)
    libres = max(1, min(MAX_ABOVE_PALETTES, BG_PALETTES - pide))

    above_grid, paletas_encima, fusionados = repartir_encima(above_grid, libres)
    # Sin capa de encima no se reserva nada, pero el DMA igual manda una paleta
    # vacía —ver `convert_above`—, así que el corte se cuenta como si hubiera
    # una.
    primera = above_split(max(1, len(paletas_encima)))
    above = convert_above(above_grid, paletas_encima, primera, len(fusionados))
    # El fondo llega **hasta donde arranca la capa de encima**, sin dejar
    # paletas en el medio: va a 8 bits y no necesita alineación. La ventana no
    # le cobra una paleta porque vive abajo de todo, adentro de
    # `CGRAM_RESERVADAS`.
    tope = primera
    if tope < 1:
        # Inalcanzable con los datos del juego —haría falta una capa de encima
        # que pida las ocho paletas— pero si pasa, el fondo se quedaría sin
        # ninguna y `bg_budget` daría un presupuesto negativo.
        raise SystemExit(
            "la capa de encima se llevó las ocho paletas y no queda ninguna "
            "para el fondo")
    # Y la paleta del fondo, con ese presupuesto y sobre **todos** sus dibujos.
    # Se decide acá y `convert` la recibe, igual que la capa de encima.
    presupuesto = bg_budget(tope)
    otras = [g for familia, _ in FAMILIAS for g in grillas.get(familia, ())]
    antes = len({p for row in base_grid for tile in row
                 for line in tile for p in line if p is not None})
    palette, base_grid, otras, merged = build_palette(base_grid, presupuesto,
                                                      otras)
    return (convert(base_grid, palette, grillas, otras,
                    {"colores": antes, "presupuesto": presupuesto,
                     "fusionados": len(merged)}), above)


def paleta_de_la_ventana(primeras=None):
    """En qué paleta va la ventana de mensaje: la **0**, siempre.

    Las celdas de la ventana se emiten una sola vez con los tres bits de paleta
    adentro, así que la paleta tiene que ser una sola para toda la ROM. Antes se
    tomaba la más baja de las capas de encima de todos los mapas —`min(primeras)
    - 1`— y el fondo de **todos** quedaba apretado abajo de ella, aunque el mapa
    tuviera media CGRAM libre arriba.

    Poniéndola en la 0 el problema desaparece: la ventana ocupa las entradas 1 a
    7 —la 0 es el color de fondo de la pantalla, que en una paleta de BG2 es el
    transparente y la ventana no dibuja—, y el fondo queda contiguo desde la 8
    hasta donde arranque la capa de encima de cada mapa. `primeras` ya no se usa
    y queda para no romper a quien llame.
    """
    return 0


# Las dos familias de tiles que anima el ChipSet, con cuántos dibujos tiene
# cada una y en el orden en que sus corridas van a la VRAM. Vive en rm2k.py
# junto con la cadencia de cada una, que es lo que dice qué dibujo toca.
FAMILIAS = rm2k.FAMILIAS_ANIMADAS


def convert(grid, palette, variantes, otras, resumen):
    """La grilla del mapa a tiles, paleta y tilemap.

    **No decide la paleta**: llega de `build_palette`, que la elige en
    `_convert_layers` con el presupuesto que le dejó la capa de encima. `grid`
    y `otras` son las grillas ya fusionadas con esa misma paleta; `variantes`
    las originales, que sólo se usan para saber cuántos dibujos trae cada
    familia. `resumen` trae lo que se midió antes de fusionar.

    `variantes` son las grillas de los **otros** dibujos de la animación del
    ChipSet, por familia: `{"agua": [g1, g2], "animado": [g1, g2, g3]}`. El
    dibujo 0 es `grid`.

    Las celdas que cambian de un dibujo a otro se llevan tiles propios, en una
    **corrida contigua al final del banco**, y no comparten ninguno con las
    celdas quietas. Animar es pisar el dato del tile en la VRAM sin tocar el
    tilemap, así que un tile compartido con una celda quieta la haría cambiar a
    ella también; y con la corrida contigua, un paso de la animación es un solo
    DMA.

    Devuelve (datos de tiles, palabras de CGRAM, tilemap, resumen). Dónde caen
    las corridas y los bytes de cada dibujo van en `resumen["animacion"]`.
    """
    # De vuelta a su familia, ya fusionadas con el mismo mapeo que `grid`, y con
    # el dibujo 0 adelante: `dibujos[familia][d]` es la grilla del dibujo `d`.
    dibujos, resto = {None: [grid]}, list(otras)
    for familia, _ in FAMILIAS:
        cuantas = len(variantes.get(familia, ()))
        dibujos[familia] = [grid] + resto[:cuantas]
        resto = resto[cuantas:]

    # Lo que decidió el asignador, como imágenes indexadas: el color `k` de la
    # paleta es la entrada `CGRAM_RESERVADAS + k`, y lo transparente es la 0.
    # Una por dibujo, todas con la misma CGRAM: `tiles` corta si dos le dan
    # distinto color a una entrada que alguna dibuja.
    posicion = {color: CGRAM_RESERVADAS + k for k, color in enumerate(palette)}
    colores = [None] * 256
    for color, entrada in posicion.items():
        colores[entrada] = color
    transparentes = [e == 0 for e in range(256)]
    ancho, alto = len(grid[0]) * CELL, len(grid) * CELL

    def imagen(g):
        pixeles = [0] * (ancho * alto)
        for cy, row in enumerate(g):
            for cx, tile in enumerate(row):
                for y, line in enumerate(tile):
                    fila = (cy * CELL + y) * ancho + cx * CELL
                    for x, color in enumerate(line):
                        if color is not None:
                            pixeles[fila + x] = posicion[color]
        return tiles_bin.png_indexado(ancho, alto, pixeles, colores,
                                      transparentes)

    imagenes = [("fondo", imagen(grid))]
    familias, animaciones = [], []
    for familia, _ in FAMILIAS:
        if len(dibujos[familia]) < 2:
            continue
        pngs = [imagen(g) for g in dibujos[familia][1:]]
        imagenes += [("%s-%d" % (familia, d + 1), png)
                     for d, png in enumerate(pngs)]
        familias.append(familia)
        animaciones.append(pngs)

    # Las celdas que cambian de un dibujo a otro se llevan tiles propios en una
    # corrida contigua por familia, después de los quietos: eso lo hace
    # `tiles`, que es quien numera. Ver "Animations" en tools/tiles/README.md.
    tile_data, cgram, tilemap, corridas = tiles_bin.convertir(
        imagenes[0][1], 8, len(grid[0]), animaciones=animaciones,
        max_tiles=MAX_TILES)
    siguiente = len(tile_data) // BYTES_PER_TILE

    # Y los otros dibujos de cada corrida, uno detrás del otro y en el orden de
    # la VRAM: así subirlos es escribir la dirección y disparar el DMA.
    animacion = {}
    for familia, (inicio, largo, bytes_de) in zip(familias, corridas):
        if not largo:
            continue
        cuantos = dict(FAMILIAS)[familia]
        if len(bytes_de) != cuantos:
            raise SystemExit("la familia %r pide %d dibujos y llegaron %d"
                             % (familia, cuantos, len(bytes_de)))
        animacion[familia] = {"base": inicio, "tiles": largo,
                              "dibujos": list(bytes_de)}

    # CGRAM: el bloque del mapa lleva **sólo sus colores** y se sube a partir de
    # `CGRAM_RESERVADAS`. Lo de abajo —el color de fondo de la pantalla y la
    # paleta de la ventana— es de toda la ROM y lo sube `cgram_base`.
    cram = [int.from_bytes(cgram[2 * e:2 * e + 2], "little")
            for e in range(CGRAM_RESERVADAS, CGRAM_RESERVADAS + len(palette))]

    summary = {
        "colores": resumen["colores"],
        "usados": len(palette),
        "presupuesto": resumen["presupuesto"],
        "fusionados": resumen["fusionados"],
        "tiles": siguiente,
        "celdas": sum(len(row) for row in tilemap),
        "animacion": animacion,
        "imagenes": imagenes,
    }
    return bytes(tile_data), cram, tilemap, summary


# --- el mapa como bloques de 16x16 -----------------------------------------
# El tilemap del PPU no pasa de 64x64 celdas, y encima hay que repartir la VRAM
# con los tiles, así que la ventana que se le deja son 64x32: 512x256 pixeles
# contra los 256x224 de la pantalla. Los mapas del juego llegan a 1000x80
# celdas, o sea que el mapa entero no está nunca en la VRAM: la ROM va
# redibujando la columna y la fila que entran mientras la cámara se mueve.
#
# Lo que se guarda en la ROM tampoco es el tilemap expandido. Una celda de 16x16
# de RM2k son cuatro celdas de 8x8 de la SNES, y es la unidad con la que el
# juego fue dibujado: se repite muchísimo. Guardando un índice a una tabla de
# bloques, el mapa más pesado pasa de 175 KB —más que la ROM entera— a 40.
#
# El bloque lleva las dos capas juntas y la pasabilidad. Que la pasabilidad
# entre en el bloque no es gratis: dos celdas que se dibujan igual podrían
# tener permisos distintos si vinieran de tiles distintos del ChipSet, así que
# va en la clave y se separan solas.
WINDOW_W, WINDOW_H = 64, 32     # la ventana de tilemap que vive en la VRAM
MAP_LAYOUT = 1                  # dos pantallas de 32x32 al lado, que es 64x32
BLOCK_BYTES = 16                # cuatro celdas de BG1 y cuatro de BG2

# --- el reparto de la VRAM --------------------------------------------------
# Las 64 KB no se reparten como uno quiera: la base de los tiles de los sprites
# va de a 16 KB, la de cada fondo de a 8 KB y la de cada tilemap de a 2 KB.
# Cuál reparto toca lo decide el conversor y viaja en el .inc: la ROM no elige
# nada.
#
# Todo mapa lleva la ventana de mensaje —desde el 2026-09-17 no es opcional; un
# mapa sin ventana de texto no existe en la práctica— y hay tres repartos que
# le hacen lugar. Hasta ese día había otros tres sin ella. La ventana necesita 8 KB
# de tiles propios —el texto son 240 tiles y no hay forma de bajarlo, porque un
# glifo de 6 px no se alinea a celdas de 8 y hay que componerlo pixel por
# pixel— más **2 KB de tilemap propio**, y los 64 KB ya estaban repartidos al
# 100%.
#
# Lo que hace posible lo de los tiles es que `encima` y `ventana` queden
# **pegados**: BG2 tiene una sola base y sus índices de tile son de 10 bits, así
# que del 0 al 255 caen en el primer banco de 8 KB y del 256 al 511 en el que
# sigue. Eso obliga a poner los sprites primero, porque la base de OBJ va de a
# 16 KB y la de un fondo de a 8.
#
# Y el tilemap propio sale de recortarle tiles a los sprites, que es donde
# sobran. Medido sobre los 318 mapas que convierten, el que más gasta usa **380
# tiles de sprite**: 253 usan 192 o menos, 58 entre 193 y 256, y 7 entre 257 y
# 380. Con 448 no se queda corto ninguno, y los 2 KB que se liberan caen en la
# palabra $1C00, que es múltiplo de 1024 y por lo tanto una base válida de
# tilemap.
#
#   sprites   $0000  14 KB  448 tiles de 4bpp   base de OBJ en 0
#   ventana_map $1C00 2 KB  el tilemap de 32x32 de la ventana
#   tiles     $2000  24 KB  384 tiles de 8bpp
#   encima    $5000   8 KB  256 tiles           <- la base de BG2
#   ventana   $6000   8 KB  256 tiles           <- los índices 256..511
#   tilemaps  $7000   8 KB
#
# El segundo cambia tiles de sprite por tiles de fondo, para los mapas que
# gastan más fondo, y ahí los 2 KB no pueden salir de los sprites —esos mapas
# usan hasta 320— sino del fondo: 480 tiles en vez de 512.
#
#   sprites     $0000   8 KB  256 tiles
#   tiles       $1000  30 KB  480 tiles de 8bpp
#   ventana_map $4C00   2 KB
#   encima      $5000   8 KB
#   ventana     $6000   8 KB
#   tilemaps    $7000   8 KB
#
# Medido sobre los 318 mapas que convierten: 309 entran en el primero, 6 en el
# segundo y 3 no entraban en ninguno —el 8, el 66 y el 250—. **El 8 ya no**:
# el 2026-09-07, con la ventana mudada a la paleta 0, sus tiles de fondo bajaron
# a 400 y entra en el segundo reparto. El número de arriba es de antes de eso y
# no se volvió a medir sobre los 318.
#
# El número viejo que estaba escrito acá era 2, y estaba mal por una razón que
# vale la pena dejar dicha: `vram_layout` no comprobaba que los tiles de fondo
# entraran en el banco del reparto elegido. `MAX_TILES` es 1024, que es el tope
# del índice del tilemap y no el del banco, así que los mapas 66 y 250 —518 y
# 620 tiles de fondo— se llevaban el reparto de 512 y se pasaban por arriba de
# la capa de encima. Nunca se vio porque ninguna receta les pide una ventana.
# El reparto de arriba daba 384 tiles de fondo, y el que le seguía cambiaba
# sprites por fondo. Los dos le daban **256 tiles a la capa de encima**, y eso
# medido es un despilfarro: sobre los 328 mapas que convierten, la mediana de
# uso es **1 tile** y 326 entran en 128. Bajarla a 128 libera 4 KB, que en 8bpp
# son 64 tiles de fondo más.
#
# Hizo falta el 2026-09-07, cuando dibujar todos los eventos —ver `cabe`— llevó
# al mapa 8 a 400 tiles de fondo y 347 de sprite, y no había reparto que le
# diera los dos.
#
# El rompecabezas es de alineación y no de espacio: `BG12NBA` fija las bases de
# BG1 y BG2 en múltiplos de 8 KB, `OBSEL` la de los objetos en múltiplos de
# 16 KB, y los tilemaps en múltiplos de 1 KB. Los tilemaps se mudaron a $5800 y
# $7800, que son los únicos dos huecos que quedan alineados en los cuatro
# repartos.
LAYOUT_VENTANA = {"sprites": (0x0000, 448), "ventana_map": (0x1C00, 1),
                  "tiles": (0x2000, 448),
                  "encima": (0x6000, 128), "ventana": (0x6800, 256)}
LAYOUT_VENTANA_FONDO = {"sprites": (0x0000, 256), "tiles": (0x1000, 480),
                        "ventana_map": (0x4C00, 1),
                        "encima": (0x6000, 128), "ventana": (0x6800, 256)}

# Y el tercero, que hace lo contrario del segundo: cambia tiles de fondo por
# tiles de sprite. Lo pidió Delcentric Factory —el mapa 17, el camino al
# auditorio—, que gasta **217 tiles de fondo y 475 de sprite** y no entraba en
# ninguno de los dos: 28 ranuras de personaje son 448 tiles justos, y encima de
# eso van los 8 glifos del cronómetro y las 19 gotas de lluvia. Son 27 tiles de
# más sobre los 448 del primer reparto, y la lluvia no se puede sacar porque el
# clima sigue al cambiar de mapa y la apertura llueve.
#
#   sprites     $0000  16 KB  512 tiles de 4bpp   base de OBJ en 0
#   tiles       $2000  24 KB  384 tiles de 8bpp   <- la base de BG1
#   ventana_map $5000   2 KB  el tilemap de 32x32 de la ventana
#   (libre)     $5400   2 KB
#   tilemap     $5800   4 KB
#   encima      $6000   8 KB  128 tiles           <- la base de BG2
#   ventana     $6800   8 KB  256 tiles           <- los índices 128..383
#   tilemap     $7800   4 KB
#
# 512 es el tope del hardware y no una elección: el campo de nombre de OAM es
# de nueve bits, y con el name select de `OBSEL` en cero las dos tablas quedan
# pegadas, que es justo lo que `OBSEL_VALUE` emite. O sea que este reparto le da
# a los sprites todo lo que la consola puede direccionar.
#
# Los 2 KB libres de $5400 son el precio de la alineación: la base de BG1 va de
# a 8 KB, así que bajar el fondo de 448 a 384 tiles libera 8 KB y la ventana
# necesita 2. No se pueden usar para nada porque no hay nada más que ubicar.
#
# **Va último a propósito.** `vram_layout` devuelve el primero que entre, así
# que ningún mapa que ya tenía reparto cambia de reparto por esto: sólo lo toman
# los que en los otros dos no entraban.
LAYOUT_VENTANA_SPRITE = {"sprites": (0x0000, 512), "tiles": (0x2000, 384),
                         "ventana_map": (0x5000, 1),
                         "encima": (0x6000, 128), "ventana": (0x6800, 256)}
# Cuántas ranuras de partida guardada tiene el cartucho. El mismo número está
# en `main.s` como `SRAM_RANURAS`, y la ROM lo comprueba: si no dieran iguales,
# la pantalla mostraría un número de ranuras y la SRAM tendría otro.
RANURAS = 4

# Dónde viven, en palabras, el tilemap y los tiles de la pantalla de ranuras.
# Los mismos números están en el `.inc` como RANURA_MAP y RANURA_VRAM.
#
# **No comparten con el menú del título**, aunque hasta el 2026-09-10 lo
# hacían: el save point abre esta pantalla con un mapa cargado y al cerrarla
# hay que reponer lo que pisó, y eso es barato sólo si lo que pisó es el banco
# de tiles de BG1, que `load_map` vuelve a subir entero. Las direcciones del
# menú —$4400 y $5000— caían en los sprites de un reparto sin ventana que ya no
# existe: los NPCs volvían del menú con las poses rotas y el héroe también si
# no era el del bloque 0. Las de acá están en la intersección del banco de BG1
# de los tres repartos, que es $2000..$4000:
#
#   LAYOUT_VENTANA        $2000..$5800
#   LAYOUT_VENTANA_FONDO  $1000..$4C00
#   LAYOUT_VENTANA_SPRITE $2000..$5000
#
# La base de tiles de un BG va de a 4096 palabras y el tilemap de a 1024: los
# tiles en $2000, que con las caras del grupo son unos 300 y pueden llegar a
# 448 —hasta $3C00—, y el tilemap en $3C00. La pantalla de título los pisa —su
# imagen llega a $3E00— y no importa: al volver de las ranuras el título se
# sube entero. `_controlar_ranuras` lo comprueba contra los repartos de
# verdad, para que mover uno no deje esto escrito mal.
RANURA_VRAM = 0x2000
# En cuántos pedazos se parten los 32 KB de tiles de una escena de batalla:
# un bloque de 32 KB es un banco entero y no entra al lado de nada.
ESCENA_TROZO = 8192
RANURA_MAP = 0x3C00

VRAM_MAP = 0x5800
VRAM_ABOVE_MAP = 0x7800

# Dónde arranca el banco de la ventana **contado desde la base de BG2**, que es
# donde empieza la capa de encima. Sale del reparto y no de un número escrito:
# con la capa de encima en 128 tiles, la ventana arranca en el índice 128 y no
# en el 256, y escribirlo a mano fue lo primero que se rompió al mover el
# reparto.
VENTANA_TILE_BASE = ((LAYOUT_VENTANA["ventana"][0] - LAYOUT_VENTANA["encima"][0])
                     // 16)

# La tabla de bloques se lee con `lda tabla, x`, o sea que vive en el banco 0
# junto con el código.
MAX_BLOCKS = 1024


def vram_layout(tiles, sprites=0):
    """Qué reparto de VRAM le toca a un mapa, según lo que gasta.

    Los dos números se miran en los tres repartos, y se devuelve el primero que
    entre.
    """
    # Los dos números se miran en los dos repartos. Antes se miraba el fondo en
    # uno y los sprites en el otro, y eso dejaba pasar un mapa de 620 tiles de
    # fondo a un banco de 512: ver el comentario de LAYOUT_VENTANA_FONDO.
    for layout in (LAYOUT_VENTANA, LAYOUT_VENTANA_FONDO, LAYOUT_VENTANA_SPRITE):
        if tiles <= layout["tiles"][1] and sprites <= layout["sprites"][1]:
            return layout
    raise SystemExit(
        "este mapa no puede llevar ventana de mensaje: gasta %d tiles de fondo "
        "y %d de sprite, y no hay reparto que le deje 8 KB de tiles más 2 KB de "
        "tilemap a la ventana" % (tiles, sprites))


def _controlar_ranuras(ranura_tiles):
    """Que la pantalla de ranuras caiga en el banco de BG1 de los cuatro repartos.

    Es lo que hace que `volver_al_mapa` pueda reponer el mapa con `load_map` y
    nada más; ver el comentario de RANURA_MAP.
    """
    fin_tiles = RANURA_VRAM + ranura_tiles * 16
    fin_map = RANURA_MAP + 32 * 32
    if not (fin_tiles <= RANURA_MAP or fin_map <= RANURA_VRAM):
        raise SystemExit(
            "los %d tiles de la pantalla de ranuras llegan a $%04X y pisan su "
            "tilemap en $%04X" % (ranura_tiles, fin_tiles, RANURA_MAP))
    for nombre, layout in (("VENTANA", LAYOUT_VENTANA),
                           ("VENTANA_FONDO", LAYOUT_VENTANA_FONDO),
                           ("VENTANA_SPRITE", LAYOUT_VENTANA_SPRITE)):
        base, cuantos = layout["tiles"]
        tope = base + cuantos * (BYTES_PER_TILE // 2)
        for que, desde, hasta in (("los tiles", RANURA_VRAM, fin_tiles),
                                  ("el tilemap", RANURA_MAP, fin_map)):
            if desde < base or hasta > tope:
                raise SystemExit(
                    "la pantalla de ranuras pone %s en $%04X..$%04X y el "
                    "banco de BG1 de LAYOUT_%s es $%04X..$%04X: al volver del "
                    "menú `load_map` no lo repondría"
                    % (que, desde, hasta, nombre, base, tope))


# La ventana de mensaje, partida en dos: lo que la ROM lleva hecho y lo que
# compone en caliente.
#
# **Por qué se compone en caliente.** Una página de mensaje ya compuesta son
# unos 240 tiles de 4bpp, o sea 7,5 KB. El juego tiene 18.808 líneas de texto:
# emitir una ventana por mensaje no entra ni cerca en un cartucho de 256 KB. La
# salida es la de FF6 —la fuente en la ROM y el texto armado desde el 65816— y
# es lo que hace `componer_mensaje` en main.s.
#
# El reparto del banco de 256 tiles que tiene la ventana:
#
#   0 .. 14       la ventana vacía, deduplicada: marco y fondo estirado
#   15 .. 254     el área de texto, 30 columnas por 8 filas de celda
#
# Las 240 del área de texto **no se deduplican**: cada celda tiene su tile fijo,
# porque la ROM las va a reescribir y no puede andar buscando repetidos. De ahí
# sale el tope de 39 caracteres por línea: con 40 la sombra del último se pasa a
# la columna 31 y harían falta 8 tiles más de los que hay. Truncar a 39 pierde
# el 1,58% de los caracteres del juego contra el 1,09% de truncar a 40.
VENTANA_TEXTO_FILA = 1           # la primera fila de celdas que lleva texto
VENTANA_TEXTO_FILAS = 8
VENTANA_TEXTO_COL = 1
VENTANA_TEXTO_COLS = 30


def _columnas():
    """Cuántos caracteres entran en una línea. Vive en `ventana.py` con el
    resto de la geometría, y el porqué del número está ahí."""
    from port import ventana as ventana_mod
    return ventana_mod.COLUMNAS


def _quince(imagen):
    """Los pixeles de una imagen RGBA como colores de 15 bits, sobre negro."""
    from PIL import Image
    llana = Image.alpha_composite(
        Image.new("RGBA", imagen.size, (0, 0, 0, 255)), imagen).convert("RGB")
    return [tuple(v >> 3 for v in p) for p in llana.get_flattened_data()]


def convert_ventana(sys_img, font_id=None):
    """La ventana de mensaje: tiles, paleta, celdas y lo que la fuente necesita.

    La imagen la arma `ventana.py`, que sigue las reglas de easyrpg-player y
    está verificada contra una captura del juego original corriendo en
    EasyRPG.
    Acá se la corta en celdas de 8x8 y se separa lo fijo de lo que la ROM
    compone.

    La paleta lleva los colores de la ventana vacía **más** los del texto y la
    sombra, aunque la ventana vacía no los use: son los que la ROM va a
    escribir. El índice 0 queda libre a propósito, que es el transparente de
    BG2 y ningún tile de la ventana lo usa.

    Devuelve un dict con:
        tiles     los de la ventana vacía, deduplicados
        cram      las 16 palabras de la paleta
        celdas    el tilemap de 32x10, con los tiles de texto ya numerados
        fondo     los 240 tiles del área de texto, sin texto, en orden
        color     el índice de paleta de cada una de las 12 filas del glifo
        sombra    el índice de la sombra
    """
    from port import fuente as fuente_mod
    from port import ventana as ventana_mod

    if font_id is None:
        font_id = fuente_mod.MINCHO
    vacia = ventana_mod.ventana(sys_img)
    pixeles = _quince(vacia)
    ancho, alto = vacia.width, vacia.height

    # Los colores del texto salen del bloque de 16x16 del System, y son los que
    # `Font::Render` usa como máscara. Cada fila del glifo toma uno solo —está
    # medido: el degradé es horizontal-uniforme— así que son doce colores, no
    # un bloque, y la sombra es uno solo.
    bloque = ventana_mod.color_de_texto(sys_img, 0)
    sombra_img = ventana_mod.color_de_sombra(sys_img)
    ox, oy = ventana_mod.TEXTO_OFS
    color_fila = []
    for py in range(fuente_mod.ALTO):
        fila = {tuple(v >> 3 for v in bloque.getpixel((ox + px, oy + py))[:3])
                for px in range(fuente_mod.ANCHO)}
        if len(fila) != 1:
            raise SystemExit(
                "la fila %d del color de texto tiene %d colores distintos; la "
                "ROM la compone con uno solo" % (py, len(fila)))
        color_fila.append(fila.pop())
    sombra = tuple(v >> 3 for v in sombra_img.getpixel((0, 0))[:3])

    colores = sorted(set(pixeles) | set(color_fila) | {sombra})
    if len(colores) > COLORS_PER_PALETTE - 1:
        raise SystemExit("la ventana usa %d colores y entran %d"
                         % (len(colores), COLORS_PER_PALETTE - 1))
    indice = {c: i + 1 for i, c in enumerate(colores)}

    def celda_de(tx, ty):
        return tuple(tuple(indice[pixeles[(ty * 8 + y) * ancho + tx * 8 + x]]
                           for x in range(8)) for y in range(8))

    # Las celdas que no llevan texto se deduplican como siempre; las del área de
    # texto se numeran de corrido a partir de ahí.
    tiles, celdas = {}, []
    for ty in range(alto // 8):
        fila = []
        for tx in range(ancho // 8):
            if (VENTANA_TEXTO_FILA <= ty < VENTANA_TEXTO_FILA + VENTANA_TEXTO_FILAS
                    and VENTANA_TEXTO_COL <= tx < VENTANA_TEXTO_COL + VENTANA_TEXTO_COLS):
                fila.append(None)       # se numera abajo, cuando se sepa cuántos
                continue
            celda = celda_de(tx, ty)
            if celda not in tiles:
                tiles[celda] = len(tiles)
            fila.append(tiles[celda])
        celdas.append(fila)

    base = len(tiles)
    fondo = []
    for n, ty in enumerate(range(VENTANA_TEXTO_FILA,
                                VENTANA_TEXTO_FILA + VENTANA_TEXTO_FILAS)):
        for m, tx in enumerate(range(VENTANA_TEXTO_COL,
                                     VENTANA_TEXTO_COL + VENTANA_TEXTO_COLS)):
            celdas[ty][tx] = base + n * VENTANA_TEXTO_COLS + m
            fondo.append(celda_de(tx, ty))
    if base + len(fondo) > 256:
        raise SystemExit("la ventana necesita %d tiles y el banco tiene 256"
                         % (base + len(fondo)))

    datos = b"".join(pack_tile(celda, planes=4)
                     for celda, _ in sorted(tiles.items(), key=lambda kv: kv[1]))
    cram = [0] + [cgram_word(c) for c in colores]
    cram += [0] * (COLORS_PER_PALETTE - len(cram))
    # El fondo arranca donde termina esto, así que si la ventana creciera se le
    # metería encima y la ROM dibujaría el texto con un color del mapa. Se mira
    # el índice más alto que se usa de verdad —el de la sombra o el de alguna
    # fila del glifo— y no cuántas palabras son distintas de cero: un color
    # negro tiene palabra cero y no se contaría.
    alto = max([indice[c] for c in color_fila] + [indice[sombra]])
    if alto >= CGRAM_RESERVADAS:
        raise SystemExit(
            "la ventana de mensaje usa la entrada %d de CGRAM y el fondo "
            "arranca en la %d: subí CGRAM_RESERVADAS" % (alto, CGRAM_RESERVADAS))
    return {"tiles": datos, "cram": cram, "celdas": celdas,
            "base": base,
            "fondo": b"".join(pack_tile(c, planes=4) for c in fondo),
            "color": [indice[c] for c in color_fila],
            "sombra": indice[sombra]}


def fuente_bytes(font_id):
    """Los 95 glifos ASCII, doce filas de seis bits cada uno.

    Es la misma tabla que `tools/port/fuente.py`, que se genera desde
    easyrpg-player, pero **con los bits dados vuelta**: allá el bit 0 es el
    pixel de la izquierda y en el formato de tiles de la consola el de la
    izquierda es el bit 7. Darlos vuelta acá y no en la ROM sale gratis: es una
    tabla de 1140 bytes que se genera una vez.
    """
    from port import fuente as fuente_mod
    out = bytearray()
    for code in range(32, 127):
        for fila in fuente_mod.filas(chr(code), font_id):
            invertida = 0
            for px in range(FUENTE_ANCHO):
                if fila >> px & 1:
                    invertida |= 1 << (7 - px)
            out.append(invertida)
    return bytes(out)


# Los glifos de la ventana ya compuestos, para cada una de las cuatro fases en
# que puede caer un carácter: la x es `VENTANA_BORDE + 6 * columna`, así que
# módulo 8 da 0, 6, 4 o 2 y nunca otra cosa. Por glifo y fase van las filas
# de celda de `FUENTE_PRE_FILAS` que toca —las doce del glifo desde
# `TEXTO_OFS_Y`, y una más de sombra— y por fila las dos celdas que puede
# pisar, cada una con tres palabras: qué se conserva del buffer, y qué se
# prende en los planos 0-1 y en los 2-3. La ROM hace
# `buf = buf & conservar | prender`, que es lo que antes calculaba en cada
# fila con `pintar`, dos veces —sombra y glifo— y con un corrimiento de a un
# bit. Ver `componer_char`.
#
# La sombra y el glifo van ya combinados, con la regla del orden de
# `Font::Render`: en una fila cae el glifo de dos filas más arriba y la sombra
# del de tres, corrida un pixel, y donde se pisan gana el glifo.
FUENTE_PRE_FILAS = FUENTE_ALTO + 1
FUENTE_PRE_CHAR = FUENTE_PRE_FILAS * 2 * 6


def fuente_prerender(fuente, colores, sombra):
    """Las cuatro tablas, una por fase (0, 2, 4 y 6), en ese orden."""
    n = len(fuente) // FUENTE_ALTO
    tablas = []
    for fase in (0, 2, 4, 6):
        out = bytearray()
        for c in range(n):
            filas = fuente[c * FUENTE_ALTO:(c + 1) * FUENTE_ALTO]
            corrida = [(f << 8) >> fase for f in filas]
            for k in range(FUENTE_PRE_FILAS):
                glifo = corrida[k] if k < FUENTE_ALTO else 0
                color = colores[k] if k < FUENTE_ALTO else 0
                sombra_m = (corrida[k - 1] >> 1) if k >= 1 else 0
                sombra_m &= ~glifo & 0xFFFF
                for celda in (0, 1):
                    g = (glifo >> (8 if celda == 0 else 0)) & 0xFF
                    s = (sombra_m >> (8 if celda == 0 else 0)) & 0xFF
                    conservar = ~((g | s) * 0x0101) & 0xFFFF
                    prender = []
                    for bits in (0, 2):
                        palabra = 0
                        for m, col in ((g, color), (s, sombra)):
                            if col >> bits & 1:
                                palabra |= m
                            if col >> (bits + 1) & 1:
                                palabra |= m << 8
                        prender.append(palabra)
                    for palabra in [conservar] + prender:
                        out += bytes([palabra & 0xFF, palabra >> 8])
        tablas.append(bytes(out))
    return tablas


def build_blocks(tilemap, above_tilemap, passable, width, height):
    """El mapa como índices a bloques de 16x16, con su tabla.

    Devuelve (celdas, tabla de bloques, pasabilidad por bloque). Las celdas van
    fila por fila, que es como las recorre la ROM.
    """
    blocks, cells = {}, []
    for by in range(height):
        for bx in range(width):
            key = (tuple(tilemap[by * 2 + dy][bx * 2 + dx]
                         for dy in (0, 1) for dx in (0, 1)),
                   tuple(above_tilemap[by * 2 + dy][bx * 2 + dx]
                         for dy in (0, 1) for dx in (0, 1)),
                   passable[by * width + bx])
            if key not in blocks:
                blocks[key] = len(blocks)
            cells.append(blocks[key])

    if len(blocks) > MAX_BLOCKS:
        raise SystemExit("el mapa usa %d bloques distintos y la tabla no puede "
                         "pasar de %d" % (len(blocks), MAX_BLOCKS))

    table = bytearray(BLOCK_BYTES * len(blocks))
    pass_bytes = bytearray(len(blocks))
    for (base, above, permisos), number in blocks.items():
        entries = list(base) + list(above)
        for i, cell in enumerate(entries):
            table[number * BLOCK_BYTES + i * 2:
                  number * BLOCK_BYTES + i * 2 + 2] = cell.to_bytes(2, "little")
        pass_bytes[number] = permisos
    return cells, bytes(table), bytes(pass_bytes)


# El registro de un mapa en la tabla. El paso es potencia de dos para que pasar
# de índice a desplazamiento sean corrimientos y no una multiplicación, y sobra
# lugar a propósito: agregar un campo no tiene que mover nada de lo que ya está.
#
# Los punteros van de a cuatro bytes aunque midan tres. El byte que sobra no se
# usa; lo que se gana es que la parte baja de cada puntero caiga siempre en una
# dirección par, que es como se la lee con el acumulador en 16 bits.
MAPA_STRIDE = 128
MAPA_ESCALARES = [
    ("MAP_BW", "ancho en celdas de 16x16"),
    ("MAP_BH", "alto en celdas de 16x16"),
    ("CAM_MAX_X", "hasta dónde llega la cámara sin salirse"),
    ("CAM_MAX_Y", ""),
    ("HERO_MAX_X", "hasta dónde llega el héroe"),
    ("HERO_MAX_Y", ""),
    ("HERO_START_X", "dónde arranca, en pixeles"),
    ("HERO_START_Y", ""),
    ("VRAM_TILES", "el reparto de la VRAM, en palabras"),
    ("VRAM_ABOVE", ""),
    ("VRAM_SPRITE", ""),
    ("VRAM_VENTANA", "0 si esta ROM no lleva ventana de mensaje"),
    ("VRAM_VENTANA_MAP", "y su tilemap propio de 32x32"),
    ("MAP_TILES", "cuántos tiles de fondo, para el DMA"),
    ("MAP_CGRAM", "cuántas palabras de CGRAM"),
    ("ABOVE_TILES", ""),
    ("ABOVE_CGRAM", ""),
    ("SPRITE_TILES", ""),
    ("SPRITE_CGRAM", ""),
    ("NPC_COUNT", "cuántos NPCs con CharSet"),
    ("EV_COUNT", "cuántos eventos tiene el mapa, con o sin gráfico"),
    ("TIMER_BASE", "el primer tile de los dígitos del cronómetro, 0 si no hay"),
    ("LLUVIA_BASE", "el primer tile de las gotas de lluvia, 0 si no hay"),
    ("ACTOR_COUNT", "cuántos candidatos a líder del grupo"),
    ("PUERTA_COUNT", "cuántas puertas salen de este mapa"),
    ("PAGINA_COUNT", "cuántas páginas de evento hay que resolver"),
    ("RUTA_GRAFICO_COUNT", "cuántos gráficos distintos pide la orden 34"),
]
MAPA_BYTES = [
    ("OBSEL_VALUE", "objetos de 8x8 y 32x32, y la página de sus tiles"),
    ("BG12NBA_VALUE", "las páginas de tiles de BG1 y BG2"),
    ("ABOVE_FIRST", "en qué entrada de CGRAM arranca la capa de encima"),
    ("TIMER_PAL", "la paleta de sprite de los dígitos del cronómetro"),
    ("LLUVIA_PAL", "la paleta de sprite de las gotas de lluvia"),
    # Un byte y no un escalar porque el registro está en sus 128 justos. El
    # tile de un bloque es siempre múltiplo de cuatro y menor que 512.
    ("GIRO_TILE4", "el tile de la ranura de giro sobre cuatro, o $FF"),
]
MAPA_PUNTEROS = ["map_tiles", "map_cgram", "above_tiles", "above_cgram",
                 "sprite_tiles", "sprite_cgram", "map_celdas", "map_bloques",
                 "bloque_pass", "npc_table", "actor_table", "puertas",
                 "paginas", "ev_pos", "npc_poses", "ruta_grafico",
                 # La animación del ChipSet: las dos corridas de tiles y sus
                 # dibujos. Ver `anim_bytes`.
                 "anim_tiles"]
MAPA_PTR_PASO = 4
# Dónde arrancan los punteros: justo después de los escalares y de los bytes,
# redondeado al paso. **Se calcula y no se escribe a mano**, porque escrito a
# mano ya falló: agregar un escalar más dejó `ABOVE_FIRST` y el primer puntero
# en el mismo desplazamiento, la ROM leyó el byte de la paleta como puntero a
# los tiles del mapa y la pantalla salió de un color plano.
#
# Es de las que no puede ver ninguna de las dos puntas: el ensamblador ve dos
# nombres distintos con el mismo valor, que es legal, y la comparación pixel a
# pixel dice "todo mal" sin decir dónde. La única defensa es que el número
# salga de los datos.
MAPA_PTR_BASE = (-(-(len(MAPA_ESCALARES) * 2 + len(MAPA_BYTES))
                   // MAPA_PTR_PASO) * MAPA_PTR_PASO)
assert MAPA_PTR_BASE + len(MAPA_PUNTEROS) * MAPA_PTR_PASO <= MAPA_STRIDE, \
    "el registro de mapa no entra en %d bytes" % MAPA_STRIDE

# Una puerta: dónde está, a qué mapa lleva y a qué celda. El paso es potencia de
# dos para que buscarla sea un corrimiento, y sobra lugar para la dirección en
# la que RM2k te deja mirando, que todavía no se usa.
PUERTA_BYTES = 16

# Una página de evento: a qué evento pertenece, qué la activa, y dónde está su
# código. Las páginas de un mismo evento van seguidas y en orden, que es lo que
# le permite a la ROM elegir la última que cumple sus condiciones en una sola
# pasada, sin llevar una tabla por evento.
PAGINA_BYTES = 32
# Sin ranura de giro: el mapa no tiene ningún quieto que se dé vuelta.
GIRO_NINGUNO = 0xFFFF
# Un candidato a líder: id, paleta, **sus quince colores** y doce punteros de 24
# bits a sus poses. Los colores van adentro de la tabla y no en un bloque aparte
# porque son pocos actores por mapa y así la ROM los sube con un DMA desde donde
# ya está parada; ver `elegir_grafico_heroe`.
#
# Están porque los líderes **comparten una ranura de CGRAM**: lidera uno a la
# vez, así que reservarle una paleta a cada uno es tenerla ocupada por alguien
# que no está en pantalla. La ROM sube los del que lidera al cambiar el grupo y
# al cargar el mapa. Ver `npcs_dibujables`.
ACTOR_COLORES = 2 * OBJ_COLORS
ACTOR_BYTES = 2 + ACTOR_COLORES + 3 * 12

# Un bit por switch. El juego consulta hasta el 1003 en las condiciones de
# página, así que con 1024 alcanza y sobra: son 128 bytes de RAM.
SWITCH_BYTES = 128

# Cuántos gráficos distintos puede pedir la orden 34 en un mapa. La tabla se
# copia a la RAM al cargar el mapa, como la de NPCs, así que el tope cuesta
# bytes de los ocho kilos del banco 0 —dos por gráfico— y no puede ser
# generoso porque sí. **El mapa que más pide de todo el juego pide seis**,
# medido sobre los 328; ocho deja dos de aire y son dieciséis bytes. El
# conversor corta si algún mapa se pasa, así que no puede quedar corto en
# silencio.
RUTA_GRAF_MAX = 8


def campos_del_mapa(mapa):
    """Los valores del registro de un mapa, en el orden en que se emiten."""
    tilemap, above, sprite = mapa["tilemap"], mapa["above"], mapa["sprite"]
    collision, layout = mapa["collision"], mapa["layout"]
    height, width = len(tilemap), len(tilemap[0])
    return {
        "MAP_BW": collision[3], "MAP_BH": collision[4],
        "CAM_MAX_X": max(0, width * CELL - 256),
        "CAM_MAX_Y": max(0, height * CELL - 224),
        "HERO_MAX_X": width * CELL - 16, "HERO_MAX_Y": height * CELL - 16,
        "HERO_START_X": collision[1] * 16, "HERO_START_Y": collision[2] * 16,
        "VRAM_TILES": layout["tiles"][0], "VRAM_ABOVE": layout["encima"][0],
        "VRAM_SPRITE": layout["sprites"][0],
        "VRAM_VENTANA": layout.get("ventana", (0, 0))[0],
        "VRAM_VENTANA_MAP": layout.get("ventana_map", (0, 0))[0],
        "MAP_TILES": len(mapa["tiles"]) // BYTES_PER_TILE,
        "MAP_CGRAM": len(mapa["cram"]) // 2,
        "ABOVE_TILES": len(above[0]) // 32,
        "ABOVE_CGRAM": len(above[1]) // 2,
        "SPRITE_TILES": len(sprite[0]) // 32 if sprite else 0,
        # Una más que los colores: el índice 0 del sprite es transparente y
        # también ocupa su lugar en CGRAM.
        "SPRITE_CGRAM": COLORS_PER_PALETTE * len(sprite[1]) if sprite else 0,
        "NPC_COUNT": len(sprite[3]) if sprite else 0,
        "EV_COUNT": len(mapa["ev_pos"]) // EV_STRIDE,
        "TIMER_BASE": sprite[5] if sprite else 0,
        "LLUVIA_BASE": sprite[10] if sprite else 0,
        "ACTOR_COUNT": len(sprite[4]) if sprite else 0,
        "PUERTA_COUNT": len(mapa["puertas"]) // PUERTA_BYTES,
        "PAGINA_COUNT": len(mapa["paginas"]),
        "RUTA_GRAFICO_COUNT": len(sprite[9]) if sprite else 0,
        "OBSEL_VALUE": 0x20 | (layout["sprites"][0] // 0x2000),
        "BG12NBA_VALUE": ((layout["encima"][0] // 0x1000) << 4)
                         | (layout["tiles"][0] // 0x1000),
        "ABOVE_FIRST": above[3] * COLORS_PER_PALETTE,
        "TIMER_PAL": (sprite[6] if sprite and sprite[6] is not None else 0),
        "LLUVIA_PAL": sprite[11] if sprite else 0,
        "GIRO_TILE4": (sprite[12] // 4 if sprite and sprite[12] != GIRO_NINGUNO
                       else 0xFF),
    }


def desplazamientos():
    """Los nombres de los campos del registro, para que main.s no los repita.

    Que el conversor emita los desplazamientos y la ROM sólo los nombre es lo
    que hace imposible que se desincronicen: si acá se agrega un campo, allá no
    hay ningún número que actualizar.
    """
    out = ["; Dónde cae cada campo dentro del registro de un mapa."]
    usado = 0
    for nombre, _ in MAPA_ESCALARES:
        out.append("M_%-14s = %d" % (nombre, usado))
        usado += 2
    for nombre, _ in MAPA_BYTES:
        out.append("M_%-14s = %d" % (nombre, usado))
        usado += 1
    for numero, nombre in enumerate(MAPA_PUNTEROS):
        out.append("M_PTR_%-10s = %d"
                   % (nombre.upper(), MAPA_PTR_BASE + numero * MAPA_PTR_PASO))
    return "\n".join(out)


def tabla_de_mapas(mapas, etiquetas):
    """La tabla que la ROM recorre para saber qué cargar.

    `etiquetas` dice, por mapa, a qué bloque apunta cada puntero. Antes esto no
    existía y el nombre se rearmaba acá con `"%s_%d" % (nombre, numero)`, o sea
    con la misma cuenta que lo había emitido: dos lugares calculando el mismo
    nombre y ninguna manera de que un bloque fuera de más de un mapa.
    """
    out = ['.segment "RODATA"',
           "; La tabla de mapas: un registro de %d bytes por mapa, con todo lo"
           % MAPA_STRIDE,
           "; que la ROM necesita para cargarlo. Los punteros son de 24 bits",
           "; porque los datos viven repartidos por todos los bancos.",
           ";",
           "; **Vive en RODATA y se lee con `lda f:mapa_tabla + campo, x`.**",
           "; Son 144 bytes por mapa, y en el banco 0 —donde la tabla tiene que",
           "; estar si se la recorre con el registro de banco de datos— eso",
           "; alcanzaba para catorce mapas y nada más: con Lashe City entera son",
           "; 33 y el banco se pasaba por 3739 bytes. Es la tercera tabla que se",
           "; muda por la misma razón; el precio es un byte por instrucción y",
           "; que los dos usos con Y hayan tenido que pasar a X, porque el",
           "; direccionamiento absoluto largo indexado sólo existe con X.",
           ";",
           "; **Entera en un banco**, que es lo que pide el `.bloque`. En LoROM",
           "; lo que sigue a $03FFFF no es la ROM del banco 4 sino la RAM, y la",
           "; primera versión de esto cayó en $03FFB1: los 144 bytes del único",
           "; registro se partían al medio y el mapa 5 arrancaba en negro. Los",
           "; demás mapas de la tanda no lo veían porque su tabla caía en otro",
           "; lado, que es exactamente la clase de error que aparece al agregar",
           "; un byte en cualquier otra parte.",
           ".bloque %d" % (MAPA_STRIDE * len(mapas)),
           "mapa_tabla:"]
    for numero, mapa in enumerate(mapas):
        campos = campos_del_mapa(mapa)
        out.append("    ; --- %d: mapa %d %r ---" % (numero, mapa["id"],
                                                     mapa["nombre"]))
        usado = 0
        for nombre, comentario in MAPA_ESCALARES:
            out.append("    .word %-6d ; +%-3d %s%s"
                       % (campos[nombre], usado, nombre,
                          "  " + comentario if comentario else ""))
            usado += 2
        for nombre, comentario in MAPA_BYTES:
            out.append("    .byte $%02X    ; +%-3d %s  %s"
                       % (campos[nombre], usado, nombre, comentario))
            usado += 1
        relleno = MAPA_PTR_BASE - usado
        # Sin relleno no va la línea: un `.byte` sin operandos es un error
        # para `ca65`.
        if relleno:
            out.append("    .byte %s ; +%d  relleno hasta los punteros"
                       % (",".join(["$00"] * relleno), usado))
        usado += relleno
        for nombre in MAPA_PUNTEROS:
            etiqueta = etiquetas[numero][nombre]
            out.append("    .byte <(%s), >(%s), ^(%s), $00 ; +%d  %s"
                       % (etiqueta, etiqueta, etiqueta, usado, nombre))
            usado += MAPA_PTR_PASO
        assert usado <= MAPA_STRIDE, usado
        if usado < MAPA_STRIDE:
            out.append("    .byte " + ",".join(["$00"] * (MAPA_STRIDE - usado)))
    return "\n".join(out)


# El bloque de la animación del ChipSet: los dibujos, uno detrás del otro y en
# el orden de la VRAM —agua 0, 1, 2; animados 0 a 3—, sin cabecera.
#
# Dónde cae cada uno y a qué dirección de VRAM va no está adentro del bloque
# sino en `anim_tabla`, una entrada por mapa. Es para que la ROM no tenga que
# leer nada del cartucho para animar: la página directa está llena, así que un
# `lda [puntero], y` no tenía dónde vivir, y la alternativa —traer la cabecera
# por DMA a la WRAM— pedía cuarenta bytes de BSS que tampoco había. Con la tabla
# armada acá, la ROM indexa y dispara el DMA.
ANIM_STRIDE = 16
ANIM_FAM_STRIDE = ANIM_STRIDE // 2


def anim_bytes(animacion):
    """Los dibujos del mapa, uno detrás del otro. Vacío si no anima nada."""
    datos = bytearray()
    for familia, _ in FAMILIAS:
        corrida = animacion.get(familia)
        if corrida:
            for dibujo in corrida["dibujos"]:
                datos += dibujo
    return bytes(datos)


def anim_tabla(mapas):
    """Una entrada por mapa, con las dos corridas ya resueltas.

    Por familia, y en el orden en que la ROM las mira:

        +0 word  dirección de VRAM, en palabras
        +2 word  desplazamiento del dibujo 0 adentro del bloque
        +4 word  cuántos bytes mide un dibujo
        +6 byte  cuántos tiles son; 0 si esta familia no anima en este mapa
        +7 byte  relleno, para que la entrada de cada familia sea de ocho

    La dirección de VRAM sale de acá y no de una cuenta en la consola porque
    acá están las dos mitades: el reparto de la VRAM del mapa y en qué tile de
    su banco arranca la corrida.

    El relleno de la segunda familia —el byte +15 de la entrada— lleva **si el
    mapa tiene algún evento quieto con animación continua**. Va acá porque es
    lo mismo que el resto: algo por mapa que la ROM mira una vez por cuadro y
    que en el registro del mapa ya no entraba. Sin él, `animar_quietos` tendría
    que recorrer las cuarenta filas de NPC en todos los mapas.
    """
    out = ['.segment "RODATA"',
           "; La animación del ChipSet, una entrada de %d bytes por mapa."
           % ANIM_STRIDE,
           "; Ver `anim_tabla` en tools/port/snes_convert.py y `anim_flush` en main.s.",
           ";",
           "; **Vive en RODATA y se lee con `lda f:anim_tabla + campo, x`**, por",
           "; lo mismo que `mapa_tabla`: son 16 bytes por mapa, y con los mapas",
           "; que piden las pruebas el banco 0 se pasaba por 361. Entera en un",
           "; banco, porque lo que sigue a $xxFFFF no es la ROM del siguiente.",
           ".bloque %d" % (ANIM_STRIDE * len(mapas)),
           "anim_tabla:"]
    for mapa in mapas:
        animacion = mapa["resumen"]["animacion"]
        out.append("    ; --- mapa %d %r ---" % (mapa["id"], mapa["nombre"]))
        desplazamiento = 0
        for familia, cuantos in FAMILIAS:
            corrida = animacion.get(familia)
            tiles = corrida["tiles"] if corrida else 0
            vram = (mapa["layout"]["tiles"][0]
                    + (corrida["base"] if corrida else 0) * BYTES_PER_TILE // 2)
            out.append("    .word %-6d ; VRAM de %s" % (vram, familia))
            out.append("    .word %-6d ; el dibujo 0, adentro del bloque"
                       % desplazamiento)
            out.append("    .word %-6d ; bytes por dibujo"
                       % (tiles * BYTES_PER_TILE))
            relleno = 0
            if familia == FAMILIAS[-1][0]:
                relleno = 1 if any(n.get("anima")
                                   for n in (mapa["sprite"][3]
                                             if mapa["sprite"] else ())) else 0
            out.append("    .byte %d, %d   ; %d tile(s)%s"
                       % (tiles, relleno, tiles,
                          ", y el mapa tiene quietos que animan"
                          if relleno else ""))
            desplazamiento += tiles * BYTES_PER_TILE * cuantos
    return "\n".join(out)


def animaciones_de_la_rom(mapas, renderer):
    """Las animaciones de batalla que el bytecode ya emitido muestra, por
    número de RM2k, cada una convertida por `animacion.py`.

    Se recorre el bytecode y no los comandos, que es lo que hace que sea la
    verdad y no una conjetura: lo que cuenta es lo que quedó emitido, después
    de que el filtro de páginas decidiera cuáles entran. Es la misma regla de
    `eventos.blancos_de_ruta`.
    """
    numeros = set()
    for mapa in mapas:
        for pagina in mapa.get("paginas", ()):
            codigo = pagina.get("codigo") or b""
            for i, c in eventos.recorrer_codigo(codigo):
                if (c[i] == eventos.OP_ANIMATION
                        and c[i + 1] != eventos.ANIM_SIN_DIBUJO):
                    numeros.add(c[i + 1])
    salida = {}
    for numero in sorted(numeros):
        info = animacion_mod.de_numero(renderer, numero)
        if info is not None:
            salida[numero] = info
    return salida


def animaciones_asm(animaciones, mapas):
    """Las animaciones de batalla del cartucho, listas para el `.inc`.

    Cuatro cosas:

      `anim_batalla_de`      por número de RM2k, qué entrada le toca, o $FF.
                             Va por número y no por un índice nuestro para que
                             ninguna de las dos puntas tenga que llevar un
                             contador que la otra adivine.
      `anim_batalla_tabla`   por entrada: cuántos cuadros, dónde cae su ancla
                             adentro de la caja y en qué cuadro arranca.
      `anim_batalla_cuadros` por cuadro, el puntero de 24 bits a sus 2 KB de
                             tiles. Uno por cuadro y no un bloque seguido por
                             animación: 28 cuadros son 57 KB y un banco tiene
                             32, así que no hay bloque que entre entero.
      `anim_batalla_cgram`   sus dieciséis colores, que la ROM sube cuando la
                             animación empieza.
      `anim_batalla_reparto` por mapa, dónde y con qué paleta se dibuja acá, o
                             0 si este mapa no dibuja animaciones.
    """
    orden = sorted(animaciones)
    entrada = {numero: k for k, numero in enumerate(orden)}
    tope = (max(orden) + 1) if orden else 1
    out = [
        "\n; --- el dibujo de las animaciones de batalla ---",
        ";",
        "; La caja es una sola para toda la ROM y el porqué está en",
        "; tools/port/animacion.py: cuatro objetos de 32x32 en una fila de bloques",
        "; de la grilla de nombres, que es lo máximo que entra en la VRAM de",
        "; sprites que le queda libre al mapa 2. Lo que cambia por mapa es",
        "; dónde cae esa fila y con qué paleta, y eso va en",
        "; `anim_batalla_reparto`, un byte por mapa.",
        "ANIM_B_CAJA   = %d" % animacion_mod.CAJA,
        "ANIM_B_OBJ    = %d" % animacion_mod.OBJ,
        "ANIM_B_OBJETOS = %d" % animacion_mod.OBJETOS,
        "ANIM_B_TILES  = %d" % animacion_mod.TILES,
        "ANIM_B_BYTES  = %d" % (animacion_mod.TILES * 32),
        "ANIM_B_STRIDE = 8",
        "; Hasta qué número de animación llega `anim_batalla_de`: el bytecode",
        "; lleva el número de RM2k tal cual y uno más grande no está en la",
        "; tabla, así que la ROM lo compara antes de leerla.",
        "ANIM_B_MAX    = %d" % tope,
        "; El centro de la pantalla, que es donde caen las de alcance",
        "; `Scope_screen`: `DrawAt(screen_width / 2, screen_height / 2)`.",
        "ANIM_B_CENTRO_X = %d" % (animacion_mod.PANTALLA[0] // 2),
        "ANIM_B_CENTRO_Y = %d" % (animacion_mod.PANTALLA[1] // 2),
        "ANIM_B_SIN      = $%02X" % eventos.ANIM_SIN_DIBUJO,
        "ANIM_B_PANTALLA = $%02X" % eventos.ANIM_BLANCO_PANTALLA,
    ]
    out.append(bloque("anim_batalla_de",
                      bytes(entrada.get(n, 0xFF) for n in range(tope))))
    tabla = bytearray()
    primero = 0
    for numero in orden:
        info = animaciones[numero]
        # El ancla **como la quiere la ROM**: con la corrida de
        # `Animation::Position` ya horneada, así que la consola sólo resta.
        ax, ay = animacion_mod.ancla_rom(info)
        tabla += bytes([len(info["cuadros"]), ax & 0xFF, ay & 0xFF, 0,
                        primero & 0xFF, primero >> 8, 0, 0])
        primero += len(info["cuadros"])
    out.append(bloque("anim_batalla_tabla", bytes(tabla)))
    cgram = bytearray()
    for numero in orden:
        colores = [(0, 0, 0)] + list(animaciones[numero]["paleta"])
        colores += [(0, 0, 0)] * (COLORS_PER_PALETTE - len(colores))
        for color in colores:
            cgram += cgram_word(color).to_bytes(2, "little")
    out.append(bloque("anim_batalla_cgram", bytes(cgram)))
    # La tabla de punteros, con etiquetas: no puede salir de `bloque()`, pero
    # **sí se declara** con `.bloque` por lo mismo que la de páginas —la ROM la
    # lee con un puntero de 24 bits y no puede quedar a caballo de dos bancos—.
    punteros = [".bloque %d" % (4 * primero), "anim_batalla_cuadros:"]
    for numero in orden:
        for k in range(len(animaciones[numero]["cuadros"])):
            punteros.append("    .dword anim_batalla_%d_%d" % (numero, k))
    out.append("\n".join(punteros))
    for numero in orden:
        info = animaciones[numero]
        for k, cuadro in enumerate(info["cuadros"]):
            datos = bytearray(animacion_mod.TILES * 32)
            for tile, celda in animacion_mod.celdas(cuadro).items():
                datos[tile * 32:(tile + 1) * 32] = pack_tile(celda, planes=4)
            out.append(bloque("anim_batalla_%d_%d" % (numero, k), bytes(datos)))
    reparto = bytearray()
    for mapa in mapas:
        sprite = mapa["sprite"]
        base, pal = (sprite[15], sprite[16]) if sprite else (0, 0)
        # El bit 7 es "acá se dibuja", y abajo van el bloque de 64 tiles y la
        # paleta, de tres bits cada uno. En un byte porque el registro de mapa
        # está en sus 128 justos: ver MAPA_STRIDE.
        reparto.append((0x80 | ((base // 64) << 3) | pal) if base else 0)
    out.append(bloque("anim_batalla_reparto", bytes(reparto)))
    return "\n".join(out) + "\n"


def escenas_asm(escenas, tropas):
    """Las escenas de batalla del cartucho, listas para el `.inc`.

    Una escena es **el fondo con los battlers ya encima**, horneada: el porqué
    y lo que cuesta están en tools/port/escena.py. Lo que se emite:

      `escena_de`      por índice de tropa —el orden de `tropa_id`—, qué escena
                       le toca, o $FF si esa tropa no tiene fondo.
      `escena_trozo`   por escena y trozo, el puntero de 24 bits a sus 8 KB de
                       tiles. Cuatro trozos y no un bloque seguido por lo mismo
                       que las animaciones: 32 KB son un banco entero y no hay
                       bloque que entre al lado de nada.
      `escena_cgram`   sus 96 colores, que van a la CGRAM desde la entrada 32.

    El tilemap no se emite: son los 512 tiles en orden y la ROM lo arma con un
    lazo. Emitirlo serían 2 KB de cartucho por escena para escribir 0, 1, 2...
    """
    E = escena_mod
    trozos = E.TILES * 64 // ESCENA_TROZO
    out = [
        "\n; --- la escena de la batalla: el fondo y los monstruos ---",
        ";",
        "; Van horneados juntos en una capa de 8bpp de 256x128, que son los",
        "; siete renglones de texto de arriba. El porqué está en",
        "; tools/port/escena.py; acá sólo viajan los bytes.",
        "ESCENA_N        = %d" % len(escenas),
        "ESCENA_ANCHO    = %d" % E.ANCHO,
        "ESCENA_ALTO     = %d" % E.ALTO,
        "ESCENA_TILES    = %d" % E.TILES,
        "ESCENA_FILAS    = %d" % E.TILES_Y,
        "ESCENA_COLUMNAS = %d" % E.TILES_X,
        "ESCENA_COLORES  = %d" % E.COLORES,
        "ESCENA_CGRAM    = %d" % E.CGRAM_BASE,
        "ESCENA_VRAM     = $%04X" % E.VRAM_TILES,
        "ESCENA_MAPA     = $%04X" % E.VRAM_MAPA,
        "ESCENA_TROZO    = %d" % ESCENA_TROZO,
        "ESCENA_TROZOS   = %d" % trozos,
        "; El tile con el que se tapa lo que queda abajo de la escena. Cae",
        "; **fuera** del bloque de tiles: 512 tiles de 8bpp son las 16.384",
        "; palabras que van de ESCENA_VRAM al final de la VRAM, así que el 512",
        "; da la vuelta y cae en la palabra 0, que mientras dura la pelea es",
        "; VRAM del mapa y no la usa nadie.",
        "ESCENA_BLANCO   = %d" % E.TILES,
    ]
    out.append(bloque("escena_de",
                      bytes(escenas_de(escenas, tropas)) or b"\xFF"))
    punteros = [".bloque %d" % (4 * max(1, len(escenas) * trozos)),
                "escena_trozo:"]
    for k in range(len(escenas)):
        for t in range(trozos):
            punteros.append("    .dword escena_%d_%d" % (k, t))
    if not escenas:
        punteros.append("    .dword 0")
    out.append("\n".join(punteros))
    cgram = bytearray()
    for info in escenas:
        colores = list(info["paleta"])
        colores += [(0, 0, 0)] * (E.COLORES - len(colores))
        for color in colores:
            cgram += cgram_word(color).to_bytes(2, "little")
    out.append(bloque("escena_cgram", bytes(cgram) or b"\x00\x00"))
    # El tile transparente con el que se tapa lo que queda abajo de la escena.
    # Sesenta y cuatro ceros: un tile de 8bpp entero en el color 0.
    out.append(bloque("escena_cero", bytes(64)))
    for k, info in enumerate(escenas):
        datos = bytearray()
        for celda in escena_mod.tiles(info):
            datos += pack_tile(celda, planes=8)
        for t in range(trozos):
            out.append(bloque("escena_%d_%d" % (k, t),
                              bytes(datos[t * ESCENA_TROZO:
                                          (t + 1) * ESCENA_TROZO])))
    return "\n".join(out) + "\n"


def escenas_de(escenas, tropas):
    """Por índice de tropa, qué escena le toca. $FF: esa tropa pelea sin
    fondo, que es lo que pasa cuando el `EnemyEncounter` no nombra ninguno."""
    cual = {info["tropa"]: k for k, info in enumerate(escenas)}
    return [cual.get(numero, 0xFF) for numero in tropas]


def bloque(label, data, per_line=16, alinear=None, acomodar=True):
    """Un bloque de datos con su declaración de acomodo.

    Cada bloque se declara antes de emitirlo: casi todos se suben por DMA, y un
    DMA que cruce de banco lee basura de la mitad para adelante. La grilla de
    celdas no se sube por DMA sino que se recorre con un puntero, así que no le
    hace falta el banco entero: sólo que sus palabras no queden partidas entre
    el final de un banco y el principio del siguiente.

    `acomodar=False` es para lo que va a TABLAS: esa área vive entera adentro
    del banco 0 —termina en $7FC0—, así que nada de lo que caiga ahí puede
    cruzar, y declararlo emitía una cuenta que siempre daba cero.
    """
    out = ([".align %d" % alinear if alinear else ".bloque %d" % len(data)]
           if acomodar else [])
    out.append("%s:" % label)
    for i in range(0, len(data), per_line):
        out.append("    .byte " + ",".join("$%02X" % b
                                           for b in data[i:i + per_line]))
    return "\n".join(out)


def tabla_de_paginas(mapa, numero, evcodigo):
    """Las páginas de evento del mapa, con el puntero a su código.

    `evcodigo` es la **etiqueta** del bloque de código, que ya no se puede
    rearmar acá: dos mapas cuyos eventos compilan a los mismos bytes comparten
    el bloque y la etiqueta no lleva el número de este mapa. Rearmarla era lo
    que hacía —`"evcodigo_%d" % numero`— y al encender la deduplicación la
    tanda lo cobró enseguida: `varios` no ensamblaba porque nombraba un
    `evcodigo_2` que ya no existía.

    No pasa por `bloque()` porque sus punteros son simbólicos: apuntan adentro
    del bloque de código, que el enlazador ubica. Pero **sí se declara** con
    `.bloque`: la ROM la recorre con `[pag_ptr], y`, y una tabla que cruce de
    banco sigue en `$03:0000`, que en LoROM no es ROM sino el espejo de la
    WRAM. Sin la declaración pasó de verdad: al crecer los sprites del mapa 2
    con los eventos dibujados con un tile, la tabla quedó a caballo de
    `$02FFFF`, la ROM leyó basura en vez de las últimas páginas —entre ellas la
    de prueba— y la sacudida al borde del mapa no arrancaba nunca. La tanda lo
    cobró en pixeles sin decir por qué; lo dijo la RAM del emulador.
    """
    out = [".bloque %d" % (PAGINA_BYTES * len(mapa["paginas"])),
           "paginas_%d:" % numero]
    # Qué eventos tienen alguna página con ruta propia: el refresco de la ROM
    # sólo mira las páginas de ésos, y con los demás no gasta ni una lectura.
    con_ruta = {p["evento"] for p in mapa["paginas"] if p.get("ruta_propia")}
    # Y cuáles cambian de gráfico con la página: el refresco también mira las
    # de ésos, bit 5, y les copia a la fila lo que la página activa dibuja.
    cambian = mapa.get("cambian", set())
    # Y cuáles sólo aparecen y desaparecen con ella: los que caminan. Van por
    # el **mismo** bit 5, porque en +13 no queda ninguno libre —con ruta propia
    # los cinco de abajo son las banderas de la ruta, y el 4 es "la animación
    # sigue quieto"—. Quien los distingue es la ROM, que ya sabe si la fila
    # camina: `npc_buf + 9` vale NPC_QUIETO o el banco de sus doce poses. Ver
    # `grafico_de_pagina` en main.s.
    aparecen = mapa.get("aparecen", set())
    # Y cuáles tienen alguna página automática que compiló: bit 7. El refresco
    # de la ROM tiene que saber si la página activa de un evento es automática
    # —de ahí sale qué arranca solo— y con esto se ahorra leer las páginas de
    # los eventos que no pueden serlo nunca. Es el mismo truco que el bit 6.
    #
    # Las **paralelas** van por este mismo bit, y no por uno propio: en +13 no
    # queda ninguno libre. El bit quiere decir "mirale las páginas a este
    # evento en el refresco", que es lo que las dos necesitan; quién es
    # automática y quién paralela lo dice el trigger de la que gane. Sin esto,
    # `elegir_paginas` ni siquiera anota cuál es la activa —filtra por $E0— y
    # `paralelos_tick` no tendría de dónde sacar su código.
    con_auto = {p["evento"] for p in mapa["paginas"]
                if p["trigger"] in (eventos.TRIGGER_AUTOMATICO,
                                    eventos.TRIGGER_PARALELO) and p["codigo"]}
    for pagina in mapa["paginas"]:
        if pagina["codigo"]:
            destino = "%s + %d" % (evcodigo, pagina["offset"])
            puntero = "<(%s), >(%s), ^(%s)" % (destino, destino, destino)
        else:
            puntero = "$00, $00, $00"   # sin código: no hay nada que correr
        out.append("    .word %-4d ; +0  el evento al que pertenece"
                   % pagina["evento"])
        out.append("    .byte %-4d ; +2  su número de página" % pagina["pagina"])
        out.append("    .byte %-4d ; +3  qué la dispara" % pagina["trigger"])
        out.append("    .word %-4d ; +4  switch que pide, o 0" % pagina["switch_a"])
        out.append("    .word %-4d ; +6  el segundo, o 0" % pagina["switch_b"])
        out.append("    .byte %s ; +8  su código" % puntero)
        out.append("    .byte %-4d ; +11 el actor que pide en el grupo, o 0"
                   % pagina["actor"])
        out.append("    .byte %-4d ; +12 su capa: 1 es la del héroe, la que "
                   "le cierra el paso" % pagina["capa"])
        propia = pagina.get("ruta_propia")
        if propia:
            # La ruta propia de la página, la que camina sola: ver
            # `eventos.ruta_propia`. Las banderas: bit 0 la tiene, 1 se
            # repite, 2 se saltea lo bloqueado, 3 mira siempre igual, 4 la
            # animación sigue quieto.
            banderas = (1 | (2 if propia["repite"] else 0)
                        | (4 if propia["saltable"] else 0)
                        | (8 if propia["dir_fija"] else 0)
                        | (16 if propia["anim_continua"] else 0) | 64
                        | (32 if pagina["evento"] in cambian
                                 or pagina["evento"] in aparecen else 0)
                        | (128 if pagina["evento"] in con_auto else 0))
            destino = "evcodigo_%d + %d" % (numero, pagina["ruta_offset"])
            out.append("    .byte %-4d ; +13 las banderas de su ruta propia"
                       % banderas)
            out.append("    .byte %-4d ; +14 su frecuencia" % propia["frecuencia"])
            out.append("    .byte %-4d ; +15 y su velocidad" % propia["velocidad"])
            out.append("    .byte <(%s), >(%s), ^(%s) ; +16 sus órdenes"
                       % (destino, destino, destino))
            out.append("    .byte %-4d ; +19 cuántas" % len(propia["ordenes"]))
        else:
            out.append("    .byte %-4d ; +13 sin ruta propia; el bit 6 dice si "
                       "otra página del evento la tiene, el 5 si el gráfico "
                       "sigue a la página, el 7 si el evento tiene alguna "
                       "automática"
                       % ((64 if pagina["evento"] in con_ruta else 0)
                          | (32 if pagina["evento"] in cambian
                                   or pagina["evento"] in aparecen else 0)
                          | (128 if pagina["evento"] in con_auto else 0)))
            out.append("    .byte %-4d ; +14 su frecuencia" % pagina["frecuencia"])
            out.append("    .byte %-4d ; +15 y su velocidad, la de una ruta "
                       "forzada sobre el evento" % pagina["velocidad"])
            out.append("    .byte 0,0,0,0")
        # +20..+23: lo que dibuja la página, para los eventos que cambian de
        # gráfico: el tile, los atributos con la paleta y la prioridad de su
        # capa, la pose con el bit 7 puesto si hay gráfico, y los bits de
        # paso de su tile o $FF. Es lo que el refresco copia a la fila.
        oam = pagina.get("oam")
        if oam is None:
            out.append("    .byte $00, $00, $00, $FF ; +20 sin gráfico")
        else:
            out.append("    .byte $%02X, $%02X, $%02X, $%02X ; +20 su gráfico: "
                       "tile, atributos, pose, paso" % oam)
        # +24..+27: la condición por variable: la ranura o $FF, cómo se
        # compara —==, >=, <=, >, <, !=— y contra qué, con signo. Es lo que
        # `condiciones_ok` le pasa a `comparar_var`.
        variable = pagina.get("variable")
        if variable is None:
            out.append("    .byte $FF, 0 ; +24 sin condición por variable")
            out.append("    .word 0")
        else:
            ranura, comparacion, contra = variable
            out.append("    .byte %d, %d ; +24 la variable que pide y la "
                       "comparación" % (ranura, comparacion))
            out.append("    .word %d ; +26 contra qué" % (contra & 0xFFFF))
        # +28: el ítem que pide tener, o 0: `condiciones_ok` mira su cuenta
        # en `FAR_ITEMS`.
        out.append("    .word %-4d ; +28 el ítem que pide, o 0" % pagina["item"])
        # +30 y +31: el giro hacia el héroe. En qué entrada de `npc_poses`
        # están las poses de su gráfico, o $FF si la página no gira, y su
        # pose. Al dispararse, la ROM sube la que mira al héroe; en un
        # refresco, un cambio a una página que no gira o con otro gráfico
        # deshace el giro. Ver GIRO en eventos.py.
        grafico = pagina.get("grafico")
        k = (mapa.get("giro_k", {}).get(tuple(grafico[:2]))
             if pagina.get("gira") and grafico and pagina["evento"] in
             mapa.get("giran", ()) else None)
        out.append("    .byte $%02X, %d ; +30 el giro: sus poses y su pose"
                   % (0xFF if k is None else k, grafico[2] if k is not None else 0))
        assert PAGINA_BYTES == 32
    if not mapa["paginas"]:
        out.append("    .byte $00")     # una etiqueta no puede quedar vacía
    return "\n".join(out)


class Materiales:
    """Los bloques de datos de la ROM, con identidad propia y no del mapa.

    Antes cada mapa emitía sus bloques con su número pegado —`map_tiles_0`,
    `map_tiles_1`— y el registro del mapa armaba el nombre del puntero con esa
    misma cuenta. O sea que la identidad de un bloque **era** el mapa que lo
    pidió, y dos mapas con los mismos tiles se los pagaban dos veces sin que
    hubiera dónde notarlo.

    Acá el bloque tiene nombre propio y el mapa guarda a cuál apunta, que es lo
    que hay que tener antes de poder compartir nada. La numeración sigue siendo
    por clase y en orden de mapa, así que sin deduplicar los nombres son los
    mismos de siempre y la ROM sale byte por byte igual: es a propósito, para
    que este paso se pueda verificar sin depender de la tanda.

    `sprite_poses` ya funcionaba así desde antes —`indice_global` en `emit`— y
    es de donde sale la forma.
    """

    def __init__(self, deduplicar=False):
        self.deduplicar = deduplicar
        self.donde = {}
        self.cuantos = collections.Counter()
        self.ahorro = collections.Counter()
        self.repetidos = collections.Counter()

    def guardar(self, clase, datos, alinear=None):
        """(etiqueta, el asm a emitir). El asm es vacío si el bloque ya estaba.

        La clave incluye la clase y el acomodo, no sólo el contenido: dos
        bloques con los mismos bytes pero distinto `.bloque` o `.align` no
        son el mismo bloque para el enlazador.
        """
        datos = bytes(datos)
        clave = (clase, alinear, datos)
        if clave in self.donde:
            if self.deduplicar:
                self.ahorro[clase] += len(datos)
                self.repetidos[clase] += 1
                return self.donde[clave], ""
        etiqueta = "%s_%d" % (clase, self.cuantos[clase])
        self.cuantos[clase] += 1
        self.donde.setdefault(clave, etiqueta)
        return etiqueta, bloque(etiqueta, datos, alinear=alinear)

    def informe(self):
        """Qué se compartió, para que el ahorro sea un número y no una idea."""
        if not self.deduplicar or not self.ahorro:
            return []
        return ["  %-14s %2d bloque(s) compartido(s), %6.1f KB"
                % (clase, self.repetidos[clase], self.ahorro[clase] / 1024.0)
                for clase, _ in self.ahorro.most_common()] + [
            "  %-14s %2d              %6.1f KB en total"
            % ("", sum(self.repetidos.values()),
               sum(self.ahorro.values()) / 1024.0)]


def datos_del_mapa(mapa, numero, indice_global, materiales):
    """Los bloques de datos de un mapa, con el número pegado a cada etiqueta.

    `indice_global` es el número que lleva en la ROM el banco de doce poses de
    cada (CharSet, índice) **tal como este mapa lo cuantizó**: ver
    `banco_de_poses`, y el reparto de bancos en `emit`.
    """
    above, sprite = mapa["above"], mapa["sprite"]
    pares = [
        ("map_tiles", mapa["tiles"]),
        ("map_cgram", mapa["cram"]),
        ("above_tiles", above[0]),
        ("above_cgram", above[1]),
        ("sprite_tiles", sprite[0] if sprite else b""),
        ("sprite_cgram", sprite_colors_bytes(sprite)),
        ("map_bloques", mapa["bloques"]),
        ("bloque_pass", mapa["pass"]),
        ("npc_table", npc_bytes(sprite[3]) if sprite else b""),
        # Dos bytes por gráfico de la orden 34: su entrada en `npc_poses` —o
        # $FF, que es esconder— y su paleta. Ver `Graficos` en eventos.py.
        ("ruta_grafico",
         bytes(b for par in (sprite[9] if sprite else []) for b in par)),
        ("ev_pos", mapa["ev_pos"]),
        ("puertas", mapa["puertas"]),
        ("evcodigo", mapa["evcodigo"]),
        ("anim_tiles", mapa["anim"]),
    ]
    etiquetas, out = {}, []
    for nombre, datos in pares:
        etiquetas[nombre], texto = materiales.guardar(nombre, datos)
        if texto:
            out.append(texto)
    # Las dos tablas de punteros a las poses de la ROM: la de los NPCs que
    # caminan y la de los candidatos a líder.
    animados = sprite[7] if sprite else []
    out.append(npc_poses_asm(numero, animados, indice_global))
    out.append(actor_table_asm(numero, sprite[4] if sprite else [],
                               animados, indice_global))
    # La grilla va aparte porque es la única que no se sube por DMA.
    etiquetas["map_celdas"], texto = materiales.guardar(
        "map_celdas", mapa["celdas"], alinear=2)
    if texto:
        out.append(texto)
    out.append(tabla_de_paginas(mapa, numero, etiquetas["evcodigo"]))
    # Las tres que no se comparten son las que llevan **punteros simbólicos**
    # adentro —a las poses de la ROM, al código de los eventos—: sus bytes los
    # pone el enlazador, así que acá no hay contenido con el cual compararlas.
    for nombre in ("npc_poses", "actor_table", "paginas"):
        etiquetas[nombre] = "%s_%d" % (nombre, numero)
    return "\n".join(out), etiquetas


def encuentros_de_la_rom(mapas, tree, pasos_de_prueba, tropas):
    """Los encuentros al azar de cada mapa del cartucho, listos para emitir.

    Los datos viven en el árbol y no en el `.lmu`: cada nodo trae su lista de
    tropas, cada cuántos pasos, y —si es un área— el rectángulo que tapa. Ver
    `eventos.zonas_de_encuentro`, que es lo que usa también la referencia.

    De paso **pide las tropas**, que es lo que hace que el cartucho lleve sus
    enemigos y el paquete de audio de la pelea: sin eso un encuentro arrancaría
    una batalla contra una tropa que no está en ninguna tabla.

    `pasos_de_prueba` reemplaza el `encounter_steps` de todos los mapas. Es
    para las ROMs de prueba: con los del juego —de 25 a 85— un encuentro tarda
    más de cien pasos, que es lo que se quiere jugando y no lo que se quiere
    en un caso de la tanda. La referencia toma el mismo número por el mismo
    flag.
    """
    registros, zonas, tropas_de_zona, por_mapa = [], [], [], []
    for mapa in mapas:
        game_map = mapa["game_map"]
        suyas = eventos.zonas_de_encuentro(tree, mapa["id"],
                                           game_map.width, game_map.height)
        pasos = (pasos_de_prueba if pasos_de_prueba is not None
                 else tree.encounter_steps.get(mapa["id"],
                                               eventos.ENC_PASOS_DEFECTO))
        if not suyas or not eventos.enc_base(pasos):
            por_mapa.append(0xFF)
            continue
        por_mapa.append(len(registros))
        registro = {"base": eventos.enc_base(pasos),
                    "umbrales": eventos.enc_umbrales_de_paso(pasos),
                    "zona_ini": len(zonas), "zona_n": len(suyas)}
        for izq, arr, der, aba, cuales in suyas:
            zonas.append({"rect": (izq, arr, der, aba),
                          "tropa_ini": len(tropas_de_zona),
                          "tropa_n": len(cuales)})
            for numero in cuales:
                tropas.pedir(numero)
            tropas_de_zona += cuales
        registros.append(registro)
    if len(registros) > 0xFF or len(zonas) > 0xFF or len(tropas_de_zona) > 0xFF:
        # Las tres tablas se indexan con un byte. Con los 53 mapas del juego
        # entero son 53 registros, 56 zonas y 322 tropas, así que la que puede
        # pasarse es la última —y hoy sólo en un cartucho que los lleve todos—.
        sys.exit("los encuentros no entran en tablas de un byte: %d "
                 "registro(s), %d zona(s), %d tropa(s)"
                 % (len(registros), len(zonas), len(tropas_de_zona)))
    return {"por_mapa": por_mapa, "registros": registros, "zonas": zonas,
            "tropas": tropas_de_zona}


def emit(path, mapas, inicial=0, heroe_encima=False, grupo_inicial=(),
         ventana=None, titulo=None, ranuras=None, cartel=None,
         animaciones=None, tropas=(), audio_batalla=None, escenas=(),
         encuentros=None):
    """El .inc que se ensambla junto con main.s.

    `titulo` es la pantalla de título —la imagen y su menú— y puede faltar;
    `ranuras` es la pantalla de ranuras y **va siempre**: la abre el save point
    desde adentro del juego, tenga la ROM título o no. Ver `pantalla_ranuras`
    en titulo.py.
    """
    for numero, mapa in enumerate(mapas):
        layout = mapa["layout"]
        for cuantos, nombre in (
                (len(mapa["tiles"]) // BYTES_PER_TILE, "tiles"),
                (len(mapa["above"][0]) // 32, "encima"),
                (len(mapa["sprite"][0]) // 32 if mapa["sprite"] else 0,
                 "sprites")):
            if cuantos > layout[nombre][1]:
                raise SystemExit(
                    "mapa %d: con este reparto de VRAM, %s necesita %d tiles y "
                    "entran %d" % (mapa["id"], nombre, cuantos,
                                   layout[nombre][1]))

    # Dónde quedó el cartel: el mapa de la tabla que se llevó sus tiles, y en
    # qué tile y con qué paleta. Sale de los mapas ya convertidos y no de una
    # variable que haya que ir pasando: el que lo tiene es el único con
    # `imagen_base` distinto de cero.
    cartel_base, cartel_pal = 0, 0
    for mapa in mapas:
        if mapa["sprite"] and mapa["sprite"][13]:
            cartel_base, cartel_pal = mapa["sprite"][13], mapa["sprite"][14]
            break

    cabecera = (
        "; Generado por tools/port/snes_convert.py. No editar.\n"
        "; Mapas: %s\n\n"
        "MAPA_COUNT   = %d\n"
        "MAPA_STRIDE  = %d\n"
        "MAPA_INICIAL = %d\n"
        "; Lo que no depende del mapa: el tilemap vive siempre en el mismo\n"
        "; lugar de la VRAM, y el paso de la tabla de NPCs no cambia.\n"
        "VRAM_MAP       = $%04X\n"
        "VRAM_ABOVE_MAP = $%04X\n"
        "MAP_LAYOUT  = %d\n"
        "NPC_STRIDE  = %d\n"
        "NPC_MAX     = %d\n"
        "NPC_QUIETO  = $%02X\n"
        "; La tabla de posiciones de eventos, y cuántas rutas forzadas\n"
        "; pueden estar corriendo a la vez sobre ellos.\n"
        "EV_STRIDE   = %d\n"
        "EV_MAX      = %d\n"
        "RUTA_EV_MAX = %d\n"
        "PUERTA_BYTES = %d\n"
        "PAGINA_BYTES = %d\n"
        "GIRO_NINGUNO = $%04X\n"
        "; Y cuántos gráficos distintos puede pedir la orden 34 en un mapa:\n"
        "; su tabla se copia a la RAM como la de NPCs.\n"
        "RUTA_GRAF_MAX = %d\n"
        "; La cabecera de un cuadro de texto, que es el primer byte del que\n"
        "; `OP_MESSAGE` nombra: los renglones en los tres bits de abajo, el\n"
        "; autocierre del `\\^` en el bit 3 y cuantas pausas de `\\|` lleva en\n"
        "; el nibble de arriba. Y cuanto dura cada pausa, que son 61 cuadros y\n"
        "; no 60: ver CUADROS_DE_PAUSA en eventos.py.\n"
        "CABECERA_LINEAS     = $%02X\n"
        "CABECERA_AUTOCIERRE = $%02X\n"
        "CUADROS_DE_PAUSA    = %d\n"
        "; El bit de arriba de la ranura de OP_VAR y de OP_KEY: si la\n"
        "; escritura pide el refresco de páginas. Lo resuelve el conversor\n"
        "; mirando qué variables miran las condiciones de página de este\n"
        "; mapa; `var_apuntar` enmascara con VAR_RANURA. Ver VAR_REFRESCO en\n"
        "; eventos.py: sin esto media Lashe City corría a 30 cuadros.\n"
        "VAR_REFRESCO = $%02X\n"
        "VAR_RANURA   = $%02X\n"
        "ANIM_ENTRADA = %d\n"
        "ANIM_SONIDO  = %d\n"
        "ANIM_DESTELLO = %d\n"
        "; El cartel del ShowPicture: dónde cae su esquina en la pantalla\n"
        "; de la consola y cuántos objetos de 32x32 mide.\n"
        "; Las coordenadas ya vienen escaladas de 320x240 a 256x224 y la X\n"
        "; puede ser negativa: el cartel del \"1 year earlier\" se sale por la\n"
        "; izquierda, que es lo que RM2k muestra. Ver tools/port/imagen.py.\n"
        "; Las banderas de `KeyInputProc`, que van en el segundo byte de\n"
        "; OP_KEY. Ver `op_key` en main.s.\n"
        "TECLA_ESPERA   = $%02X\n"
        "TECLA_DIRS     = $%02X\n"
        "TECLA_DECISION = $%02X\n"
        "TECLA_CANCELAR = $%02X\n"
        "TECLA_ARRANCA  = $%02X\n"
        "TECLA_VALOR_DECISION = %d\n"
        "TECLA_VALOR_CANCELAR = %d\n"
        "; Y las cuatro direcciones, con el mismo número que les da\n"
        "; `CheckInput`. El orden en que se miran sale de acá: de mayor a\n"
        "; menor, que es lo que dice \"RPG processes keys from highest\n"
        "; variable value to lowest\".\n"
        "TECLA_VALOR_ARRIBA   = %d\n"
        "TECLA_VALOR_DERECHA  = %d\n"
        "TECLA_VALOR_IZQUIERDA = %d\n"
        "TECLA_VALOR_ABAJO    = %d\n"
        "; En qué tile de su banco de sprites arranca y con qué paleta.\n"
        "; Van de globales y no en el registro del mapa porque el cartel es\n"
        "; **uno solo por ROM** y vive en un solo mapa: los dos campos\n"
        "; ocupaban los últimos bytes libres de MAPA_STRIDE, y agrandar el\n"
        "; registro para eso habría sido caro por nada. Que ningún otro mapa\n"
        "; lo muestre lo controla el conversor, que corta.\n"
        "IMAGEN_BASE = %d\n"
        "IMAGEN_PAL  = %d\n"
        "IMAGEN_X    = %d\n"
        "IMAGEN_Y    = %d\n"
        "IMAGEN_OBJETOS = %d\n"
        "; Cuántos tiles de la grilla de nombres hay que saltear para pasar\n"
        "; de un objeto al siguiente, y de una fila de cuatro a la que sigue.\n"
        "IMAGEN_PASO = %d\n"
        "IMAGEN_FILA = %d\n"
        "; La lluvia: ver OP_WEATHER en eventos.py.\n"
        "LLUVIA_GOTAS_MAX = %d\n"
        "LLUVIA_GOTAS_0 = %d\n"
        "LLUVIA_GOTAS_1 = %d\n"
        "LLUVIA_GOTAS_2 = %d\n"
        "LLUVIA_VIDA   = %d\n"
        "LLUVIA_NACE   = %d\n"
        "LLUVIA_SEMILLA = $%04X\n"
        "CLIMA_LLUVIA  = %d\n"
        "; El inventario: un byte por ítem del LDB y el tope de RM2k. Ver\n"
        "; OP_ITEM en eventos.py.\n"
        "ITEMS_N       = %d\n"
        "ITEM_MAX      = %d\n"
        "; Las variables: cuántas ranuras lleva esta ROM —al menos una, porque\n"
        "; un largo cero cerraría la tabla de la partida—, las clases de\n"
        "; operando de ControlVars que la ROM distingue, la suma, y la\n"
        "; semilla del azar. Ver 'las variables de RM2k' en eventos.py.\n"
        "VARIABLES_N   = %d\n"
        "VAR_SUMAR     = %d\n"
        "VAR_VARIABLE  = %d\n"
        "VAR_AZAR      = %d\n"
        "VAR_OTRO      = %d\n"
        "; La clase 6, las coordenadas de un personaje: el blanco va como el de\n"
        "; OP_ROUTE —0 el héroe, el índice del evento más uno— y el otro operando\n"
        "; dice cuál coordenada. Ver VAR_PERSONAJE en eventos.py.\n"
        "VAR_PERSONAJE = %d\n"
        "PERSONAJE_X   = %d\n"
        "PERSONAJE_Y   = %d\n"
        "AZAR_SEMILLA  = $%04X\n"
        "; Y la del azar de los encuentros, que es otra a propósito: caminar no\n"
        "; le corre el azar al mapa. Ver ENC_SEMILLA en eventos.py.\n"
        "ENC_SEMILLA   = $%04X\n"
        "TIMER_PONER_VAR = %d\n"
        "; Las clases de condición de ConditionalBranch que sabemos,\n"
        "; con el número de RM2k tal cual.\n"
        "COND_ORO    = %d\n"
        "COND_ITEM   = %d\n"
        "COND_ACTOR  = %d\n"
        "; Y las dos preguntas de actor que llevan dos operandos, con su\n"
        "; opcode propio: ver OP_IF_ACTOR en eventos.py.\n"
        "COND_ACTOR_HABILIDAD = %d\n"
        "COND_ACTOR_EQUIPO    = %d\n"
        "ORO_MAX     = %d\n"
        "; Las dos operaciones de PanScreen que compilan.\n"
        "PAN_CORRER  = %d\n"
        "PAN_VOLVER  = %d\n"
        "; Las tres operaciones del cronómetro.\n"
        "TIMER_PONER    = %d\n"
        "TIMER_ARRANCAR = %d\n"
        "; Y sus cinco glifos en pantalla: dónde va el primero y cuánto\n"
        "; mide cada uno. El de los dos puntos es el número 10.\n"
        "TIMER_X        = %d\n"
        "TIMER_Y        = %d\n"
        "TIMER_GLIFO_W  = %d\n"
        "TIMER_DOS_PUNTOS = %d\n"
        "; Cuántos cuadros entran en un segundo, y los que `SetTimer` le\n"
        "; suma de más para que el primer segundo se vea entero.\n"
        "TIMER_CUADROS  = %d\n"
        "TIMER_DE_MAS   = %d\n"
        "; Cuántos destellos pueden estar corriendo a la vez.\n"
        "FLASH_MAX   = %d\n"
        "; Cuántos eventos con página paralela puede haber en un mapa.\n"
        "PARALELO_MAX = %d\n"
        "TRIGGER_AUTOMATICO = %d\n"
        "TRIGGER_ACCION     = %d\n"
        "TRIGGER_TOCA_HEROE = %d\n"
        "TRIGGER_PARALELO   = %d\n"
        "; Cuántos cuadros dura un paso de una celda. Sale del modelo y no de\n"
        "; una cuenta en la ROM: es lo que los dos lados tienen que contar\n"
        "; igual para que una ruta forzada termine en el mismo cuadro.\n"
        "CUADROS_POR_CELDA = %d\n"
        "; La frecuencia más alta de una ruta, que es donde topan las\n"
        "; órdenes 30 y 31. La más baja la topa la ROM en 1, como RM2k;\n"
        "; lo que garantiza que no se llegue es el conversor, que rechaza\n"
        "; la ruta.\n"
        "RUTA_FRECUENCIA = %d\n"
        "; Y cuánto cuesta un `wait` adentro de una ruta forzada. **No es un\n"
        "; cuadro**: en RM2k es `SetMaxStopCountForWait`, o sea\n"
        "; `20 + (1 << (8 - frecuencia))`, y con la frecuencia 8 —la única\n"
        "; que el conversor deja pasar— son veinte.\n"
        "RUTA_ESPERA = %d\n"
        "; Y el salto: cuánto le queda al arrancar y cuánto baja por cuadro.\n"
        "; No depende de la distancia —saltar cinco celdas cuesta lo mismo\n"
        "; que saltar en el lugar—, y son once cuadros.\n"
        "SALTO_PASO = %d\n"
        "SALTO_VELOCIDAD = %d\n"
        "TINTE_NEUTRO = %d\n"
        "; El fundido de los teletransportes: 35 cuadros de ida y 35 de\n"
        "; vuelta, como RM2k, y de cada 35 la rampa son 24. El mapa se carga\n"
        "; en el primer cuadro negro, que es el %d. Estos números y la tabla\n"
        "; de más abajo salen de las constantes del fundido de\n"
        "; tools/port/eventos.py.\n"
        "FUNDIDO_CUADROS = %d\n"
        "FUNDIDO_TOTAL   = %d\n"
        "FUNDIDO_RAMPA   = %d\n"
        "FUNDIDO_NEGRO   = %d\n"
        "FUNDIDO_CARGA   = %d\n"
        "BRILLO_MAX      = %d\n"
        "; Los pesos de luminancia del Y'CbCr, que son con los que RM2k\n"
        "; satura. Suman 65536 exactos, así que sobre canales de cinco bits\n"
        "; dan una luminancia de cinco bits sin reescalar nada.\n"
        "LUZ_R = %d\n"
        "LUZ_G = %d\n"
        "LUZ_B = %d\n"
        "; Un bit por switch. El más alto que el juego consulta es el 1003.\n"
        "SWITCH_BYTES = %d\n"
        "; El grupo con el que arranca la partida, y su tope. En RM2k el\n"
        "; gráfico del héroe es el del primero, así que esto decide qué\n"
        "; sprite se dibuja; `ChangePartyMembers` lo mueve en caliente.\n"
        "GRUPO_MAX      = %d\n"
        "GRUPO_INICIAL_N = %d\n"
        "ACTOR_BYTES    = %d\n"
        "; Cuántos bytes de esa entrada son los quince colores del\n"
        "; actor: la ROM los sube a la ranura que los líderes\n"
        "; comparten. Ver `elegir_grafico_heroe`.\n"
        "ACTOR_COLORES  = %d\n"
        "OBJ_COLORS     = %d\n"
        "; La capa del héroe, para ordenarlo contra los NPCs.\n"
        "HERO_LAYER  = %d\n"
        "; Su prioridad de objeto. $10 —debajo de la capa de encima— en\n"
        "; toda ROM que no sea la de `encima`, que la sube a $20\n"
        "; para ejercitar la prioridad 2. Ningún evento del juego llega\n"
        "; a ejercitarla: ver 'Cómo se verifica' en README.md.\n"
        "HERO_PRIORITY = $%02X\n"
        "; La ventana de mensaje: sus tiles viven en la segunda mitad del\n"
        "; banco de BG2, o sea a partir del índice 256, y sus celdas ya\n"
        "; vienen armadas con ese corrimiento y con la prioridad de la capa\n"
        "; de encima.\n"
"; Y dónde arranca el fondo en CGRAM: abajo de él viven el color de\n"
        "; fondo de la pantalla y la paleta de la ventana de mensaje, que\n"
        "; son de toda la ROM. El fondo va a 8 bits y direcciona CGRAM en\n"
        "; directo, así que le alcanza con arrancar corrido.\n"
        "CGRAM_BASE     = %d\n"
"VENTANA_CGADD  = %d\n"
        "VENTANA_TILES  = %d\n"
        "VENTANA_FILAS_ = %d\n"
        "VENTANA_COLS   = %d\n"
        "; El área de texto: dónde arranca en el banco de tiles de la\n"
        "; ventana y qué celdas ocupa. Sus tiles no están deduplicados —la\n"
        "; ROM los reescribe— y de ahí sale el tope de caracteres por línea.\n"
        "VENTANA_TEXTO_BASE = %d\n"
        "VENTANA_TEXTO_FILA = %d\n"
        "VENTANA_TEXTO_FILAS = %d\n"
        "VENTANA_TEXTO_COL  = %d\n"
        "VENTANA_TEXTO_COLS = %d\n"
        "MENSAJE_COLS   = %d\n"
        "; La fuente: 95 glifos ASCII de seis bits por doce filas, y el\n"
        "; índice de paleta de la sombra. El de cada fila del glifo está en\n"
        "; fuente_color.\n"
        "FUENTE_ALTO    = %d\n"
        "FUENTE_ANCHO   = %d\n"
        "FUENTE_SOMBRA  = %d\n"
        "FUENTE_PRE_FILAS = %d\n"
        "FUENTE_PRE_CHAR  = %d\n"
        "; La animación del ChipSet. Cada mapa tiene una entrada en\n"
        "; `anim_tabla` con sus dos corridas y un bloque con los dibujos;\n"
        "; ver `anim_tabla` en snes_convert.py. Las cadencias y el ciclo\n"
        "; del agua salen de `rm2k.py`, que es de donde los lee la\n"
        "; referencia.\n"
        "ANIM_FAMILIAS  = %d\n"
        "ANIM_STRIDE    = %d\n"
        "ANIM_FAM_STRIDE = %d\n"
        "AGUA_CUADROS   = %d\n"
        "AGUA_DIBUJOS   = %d\n"
        "AGUA_CICLO_N   = %d\n"
        "ANIMADO_CUADROS = %d\n"
        "ANIMADO_PASOS  = %d\n"
        "BYTES_POR_TILE = %d\n"
        "; La pantalla de título. TITULO_TILES en 0 quiere decir que esta ROM\n"
        "; no la lleva y que los bloques de abajo son un byte de relleno; el\n"
        "; código de main.s se apaga solo con eso. Vive sola en la VRAM —no\n"
        "; comparte con ningún mapa, porque mientras se ve no hay mapa\n"
        "; cargado— así que sus dos direcciones son fijas y no salen del\n"
        "; reparto de `vram_layout`.\n"
        "TITULO_TILES   = %d\n"
        "TITULO_VRAM    = $0000\n"
        "TITULO_MAP     = $4000\n"
        "TITULO_COLORES = %d\n"
        "; El menú, en BG2 a cuatro bits por pixel: su banco de tiles, cuántas\n"
        "; opciones tiene y cuál está elegida al entrar. El cursor no se dibuja\n"
        "; aparte: hay un tilemap por opción y moverlo es subir el otro.\n"
        ";\n"
        "; El reparto de la VRAM en esta pantalla, en palabras, y por qué cada\n"
        "; uno está donde está: los tiles de la imagen arrancan en 0 y se\n"
        "; llevan 15872, así que todo lo demás va **arriba** de eso. La base de\n"
        "; tiles de un BG va de a 4096 palabras, que es lo que fija $5000 para\n"
        "; el menú; los tilemaps van de a 1024 y entran en el hueco de al lado.\n"
        ";\n"
        ";   $0000 .. $3E00   los 496 tiles de la imagen, a 8bpp\n"
        ";   $4000 .. $4400   su tilemap de 32x32\n"
        ";   $4400 .. $4800   el del menú\n"
        ";   $5000 ..         los tiles del menú, a 4bpp\n"
        "TITULO_MENU_CGRAM = %d\n"
        "TITULO_MENU_TILES = %d\n"
        "TITULO_MENU_VRAM  = $5000\n"
        "TITULO_MENU_MAP   = $4400\n"
        "TITULO_MENU_N     = %d\n"
        "; La pantalla de ranuras, que usan las dos puntas: 'Resume the Story'\n"
        "; y el save point. Es una pantalla propia —no una capa encima del\n"
        "; título— así que se sube entera al entrar. **Va en toda ROM**, con\n"
        "; título o sin él: el save point la abre desde adentro del juego, y\n"
        "; por eso sus direcciones de VRAM son suyas y no las del menú: caen\n"
        "; en el banco de tiles de BG1 de los cuatro repartos, que es lo que\n"
        "; `volver_al_mapa` repone con `load_map`. Ver RANURA_MAP en el\n"
        "; conversor.\n"
        "RANURA_VRAM       = $%04X\n"
        "RANURA_MAP        = $%04X\n"
        ";\n"
        "; Los bloques de celdas: la cabecera tiene dos variantes —cargar y\n"
        "; guardar— y cada ranura cuatro —vacía o llena, con cursor o sin él—.\n"
        "; Mover el cursor es reescribir dos filas y no un tilemap entero.\n"
        "SRAM_RANURAS_N    = %d\n"
        "RANURA_TILES      = %d\n"
        "RANURA_CAB_FILA   = %d\n"
        "RANURA_CAB_FILAS  = %d\n"
        "RANURA_CAB_CELDAS = %d\n"
        "RANURA_FILA0      = %d\n"
        "RANURA_SALTO      = %d\n"
        "RANURA_FILAS      = %d\n"
        "RANURA_CELDAS     = %d\n"
        "; Y dónde va cada fila en el tilemap, en palabras. También sale de una\n"
        "; tabla: la cuenta es RANURA_FILA0 + n * RANURA_SALTO, por 32, y\n"
        "; escribirla en el 65816 sería el cuarto lugar donde equivocarse.\n"
        "RANURA_CAB_VRAM   = %d\n"
        "; Cuántos bloques hay antes del primero de las filas: son las dos\n"
        "; cabeceras, cargar y guardar.\n"
        "RANURA_BLOQUE_FILAS = 2\n"
        "; El grupo de la partida guardada, encima de la fila: las caras de\n"
        "; hasta RANURA_CARAS_MAX, de RANURA_CARA_COLS por RANURA_CARA_FILAS\n"
        "; celdas, y el nombre del primero. Qué bloque le toca a cada actor lo\n"
        "; dicen `ranura_cara_bloque` y `ranura_nombre_bloque`, por id de actor\n"
        "; hasta RANURA_ACTORES_N, con $FF para 'no tiene'; y a dónde van,\n"
        "; `ranura_cara_vram` —de a cuatro por ranura— y `ranura_nombre_vram`.\n"
        "RANURA_CARAS_MAX  = %d\n"
        "RANURA_CARA_COLS  = %d\n"
        "RANURA_CARA_FILAS = %d\n"
        "RANURA_NOMBRE_COLS  = %d\n"
        "RANURA_NOMBRE_FILAS = %d\n"
        "RANURA_ACTORES_N  = %d\n"
        "; Cuántas entradas de CGRAM sube la pantalla de ranuras: la paleta 0\n"
        "; del texto y una por cara, de dieciséis cada una.\n"
        "RANURA_CGRAM_N    = %d\n"
        "; Cuántas entradas de CGRAM usa el menú del título: una paleta de\n"
        "; dieciséis, la 0. Ya está definida más arriba, con la pantalla de\n"
        "; título; esto confirma que las dos cuentas den lo mismo.\n"
        ".assert TITULO_MENU_CGRAM = %d, error, \"dos cuentas del CGRAM del menú\"\n\n"
        % (", ".join("%d %s" % (m["id"], m["nombre"]) for m in mapas),
           len(mapas), MAPA_STRIDE, inicial,
           VRAM_MAP, VRAM_ABOVE_MAP, MAP_LAYOUT, NPC_STRIDE, NPC_MAX,
           NPC_QUIETO,
           EV_STRIDE, EV_MAX, RUTA_EV_MAX,
           PUERTA_BYTES, PAGINA_BYTES, GIRO_NINGUNO, RUTA_GRAF_MAX,
           eventos.CABECERA_LINEAS, eventos.CABECERA_AUTOCIERRE,
           eventos.CUADROS_DE_PAUSA, eventos.VAR_REFRESCO, eventos.VAR_RANURA_MAX,
           eventos.ANIM_ENTRADA, eventos.ANIM_SONIDO, eventos.ANIM_DESTELLO, eventos.TECLA_ESPERA,
           eventos.TECLA_DIRS, eventos.TECLA_DECISION,
           eventos.TECLA_CANCELAR, eventos.TECLA_ARRANCA,
           eventos.TECLA_VALOR_DECISION, eventos.TECLA_VALOR_CANCELAR,
           eventos.TECLA_VALOR_DIR[0], eventos.TECLA_VALOR_DIR[1],
           eventos.TECLA_VALOR_DIR[3], eventos.TECLA_VALOR_DIR[2],
           cartel_base, cartel_pal,
           cartel["x"] if cartel else 0, cartel["y"] if cartel else 0,
           cartel["objetos"] if cartel else 0,
           imagen.OBJ_LADO, 4 * imagen.GRILLA,
           max(eventos.LLUVIA_GOTAS),
           eventos.LLUVIA_GOTAS[0], eventos.LLUVIA_GOTAS[1],
           eventos.LLUVIA_GOTAS[2], eventos.LLUVIA_VIDA,
           eventos.LLUVIA_NACE, eventos.LLUVIA_SEMILLA,
           eventos.CLIMA_LLUVIA,
           eventos.ITEMS_N,
           eventos.ITEM_MAX,
           variables_n(),
           eventos.VAR_SUMAR, eventos.VAR_VARIABLE, eventos.VAR_AZAR,
           eventos.VAR_OTRO,
           eventos.VAR_PERSONAJE, eventos.PERSONAJE_X, eventos.PERSONAJE_Y,
           eventos.AZAR_SEMILLA, eventos.ENC_SEMILLA,
           eventos.TIMER_PONER_VAR,
           eventos.COND_ORO, eventos.COND_ITEM,
           eventos.COND_ACTOR, eventos.COND_ACTOR_HABILIDAD,
           eventos.COND_ACTOR_EQUIPO,
           eventos.ORO_MAX,
           eventos.PAN_CORRER, eventos.PAN_VOLVER,
           eventos.TIMER_PONER, eventos.TIMER_ARRANCAR,
           TIMER_X, TIMER_Y, TIMER_GLIFO_W, TIMER_GLIFOS - 1,
           eventos.CUADROS_POR_SEGUNDO, eventos.TIMER_CUADROS_DE_MAS,
           FLASH_MAX, PARALELO_MAX,
           eventos.TRIGGER_AUTOMATICO, eventos.TRIGGER_ACCION,
           eventos.TRIGGER_TOCA_HEROE, eventos.TRIGGER_PARALELO,
           eventos.CUADROS_POR_CELDA, eventos.RUTA_FRECUENCIA,
           eventos.CUADROS_DE_ESPERA_DE_RUTA,
           eventos.SALTO_PASO, eventos.SALTO_VELOCIDAD,
           eventos.TINTE_NEUTRO,
           eventos.FUNDIDO_RAMPA,
           eventos.FUNDIDO_CUADROS, eventos.FUNDIDO_TOTAL,
           eventos.FUNDIDO_RAMPA, eventos.FUNDIDO_NEGRO,
           eventos.FUNDIDO_RAMPA, eventos.BRILLO_MAX,
           eventos.LUZ_R, eventos.LUZ_G, eventos.LUZ_B, SWITCH_BYTES,
           eventos.GRUPO_MAX, len(grupo_inicial), ACTOR_BYTES,
           ACTOR_COLORES, OBJ_COLORS,
           rm2k.LAYER_SAME,
           OBJ_PRIORITY_ABOVE if heroe_encima else OBJ_PRIORITY,
           CGRAM_RESERVADAS,
           paleta_de_la_ventana() * COLORS_PER_PALETTE,
           len(ventana["tiles"]) // 32,
           VENTANA_FILAS_INC, VENTANA_COLS_INC,
           ventana["base"],
           VENTANA_TEXTO_FILA, VENTANA_TEXTO_FILAS,
           VENTANA_TEXTO_COL, VENTANA_TEXTO_COLS, _columnas(),
           FUENTE_ALTO, FUENTE_ANCHO,
           ventana["sombra"],
           FUENTE_PRE_FILAS, FUENTE_PRE_CHAR,
           len(FAMILIAS), ANIM_STRIDE, ANIM_FAM_STRIDE,
           rm2k.AGUA_CUADROS_LENTO,
           FAMILIAS[0][1],
           len(rm2k.AGUA_CICLO), rm2k.ANIMADO_CUADROS, rm2k.ANIMADO_PASOS,
           BYTES_PER_TILE,
           0 if titulo is None else len(titulo["tiles"]),
           0 if titulo is None else len(titulo["paleta"]),
           titulo_mod.MENU_CGRAM,
           0 if titulo is None else len(titulo["menu_tiles"]),
           0 if titulo is None else len(titulo["menu_tilemaps"]),
           RANURA_VRAM, RANURA_MAP,
           len(ranuras["filas"]),
           len(ranuras["tiles"]),
           titulo_mod.CABECERA_Y // titulo_mod.CELL,
           titulo_mod.CABECERA_FILAS,
           titulo_mod.CABECERA_FILAS * titulo_mod.COLS,
           titulo_mod.RANURA_Y // titulo_mod.CELL,
           titulo_mod.RANURA_SALTO // titulo_mod.CELL,
           titulo_mod.RANURA_FILAS,
           titulo_mod.RANURA_FILAS * titulo_mod.COLS,
           titulo_mod.CABECERA_Y // titulo_mod.CELL * 32,
           titulo_mod.CARAS_MAX, titulo_mod.CARA_CELDAS,
           titulo_mod.CARA_CELDAS, titulo_mod.NOMBRE_COLS,
           titulo_mod.NOMBRE_FILAS,
           (max(list(ranuras["caras"]) + list(ranuras["nombres"]) + [-1])
            + 1),
           len(ranuras["paletas"]) * titulo_mod.MENU_CGRAM,
           titulo_mod.MENU_CGRAM))

    with open(path, "w") as handle:
        handle.write(cabecera)
        handle.write(desplazamientos())
        handle.write("\n\n")
        # La rampa del fundido, en el banco 0 porque `fundido_tick` la lee con
        # `lda fundido_rampa, x`. Sale de `eventos.rampa_de_fundido()`, que es
        # la misma que usa la referencia: escribirla también en main.s sería la
        # duplicación de siempre, dos lados que se pueden equivocar igual.
        handle.write('.segment "TABLAS"\n'
                     '; El brillo maestro en cada cuadro de la rampa, de negro\n'
                     '; a lleno. Bajando se lee al revés.\n'
                     'fundido_rampa:\n    .byte %s\n\n'
                     % ",".join(str(v) for v in eventos.rampa_de_fundido()))
        # Los datos van en RODATA, que el enlazador reparte por los bancos de
        # arriba. Lo que queda en TABLAS —o sea en el banco 0— es lo que la ROM
        # recorre con `lda tabla, x` a secas, que direcciona el banco de datos.
        # `mapa_tabla` ya no está entre ésas: ver `tabla_de_mapas`.
        handle.write('.segment "RODATA"\n')
        # Las doce poses de cada personaje que cambia de pose, **una vez por
        # cuantización** y no una por ROM: dos mapas que dibujen al mismo
        # personaje con la misma paleta comparten el banco, y si uno lo
        # cuantizó distinto —porque le prestó una paleta ajena, como el mapa 8
        # a Chara2:0, o le bajó un color— lleva el suyo. Hasta el 2026-09-10
        # esto era un `sys.exit`, y el reparto de paletas tenía una regla para
        # esquivarlo que el préstamo no miraba: agregar Lashe City 33,36 a la
        # demo cortaba ahí. Un banco de más son 6 KB de cartucho; un corte es
        # un mapa que no entra.
        indice_global, bancos, indice_por_mapa = {}, [], []
        for mapa in mapas:
            propio = {}
            for par, datos in (mapa["sprite"][8].items()
                               if mapa["sprite"] else ()):
                clave = (par, datos)
                if clave not in indice_global:
                    if any(k[0] == par for k in indice_global):
                        print("  mapa %d: %s:%d va con un banco de poses "
                              "propio, cuantizado distinto que en otro mapa"
                              % (mapa["id"], par[0], par[1]))
                    indice_global[clave] = len(bancos)
                    bancos.append(datos)
                propio[par] = indice_global[clave]
            indice_por_mapa.append(propio)
        handle.write("; --- las poses de los personajes que cambian de pose, "
                     "de toda la ROM ---\n")
        for g, datos in enumerate(bancos):
            handle.write(bloque("sprite_poses_%d" % g, datos) + "\n")
        handle.write("\n")
        materiales = Materiales(deduplicar=True)
        etiquetas = []
        for numero, mapa in enumerate(mapas):
            handle.write("; --- %d: mapa %d %r ---\n"
                         % (numero, mapa["id"], mapa["nombre"]))
            texto, suyas = datos_del_mapa(mapa, numero,
                                          indice_por_mapa[numero], materiales)
            etiquetas.append(suyas)
            handle.write(texto)
            handle.write("\n")
        if True:
            # La ventana de mensaje es una sola para toda la ROM —el mismo
            # skin, el mismo tamaño— así que va como bloque global y no en la
            # tabla de mapas. Lo único que depende del mapa es en qué paleta
            # entra, y eso se resuelve arriba, al elegir el reparto de CGRAM.
            #
            # BG2 va en 4 bits, así que su celda **sí** usa los tres bits de
            # paleta —a diferencia del fondo, que va en 8 y los ignora—. La
            # ventana va en la 0 y es la misma para todos los mapas: sus celdas
            # se emiten una sola vez. Que el fondo no la pise sale del reparto
            # —arranca en `CGRAM_RESERVADAS`— pero se controla igual: si la
            # pisara, la ventana saldría con los colores del mapa y ninguna
            # comparación de un solo mapa lo vería.
            paleta = paleta_de_la_ventana()
            for m in mapas:
                if len(m["cram_words"]) + CGRAM_RESERVADAS > \
                        m["above"][3] * COLORS_PER_PALETTE:
                    raise SystemExit(
                        "el fondo del mapa %d usa %d entradas de CGRAM desde "
                        "la %d y pisa la capa de encima, que arranca en la %d"
                        % (m["id"], len(m["cram_words"]), CGRAM_RESERVADAS,
                           m["above"][3] * COLORS_PER_PALETTE))
            handle.write("\n; --- la ventana de mensaje ---\n")
            handle.write(bloque("ventana_tiles", ventana["tiles"]) + "\n")
            # Sólo las `CGRAM_RESERVADAS` de abajo: de la 8 para arriba es
            # del fondo, y subir las dieciséis se lo borraría.
            handle.write(bloque("ventana_cgram",
                                b"".join(w.to_bytes(2, "little")
                                         for w in ventana["cram"]
                                         [:CGRAM_RESERVADAS])) + "\n")
            plano = bytearray()
            for fila in ventana["celdas"]:
                for celda in fila:
                    # El índice de tile va corrido a la segunda mitad del banco
                    # de BG2, y con la prioridad de la capa de encima para que
                    # tape al héroe y a los NPCs.
                    plano += (entry(VENTANA_TILE_BASE + celda, False, False,
                                    PRIORITY_ABOVE)
                              | (paleta << 10)).to_bytes(2, "little")
            handle.write(bloque("ventana_celdas", bytes(plano)) + "\n")
            # El área de texto sin texto: los 240 tiles que la ROM copia al
            # buffer antes de dibujar encima. Van en el orden en que la ROM los
            # necesita, o sea el de las celdas.
            handle.write(bloque("ventana_fondo", ventana["fondo"]) + "\n")
            # La fuente y los colores. `fuente_color` es el índice de paleta de
            # cada una de las doce filas del glifo: el degradé de RM2k sale de
            # una máscara de 16x16, pero cada fila es de un solo color, así que
            # doce bytes alcanzan y la ROM no tiene que muestrear nada.
            handle.write(bloque("fuente_tabla", ventana["fuente"]) + "\n")
            pre = fuente_prerender(ventana["fuente"], ventana["color"],
                                   ventana["sombra"])
            for fase, datos in enumerate(pre):
                handle.write(bloque("fuente_pre%d" % fase, datos) + "\n")
            handle.write(bloque("mensajes", ventana["mensajes"]) + "\n")
        # --- el cartel del ShowPicture ---
        #
        # Sus quince colores tal cual salieron de `imagen.convertir`, en el
        # orden en que los tiles los indexan. Van en un bloque global y no en
        # la tabla de mapas porque el cartel es uno solo por ROM; lo que sí es
        # del mapa es en qué tile y en qué paleta quedó, que va en el registro.
        #
        # La entrada 0 va también, en negro, y no porque se dibuje —el índice 0
        # de un sprite es transparente— sino para que la ROM suba las dieciséis
        # de una: el DMA arranca en la entrada de la paleta, no una más
        # adelante, y descontar uno acá es justo la cuenta que se escribe bien
        # de un lado y mal del otro.
        handle.write("\n; --- el cartel del ShowPicture ---\n")
        colores = ([(0, 0, 0)] + list(cartel["paleta"])) if cartel else [(0, 0, 0)]
        handle.write(bloque("imagen_cgram",
                            b"".join(cgram_word(c).to_bytes(2, "little")
                                     for c in colores)) + "\n")
        # Los productos del destello de pantalla: `d * nivel // 31` para d y
        # nivel de 0 a 31, en la fila del nivel. Es la cuenta de
        # `destellar_canal`, y la ROM la leía del multiplicador y el divisor
        # para cada una de las 96 entradas de sus tablas en cada cuadro
        # impar: ver `una_tabla_de_destello`.
        handle.write(bloque("prod31_tabla", bytes(
            d * n // 31 for n in range(32) for d in range(32))) + "\n")
        handle.write(animaciones_asm(animaciones or {}, mapas))
        # --- la pantalla de título ---
        #
        # Va entera en BG1, que en modo 3 tiene ocho bits por pixel: la imagen
        # direcciona CGRAM en directo y no hay que repartirla en paletas de
        # dieciséis, que es lo que un mapa sí tiene que hacer porque los
        # sprites necesitan las suyas. Acá no hay sprites.
        #
        # Los tiles se deduplican como los del mapa. La imagen tiene mucho negro
        # —la mitad de abajo, que es donde va el menú— así que de las 1024
        # celdas quedan menos de 500.
        handle.write("\n; --- la pantalla de título ---\n")
        if titulo is None:
            handle.write(bloque("titulo_tiles", b"\x00") + "\n")
            handle.write(bloque("titulo_cgram", b"\x00") + "\n")
            handle.write(bloque("titulo_celdas", b"\x00") + "\n")
            handle.write(bloque("titulo_menu_tiles", b"\x00") + "\n")
            handle.write(bloque("titulo_menu_celdas", b"\x00") + "\n")
        else:
            datos = bytearray()
            for celda in titulo["tiles"]:
                datos += pack_tile(celda, planes=8)
            handle.write(bloque("titulo_tiles", bytes(datos)) + "\n")
            # CGRAM entera de una vez: primero la paleta del menú, que ocupa
            # las de abajo porque un BG de 4 bits sólo alcanza ésas, y después
            # los colores de la imagen. Los índices de los tiles ya vienen
            # corridos desde `titulo.convertir`.
            colores = list(titulo["menu_paleta"])
            colores += [(0, 0, 0)] * (titulo_mod.MENU_CGRAM - len(colores))
            colores += list(titulo["paleta"])
            handle.write(bloque("titulo_cgram",
                                b"".join(cgram_word(c).to_bytes(2, "little")
                                         for c in colores)) + "\n")
            # El menú: un banco de tiles de 4 bits y un tilemap por opción
            # seleccionada. Mover el cursor es subir el otro tilemap, y por eso
            # van seguidos y del mismo tamaño: la ROM los indexa multiplicando.
            menu = bytearray()
            for celda in titulo["menu_tiles"]:
                menu += pack_tile(celda, planes=4)
            handle.write(bloque("titulo_menu_tiles", bytes(menu)) + "\n")
            plano = bytearray()
            for mapa_menu in titulo["menu_tilemaps"]:
                for indice in mapa_menu:
                    plano += entry(indice, False, False,
                                   PRIORITY_ABOVE).to_bytes(2, "little")
            handle.write(bloque("titulo_menu_celdas", bytes(plano)) + "\n")
            # El tilemap es de 32x32 y la imagen ocupa 32x28: las cuatro filas
            # que sobran quedan en el tile 0, que es negro entero. Sin
            # rellenarlas el PPU mostraría ahí lo que hubiera quedado en la
            # VRAM, y abajo de todo es justo donde va el menú.
            plano = bytearray()
            for fila in range(32):
                for col in range(32):
                    indice = (titulo["tilemap"][fila * 32 + col]
                              if fila < titulo_mod.FILAS else 0)
                    plano += entry(indice, False, False).to_bytes(2, "little")
            handle.write(bloque("titulo_celdas", bytes(plano)) + "\n")

        # La pantalla de ranuras, que **va en toda ROM** y no sólo en las que
        # llevan título: la abre el save point desde adentro del juego. Hasta
        # el 2026-09-10 salía sólo con `--con-titulo` y sin él quedaba un byte
        # de relleno con `RANURA_TILES` en cero; y un DMA de "cero bytes" son
        # 65536, así que abrirla desde una ROM sin título llenaba la VRAM de
        # basura. Es la "pantalla negra con basura arriba" que ESTADO.md
        # describía como un misterio del contexto del intérprete.
        #
        # Su banco de tiles es propio: comparte la dirección de VRAM con el del
        # menú del título, pero no los tiles, porque las dos pantallas se suben
        # enteras cada vez que se entra a una.
        handle.write("\n; --- la pantalla de ranuras ---\n")
        datos = bytearray()
        for celda in ranuras["tiles"]:
            datos += pack_tile(celda, planes=4)
        handle.write(bloque("ranura_tiles", bytes(datos)) + "\n")

        def celdas_asm(bloques):
            plano = bytearray()
            for celdas in bloques:
                for indice in celdas:
                    plano += entry(indice, False, False).to_bytes(2, "little")
            return bytes(plano)

        # Cada bloque de celdas va con etiqueta propia y se nombra por una
        # tabla de punteros, igual que los temas de música. Es más ROM que
        # calcular el desplazamiento con corrimientos —tres tablas de un byte
        # por bloque— y a cambio la ROM no tiene que multiplicar por 96 ni por
        # 192 en ningún lado. Esa multiplicación estaría escrita acá y allá,
        # que es exactamente la forma de error que este repo ya pagó tres
        # veces.
        #
        # El orden: primero las dos cabeceras —cargar y guardar— y después, por
        # ranura, las cuatro variantes como llena * 2 + cursor.
        bloques_ranura = []
        for modo, celdas in enumerate(ranuras["cabeceras"]):
            nombre = "ranura_cab_%d" % modo
            handle.write(bloque(nombre, celdas_asm([celdas])) + "\n")
            bloques_ranura.append(nombre)
        for numero, fila in enumerate(ranuras["filas"]):
            for llena in (0, 1):
                for cursor in (0, 1):
                    nombre = "ranura_%d_%d%d" % (numero, llena, cursor)
                    handle.write(
                        bloque(nombre, celdas_asm([fila[llena][cursor]]))
                        + "\n")
                    bloques_ranura.append(nombre)
        # Y detrás, por actor que pueda entrar al grupo, su cara y su nombre:
        # la ROM los escribe encima de la fila según lo que la partida guardó.
        # Las celdas de las caras llevan la paleta en sus tres bits, que acá
        # sí se usan: es BG2 a 4bpp.
        bloque_de_cara, bloque_de_nombre = {}, {}
        for actor in sorted(ranuras["caras"]):
            nombre = "ranura_cara_%d" % actor
            handle.write(bloque(nombre, celdas_asm([ranuras["caras"][actor]]))
                         + "\n")
            bloque_de_cara[actor] = len(bloques_ranura)
            bloques_ranura.append(nombre)
        for actor in sorted(ranuras["nombres"]):
            nombre = "ranura_nombre_%d" % actor
            handle.write(bloque(nombre,
                                celdas_asm([ranuras["nombres"][actor]]))
                         + "\n")
            bloque_de_nombre[actor] = len(bloques_ranura)
            bloques_ranura.append(nombre)
        # Y los del menú de pausa, que viven en el mismo banco de tiles: cada
        # orden en sus dos variantes —la 1 es deshabilitada, en la paleta de
        # lo gris—, la moneda, y un bloque por actor con la cara adentro. El
        # cursor y las cifras del oro no van como bloques: son dos celdas cada
        # uno y la ROM las escribe palabra por palabra, ver `menu_cifra_celdas`.
        menu = ranuras["menu"]
        bloque_menu_opcion = len(bloques_ranura)
        for orden, variantes in enumerate(menu["opciones"]):
            for deshabilitada, celdas in enumerate(variantes):
                nombre = "menu_opcion_%d_%d" % (orden, deshabilitada)
                handle.write(bloque(nombre, celdas_asm([celdas])) + "\n")
                bloques_ranura.append(nombre)
        bloque_menu_moneda = len(bloques_ranura)
        handle.write(bloque("menu_moneda", celdas_asm([menu["moneda"]]))
                     + "\n")
        bloques_ranura.append("menu_moneda")
        bloque_de_actor = {}
        for actor in sorted(menu["actores"]):
            nombre = "menu_actor_%d" % actor
            handle.write(bloque(nombre, celdas_asm([menu["actores"][actor]]))
                         + "\n")
            bloque_de_actor[actor] = len(bloques_ranura)
            bloques_ranura.append(nombre)
        # Y la pantalla de ítems, que tiene banco propio: la fuente de a una
        # letra por celda, sus dos paletas, y el texto de cada ítem que la ROM
        # conoce —nombre y dos renglones de descripción—, en ASCII.
        datos = bytearray()
        for celda in ranuras["items_tiles"]:
            datos += pack_tile(celda, planes=4)
        handle.write(bloque("items_tiles", bytes(datos)) + "\n")
        handle.write(bloque("items_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little")
            for paleta in ranuras["items_paletas"]
            for c in list(paleta) + [(0, 0, 0)] * (titulo_mod.MENU_CGRAM
                                                   - len(paleta)))) + "\n")
        item_textos, item_textos_ofs = bytearray(), []
        # Textos muertos delante de todos los demás, para que los índices de
        # la batalla pasen de 255 en un cartucho de un mapa. Lo que dice
        # `--relleno-de-textos`: reproducirlo de verdad pide los cincuenta y
        # siete ítems de `demo-ciudad`, o sea sus veintinueve mapas y dos
        # minutos y medio de conversor por caso. **No cambia un pixel**: son
        # textos de largo cero que nadie dibuja, y el índice de un texto no lo
        # modela la referencia —ella escribe caracteres—, así que el flag es de
        # un solo lado a propósito.
        for _ in range(ranuras.get("relleno_textos") or 0):
            item_textos_ofs.append((0, 0))

        def texto_nuevo(texto):
            texto = titulo_mod.texto_de_item(texto, 255)
            item_textos_ofs.append((len(item_textos), len(texto)))
            item_textos.extend(texto.encode("ascii"))
            return len(item_textos_ofs) - 1

        for numero in ranuras["items"]:
            item = ranuras["items_db"][numero]
            for texto in ([titulo_mod.texto_de_item(
                    item.name, titulo_mod.ITEM_NOMBRE_ANCHO)]
                    + titulo_mod.partir_descripcion(item.description)):
                texto_nuevo(texto)
        # Y los fijos, detrás: los parámetros y las ranuras del equipo, y el
        # nombre de cada actor que puede entrar al grupo. Ver pantallas.py.
        P = pantallas_mod
        B = batalla_mod
        db = ranuras["db"]
        texto_param = [texto_nuevo(t[:P.EQ_PARAM_VALOR - 1])
                       for t in db.term_params]
        texto_ranura = [texto_nuevo(t[:P.EQ_RANURA_NOMBRE_COL
                                      - P.EQ_RANURA_TERM_COL - 1])
                        for t in db.term_equipo]
        texto_actor = {a: texto_nuevo(db.actors[a].name)
                       for a in ranuras["actores"]}
        # Los de la tienda: los once mensajes de cada uno de los tres juegos,
        # de a dos renglones —`partir_descripcion`, como en pantallas.py—, y
        # "Owned Items", "Equipped Items" y la moneda.
        texto_tienda = None
        for juego in range(3):
            term = P.terminos_tienda(db, juego)
            for nombre in P.TI_TERMINOS:
                for renglon in titulo_mod.partir_descripcion(term[nombre]):
                    t = texto_nuevo(renglon)
                    if texto_tienda is None:
                        texto_tienda = t
        texto_tengo = texto_nuevo(P.lcf_termino(db, P.TI_TERMINO_TENGO))
        texto_llevo = texto_nuevo(P.lcf_termino(db, P.TI_TERMINO_LLEVO))
        texto_moneda = texto_nuevo(db.term_gold)
        # Y los de la batalla: los quince términos del LDB que la pantalla usa
        # —en el orden de `pantallas.BA_TERMINOS`, que es el que la ROM
        # indexa— y el nombre de cada enemigo que alguna tropa del cartucho
        # traiga. Las tres órdenes van **ya recortadas**, por
        # `pantallas.texto_de_orden`: el LDB las trae con espacios adelante y
        # eso correría el texto de su columna.
        term_batalla = P.terminos_batalla(db)
        texto_batalla = None
        for nombre, _chunk in P.BA_TERMINOS:
            texto = term_batalla[nombre]
            if nombre in ("atacar", "defender", "huir"):
                texto = P.texto_de_orden(texto)
            t = texto_nuevo(texto)
            if texto_batalla is None:
                texto_batalla = t
        enemigos_rom = sorted({e for numero in tropas
                               if numero in db.troops
                               for e in db.troops[numero].members})
        texto_enemigo = {e: texto_nuevo(titulo_mod.texto_de_item(
            db.enemies[e].name, P.BA_NOMBRE_ANCHO)) for e in enemigos_rom}
        # Y los de las habilidades: las que sabe algún actor que puede entrar
        # al grupo, **a su nivel del LDB** —ver `batalla.habilidades_de`—,
        # ordenadas por número, que es el orden en que el menú las pone. Con el
        # grupo de la intro son siete: 129, 130, 131, 143, 144, 146 y 150.
        habilidades_rom = sorted({h for a in ranuras["actores"]
                                  for h in B.habilidades_de(db, a)})
        texto_hab = {h: texto_nuevo(titulo_mod.texto_de_item(
            db.skills[h].name, P.BA_HAB_NOMBRE_ANCHO))
            for h in habilidades_rom}
        texto_hab_desc = {h: texto_nuevo(titulo_mod.texto_de_item(
            db.skills[h].description, P.BA_HAB_DESC_ANCHO))
            for h in habilidades_rom}
        # Los dos renglones que RM2k dice al usarla: `using_message1` va detrás
        # del nombre del que la usa y `using_message2` solo, en el renglón de
        # abajo. `GetSkillFirstStartMessage2k` y su hermana.
        texto_hab_msg1 = {h: texto_nuevo(db.skills[h].using_message1)
                          for h in habilidades_rom}
        texto_hab_msg2 = {h: texto_nuevo(db.skills[h].using_message2)
                          for h in habilidades_rom}
        # Y cómo se llama la orden de cada actor: `Game_Actor::GetSkillName`,
        # o sea su `skill_name` —"AgentTrain", "Telepathy", "Slicing"— y no el
        # `command_skill` del LDB. Va recortada como las otras cuatro órdenes.
        texto_hab_orden = {a: texto_nuevo(P.texto_de_orden(
            B.nombre_de_orden_habilidad(db, a))) for a in ranuras["actores"]}
        handle.write(bloque("item_textos", bytes(item_textos) or b"\x00")
                     + "\n")
        if len(bloques_ranura) > 255:
            raise SystemExit("la pantalla de ranuras tiene %d bloques y las "
                             "tablas que los nombran son de un byte"
                             % len(bloques_ranura))
        # Las tablas que los nombran **no van acá**: la ROM las lee con
        # `lda ranura_bloque_lo, x`, que direcciona el banco de datos, así que
        # tienen que vivir en el banco 0 junto con el código. Se emiten más
        # abajo, en el segmento TABLAS.
        #
        # La paleta va rellena hasta las TITULO_MENU_CGRAM entradas, que es lo
        # que la ROM sube de una vez: si el texto usa menos colores, el DMA
        # leería lo que siga en el cartucho.
        colores = []
        for paleta in ranuras["paletas"]:
            paleta = list(paleta)
            colores += paleta + [(0, 0, 0)] * (titulo_mod.MENU_CGRAM
                                               - len(paleta))
        handle.write(bloque("ranura_cgram",
                            b"".join(cgram_word(c).to_bytes(2, "little")
                                     for c in colores)) + "\n")

        handle.write('\n.segment "TABLAS"\n')
        # Los bloques de celdas de la pantalla de ranuras se nombran por
        # punteros, y las tres tablas van en el banco 0 porque la ROM las lee
        # con `lda ranura_bloque_lo, x`. Lo mismo `ranura_vram`, que dice a qué
        # dirección del tilemap va cada fila: la cuenta sale de la misma
        # geometría que dibujó el texto y por eso vive en un solo lado.
        for campo, prefijo in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write("ranura_bloque_%s:\n    .byte %s\n"
                         % (campo, ", ".join(prefijo + e
                                             for e in bloques_ranura)))
        fila_de = [RANURA_MAP + (titulo_mod.RANURA_Y
                                 + n * titulo_mod.RANURA_SALTO)
                   // titulo_mod.CELL * 32 for n in range(RANURAS)]
        handle.write("ranura_vram:\n    .word %s\n" % ", ".join(
            str(v) for v in fila_de))
        # A dónde van las caras —de a cuatro entradas por ranura, para que el
        # índice sea la ranura por cuatro más el lugar, sin multiplicar por
        # tres— y el nombre del líder.
        handle.write("ranura_cara_vram:\n    .word %s\n" % ", ".join(
            str(fila_de[n] + titulo_mod.CARA_COL
                + lugar * titulo_mod.CARA_PASO if lugar < titulo_mod.CARAS_MAX
                else 0)
            for n in range(RANURAS) for lugar in range(4)))
        handle.write("ranura_nombre_vram:\n    .word %s\n" % ", ".join(
            str(fila_de[n] + titulo_mod.NOMBRE_FILA * 32
                + titulo_mod.NOMBRE_COL) for n in range(RANURAS)))
        actores_n = max(list(bloque_de_cara) + list(bloque_de_nombre)
                        + [-1]) + 1
        for nombre, tabla in (("ranura_cara_bloque", bloque_de_cara),
                              ("ranura_nombre_bloque", bloque_de_nombre)):
            handle.write("%s:\n    .byte %s\n" % (nombre, ", ".join(
                str(tabla.get(actor, 0xFF)) for actor in range(actores_n))
                or "$FF"))
        # El menú de pausa: sus bloques, y a dónde va cada cosa en el tilemap,
        # en palabras. La geometría es la de `titulo.py` y sale de ahí.
        T = titulo_mod

        def celda_vram(fila, col):
            return RANURA_MAP + fila * 32 + col

        filas_opcion = [(T.MENU_OPC_Y + n * T.MENU_OPC_SALTO) // T.CELL
                        for n in range(T.MENU_OPCIONES)]
        menu_actores_n = max(list(bloque_de_actor) + [-1]) + 1
        handle.write(
            "MENU_OPCIONES     = %d\n"
            "MENU_GUARDAR      = %d\n"
            "MENU_BLQ_OPCION   = %d\n"
            "MENU_BLQ_MONEDA   = %d\n"
            "MENU_OPC_COLS     = %d\n"
            "MENU_MONEDA_COLS  = %d\n"
            "MENU_MONEDA_VRAM  = %d\n"
            "MENU_ACTOR_COLS   = %d\n"
            "MENU_ACTOR_FILAS  = %d\n"
            "MENU_FILAS_GRUPO  = %d\n"
            "MENU_ACTORES_N    = %d\n"
            "OBJETIVO_CURSOR_DESPL = %d\n"
            "MENU_HP_CIFRAS    = %d\n"
            "MENU_HP_DESPL     = %d\n"
            % (T.MENU_OPCIONES, T.MENU_GUARDAR, bloque_menu_opcion,
               bloque_menu_moneda, T.MENU_OPC_COLS, T.MENU_MONEDA_COLS,
               celda_vram(T.MENU_ORO_Y // T.CELL, T.MENU_MONEDA_COL),
               T.MENU_ACTOR_COLS, T.MENU_ACTOR_FILAS, T.MENU_FILAS_GRUPO,
               menu_actores_n,
               T.OBJETIVO_CURSOR_FILA * 32
               + T.OBJETIVO_CURSOR_COL - T.MENU_ACTOR_COL,
               # Y a cuántas celdas de la primera del bloque del actor cae la
               # de las centenas de sus HP, que es lo que `menu_hp_escribir`
               # le suma a `menu_fila_vram`.
               T.MENU_HP_CIFRAS,
               T.MENU_HP_FILA * 32 + T.MENU_HP_COL - T.MENU_ACTOR_COL))
        # Qué órdenes hacen algo: 1 sí, 0 no. La de guardar además mira el
        # permiso, en la ROM.
        handle.write("menu_hecha:\n    .byte %s\n" % ", ".join(
            "1" if n in T.MENU_HECHAS else "0"
            for n in range(T.MENU_OPCIONES)))
        handle.write("menu_opcion_vram:\n    .word %s\n" % ", ".join(
            str(celda_vram(f, T.MENU_OPC_COL)) for f in filas_opcion))
        handle.write("menu_cursor_vram:\n    .word %s\n" % ", ".join(
            str(celda_vram(f, T.MENU_CURSOR_COL)) for f in filas_opcion))
        handle.write("menu_fila_vram:\n    .word %s\n" % ", ".join(
            str(celda_vram(r * T.MENU_ACTOR_FILAS, T.MENU_ACTOR_COL))
            for r in range(T.MENU_FILAS_GRUPO)))
        # Las dos celdas de cada cifra y del cursor, arriba y abajo: la ROM
        # las escribe de a una palabra.
        handle.write("menu_cifra_celdas:\n    .word %s\n" % ", ".join(
            "$%04X" % entry(c, False, False) for cifra in menu["cifras"]
            for c in cifra))
        handle.write("menu_cursor_celdas:\n    .word %s\n" % ", ".join(
            "$%04X" % entry(c, False, False) for c in menu["cursor"]))
        handle.write("menu_actor_bloque:\n    .byte %s\n" % (", ".join(
            str(bloque_de_actor.get(a, 0xFF)) for a in range(menu_actores_n))
            or "$FF"))
        # La pantalla de ítems. `item_k` va del número de RM2k a su lugar en
        # las tablas de la ROM, $FF si esta ROM no lo conoce; lo demás es por
        # lugar. `item_uso`: bit 0 si va en blanco y A hace algo, bit 1 si
        # usarlo gasta uno —los de switch con usos—, bit 2 si abre la elección
        # de actor —las medicinas—, bit 3 si es un arma a dos manos. Los textos
        # van de a tres por ítem —el nombre y los
        # dos renglones de la descripción—: el texto `t` es el `3k + campo`.
        items = ranuras["items"]
        db_items = ranuras["items_db"]
        if len(items) > 255:
            raise SystemExit("%d ítems no entran en las tablas de un byte"
                             % len(items))
        k_de = {numero: k for k, numero in enumerate(items)}
        handle.write(
            "ITEMS_ROM         = %d\n"
            "ITEMS_TILES       = %d\n"
            "ITEMS_CGRAM_N     = %d\n"
            "ITEM_FILAS        = %d\n"
            "ITEM_CURSOR_COL   = %d\n"
            "ITEM_NOMBRE_COL   = %d\n"
            "ITEM_DOS_PUNTOS_COL = %d\n"
            "ITEM_CIFRAS_COL   = %d\n"
            "ITEM_DESC_VRAM    = %d\n"
            "ITEM_DESC_COL     = %d\n"
            "ITEM_PRIMER_CARACTER = %d\n"
            "ITEM_GLIFOS_GRIS  = %d\n"
            % (len(items), len(ranuras["items_tiles"]),
               len(ranuras["items_paletas"]) * titulo_mod.MENU_CGRAM,
               T.ITEM_FILAS, T.ITEM_CURSOR_COL, T.ITEM_NOMBRE_COL,
               T.ITEM_DOS_PUNTOS_COL, T.ITEM_CIFRAS_COL,
               celda_vram(T.ITEM_DESC_Y // T.CELL, T.ITEM_DESC_COL),
               T.ITEM_DESC_COL,
               T.ITEM_PRIMER_CARACTER, T.ITEM_CARACTERES * 4))

        def bytes_asm(etiqueta, valores, formato="%d", declarar=False):
            if declarar:
                handle.write(".bloque %d\n" % max(1, len(valores)))
            handle.write("%s:\n    .byte %s\n" % (etiqueta, ", ".join(
                formato % v for v in valores) or "$FF"))

        def words_asm(etiqueta, valores, formato="%d", declarar=False):
            if declarar:
                handle.write(".bloque %d\n" % max(2, 2 * len(valores)))
            handle.write("%s:\n    .word %s\n" % (etiqueta, ", ".join(
                formato % v for v in valores) or "0"))

        # `item_k` va fuera del banco 0 —se lee con `lda f:item_k, x`—: el
        # banco del código se llenó con el paquete de audio.
        handle.write('.segment "RODATA"\n')
        bytes_asm("item_k", [k_de.get(n, 0xFF)
                             for n in range(eventos.ITEMS_N)],
                  declarar=True)
        handle.write('.segment "TABLAS"\n')
        words_asm("item_id", items)
        bytes_asm("item_uso", [
            (1 if T.item_usable(db_items[n]) else 0)
            | (2 if T.item_usable(db_items[n])
               and not T.item_pide_actor(db_items[n])
               and db_items[n].uses else 0)
            | (4 if T.item_pide_actor(db_items[n]) else 0)
            | (8 if db_items[n].two_handed else 0)
            for n in items])
        # `item_switch` va fuera del banco 0 —se lee con `lda f:item_switch, x`,
        # una sola vez por ítem usado— porque los encuentros al azar lo pasaron
        # por 34 bytes el 2026-09-13. Son 124: la tabla más grande de las que
        # se leen con X y no están en ningún lazo por cuadro.
        handle.write('.segment "RODATA"\n')
        words_asm("item_switch", [db_items[n].switch_id for n in items])
        handle.write('.segment "TABLAS"\n')
        # Lo que cada ítem hace en una pelea: si entra en la lista que se
        # ofrece y cuánto cura. La regla de cuáles entran es
        # `batalla.item_usable_en_batalla`, o sea `Game_Party::IsItemUsable`
        # con la pelea abierta más lo que este port sabe hacer; la cuenta de
        # cuánto cura es `Game_BattleAlgorithm::Item::vExecute`.
        # **Fuera del banco 0**, como `item_k` y por lo mismo: con los mapas de
        # `demo-ciudad` el área de código quedó en 32775 de 32704 al ponerlas
        # acá. La pelea las lee con `lda f:item_batalla, x`.
        handle.write('.segment "RODATA"\n')
        bytes_asm("item_batalla", [
            1 if B.item_usable_en_batalla(db_items[n]) else 0 for n in items],
            declarar=True)
        bytes_asm("item_cura_rate", [db_items[n].recover_hp_rate
                                     for n in items], declarar=True)
        words_asm("item_cura_hp", [min(db_items[n].recover_hp, 0xFFFF)
                                   for n in items], declarar=True)
        handle.write('.segment "TABLAS"\n')
        # Las cuatro de los textos van **fuera del banco 0**, como `item_k` y
        # por lo mismo: ahí no entran. Con los diez mapas de `demo-ciudad` el
        # área de código quedaba en 32622 de 32704 —ochenta y dos bytes
        # libres— y el cartel del `ShowPicture` no entraba. Se leen con
        # `lda f:item_txt_lo, x`, que cuesta un byte y un ciclo por lectura en
        # trece lugares, ninguno adentro de un lazo por cuadro.
        handle.write('.segment "RODATA"\n')
        for campo, prefijo in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write(".bloque %d\n" % max(1, len(item_textos_ofs)))
            handle.write("item_txt_%s:\n    .byte %s\n" % (campo, ", ".join(
                "%s(item_textos + %d)" % (prefijo, ofs)
                for ofs, _ in item_textos_ofs) or "0"))
        bytes_asm("item_txt_n", [n for _, n in item_textos_ofs],
                  declarar=True)
        handle.write('.segment "TABLAS"\n')
        words_asm("item_fila_vram", [
            celda_vram(T.ITEM_LISTA_Y // T.CELL + 2 * f, 0)
            for f in range(T.ITEM_FILAS)])
        # Las dos celdas de cada carácter, arriba y abajo: primero los 95 en
        # blanco y después en gris. El carácter `c` en la variante `g` está en
        # `g * ITEM_GLIFOS_GRIS + (c - ITEM_PRIMER_CARACTER) * 4`.
        # --- el equipo ---
        # Por ítem conocido: su tipo, lo que suma —ataque, defensa, espíritu,
        # agilidad, con signo— y quién puede ponérselo, un bit por actor. Por
        # actor, del 0 al último del LDB: sus parámetros del nivel y su equipo
        # inicial, que la ROM copia a `FAR_EQUIPO` en el reset. Y dónde va
        # cada cosa en el búfer de la pantalla, en bytes: fila * 64 + col * 2.
        actores_n = max(db.actors) + 1

        def pos(fila, col):
            return fila * 64 + col * 2

        bytes_asm("item_tipo", [db_items[n].type for n in items])
        handle.write('.segment "RODATA"\n')     # ídem: ver `item_txt_lo`
        words_asm("item_puntos", [p & 0xFFFF for n in items
                                  for p in db_items[n].puntos],
                  declarar=True)
        # `item_actores` va también fuera del banco 0 —se lee con
        # `lda f:item_actores, x`—: son 496 bytes, los más gordos que le
        # quedaban a `TABLAS`, y el banco 0 se pasó. No es una previsión: el
        # 2026-09-13 `just demo demo-ciudad` cortaba con "el área no
        # entra: 32719 bytes en 32704" y ningún caso de la tanda lo veía.
        # Se lee una vez por ítem al armar la lista de la pantalla de equipo,
        # así que el ciclo de más del direccionamiento largo no se nota.
        bytes_asm("item_actores", [
            sum(1 << b for b in range(8)
                if 8 * byte + b + 1 < actores_n
                and db_items[n].equipable_por(8 * byte + b + 1))
            for n in items for byte in range(8)], declarar=True)
        # `actor_params` va fuera del banco 0 —se lee con
        # `lda f:actor_params, x`, una sola vez por pantalla de equipo— por lo
        # mismo que `item_k`: son 488 bytes y el banco del código se llenó, y
        # esta vez con el dibujo de las animaciones de batalla.
        handle.write('.segment "RODATA"\n')
        words_asm("actor_params", [
            (titulo_mod.parametro_de(db.actors[a], k)
             if a in db.actors else 0) & 0xFFFF
            for a in range(actores_n)
            for k in ("attack", "defense", "spirit", "agility")],
            declarar=True)
        handle.write('.segment "TABLAS"\n')
        handle.write('\n.segment "RODATA"\n')
        handle.write(".bloque %d\n" % (2 * actores_n * P.RANURAS_EQUIPO))
        handle.write("equipo_inicial:\n    .word %s\n" % ", ".join(
            str(db.actors[a].initial_equipment[r] if a in db.actors else 0)
            for a in range(actores_n) for r in range(P.RANURAS_EQUIPO)))
        # Y qué habilidades sabe cada actor, para la rama 4 de
        # `ConditionalBranch`: dónde arranca su lista y cuántas tiene, y las
        # listas pegadas una detrás de otra. Salen de `batalla.aprendidas_de`,
        # que es de donde las saca también la referencia —ver
        # `eventos.indexar_actores`—, así que los dos lados no pueden contestar
        # distinto.
        #
        # Va aparte de `actor_hab`, que es la lista del **menú de la pelea**:
        # ésa lleva sólo las que este port sabe ejecutar y sólo de los actores
        # que pueden entrar al grupo, y `IsSkillLearned` no filtra ninguna de
        # las dos cosas. Con los 60 actores del LDB son 81 habilidades
        # aprendidas, o sea 162 bytes más los 122 del índice.
        sabe_hab, sabe_hab_ini, sabe_hab_n = [], [], []
        for a in range(actores_n):
            suyas = B.aprendidas_de(db, a) if a in db.actors else []
            sabe_hab_ini.append(len(sabe_hab))
            sabe_hab_n.append(len(suyas))
            sabe_hab += suyas
        if len(sabe_hab) > 255:
            raise SystemExit("las habilidades aprendidas del LDB son %d y "
                             "`sabe_hab_ini` es de un byte" % len(sabe_hab))
        handle.write('.segment "RODATA"\n')
        words_asm("sabe_hab", sabe_hab or [0], declarar=True)
        bytes_asm("sabe_hab_ini", sabe_hab_ini, declarar=True)
        bytes_asm("sabe_hab_n", sabe_hab_n, declarar=True)
        handle.write('\n.segment "TABLAS"\n')
        words_asm("actor_txt", [texto_actor.get(a, 0xFFFF)
                                for a in range(actores_n)], "$%04X")
        words_asm("eq_param_pos", [pos(f, c) for f, c in P.EQ_PARAMS])
        words_asm("item_precio", [db_items[n].price for n in items])
        handle.write(
            "TI_TEXTO          = %d\n"
            "TI_TEXTO_TENGO    = %d\n"
            "TI_TEXTO_LLEVO    = %d\n"
            "TI_TEXTO_MONEDA   = %d\n"
            "TI_SEGUNDO        = %d\n"
            "TI_ORDEN_POS0     = %d\n"
            "TI_ORO_POS        = %d\n"
            "TI_TENGO_POS      = %d\n"
            "TI_TENGO_NUM      = %d\n"
            "TI_LLEVO_POS      = %d\n"
            "TI_LLEVO_NUM      = %d\n"
            "TI_LISTA_POS0     = %d\n"
            "TI_LISTA_FILAS    = %d\n"
            "TI_PRECIO         = %d\n"
            "TI_CUANTOS        = %d\n"
            "TI_TOTAL_POS      = %d\n"
            % (texto_tienda, texto_tengo, texto_llevo, texto_moneda,
               P.TI_SEGUNDO, pos(P.TI_ORDEN_FILA0, 0),
               pos(P.TI_ORO_FILA, P.TI_ORO_COL),
               pos(P.TI_TENGO_FILA, P.TI_ESTADO_COL),
               pos(P.TI_TENGO_FILA, P.TI_ESTADO_NUM),
               pos(P.TI_LLEVO_FILA, P.TI_ESTADO_COL),
               pos(P.TI_LLEVO_FILA, P.TI_ESTADO_NUM),
               pos(P.TI_LISTA_FILA0, 0), P.TI_LISTA_FILAS,
               P.TI_PRECIO_COL * 2, P.TI_CUANTOS_COL * 2,
               pos(P.TI_TOTAL_FILA, P.TI_ORO_COL)))
        handle.write(
            "ACTORES_N         = %d\n"
            "RANURAS_EQUIPO    = %d\n"
            "EQ_TEXTO_PARAM    = %d\n"
            "EQ_TEXTO_RANURA   = %d\n"
            "EQ_ACTOR_POS      = %d\n"
            "EQ_PARAM_VALOR    = %d\n"
            "EQ_PARAM_FLECHA   = %d\n"
            "EQ_RANURA_POS0    = %d\n"
            "EQ_RANURA_TERM    = %d\n"
            "EQ_RANURA_NOMBRE  = %d\n"
            "EQ_RANURA_ANCHO   = %d\n"
            "EQ_LISTA_POS0     = %d\n"
            "EQ_LISTA_FILAS    = %d\n"
            "EQ_CURSOR         = %d\n"
            "PANT_NOMBRE       = %d\n"
            "PANT_DOS_PUNTOS   = %d\n"
            "PANT_DESC_POS     = %d\n"
            % (actores_n, P.RANURAS_EQUIPO, texto_param[0], texto_ranura[0],
               pos(P.EQ_ACTOR_FILA, 1), P.EQ_PARAM_VALOR * 2,
               P.EQ_PARAM_FLECHA * 2, pos(P.EQ_RANURA_FILA0, 0),
               P.EQ_RANURA_TERM_COL * 2, P.EQ_RANURA_NOMBRE_COL * 2,
               P.EQ_RANURA_NOMBRE_ANCHO, pos(P.EQ_LISTA_FILA0, 0),
               P.EQ_LISTA_FILAS, P.EQ_CURSOR_COL * 2,
               T.ITEM_NOMBRE_COL * 2, T.ITEM_DOS_PUNTOS_COL * 2,
               pos(T.ITEM_DESC_Y // T.CELL, T.ITEM_DESC_COL)))
        # --- la batalla ---
        # Los HP máximos de cada actor a su nivel, por número de actor. Van
        # aparte de `actor_params`, que lleva los cuatro que la pantalla de
        # equipo muestra; los HP no los toca el equipo, como en RM2k.
        handle.write('.segment "RODATA"\n')
        words_asm("actor_hpmax", [
            (titulo_mod.parametro_de(db.actors[a], "maxhp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(actores_n)])
        # Y los SP, que son estado desde el 2026-09-13 por lo mismo que los HP:
        # las habilidades los gastan. Ver `hp_inicial_poner` en main.s.
        words_asm("actor_spmax", [
            (titulo_mod.parametro_de(db.actors[a], "maxsp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(actores_n)])
        # --- las habilidades ---
        #
        # Una fila por habilidad que el cartucho lleva, en el orden de
        # `habilidades_rom`, que es por número de RM2k. Los campos son los de
        # `lcf.Skill` y las cuentas que los usan están en `batalla.py`:
        # `efecto_habilidad` es `Algo::CalcSkillEffect` y `costo_de` es
        # `CalcSkillCost`.
        #
        # Van **fuera del banco 0** y declaradas con `.bloque`, como todo lo
        # que la pelea lee con `lda f:`: el banco del código está lleno, y una
        # tabla partida entre dos bancos se leería mal desde la mitad.
        lugar_hab = {h: k for k, h in enumerate(habilidades_rom)}
        # Que todas las que llegan acá sean de las que la pelea sabe ofrecer lo
        # garantiza `batalla.habilidad_usable`, que es el filtro que
        # `habilidades_de` aplica de los dos lados. Se vuelve a comprobar por
        # si alguna vez se emitieran desde otro lado: un alcance de a muchos o
        # un costo de tres cifras se dibujarían mal en silencio.
        for h in habilidades_rom:
            if not B.habilidad_usable(db.skills[h]):
                raise SystemExit(
                    "la habilidad %d —tipo %d, alcance %d, %d SP— no es de las "
                    "que esta pelea sabe ofrecer" % (h, db.skills[h].type,
                                                     db.skills[h].scope,
                                                     db.skills[h].sp_cost))
        words_asm("hab_id", habilidades_rom, declarar=True)
        words_asm("hab_txt", [texto_hab[h] for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_desc", [texto_hab_desc[h] for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_msg1", [texto_hab_msg1[h] for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_msg2", [texto_hab_msg2[h] for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_power", [db.skills[h].power for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_switch", [db.skills[h].switch_id
                                 for h in habilidades_rom], declarar=True)
        bytes_asm("hab_sp", [db.skills[h].sp_cost for h in habilidades_rom],
                  declarar=True)
        # El tipo: 0 es `normal` y 3 es `switch`, que es la que prende un
        # switch y no hace nada más. Ver `Skill::vExecute`.
        bytes_asm("hab_tipo", [db.skills[h].type for h in habilidades_rom],
                  declarar=True)
        bytes_asm("hab_fis", [db.skills[h].physical_rate
                              for h in habilidades_rom], declarar=True)
        bytes_asm("hab_mag", [db.skills[h].magical_rate
                              for h in habilidades_rom], declarar=True)
        bytes_asm("hab_var", [db.skills[h].variance
                              for h in habilidades_rom], declarar=True)
        bytes_asm("hab_hit", [db.skills[h].hit for h in habilidades_rom],
                  declarar=True)
        # Qué toca, un bit por cosa, en el orden en que `Skill::vExecute` las
        # mira —que es el orden en que consume azar y por eso importa—: HP, SP,
        # ataque, defensa, espíritu y agilidad. El bit 6 dice si apunta a
        # enemigos —`Algo::SkillTargetsEnemies`— y el 7 si ignora la defensa.
        bytes_asm("hab_afecta", [
            (1 if db.skills[h].affect_hp else 0)
            | (2 if db.skills[h].affect_sp else 0)
            | (4 if db.skills[h].affect_attack else 0)
            | (8 if db.skills[h].affect_defense else 0)
            | (16 if db.skills[h].affect_spirit else 0)
            | (32 if db.skills[h].affect_agility else 0)
            | (64 if db.skills[h].apunta_a_enemigos else 0)
            | (128 if db.skills[h].ignore_defense else 0)
            for h in habilidades_rom], "$%02X", declarar=True)
        # Y por actor: dónde arranca su lista en `actor_hab`, cuántas tiene, y
        # cómo se llama su orden en el menú. Un actor que no puede entrar al
        # grupo no tiene ninguna: la lista se arma con `ranuras["actores"]`.
        actor_hab, actor_hab_ini, actor_hab_n = [], [], []
        for a in range(actores_n):
            suyas = (B.habilidades_de(db, a)
                     if a in ranuras["actores"] else [])
            actor_hab_ini.append(len(actor_hab))
            actor_hab_n.append(len(suyas))
            actor_hab += [lugar_hab[h] for h in suyas]
        if len(actor_hab) > 255 or len(habilidades_rom) > 255:
            raise SystemExit("las habilidades del cartucho no entran en las "
                             "tablas de un byte: %d habilidades, %d "
                             "aprendidas" % (len(habilidades_rom),
                                             len(actor_hab)))
        bytes_asm("actor_hab", actor_hab, declarar=True)
        bytes_asm("actor_hab_ini", actor_hab_ini, declarar=True)
        bytes_asm("actor_hab_n", actor_hab_n, declarar=True)
        words_asm("actor_hab_txt", [texto_hab_orden.get(a, 0xFFFF)
                                    for a in range(actores_n)], "$%04X",
                  declarar=True)
        # Las tropas que alguna pelea del cartucho pide, y los enemigos que las
        # forman. El bytecode lleva el **número de RM2k** de la tropa, así que
        # `tropa_id` es lo que la ROM busca; que la lista sea sólo la de las
        # tropas usadas no cambia un byte de ninguna página. Ver
        # `eventos.Tropas`.
        usadas = [n for n in tropas if n in db.troops]
        lugar_de = {e: k for k, e in enumerate(enemigos_rom)}
        miembros, inicios = [], []
        for numero in usadas:
            lista = db.troops[numero].members[:B.ENEMIGOS_MAX]
            inicios.append(len(miembros))
            miembros += [lugar_de[e] for e in lista]
        if len(miembros) > 255 or len(usadas) > 255:
            raise SystemExit("las tropas del cartucho no entran en las tablas "
                             "de un byte: %d tropas, %d miembros"
                             % (len(usadas), len(miembros)))
        words_asm("tropa_id", usadas)
        bytes_asm("tropa_ini", inicios)
        bytes_asm("tropa_n", [len(db.troops[n].members[:B.ENEMIGOS_MAX])
                              for n in usadas])
        bytes_asm("tropa_miembro", miembros)
        # Y los encuentros al azar, que también hablan de tropas por su número
        # de RM2k. Van acá afuera del banco 0 —se leen con `lda f:tabla, x`—
        # porque allá quedaban ochenta y cinco bytes y esto son unos doscientos.
        # Ver `encuentros_de_la_rom` y la sección de `main.s`.
        enc = encuentros or {"por_mapa": [0xFF] * len(mapas), "registros": [],
                             "zonas": [], "tropas": []}
        bytes_asm("enc_mapa", enc["por_mapa"], declarar=True)
        words_asm("enc_base", [r["base"] for r in enc["registros"]])
        umbrales = []
        for r in enc["registros"]:
            # Siete umbrales y uno de relleno: con ocho el índice del registro
            # es un corrimiento y no una multiplicación. Ver ENC_STRIDE.
            umbrales += list(r["umbrales"]) + [0xFF]
        bytes_asm("enc_umbral_n", umbrales)
        bytes_asm("enc_zona_ini", [r["zona_ini"] for r in enc["registros"]])
        bytes_asm("enc_zona_n", [r["zona_n"] for r in enc["registros"]])
        for k, etiqueta in enumerate(("enc_izq", "enc_arr", "enc_der",
                                      "enc_aba")):
            words_asm(etiqueta, [z["rect"][k] for z in enc["zonas"]])
        bytes_asm("enc_tropa_ini", [z["tropa_ini"] for z in enc["zonas"]])
        bytes_asm("enc_tropa_n", [z["tropa_n"] for z in enc["zonas"]])
        words_asm("enc_tropa", enc["tropas"])
        words_asm("enemigo_hp", [db.enemies[e].max_hp for e in enemigos_rom])
        words_asm("enemigo_atk", [db.enemies[e].attack for e in enemigos_rom])
        words_asm("enemigo_def", [db.enemies[e].defense for e in enemigos_rom])
        words_asm("enemigo_agi", [db.enemies[e].agility for e in enemigos_rom])
        # El espíritu y los SP: los pide `CalcSkillEffect`, que le resta al
        # efecto `magical_rate * spi_del_blanco / 80`. Hasta el 2026-09-13 no
        # los leía nadie porque ninguna cuenta de la pelea los usaba.
        words_asm("enemigo_spi", [db.enemies[e].spirit for e in enemigos_rom])
        words_asm("enemigo_sp", [db.enemies[e].max_sp for e in enemigos_rom])
        bytes_asm("enemigo_hit", [db.enemies[e].hit for e in enemigos_rom])
        # El crítico, ya en por ciento entero: `CalcCriticalHitChance` lo
        # calcula como `1 / critical_hit_chance` por cien y lo trunca.
        bytes_asm("enemigo_crit", [
            (100 // (db.enemies[e].critical_hit_chance or 30))
            if db.enemies[e].critical_hit else 0 for e in enemigos_rom])
        words_asm("enemigo_txt", [texto_enemigo[e] for e in enemigos_rom])
        # Y la escena de cada tropa: el fondo con los battlers encima. `usadas`
        # es el mismo orden que `tropa_id`, que es lo que `escena_de` indexa.
        handle.write(escenas_asm(list(escenas), usadas))
        handle.write('.segment "TABLAS"\n')
        # El producto de la cuenta del acierto tiene que entrar en dieciséis
        # bits: (100 - acierto) por la suma de las dos agilidades. Con el
        # acierto mínimo de 70 son 30 por 1998, y el tope de agilidad lo cuida
        # `BA_AGI_TOPE`; un enemigo que acertara menos lo desbordaría sin
        # avisar, así que se corta acá.
        # `recover_hp_rate * hp_max` tiene que entrar en dieciséis bits: la
        # ROM lo hace con el multiplicador del hardware, que da una palabra.
        # Con el por ciento topado en 100 eso son hp_max de hasta 655, y los
        # actores de este juego andan en 40. Un actor más gordo desbordaría sin
        # avisar, así que se corta acá.
        for a in range(actores_n):
            maximo = (titulo_mod.parametro_de(db.actors[a], "maxhp")
                      if a in db.actors else 0)
            if maximo * 100 > 0xFFFF:
                raise SystemExit(
                    "el actor %d tiene %d HP y la cuenta de la curación de la "
                    "ROM está dimensionada para 655" % (a, maximo))
        for e in enemigos_rom:
            if db.enemies[e].hit < 70:
                raise SystemExit("el enemigo %d acierta %d, y la cuenta del "
                                 "acierto de la ROM está dimensionada para 70"
                                 % (e, db.enemies[e].hit))
        handle.write(
            "TROPAS_N          = %d\n"
            "BATALLA_SEMILLA   = $%04X\n"
            "BA_TXT_BASE       = %d\n"
            "BA_ENEMIGO_POS0   = %d\n"
            "BA_GRUPO_POS0     = %d\n"
            "BA_MSG_POS1       = %d\n"
            "BA_MSG_POS2       = %d\n"
            "BA_FILA_BYTES     = %d\n"
            "BA_CURSOR_DX      = %d\n"
            "BA_NOMBRE_DX      = %d\n"
            "BA_NOMBRE_ANCHO   = %d\n"
            "BA_HP_DX          = %d\n"
            "BA_HP_NUM_DX      = %d\n"
            "BA_BARRA_DX       = %d\n"
            "BA_HPMAX_DX       = %d\n"
            "BA_MSG_DX         = %d\n"
            % (len(usadas), B.BATALLA_SEMILLA, texto_batalla,
               pos(P.BA_ENEMIGO_FILA0, 0), pos(P.BA_GRUPO_FILA0, 0),
               pos(P.BA_MSG_FILA1, 0), pos(P.BA_MSG_FILA2, 0), 2 * 64,
               P.BA_CURSOR_COL * 2, P.BA_NOMBRE_COL * 2, P.BA_NOMBRE_ANCHO,
               P.BA_HP_COL * 2, P.BA_HP_NUM * 2, P.BA_BARRA_COL * 2,
               P.BA_HP_MAX_NUM * 2, 1 * 2))
        # El audio: el tema de la pelea, el de la victoria y los cinco efectos,
        # con el índice que sacaron de `Temas`. $FF y $FFFF quieren decir "el
        # LDB lo tiene apagado", que es el caso de `battle_se` en este juego.
        # Quién suena en qué momento está en `eventos.AUDIO_BATALLA`, sacado de
        # easyrpg-player; acá sólo viajan los números.
        audio = audio_batalla or {}
        # El paquete de audio de la pelea va detrás de los de los mapas, así
        # que su índice es cuántos mapas lleva la ROM. Lo emite acá y lo
        # comprueba la sección de música, que es la que arma la lista.
        #
        # De dieciséis bits, y el "no hay" es $FFFF: con los 328 mapas del
        # juego entero el índice no entra en un byte, igual que `mapa_actual`.
        # Ver `batalla_audio_cargar`.
        handle.write(
            "BA_TEMA           = $%02X\n"
            "BA_TEMA_FIN       = $%02X\n"
            "BA_PAQUETE        = $%04X\n"
            % (audio.get("battle_music", 0xFF),
               audio.get("battle_end_music", 0xFF),
               len(mapas) if audio else 0xFFFF))
        for nombre, constante in (("dodge_se", "BA_SE_ERRAR"),
                                  ("enemy_attack_se", "BA_SE_ATAQUE"),
                                  ("enemy_damaged_se", "BA_SE_DANO_ENEMIGO"),
                                  ("actor_damaged_se", "BA_SE_DANO_ACTOR"),
                                  ("enemy_death_se", "BA_SE_MUERTE"),
                                  ("escape_se", "BA_SE_HUIR"),
                                  ("item_se", "BA_SE_ITEM")):
            handle.write("%-18s= $%04X\n"
                         % (constante, audio.get(nombre, 0xFFFF)))
        # Los términos, por su lugar en `pantallas.BA_TERMINOS`.
        for k, (nombre, _chunk) in enumerate(P.BA_TERMINOS):
            handle.write("BA_TXT_%-11s= BA_TXT_BASE + %d\n"
                         % (nombre.upper(), k))
        # Las cinco órdenes del menú, con lo que la ROM necesita de cada una:
        # en qué renglón y en qué columna va, qué término la nombra y si va
        # siempre en gris. Van en tablas y no en una cuenta porque desde el
        # 2026-09-13 **no son tres seguidas en un renglón**: son las cinco del
        # menú del ABL repartidas en dos. Ver `pantallas.BA_ORDENES`.
        handle.write("BA_ORDENES_N      = %d\n" % len(P.BA_ORDENES))
        handle.write("BA_ITEM_CUENTA_DX = %d\n" % (P.BA_ITEM_CUENTA_COL * 2))
        handle.write("BA_ORDEN_USAR     = %d\n" % P.BA_ORDEN_USAR)
        handle.write("BA_ORDEN_HUIR     = %d\n" % P.BA_ORDEN_HUIR)
        handle.write("BA_ORDEN_ATACAR   = %d\n" % P.BA_ORDEN_ATACAR)
        handle.write("BA_ORDEN_DEFENDER = %d\n" % P.BA_ORDEN_DEFENDER)
        handle.write("BA_ORDEN_HABILIDAD= %d\n" % P.BA_ORDEN_HABILIDAD)
        # La pantalla de habilidades: dos columnas con el nombre y el costo, y
        # la descripción de la que marca el cursor arriba de todo. La geometría
        # sale de `pantallas.py`, como la de la lista de ítems.
        handle.write(
            "HABILIDADES_N     = %d\n"
            "BA_HAB_DESC_POS   = %d\n"
            "BA_HAB_POS0       = %d\n"
            "BA_HAB_FILAS      = %d\n"
            "BA_HAB_COLUMNAS   = %d\n"
            "BA_HAB_COLUMNA_DX = %d\n"
            "BA_HAB_NOMBRE_DX  = %d\n"
            "BA_HAB_NOMBRE_ANCHO = %d\n"
            "BA_HAB_GUION_DX   = %d\n"
            "BA_HAB_COSTO_DX   = %d\n"
            "BA_HAB_COSTO_CIFRAS = %d\n"
            % (len(habilidades_rom),
               pos(P.BA_HAB_DESC_FILA, P.BA_HAB_DESC_COL),
               pos(P.BA_HAB_FILA0, 0), P.BA_HAB_FILAS, P.BA_HAB_COLUMNAS,
               P.BA_HAB_COLUMNA_DX * 2, P.BA_HAB_NOMBRE_COL * 2,
               P.BA_HAB_NOMBRE_ANCHO, P.BA_HAB_GUION_COL * 2,
               P.BA_HAB_COSTO_COL * 2, P.BA_HAB_COSTO_CIFRAS))
        handle.write('.segment "RODATA"\n')
        words_asm("ba_orden_fila", [
            pos((P.BA_MSG_FILA1, P.BA_MSG_FILA2)[f], 0)
            for _n, f, _c in P.BA_ORDENES])
        words_asm("ba_orden_dx", [c * 2 for _n, _f, c in P.BA_ORDENES])
        # **De dos bytes.** Un índice de texto no entra en uno: con los 29
        # mapas de `demo-ciudad` los de la batalla arrancan en el 273, y la
        # tabla de un byte que había acá hasta el 2026-09-14 los emitía igual
        # —`.byte 273`— para que el ensamblador los truncara sin decir nada.
        words_asm("ba_orden_txt", [
            texto_batalla + [n for n, _c in P.BA_TERMINOS].index(nombre)
            for nombre, _f, _c in P.BA_ORDENES])
        bytes_asm("ba_orden_gris", [
            1 if k in P.BA_ORDEN_SIN_HACER else 0
            for k in range(len(P.BA_ORDENES))])
        handle.write('.segment "TABLAS"\n')

        glifos = ranuras["items_glifos"]
        # Fuera del banco 0, como `item_k`: se lee con `lda f:`.
        handle.write('.segment "RODATA"\n')
        # **Con el bit de prioridad puesto**, desde que la pelea dibuja la
        # escena en BG1: en modo 3 el orden del PPU deja BG1 de prioridad 0
        # **arriba** de BG2 de prioridad 0, así que sin esto el fondo taparía
        # las letras. En las otras pantallas que usan estos glifos —ítems,
        # equipo, tienda— BG1 está apagado y el bit no cambia un pixel; la
        # referencia lo ignora, que es lo que hace el PPU con los pixeles
        # transparentes de las celdas vacías.
        words_asm("item_glifo_celdas", [
            entry(celda, False, False, priority=1) for gris in (0, 1)
            for n in range(T.ITEM_CARACTERES)
            for celda in glifos[gris][chr(T.ITEM_PRIMER_CARACTER + n)]],
            "$%04X", declarar=True)
        handle.write('.segment "TABLAS"\n')
        handle.write("\n")
        # `fuente_color` va en el banco 0 y no con el resto de la ventana: la
        # ROM la lee con `lda fuente_color, y`, y ese modo direcciona el banco
        # de datos. Con ella en RODATA leía basura, y el texto salía en negro.
        handle.write(bloque("fuente_color", bytes(ventana["color"]),
                            acomodar=False) + "\n")
        handle.write("grupo_inicial:\n    .byte %s\n\n"
                     % ",".join("%d" % a for a in grupo_inicial) or "0")
        handle.write(tabla_de_senos() + "\n")
        # Cuántos cuadros se queda quieto un personaje después de un paso y
        # después de un giro, por frecuencia de ruta: el contador de parada de
        # RM2k, en dos tablas de nueve para indexar con la frecuencia tal cual.
        # Salen de las mismas funciones que usa la referencia. La 0 y la 1 no
        # se compilan; llevan cero para que la tabla no tenga agujeros.
        handle.write("ruta_tras_paso:\n    .byte %s\n" % ",".join(
            "%d" % (eventos.espera_tras_paso(f)
                    if f >= eventos.RUTA_FRECUENCIA_MIN else 0)
            for f in range(eventos.RUTA_FRECUENCIA + 1)))
        handle.write("ruta_tras_giro:\n    .byte %s\n\n" % ",".join(
            "%d" % (eventos.espera_tras_giro(f)
                    if f >= eventos.RUTA_FRECUENCIA_MIN else 0)
            for f in range(eventos.RUTA_FRECUENCIA + 1)))
        handle.write(tabla_de_mapas(mapas, etiquetas))
        handle.write("\n\n")
        # Después de la de mapas, que ya dejó el segmento en RODATA.
        handle.write(anim_tabla(mapas))
        handle.write("\n")
    return materiales.informe()


def sprite_colors_bytes(sprite):
    """Las paletas de los sprites como bytes de CGRAM.

    Cada una son 16 entradas: el índice 0 es transparente y no se dibuja, pero
    igual ocupa su lugar, y las que sobran se rellenan para que la siguiente
    empiece donde el hardware la espera.
    """
    if not sprite:
        return b""
    out = bytearray()
    for palette in sprite[1]:
        out += cgram_word(BACKDROP).to_bytes(2, "little")
        for color in palette:
            out += cgram_word(color).to_bytes(2, "little")
        out += bytes(2 * (COLORS_PER_PALETTE - 1 - len(palette)))
    return bytes(out)


def puertas_bytes(puertas, indices):
    """Las puertas listas para la ROM, ya con el índice de tabla del destino.

    Las que llevan a un mapa que no entró en la ROM se descartan acá: en la
    consola serían un salto al vacío, y es mejor que no hagan nada a que hagan
    cualquier cosa. El conversor avisa cuántas quedaron afuera.
    """
    out = bytearray()
    afuera = 0
    for puerta in puertas:
        destino = indices.get(puerta["mapa"])
        if destino is None:
            afuera += 1
            continue
        registro = bytearray(PUERTA_BYTES)
        registro[0:2] = puerta["x"].to_bytes(2, "little")
        registro[2:4] = puerta["y"].to_bytes(2, "little")
        registro[4:6] = puerta["destino_x"].to_bytes(2, "little")
        registro[6:8] = puerta["destino_y"].to_bytes(2, "little")
        # El índice del mapa va en dos bytes, como el de OP_TELEPORT: en uno
        # el formato no puede nombrar los 328 mapas del juego. La ROM ya lo
        # leía como word —con un `and #$00FF` porque el de al lado era cero—,
        # así que esto es lo que hacía falta para que el alto sirva.
        registro[8:10] = destino.to_bytes(2, "little")
        out += registro
    return bytes(out), afuera


# Un evento en la tabla de posiciones: x e y en celdas, las dos de 16 bits
# porque hay mapas de 500 celdas de ancho.
EV_STRIDE = 4
# Cuántos eventos guarda la RAM. El mapa más poblado de este juego tiene 114
# —medido sobre los 328—; el conversor corta si alguno se pasa, así que el
# número no puede quedar corto en silencio. Cada uno cuesta seis bytes de RAM
# entre `ev_pos_buf` y `eleg_por_ev`.
EV_MAX = 120
# Cuántas rutas forzadas pueden estar corriendo a la vez sobre eventos. La
# página que más manda a caminar de este juego mueve cuatro eventos distintos, y
# una ruta sobrevive al final de su página, así que puede haber otra corriendo
# encima. Ocho da margen y cuesta 88 bytes de RAM.
RUTA_EV_MAX = 12
# Cuántos destellos pueden estar corriendo a la vez. Las páginas de este juego
# los encadenan de a uno —casi todos esperan a que termine— así que cuatro sobra;
# el conversor no lo puede comprobar porque depende de qué corra cuándo, y una
# ranura que falte hace que el destello no se vea.
FLASH_MAX = 4
# Cuántos eventos con página paralela puede haber a la vez en un mapa. Era 12
# porque el más cargado era el 8 —Lashe City— con ocho: los cuatro autos y los
# cuatro que los reubican.
#
# **Con `ChangeSpriteAssociation` hecho son 40**, y los pone un solo mapa: cada
# obstáculo de la persecución en auto es un evento con una página paralela que
# compara la celda del auto con la suya, y los mapas 49, 52 y 54 tienen
# cuarenta cada uno. Antes no contaban porque ninguna de esas páginas compilaba.
# Medido sobre los 328 mapas con todo lo que hay hecho hoy; el conversor corta
# si alguno se pasa.
#
# Lo que cuesta: ocho bytes de `FAR_PAR_LISTA` por ranura —RAM lejana, no la
# BSS; ver `PAR_LISTA_BYTES` en `main.s`, que además del evento guarda la página
# que el refresco le eligió— y **una vuelta de intérprete por cuadro por cada
# uno**. Es lo segundo lo que hay que mirar si la carrera se pone lenta: lo
# primero ya no está, porque la página dejó de resolverse en cada cuadro.
#
# 48 por ocho son 384 bytes, y de `FAR_PAR_LISTA` a `FAR_AZAR` hay 508.
PARALELO_MAX = 48
# Un NPC en la RAM de la ROM. Eran ocho bytes; los cuatro de más son para los
# que caminan: a cuál evento corresponden y dónde está su tabla de poses.
#
#   +0 x, +2 y   en pixeles
#   +4 clave     capa y Y, que es lo que compara `build_oam`
#   +6 tile, +7 atributos
#   +8 evento    su índice en la tabla de eventos, o $FF si no camina
#   +9 poses     su entrada en `npc_poses`, o $FF
#   +10 dir      hacia dónde mira su página, para la primera pose de una ruta
#   +11 relleno, para que la ranura se indexe con dos corrimientos
NPC_STRIDE = 16
NPC_QUIETO = 0xFF        # en +9: este NPC no camina

# La tabla de NPCs del mapa que está cargado se copia a RAM, porque build_oam la
# recorre con un índice y eso direcciona el banco de datos. El techo de arriba
# lo pone OAM: entran 128 objetos y uno es el héroe, así que ningún mapa puede
# **mostrar** más de 127.
#
# El número no es ése desde el 2026-09-06, y no por gusto: la fila mide
# dieciséis bytes, así que el tope se lleva dos kilos de los ocho que tiene el
# banco 0 de RAM, y la RAM se acabó —ver "La pila y la BSS comparten los ocho
# kilos" en README.md—. **El mapa con más filas de todo el juego tiene 99**,
# medido sobre los 328, así que 104 deja cinco de aire y devuelve 368 bytes. No
# puede quedar corto en silencio: el conversor corta si algún mapa se pasa.
NPC_MAX = 104


def orden_de_dibujo(npc):
    """Con qué se ordena un evento para dibujarlo, de adelante hacia atrás.

    RM2k ordena por **mayor Y, después mayor X, y después mayor id**. Sale de
    `Game_Character::GetScreenZ` en easyrpg-player, que arma un Z de 64 bits con
    la capa arriba, la Y, la X y el id abajo, con el comentario puesto:

        The rendering order of characters is: Highest Y, Highest X, Highest ID

    Los dos desempates faltaban de los dos lados. Con NPCs quietos casi no se
    nota —hay que tener dos en la misma fila y que alguno tape al otro— pero en
    cuanto uno camina cambia de fila todo el tiempo y empata con cualquiera.

    El índice de la tabla vale por el id: los eventos vienen ordenados por id,
    así que el orden es el mismo.
    """
    return (npc["layer"], npc["y"], npc["x"], npc["evento"])


def sort_key(layer, y):
    """Cómo ordena RM2k: primero la capa y recién después la Y.

    Un evento "below" queda debajo del héroe aunque esté más adelante en la
    pantalla, y uno "above" lo tapa siempre. Meter la capa en los bits altos
    hace que una sola comparación de 16 bits decida las dos cosas.
    """
    return (layer << 12) | (y & 0x0FFF)


# Cuánto ocupa cada opcode, para recorrer el bytecode sin ejecutarlo. Los que
# llevan largo variable van con None y se miden aparte.
# El recorrido del bytecode vive en eventos.py, con la tabla de largos: acá
# había una copia y la de allá se quedó vieja sin que nadie lo viera.
recorrer_codigo = eventos.recorrer_codigo


def orden_de_mapas(args):
    """Los mapas de la ROM, en el orden de la tabla y sin repetidos.

    Está en una función y no escrito tres veces porque **el orden es el
    contrato**: un teletransporte compilado guarda el índice en esta tabla, no
    el id de RM2k. Dos listas que se armen distinto llevarían el mismo bytecode
    a mapas distintos.
    """
    return [args.map_id] + [m for m in (args.mapas or []) if m != args.map_id]


# Cuántos eventos quietos con animación continua anima un mapa. Ver el porqué
# —y el número medido— adentro de `eventos_movibles`.
ANIMA_QUIETO_MAX = 4


def eventos_movibles(game_map, indice_de_mapa, asociaciones=()):
    """Los eventos con gráfico a los que alguna página compilable manda a
    caminar, y los gráficos a los que alguna ruta cambia con la orden 34.

    Hace falta antes de armar el banco de sprites: a los que se mueven hay que
    darles **las doce poses** del ciclo de caminata, y a los demás la única que
    declaran. Dárselas a cualquiera que aparezca en un MoveEvent sería más
    simple y no entra: hay mapas con siete, y son 1232 tiles de sprite.

    Los gráficos de la orden 34 salen de la misma pasada y por lo mismo: a un
    evento que cambia de gráfico hay que meterle en el cartucho las doce poses
    del gráfico nuevo, y eso se decide antes de armar el banco. **El orden
    tiene que ser el mismo que el de la compilación de verdad**, porque el
    bytecode lleva el índice: lo garantiza que las dos pasadas compilen las
    mismas páginas, con el mismo bloque de textos. Sin `Graficos` acá una
    ruta con la 34 no compilaría en esta pasada y sí en la otra, y las dos
    listas se irían.

    Se compilan las páginas para saberlo y se tira lo compilado. Es trabajo
    repetido —main() las vuelve a compilar con el bloque de textos de verdad—
    pero no es una **regla** repetida: la decisión de qué compila la toma la
    misma función las dos veces.
    """
    graficos = eventos.Graficos(asociaciones)
    paginas = eventos.paginas_del_mapa(
        game_map, indice_de_mapa,
        eventos.Mensajes(), graficos=graficos)
    npcs = rm2k.collect_npcs(game_map)
    visibles = {npc["evento"] for npc in npcs}
    # Y los que caminan solos con la ruta propia de alguna página, que
    # necesitan las doce poses igual que los que manda a caminar un MoveEvent.
    propios = {p["evento"] for p in paginas if p.get("ruta_propia")}
    # Y los quietos con animación continua —el save point de Lashe City—, que
    # no caminan pero **cambian de columna igual**. Sin las doce poses su ranura
    # de VRAM llevaría una sola y no habría con qué animarlos: los quietos
    # comparten ranura por (CharSet, índice, pose) y no tienen una propia.
    con_ruta = (eventos.blancos_de_ruta(paginas) | propios) & visibles
    animados = {npc["evento"] for npc in npcs
                if npc.get("anima")} & visibles - con_ruta
    # Y el tope: un evento quieto que anima **cuesta una ranura entera de VRAM**
    # —doce tiles— porque deja de compartir la de su (CharSet, índice, pose) y
    # pasa a tener las doce poses suyas, como los que caminan. Un mapa con
    # treinta —el 52 tiene treinta— pide 572 tiles de sprite y entran 384.
    #
    # Así que un mapa con más de `ANIMA_QUIETO_MAX` no anima **ninguno**, y no
    # unos sí y otros no: dos fuentes iguales, una moviéndose y la otra
    # congelada, se ve peor que las dos quietas. Medido sobre los 328 mapas del
    # juego: 312 tienen cuatro o menos, y de los mapas que hoy llevan las ROMs
    # el único que se pasa es el 52.
    if len(animados) > ANIMA_QUIETO_MAX:
        animados = set()
    # Y los que se dan vuelta hacia el héroe cuando les habla: los eventos con
    # alguna página de acción o de contacto que compiló y gira —ver GIRO en
    # eventos.py—, con los gráficos de **todas** sus páginas que giran. Las
    # doce poses de cada uno van al cartucho, que es de donde la ROM saca la
    # que mira al héroe; el refresco compara los gráficos de las páginas para
    # saber si el giro sobrevive a un cambio de página.
    giran = {}
    for p in paginas:
        if (p["codigo"] and p.get("gira")
                and p["trigger"] in (eventos.TRIGGER_ACCION,
                                     eventos.TRIGGER_TOCA_HEROE)):
            giran[p["evento"]] = set()
    for p in paginas:
        if p["evento"] in giran and p.get("gira") and p["grafico"]:
            giran[p["evento"]].add(tuple(p["grafico"][:2]))
    return con_ruta | animados, list(graficos.pares), animados, giran


def graficos_de_prueba(argumento):
    """Los (CharSet, índice) de `--grafico-de-prueba`, o () si no hay."""
    return tuple((charset, int(indice)) for charset, indice in argumento or ())


def variables_n():
    """Cuántas ranuras de variables lleva la ROM: al menos una —un largo cero
    cerraría la tabla de la partida— y hasta 256, que es lo que entra entre
    `FAR_VARIABLES` y `FAR_ITEMS`."""
    n = max(1, len(eventos.VARIABLE_SLOT))
    if n > 256:
        sys.exit("%d variables no entran en la RAM lejana: FAR_ITEMS está a "
                 "512 bytes de FAR_VARIABLES" % n)
    return n


def tabla_de_senos():
    """El seno que la sacudida de pantalla lee por índice, para el banco."""
    out = ["; El seno a escala 127, para la sacudida de pantalla: es la misma",
           "; lista que arma `SENO_SACUDIDA` en eventos.py.",
           ";",
           "; Va fuera del banco 0 —`lda f:seno_sacudida, x`, una lectura por",
           "; cuadro de sacudida— por lo mismo que `item_k`: son 256 bytes y",
           "; el banco del código se llenó.",
           '.segment "RODATA"',
           "seno_sacudida:"]
    valores = eventos.SENO_SACUDIDA
    for i in range(0, 256, 16):
        out.append("    .byte " + ",".join("$%02X" % (v & 0xFF)
                                            for v in valores[i:i + 16]))
    # Y se vuelve al banco 0: lo que sigue —`ruta_tras_paso` y compañía— se lee
    # con direccionamiento absoluto indexado y tiene que quedar acá.
    out.append('.segment "TABLAS"')
    return "\n".join(out) + "\n"


def ev_pos_bytes(game_map):
    """Dónde arranca cada evento del mapa, en celdas y en orden de índice.

    Va **todo** el mapa y no sólo los eventos con gráfico: una ruta forzada
    puede caer sobre uno invisible, y de hecho la mitad de las de este juego lo
    hacen. La ROM la copia a RAM al cargar el mapa porque una ruta la cambia, y
    la siguiente ruta sobre el mismo evento arranca de donde quedó: hay una
    página que manda a caminar nueve veces al mismo.

    El orden es el índice de la tabla, que es lo que lleva el bytecode. **No es
    el id de RM2k**: 39 mapas tienen huecos en la numeración, y traducir es
    justamente lo que hace `eventos.Eventos`.
    """
    if len(game_map.events) > EV_MAX:
        raise SystemExit("el mapa tiene %d eventos y la RAM de la ROM guarda %d"
                         % (len(game_map.events), EV_MAX))
    out = bytearray()
    for event in game_map.events:
        out += event.x.to_bytes(2, "little")
        out += event.y.to_bytes(2, "little")
    return bytes(out)


def npc_bytes(table):
    """La tabla de NPCs: NPC_STRIDE bytes por cada uno.

    Posición en el mapa, la clave con la que se ordena contra el héroe, qué tile
    de sprite le toca, y el byte de atributos ya armado con su paleta. La ROM
    sólo resta la cámara y lo copia a OAM.

    Los que caminan llevan además a qué evento corresponden y dónde está su
    tabla de doce poses, que es lo que le permite a la ROM cambiarles el tile
    mientras dan un paso.
    """
    out = bytearray()
    for npc in table:
        out += npc["x"].to_bytes(2, "little")
        out += npc["y"].to_bytes(2, "little")
        # La clave va con la Y en pixeles, que es como la calcula la ROM a
        # partir de la posición del héroe. Con la Y en celdas, la del héroe
        # sería siempre mayor y quedaría siempre adelante de todos.
        #
        # Y `npc["y"]` **ya está en pixeles**: lo pasa a pixeles `npc_table`.
        # Multiplicarlo otra vez por 16 —que es lo que hacía acá— daba una clave
        # dieciséis veces más grande que la del héroe, y como `sort_key` recorta
        # a doce bits, encima daba la vuelta. La comparación no lo veía porque
        # el orden **entre** NPCs lo fija el `sorted` del conversor y esta clave
        # sólo decide dónde entra el héroe: hacía falta que el héroe pisara a un
        # NPC para que se notara, y ninguna prueba lo hacía.
        out += sort_key(npc["layer"], npc["y"]).to_bytes(2, "little")
        out.append(npc["tile"] & 0xFF)
        # vhoopppN: la prioridad son los bits 5 y 4, así que el valor va corrido
        # cuatro lugares. Los eventos marcados "above" van en prioridad 2, que
        # es lo único que queda por encima de BG2 1; el resto comparten con el
        # héroe la prioridad 1, y como esa capa los tapa, caminan por debajo.
        prioridad = (OBJ_PRIORITY_ABOVE
                     if npc["layer"] == rm2k.LAYER_ABOVE
                     else OBJ_PRIORITY)
        out.append(prioridad | ((npc["palette"] & 0x07) << 1)
                   | ((npc["tile"] >> 8) & 0x01))
        # El índice del evento va **siempre**, aunque el NPC no camine: es el
        # último desempate del orden de dibujado, y la referencia lo usa para
        # todos. Lo que distingue a los que caminan es la tabla de poses.
        out.append(npc["evento"])
        out.append(NPC_QUIETO if npc["poses"] is None else npc["poses"])
        # Hacia dónde mira su página. Una ruta forzada que todavía no dio
        # ninguna orden de girar lo deja mirando para acá, que es de donde sale
        # la primera pose que se dibuja.
        out.append(npc["dir"])
        out.append(0)               # relleno
        # +12: la pose que hay en VRAM, que al cargar es la de su página. La
        # ROM la compara con la que quiere dibujar y sube la nueva si difiere.
        out.append(npc["pose"])
        # +13: la velocidad de su página, para una ruta forzada sobre él, y en
        # el bit 7 si es un quieto con animación continua. Van juntos porque la
        # fila no tiene un byte libre —el +11 lo usa el salto— y porque los dos
        # los lee la misma cuenta: cada cuántos cuadros cambia de columna sale
        # de la velocidad. Ver `animar_quietos` en main.s.
        out.append(npc["velocidad"] | (0x80 if npc.get("anima") else 0))
        # +14: si se dibuja. Un evento cuya página activa no tiene gráfico
        # está en la tabla escondido, para aparecer cuando otra página gane.
        out.append(1 if npc["visible"] else 0)
        # +15: los bits de paso que su tile le impone a la celda, o $FF: ver
        # `rm2k.pasabilidad_del_tile`. Los dos los rehace el refresco.
        out.append(0xFF if npc["tile_pasa"] is None else npc["tile_pasa"])
    assert len(out) == NPC_STRIDE * len(table)
    return bytes(out)


def puntero(destino):
    """Los tres bytes de un puntero simbólico, para `.byte`."""
    return "<(%s), >(%s), ^(%s)" % (destino, destino, destino)


def npc_poses_asm(numero, animados, indice_global):
    """Los punteros a las doce poses de cada personaje que cambia de pose.

    Una entrada por personaje animado —`k`, el mismo índice que lleva la fila
    del NPC en +9 y el actor en su tabla— y en cada una doce punteros de 24
    bits a `sprite_poses_N_k + pose * 512`. Son simbólicos porque apuntan
    adentro de bloques que ubica el enlazador, como los de las páginas.
    """
    out = [".bloque %d" % (3 * SPRITE_POSES * max(1, len(animados))),
           "npc_poses_%d:" % numero]
    for par in animados:
        for pose in range(SPRITE_POSES):
            out.append("    .byte " + puntero(
                "sprite_poses_%d + %d" % (indice_global[par],
                                          pose * POSE_BYTES)))
    if not animados:
        out.append("    .byte $00")     # una etiqueta no puede quedar vacía
    return "\n".join(out)


def actor_table_asm(numero, actores, animados, indice_global):
    """Los candidatos a líder: id, paleta, y el puntero a cada una de sus poses.

    ACTOR_BYTES por actor. La ROM recorre la tabla buscando el id del primero
    del grupo; son dos o tres entradas, así que buscar linealmente sale más
    barato que indexar por id, que pediría 256 huecos. Un actor sin gráfico
    lleva doce punteros en $FFFFFF, que es el centinela que `place_hero` mira.
    """
    out = [".bloque %d" % (ACTOR_BYTES * max(1, len(actores))),
           "actor_table_%d:" % numero]
    for actor, paleta, k, colores in actores:
        out.append("    .byte $%02X, $%02X" % (actor & 0xFF, paleta & 0x07))
        # Sus quince colores, en el orden en que sus poses los indexan. Un actor
        # sin gráfico los lleva en cero y la ROM no los sube: no se dibuja.
        palabras = list(colores) + [0] * (OBJ_COLORS - len(colores))
        out.append("    .byte " + ",".join(
            "$%02X,$%02X" % (w & 0xFF, w >> 8) for w in palabras))
        for pose in range(SPRITE_POSES):
            if k is None:
                out.append("    .byte $FF, $FF, $FF")
            else:
                out.append("    .byte " + puntero(
                    "sprite_poses_%d + %d" % (indice_global[animados[k]],
                                              pose * POSE_BYTES)))
    if not actores:
        out.append("    .byte $00")
    return "\n".join(out)


def parser_de_flags():
    """Los flags del conversor. Aparte de `main` para quien necesite leer una
    línea de comandos sin convertir nada."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=7)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("-o", "--output",
                        default=os.path.join(REPO, "rom/build/inc/mapdata.inc"))
    parser.add_argument("--relleno-de-textos", type=int, default=0,
                        help="textos muertos delante del bloque de textos de\n"
                             "las pantallas, para que los índices de la\n"
                             "batalla pasen de 255 sin armar un cartucho de\n"
                             "veintinueve mapas. No cambia un pixel: la\n"
                             "referencia no modela índices de texto")
    parser.add_argument("--con-titulo", action="store_true",
                        help="lleva la pantalla de título del juego, con su "
                             "menú de empezar y cargar. Sin esto la ROM "
                             "arranca directo en el mapa, que es lo que hace "
                             "toda la tanda de regresión: la pantalla de "
                             "título le agregaría cuadros al arranque y los "
                             "96 casos comparan cuadros contados desde el "
                             "reset.")
    parser.add_argument("--banco-entero", action="store_true",
                        help="que **todos** los temas aporten muestras al "
                             "banco compartido, en vez de recortar los "
                             "últimos hasta que el banco entre en la ARAM. "
                             "El recorte es lo que hace que en `demo-ciudad` "
                             "a los nueve temas del final les falten entre el "
                             "28%% y el 88%% de las notas —las que piden un "
                             "programa que no está—; con esto no falta "
                             "ninguna y lo que baja es la resolución de "
                             "todas. El banco pasa a no entrar entero en la "
                             "ARAM, que no es un problema: ahí vive un "
                             "paquete de mapa por vez")
    parser.add_argument("--banco-sin-prioridad", action="store_true",
                        help="que el tema del mapa de arranque **no** tenga "
                             "prioridad para aportar muestras al banco. Es "
                             "para las ROMs de escuchar: arrancar en el mapa "
                             "20 le da prioridad a su tema y entonces suena "
                             "entero, que es justo lo contrario de lo que se "
                             "quiere reproducir. Con esto el reparto del "
                             "banco es el mismo que el de `demo-ciudad`, que "
                             "arranca en un mapa sin música")
    parser.add_argument("--con-timer", action="store_true",
                        help="la ROM lleva los dígitos del cronómetro: once "
                             "glifos de la imagen de System al final del banco "
                             "de sprites. Comparten paleta con un personaje")
    parser.add_argument("--grafico-de-prueba", nargs=2, action="append",
                        default=None, metavar=("CHARSET", "INDICE"),
                        help="mete este gráfico en el banco de sprites\n"
                             "de los mapas donde corre algún caso, para que la\n"
                             "página de prueba pueda cambiarle el gráfico a\n"
                             "alguien con la orden 34 o con\n"
                             "ChangeSpriteAssociation. Se puede repetir.\n"
                             "Ninguna página que compile hoy cambia de\n"
                             "gráfico, así que sin esto el camino no lo\n"
                             "corre nada")
    parser.add_argument("--tema-de-arranque", default=None, metavar="NOMBRE",
                        help="hace que la ROM arranque tocando ese tema en vez\n"
                             "del que le toca al mapa. Existe para escuchar un\n"
                             "tema desde el arranque —la receta `musica`— y\n"
                             "para las pruebas: los mapas donde esto empieza\n"
                             "no traen música propia y sin el flag la ROM sale\n"
                             "callada. No cambia el bytecode")
    parser.add_argument("--encuentros-de-prueba", type=int, default=None,
                        metavar="PASOS",
                        help="cada cuántos pasos hay un encuentro al azar, "
                             "para todos los mapas del cartucho. Sin esto vale "
                             "el del árbol del juego, que va de 25 a 85 pasos; "
                             "0 los apaga. La referencia toma el mismo número")
    parser.add_argument("--heroe-encima", action="store_true",
                        help="el héroe en prioridad 2 de objeto, por "
                             "encima de la capa que debería taparlo. "
                             "Es la única forma de ejercitarla: el "
                             "único evento above del juego no llega a "
                             "pisar la capa de encima")
    parser.add_argument("--grupo", nargs="+", type=int, default=None,
                        metavar="ACTOR",
                        help="el grupo con el que arranca, por ids de actor. El gráfico "
                             "del héroe es el del primero, que es como lo decide "
                             "RM2k. Por defecto, el de la base: este juego "
                             "arranca con el actor 10, DummyHero, cuyo sprite es "
                             "una celda vacía a propósito")
    parser.add_argument("--comandos-de-prueba", default=None,
                        metavar="ARCHIVO",
                        help="la página de prueba de este caso, como la lista "
                             "de comandos de una página de RM2k en el JSON de "
                             "Ditto —ver pruebas/casos/—. La compila el mismo "
                             "camino que una página del juego, con el "
                             "contexto del mapa donde corre: el de su "
                             "Teleport si empieza con uno, y si no el de "
                             "arranque")
    parser.add_argument("--charset", default=None,
                        help="forzar el CharSet del héroe; por defecto sale "
                             "del primero del grupo, que es como lo decide RM2k")
    parser.add_argument("--charset-index", type=int, default=None,
                        help="cuál de los 8 personajes del CharSet")
    parser.add_argument("--mapas", nargs="+", type=int, metavar="ID",
                        help="otros mapas para meter en la misma ROM. El de "
                             "--map-id va primero en la tabla")
    parser.add_argument("--inicial", type=int, default=0, metavar="N",
                        help="en qué índice de la tabla arranca la ROM. Sirve "
                             "para probar un mapa que no sea el primero, que "
                             "es el único caso donde el desplazamiento del "
                             "registro no es cero")
    parser.add_argument("--inicio", nargs=2, type=int, metavar=("TX", "TY"),
                        help="dónde plantar al héroe, en celdas de 16x16. Sin "
                             "esto arranca en el tile abierto más cercano al "
                             "centro. Sirve para llevar la cámara a un lugar "
                             "puntual sin tener que caminar hasta él")
    return parser


def main():
    parser = parser_de_flags()
    argv, tramos = partir_en_casos(sys.argv[1:])
    args = parser.parse_args(argv)
    args.casos = casos_de_prueba(parser, args, tramos)
    orden = orden_de_mapas(args)
    if not 0 <= args.inicial < len(orden):
        sys.exit("--inicial %d pero hay %d mapas" % (args.inicial, len(orden)))
    for caso in args.casos:
        caso.mapa = mapa_del_caso(caso, orden, args.inicial)
    de_archivo = comandos_de_casos(args)
    # Qué mapas llevan los dígitos del cronómetro, que cuestan una paleta de
    # sprite. Con `--con-timer`, todos: es lo que piden las demos, donde la
    # cuenta atrás arranca en un mapa y se ve en los que siguen. Sin él, los
    # mapas donde corre un caso que lo toca: hasta el paso 9e bastaba uno para
    # que los llevaran todos los del cartucho, y en el cartucho único del 9f
    # eso le sacaba la paleta a cada mapa —medido, quince goldens se movían—.
    # Un mapa sin dígitos no los dibuja: `TIMER_BASE` en cero, ver
    # `timer_oam`.
    args.timer_en = set(orden) if args.con_timer else {
        caso.mapa for caso in args.casos
        if any(cmd.code == eventos.TIMER_OPERATION for cmd in caso.comandos)}

    renderer = Renderer(args.game_dir)

    # El gráfico del héroe sale del grupo, no de acá. En RM2k lo da el primero
    # de la lista, y este juego arranca con el actor 10 —'DummyHero', que es
    # Chubby2[2]—. Hasta ahora había un default puesto a mano que daba
    # Future1[0], o sea el sprite de otro personaje; los dos lados de la
    # comparación lo tenían igual de mal, así que el cero no lo delataba.
    # --charset queda para forzarlo a mano cuando hace falta.
    grupo = args.grupo if args.grupo else renderer.database.party
    if args.charset is None:
        args.charset, indice = renderer.database.lider(grupo)
        if args.charset_index is None:
            args.charset_index = indice
    if args.charset_index is None:
        args.charset_index = 0

    # Los candidatos a líder se calculan con todos los mapas de la ROM juntos,
    # porque el grupo es estado global: una página del mapa A puede meter a
    # alguien que después camina por el mapa B.
    args_game_dir[0] = args.game_dir
    todos = orden_de_mapas(args)
    # **Los índices van antes que todo lo que compile una página**, y
    # `lideres_posibles` compila páginas. Estaban después, y el precio era
    # concreto: sin `indexar_variables`, ninguna `ControlVars` compila, así que
    # `RaceController1` del mapa 49 —que arranca con un `PlayBGM` y sigue con
    # dos `ControlVars`— no compilaba **en esa pasada** y sí en la de verdad.
    # Los actores que mete al grupo se perdían: `CarRED` no entraba en la tabla
    # de actores del mapa y el héroe de la persecución se dibujaba **sin
    # gráfico**, o sea que el auto no se veía. Es el mismo agujero que ESTADO.md
    # ya tenía anotado para las cuentas de páginas, en otro lugar.
    #
    # Las variables del juego entero, con su ranura. La referencia arma el
    # mismo índice.
    extra = eventos.variables_de_comandos(de_archivo)
    if len(args.casos) > 1:
        # La que elige el caso: ver `eventos.VARIABLE_DE_CASO`. Con uno solo
        # no hace falta, y así ese cartucho sale igual que antes de `--caso`.
        extra.add(eventos.VARIABLE_DE_CASO)
    eventos.indexar_variables(args.game_dir, extra)
    # Y las animaciones de batalla, que `ShowBattleAnimation` compila con su
    # línea de tiempo adentro: ver OP_ANIMATION.
    eventos.indexar_animaciones(args.game_dir)
    # Y los eventos comunes, que `CallEvent` compila en el lugar:
    # los dos lados tienen que mirar la misma base.
    eventos.indexar_comunes(args.game_dir)
    eventos.indexar_audio_de_batalla(args.game_dir)
    # Y los términos de la posada, con los que `ShowInn` arma su saludo.
    eventos.indexar_terminos(args.game_dir)
    # Y el equipo y las habilidades de cada actor del LDB: es lo que contestan
    # las dos ramas de actor con dos operandos, y la referencia lo arma con la
    # misma función. **Antes de `lideres_posibles`**, que compila páginas: ver
    # su comentario.
    eventos.indexar_actores(args.game_dir)
    args.lideres = lideres_posibles(renderer, todos, grupo)
    # Y los del grupo con que sigue cada página de prueba, detrás: la prueba
    # puede arrancar con él en cualquier mapa del cartucho.
    for caso in args.casos:
        de_prueba = grupo_de_la_pagina(caso, grupo)
        if de_prueba:
            for actor in lideres_posibles(renderer, todos, de_prueba):
                if actor not in args.lideres:
                    args.lideres.append(actor)
    # Si algún mapa pone lluvia, todos llevan las gotas: ver `hay_lluvia`.
    args.con_lluvia = hay_lluvia(todos, de_archivo)
    # En cuántos mapas de esta ROM aparece cada personaje. Lo usa el reparto de
    # paletas para elegir a quién puede bajarle un color sin romper nada: el
    # banco de poses es **de la ROM entera**, así que un personaje que está en
    # dos mapas tiene que quedar cuantizado igual en los dos. Cuantizarlo
    # distinto no da una imagen fea sino un `sys.exit` al emitir, que es lo que
    # pasó la primera vez que esto se escribió: `Future1:4` bajaba en un mapa y
    # no en el otro.
    args.mapas_por_personaje = mapas_por_personaje(renderer, todos,
                                                   args.game_dir)
    # El cartel del `ShowPicture`, uno por ROM: ver `eventos.Imagenes`. Se lo
    # queda el primer mapa de la tabla que lo muestre, que es el orden en que
    # `convertir` los recorre; la referencia elige con la misma función.
    args.imagenes = eventos.Imagenes(args.game_dir)
    args.imagenes.mapa = None
    # Y las ranuras que `ChangeSpriteAssociation` le reserva a la tabla de
    # gráficos de **todos** los mapas, por la misma razón que el cartel: el
    # gráfico que le pone a un actor cruza el teletransporte, así que su índice
    # tiene que valer lo mismo en los dos mapas. Ver `eventos.asociaciones_de`.
    #
    # Los de las páginas de prueba entran por la misma puerta: si fueran por
    # `--grafico-de-prueba` tendrían índice sólo en los mapas donde corre un
    # caso, y lo que el comando hace —cruzar el teletransporte— no se podría
    # probar.
    args.asociaciones = eventos.asociaciones_de(
        [lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % m))
         for m in todos], de_archivo)

    mapas = [convertir(renderer, map_id, args,
                       inicio=args.inicio if map_id == args.map_id else None)
             for map_id in todos]
    # Antes acá se reconvertían los mapas cuya capa de encima arrancaba más
    # arriba que la paleta de la ventana, para apretarles el fondo debajo de
    # ella. Con la ventana en la paleta 0 no hay nada que apretar: el fondo de
    # cada mapa arranca en `CGRAM_RESERVADAS` y llega hasta su propia capa de
    # encima, sin depender de lo que necesiten los otros mapas de la ROM.
    # Las puertas se resuelven cuando están todos los mapas: una puede llevar a
    # cualquier otro, así que el índice de destino no se sabe hasta el final.
    indices = {mapa["id"]: numero for numero, mapa in enumerate(mapas)}

    # El bloque de textos es de la ROM entera y se arma mientras se compilan las
    # páginas: cada `ShowMessage` deja su texto acá y se lleva un
    # desplazamiento, que es lo que va en el bytecode. La referencia arma el
    # mismo bloque en el mismo orden.
    mensajes = eventos.Mensajes()
    # Los temas que los PlayBGM de las páginas piden, numerados en el orden en
    # que aparecen. La ROM lleva uno solo —ver `Temas`— y lo elige más abajo,
    # cuando ya están todos compilados y se sabe cuáles se piden.
    temas = eventos.Temas()
    # Y las tropas que los EnemyEncounter piden. No numera nada —el bytecode
    # lleva el id de RM2k— así que sólo dice qué tablas de enemigos hay que
    # emitir. Ver `eventos.Tropas`.
    tropas = eventos.Tropas()
    # Los textos de las páginas de prueba van **primero**, antes de todos los
    # mapas, y eso no es estético: así su desplazamiento no depende de cuántos
    # textos traiga el mapa donde arranca la ROM ni de en qué orden se
    # compilen —el primero es el 0—. Se guardan acá y la compilación de la
    # página, más abajo, los encuentra guardados, porque el bloque deduplica
    # por contenido.
    for cmd, extra_lineas in eventos.agrupar(de_archivo):
        if cmd.code == eventos.SHOW_MESSAGE:
            mensajes.agregar([cmd.string] + extra_lineas)
    # Las páginas de prueba ya compiladas, por caso: ver la segunda vuelta.
    de_prueba = {}

    for mapa in mapas:
        mapa["puertas"], afuera = puertas_bytes(mapa["puertas_crudas"], indices)
        cuantas = len(mapa["puertas"]) // PUERTA_BYTES
        if cuantas or afuera:
            print("  mapa %d: %d puerta(s)%s"
                  % (mapa["id"], cuantas,
                     ", %d a mapas que no están en la ROM" % afuera
                     if afuera else ""))

        # Los eventos automáticos: sus páginas con las condiciones, y el código
        # de las que se pueden ejecutar, todo seguido en un solo bloque.
        # Un registro de gráficos por mapa: la orden 34 lleva el índice y la
        # tabla `ruta_grafico` del mapa lo resuelve. Ver `eventos.Graficos`.
        graficos = eventos.Graficos(args.asociaciones)
        temas.mapa = mapas.index(mapa)      # para su paquete de audio
        paginas = eventos.paginas_del_mapa(mapa["game_map"], indices.get,
                                           mensajes, temas, graficos,
                                           args.imagenes, tropas)
        temas.mapa = None
        # Un intérprete por evento con alguna página paralela que compile. La
        # ROM los lleva en una lista de tope fijo y **no avisa** si se le pasa
        # —los que sobran no correrían y nada lo diría—, así que el corte va acá.
        con_paralela = {p["evento"] for p in paginas
                        if p["trigger"] == eventos.TRIGGER_PARALELO
                        and p["codigo"]}
        if len(con_paralela) > PARALELO_MAX:
            sys.exit("el mapa %d tiene %d eventos con página paralela y entran "
                     "%d: ver PARALELO_MAX"
                     % (mapa["id"], len(con_paralela), PARALELO_MAX))
        if con_paralela:
            print("  mapa %d: %d evento(s) con página paralela"
                  % (mapa["id"], len(con_paralela)))
        if args.grafico_de_prueba and mapa["id"] in mapas_de_prueba(args):
            for charset, index in graficos_de_prueba(args.grafico_de_prueba):
                graficos.indice(charset, index)
        # **Sólo el mapa que se llevó sus tiles puede mostrar el cartel.** El
        # banco de sprites es de cada mapa, así que desde otro los seis objetos
        # leerían lo que hubiera en esos tiles. No pasa hoy —el cartel del "1
        # year earlier" lo muestra una sola página— y por eso esto corta en vez
        # de elegir: el día que dos mapas muestren el mismo, hay que decidir si
        # sus tiles van en los dos, y esa decisión no la puede tomar el
        # conversor solo.
        if (args.imagenes.nombre is not None
                and mapa["id"] != args.imagenes.mapa):
            for pagina in paginas:
                codigo = pagina["codigo"]
                if codigo and any(codigo[i] == eventos.OP_PICTURE
                                  for i, _c in eventos.recorrer_codigo(codigo)):
                    sys.exit(
                        "mapa %d: muestra el cartel %r y sus tiles quedaron en "
                        "el mapa %d; la ROM lo lleva en uno solo. Ver "
                        "`cartel_de_imagen`."
                        % (mapa["id"], args.imagenes.nombre,
                           args.imagenes.mapa))
        if graficos.pares != mapa["graficos_de_ruta"]:
            # Las dos pasadas compilaron cosas distintas. No puede pasar —las
            # dos usan `paginas_del_mapa` con el mismo bloque de textos— y si
            # pasara, el bytecode quedaría apuntando a la tabla equivocada sin
            # que nada lo diga.
            sys.exit("mapa %d: las dos pasadas numeraron distinto los gráficos "
                     "de ruta: %s contra %s"
                     % (mapa["id"], graficos.pares, mapa["graficos_de_ruta"]))
        # Las páginas de los casos que corren en este mapa, compiladas con su
        # contexto aunque vayan a vivir en el mapa de arranque: ver
        # `mapa_del_caso`. Se ponen allá en la segunda vuelta, cuando ya
        # están todas.
        for k, caso in enumerate(args.casos):
            if caso.mapa == mapa["id"]:
                de_prueba[k] = pagina_de_caso(caso, mapa, temas, graficos,
                                              mensajes, indices,
                                              args.imagenes)
        mapa["paginas"] = paginas
        # Y a qué mapas de afuera de la ROM apuntan las que no compilan.
        #
        # Un `Teleport` a un mapa que no entró corta la página entera, y una
        # página que no compila no hace **nada**: ni el teletransporte ni lo que
        # venía antes. `evento` lo dice en su comentario desde siempre,
        # pero el conteo de arriba no distingue esta razón de las otras por las
        # que una página se cae, y es la única que se arregla desde afuera
        # —sumando el mapa— y no tocando el compilador. Así se pasó por alto la
        # página del ascensor del mapa 2, que se veía abrirse y no llevaba a
        # ningún lado porque termina saltando al mapa 3. La lista de puertas ya
        # avisa lo mismo; esto es su equivalente para las páginas.
        afuera_de, cuantas = set(), 0
        for pagina in paginas:
            if pagina["codigo"] or pagina["trigger"] not in eventos.TRIGGERS \
                    or pagina.get("prueba"):
                continue        # la página de prueba no sale del juego
            evento = mapa["game_map"].events[pagina["evento"]]
            faltan = {cmd.parameters[0]
                      for cmd in evento.pages[pagina["pagina"]].commands
                      if cmd.code == eventos.TELEPORT and cmd.parameters
                      and indices.get(cmd.parameters[0]) is None}
            if faltan:
                afuera_de |= faltan
                cuantas += 1
        if afuera_de:
            print("  mapa %d: %d de ésas no %s por un teletransporte a un mapa "
                  "que no entró en la ROM: %s"
                  % (mapa["id"], cuantas,
                     "compila" if cuantas == 1 else "compilan",
                     ", ".join(str(m) for m in sorted(afuera_de))))
        # Las deudas se avisan. Una página que se acepta sin hacer todo lo que
        # pide es una diferencia con el juego original, y callarla es cómo se
        # vuelve invisible: acá se nombra el comando y qué se pierde.
        deudas = set()
        for evento in mapa["game_map"].events:
            for page in evento.pages:
                if page.trigger != eventos.TRIGGER_AUTOMATICO:
                    continue
                # Con el mismo bloque de textos que arriba: si acá fuera
                # None, una página con un cuadro de texto no compilaría y su
                # deuda —un PlayBGM, digamos— quedaría sin avisar aunque la ROM
                # sí la corra. Volver a agregar un texto que ya está no crece
                # el bloque: la clave es el contenido.
                if eventos.compilar_pagina(page, indices.get,
                                           mensajes) is None:
                    continue
                deudas |= set(eventos.deudas_de_la_pagina(page,
                                                          args.imagenes))
        for codigo_cmd in sorted(deudas):
            print("  mapa %d: AVISO, una página usa %s y la ROM no lo hace; "
                  "ver ACEPTADOS_SIN_HACER en tools/port/eventos.py"
                  % (mapa["id"], event_codes.EVENT_CODES.get(codigo_cmd,
                                                             codigo_cmd)))


    # La segunda vuelta: con las páginas de todos los casos compiladas, se
    # ponen en el mapa de arranque y se arma el bloque de cada mapa.
    for mapa in mapas:
        paginas = mapa["paginas"]
        if args.casos and mapa is mapas[args.inicial]:
            # Las páginas de prueba, sólo en el mapa donde arranca la ROM. No
            # salen del juego sino de `pruebas/casos/`: existen porque hay
            # caminos del intérprete que ninguna página del juego que compile
            # ejercita —la primera fue una espera—.
            #
            # Va en el **índice 0**, el del evento vacío que `convertir` puso
            # al principio del mapa: la ROM recorre los eventos de menor a
            # mayor, y esta página tiene que correr antes que las del juego.
            # Hasta el 2026-09-17 iba en el primer índice libre, al final.
            #
            # **Una página por caso**, y la k pide que `VARIABLE_DE_CASO`
            # valga al menos k: ver su comentario. La 0 no pide nada, así que
            # un cartucho de un solo caso es el de siempre.
            paginas = paginas + [{
                "evento": 0, "pagina": k, "prueba": True,
                "trigger": eventos.TRIGGER_AUTOMATICO,
                "switch_a": 0, "switch_b": 0, "actor": 0,
                "variable": ((eventos.ranura_de_variable(
                    eventos.VARIABLE_DE_CASO),
                    eventos.COMPARAR_AL_MENOS, k) if k else None),
                "item": 0, "capa": 0,
                "frecuencia": eventos.RUTA_FRECUENCIA, "velocidad": 4,
                "codigo": de_prueba[k]} for k in range(len(args.casos))] + [{
                # Y la que la apaga: misma idea que en la referencia, ver
                # `PAGINA_DE_PRUEBA_APAGADA`. Sin código, así que en cuanto
                # gana, el evento inventado deja de tener una automática que
                # correr y la primera no se repite.
                "evento": 0, "pagina": len(args.casos), "prueba": True,
                "trigger": eventos.TRIGGER_AUTOMATICO,
                "switch_a": eventos.SWITCH_DE_PRUEBA, "switch_b": 0,
                "actor": 0, "variable": None, "item": 0, "capa": 0,
                "frecuencia": eventos.RUTA_FRECUENCIA, "velocidad": 4,
                "codigo": b""}]
        codigo = bytearray()
        for pagina in paginas:
            pagina["offset"] = len(codigo)
            if pagina["codigo"]:
                codigo += pagina["codigo"]
            # Y las órdenes de la ruta propia, detrás, un byte por orden.
            propia = pagina.get("ruta_propia")
            if propia:
                pagina["ruta_offset"] = len(codigo)
                codigo += bytes(propia["ordenes"])
        mapa["paginas"] = paginas
        # Lo que dibuja cada página de los eventos que cambian de gráfico, ya
        # como lo quiere OAM: es lo que la ROM copia a la fila del NPC cuando
        # la página activa cambia. Ver `tabla_de_paginas`, +20.
        for pagina in paginas:
            sigue = pagina["evento"] in mapa["cambian"]
            if not sigue and pagina["evento"] not in mapa["aparecen"]:
                continue
            grafico = pagina.get("grafico")
            if grafico is None \
                    or grafico[:2] in mapa["afuera"].get(pagina["evento"], ()):
                continue
            if not sigue:
                # El que sólo aparece no lleva tile ni atributos: los suyos
                # apuntan a su ranura de doce poses y la ROM no los toca. Va
                # la pose —con el bit 7, que es "esta página dibuja algo"— y
                # lo que su tile le impone a la celda.
                pagina["oam"] = (0, 0, grafico[2] | 0x80,
                                 0xFF if pagina.get("tile_pasa") is None
                                 else pagina["tile_pasa"])
                continue
            block, slot = mapa["where"][grafico]
            tile = block_tile(block)
            prioridad = (OBJ_PRIORITY_ABOVE
                         if pagina["capa"] == rm2k.LAYER_ABOVE
                         else OBJ_PRIORITY)
            pagina["oam"] = (tile & 0xFF,
                             prioridad | ((slot & 0x07) << 1) | ((tile >> 8) & 1),
                             grafico[2] | 0x80,
                             0xFF if pagina.get("tile_pasa") is None
                             else pagina["tile_pasa"])
        mapa["evcodigo"] = bytes(codigo)
        # Cuántos eventos distintos puede llegar a mandar a caminar este mapa.
        # La ROM tiene RUTA_EV_MAX ranuras y una ruta que no encuentre lugar se
        # descarta **sin decir nada**, que es la clase de diferencia que ninguna
        # comparación vería: la referencia la caminaría y la consola no. Con los
        # datos de este juego el peor mapa usa dos, así que el control no molesta
        # a nadie; está para que un cambio futuro no las tire en silencio.
        #
        # Las páginas que **corren** acá: las del mapa y las de los casos que
        # saltan a él, que viven en el de arranque. Ver `mapa_del_caso`.
        corren_aca = [p["codigo"] for p in paginas
                      if p["codigo"] and not p.get("prueba")]
        corren_aca += [de_prueba[k] for k, caso in enumerate(args.casos)
                       if caso.mapa == mapa["id"]]
        blancos = {c[i + 1] for codigo in corren_aca
                   for i, c in recorrer_codigo(codigo)
                   if c[i] == eventos.OP_ROUTE and c[i + 1]}
        # Y que nadie destelle a alguien que comparte gráfico con otro. En la
        # consola el destello se hace sobre la paleta del personaje, así que dos
        # que compartan gráfico destellarían juntos. `eventos.py` ya rechaza el
        # caso de dos eventos; acá se cubre el que allá no se puede ver, que es
        # el del héroe: qué gráfico tiene depende del grupo, y eso lo sabe el
        # conversor y no el compilador.
        #
        # `separar_del_heroe` ya evita esto en los mapas cuyas páginas destellan
        # al héroe. Esto queda para lo que aquél no ve: un `FlashSprite` que
        # llega adentro de un evento común, que se compila en el lugar desde
        # cualquier `CallEvent` y no está en las páginas del mapa.
        graficos = collections.Counter(
            (npc["charset"], npc["index"])
            for npc in rm2k.collect_npcs(mapa["game_map"]))
        for actor in args.lideres:
            a = renderer.database.actors[actor]
            graficos[(a.charset, a.charset_index)] += 1
        for codigo in corren_aca:
            for i, c in recorrer_codigo(codigo):
                if c[i] != eventos.OP_FLASH or c[i + 1] != 0:
                    continue
                for actor in args.lideres:
                    a = renderer.database.actors[actor]
                    if graficos[(a.charset, a.charset_index)] > 1:
                        raise SystemExit(
                            "mapa %d: una página hace destellar al héroe, y el "
                            "actor %d se dibuja con %s[%d], que también usa un "
                            "NPC del mapa. En la consola comparten paleta y "
                            "destellarían los dos"
                            % (mapa["id"], actor, a.charset, a.charset_index))

        if len(blancos) > RUTA_EV_MAX:
            raise SystemExit(
                "mapa %d: sus páginas mandan a caminar %d eventos distintos y "
                "la ROM tiene %d ranuras de ruta"
                % (mapa["id"], len(blancos), RUTA_EV_MAX))
        corribles = sum(1 for p in paginas if p["codigo"])
        if paginas:
            print("  mapa %d: %d página(s) de evento automático, %d ejecutable(s)"
                  % (mapa["id"], len(paginas), corribles))

    if not 0 <= args.inicial < len(mapas):
        sys.exit("--inicial %d pero hay %d mapas" % (args.inicial, len(mapas)))
    from port import ventana as ventana_mod
    skin = ventana_mod.skin(args.game_dir, renderer.database.system_name)
    font_id = renderer.database.font_id
    ventana_datos = convert_ventana(skin, font_id)
    ventana_datos["fuente"] = fuente_bytes(font_id)
    ventana_datos["mensajes"] = mensajes.bytes()
    print("  ventana de mensaje: %d tiles fijos + %d de texto, %d colores; "
          "fuente %d B, %d cuadro(s) de texto en %d B"
          % (len(ventana_datos["tiles"]) // 32,
             len(ventana_datos["fondo"]) // 32,
             sum(1 for w in ventana_datos["cram"] if w),
             len(ventana_datos["fuente"]), len(mensajes.textos),
             len(ventana_datos["mensajes"])))
    # La pantalla de ranuras va en toda ROM: la abre el save point desde
    # adentro del juego, y "Resume the Story" desde el título cuando lo hay.
    # Se dibuja con la misma fuente y la misma skin que la ventana de mensaje,
    # y vive en la VRAM del título, donde no hay mapa.
    # Los actores que pueden estar en el grupo cuando se guarda, para tener
    # su cara y su nombre en el cartucho: los de arranque y todos los que
    # agrega algún `ChangePartyMembers` de estos mapas, compilen sus páginas o
    # no. Es un superconjunto a propósito: una cara de más cuesta 36 tiles y
    # una de menos deja un hueco en el menú.
    miembros = miembros_posibles(todos, grupo, de_archivo)
    # Y los ítems que pueden estar en el inventario, para llevar su nombre y
    # su descripción: ver "la pantalla de ítems" en titulo.py.
    items_rom = items_posibles(todos, miembros, renderer.database,
                               de_archivo)
    (ranura_tiles, ranura_paletas, ranura_cabs, ranura_filas, ranura_caras,
     ranura_nombres, ranura_menu) = titulo_mod.pantalla_ranuras(
        skin, renderer.database, RANURAS, renderer.database.font_id,
        miembros, args.game_dir)
    items_tiles, items_paletas, items_glifos = titulo_mod.pantalla_items(
        skin, renderer.database.font_id)
    ranuras_datos = {"tiles": ranura_tiles, "paletas": ranura_paletas,
                     "cabeceras": ranura_cabs, "filas": ranura_filas,
                     "caras": ranura_caras, "nombres": ranura_nombres,
                     "menu": ranura_menu, "items": items_rom,
                     "db": renderer.database, "actores": miembros,
                     "relleno_textos": args.relleno_de_textos,
                     "items_db": renderer.database.items,
                     "items_tiles": items_tiles,
                     "items_paletas": items_paletas,
                     "items_glifos": items_glifos}
    _controlar_ranuras(len(ranura_tiles))
    print("  pantalla de ranuras: %d, %d tiles de 4bpp (%d B) + %d paletas, "
          "%d B de celdas; %d actores con cara: %s"
          % (RANURAS, len(ranura_tiles), len(ranura_tiles) * 32,
             len(ranura_paletas),
             (len(ranura_cabs) * len(ranura_cabs[0])
              + RANURAS * 4 * len(ranura_filas[0][0][0])) * 2,
             len(ranura_caras),
             ", ".join("%d %s" % (a, renderer.database.actors[a].name)
                       for a in sorted(ranura_caras)) or "ninguno"))
    titulo_datos = None
    if args.con_titulo:
        from PIL import Image
        nombre = renderer.database.title_name
        imagen = Image.open(os.path.join(args.game_dir, "Title",
                                         nombre + ".png"))
        tiles, paleta, tilemap = titulo_mod.convertir(imagen)
        textos = titulo_mod.opciones(renderer.database)
        menu_tiles, menu_paleta, menu_mapas = titulo_mod.menu(
            skin, textos, renderer.database.font_id)
        titulo_datos = {"tiles": tiles, "paleta": paleta, "tilemap": tilemap,
                        "menu_tiles": menu_tiles, "menu_paleta": menu_paleta,
                        "menu_tilemaps": menu_mapas}
        print("  pantalla de título %r: %d tiles de 8bpp (%d B) + %d colores, "
              "%d B de tilemap" % (nombre, len(tiles), len(tiles) * 64,
                                   len(paleta), 32 * 32 * 2))
        print("    menú (%s): %d tiles de 4bpp (%d B) + %d colores, %d tilemap(s)"
              % (", ".join(repr(t) for t in textos), len(menu_tiles),
                 len(menu_tiles) * 32, len(menu_paleta), len(menu_mapas)))
    # Las animaciones de batalla que el bytecode ya emitido muestra: sus
    # cuadros prerenderizados van al cartucho y la ROM los sube por DMA.
    animaciones = animaciones_de_la_rom(mapas, renderer)
    for numero in sorted(animaciones):
        datos = animacion_mod.informe(numero, animaciones[numero])
        print("  animación %d: %d cuadros de %dx%d, achicada de %dx%d al %d%%,"
              " %d colores, %d B"
              % (datos["animacion"], datos["cuadros"], datos["caja"][0],
                 datos["caja"][1], datos["original"][0], datos["original"][1],
                 datos["porciento"], datos["colores"], datos["bytes"]))
    # Los encuentros al azar de cada mapa, que piden sus tropas. Van **antes**
    # que las de las páginas de prueba, que van al final: así las tropas del
    # cartucho se numeran por los mapas y la inventada va última, que es lo
    # mismo que hace `temas_de_la_rom` con el tema del mapa. Pedirla antes le
    # daba siempre el índice 0, y con eso ningún caso de la tanda ejercitaba
    # que `escena_de` y `tropa_id` se indexen de verdad. Por eso
    # `pagina_de_caso` compila sin `Tropas`.
    encuentros = encuentros_de_la_rom(mapas, renderer.tree,
                                      args.encuentros_de_prueba, tropas)
    cuantas = sum(z["tropa_n"] for z in encuentros["zonas"])
    if encuentros["registros"]:
        print("  encuentros al azar: %d mapa(s), %d zona(s), %d tropa(s)"
              % (len(encuentros["registros"]), len(encuentros["zonas"]),
                 cuantas))
    for cmd in de_archivo:
        if cmd.code == eventos.ENEMY_ENCOUNTER:
            tropas.pedir(eventos.tropa_de_encuentro(cmd),
                         eventos.fondo_de_encuentro(cmd))
    # El audio de la pelea, con los índices que ya sacó de `temas` mientras las
    # páginas compilaban. Se vuelve a pedir sólo para leerlos: `Temas` numera
    # una vez y devuelve lo mismo, y lo anotado va al paquete de la pelea y no
    # al de ningún mapa.
    audio_batalla = eventos.audio_de_batalla(temas) if tropas.ids else None
    # La escena de cada tropa que pelea con fondo: el fondo de batalla del
    # `EnemyEncounter` con los battlers de la tropa horneados encima. Ver
    # tools/port/escena.py, que es donde está el porqué y el presupuesto.
    escenas = []
    for numero in tropas.ids:
        fondo = tropas.fondos.get(numero)
        info = (escena_mod.convertir(renderer.database, numero, fondo,
                                     args.game_dir) if fondo else None)
        if info is None:
            if fondo:
                print("  la tropa %d pelea sin fondo: no encontré %r"
                      % (numero, fondo))
            continue
        escenas.append(info)
        datos = escena_mod.informe(info)
        print("  escena de la tropa %d sobre %r: %dx%d, %d tiles de 8bpp "
              "(%d B), %d colores desde la entrada %d de la CGRAM"
              % (datos["tropa"], datos["fondo"], escena_mod.ANCHO,
                 escena_mod.ALTO, datos["tiles"], datos["bytes"],
                 datos["colores"], escena_mod.CGRAM_BASE))
    informe = emit(args.output, mapas, args.inicial, args.heroe_encima, grupo,
                   ventana_datos, titulo_datos, ranuras_datos,
                   args.imagenes.info, animaciones, tropas.ids, audio_batalla,
                   escenas, encuentros)
    if len(args.casos) > 1:
        # Dónde escribe el arnés el número de caso: ver `--caso`.
        with open(args.output, "a") as handle:
            handle.write("\nCASO_RANURA = %d\n" % eventos.ranura_de_variable(
                eventos.VARIABLE_DE_CASO))
    print("%d mapa(s) -> %s, arranca en el %d (mapa %d)"
          % (len(mapas), args.output, args.inicial, mapas[args.inicial]["id"]))
    # Lo que decidió el asignador, como imágenes: para mirar qué colores se
    # perdieron y en qué paleta quedó cada celda sin armar ni correr la ROM.
    # Son indexadas y sus índices son entradas de CGRAM, así que un editor en
    # modo indexado las abre tal como las va a ver `tiles`.
    asignador = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                             "asignador")
    os.makedirs(asignador, exist_ok=True)
    for mapa in mapas:
        imagenes = list(mapa["imagenes_fondo"]) + [("encima", mapa["above"][5])]
        for nombre, png in imagenes:
            with open(os.path.join(asignador, "%04d-%s.png"
                                   % (mapa["id"], nombre)), "wb") as handle:
                handle.write(png)
    if informe:
        print("material compartido entre mapas:")
        for linea in informe:
            print(linea)

    # La música sale de acá y no de una receta aparte. `musicdata.inc` era
    # estado global como lo fue `mapdata.inc`, con el agravante de que nadie lo
    # regeneraba: una ROM armada para los mapas 4, 7, 19 y 1 —que no tienen
    # música— sonaba con el tema del mapa 348, que era el último que alguien
    # había generado a mano. Emitirlos juntos es lo único que garantiza que los
    # dos describan la misma ROM.
    #
    # Van **todos los temas que quepan**, compartiendo un solo banco de
    # muestras, y suena el del mapa donde la ROM arranca; los demás los prende
    # un `PlayBGM`. Lo que decide cuántos entran es la ARAM y no el cartucho:
    # ver `Banco` en snes_music.py, y "Varios temas en el cartucho" en el
    # README.
    musica = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                          "musicdata.inc")
    pedidos, arranque, tema_titulo = temas_de_la_rom(
        mapas[args.inicial]["id"], temas, args.game_dir,
        args.tema_de_arranque,
        renderer.database.title_music if args.con_titulo else None)
    # Los efectos, en el orden en que los piden las páginas compiladas: los
    # mapas se compilan en el orden de la ROM, así que los del mapa donde
    # arranca van primero —en la demo, la lluvia y el trueno de la apertura—.
    pedidos_se = []
    for nombre, _v, _t, _b in temas.sonidos:
        if nombre not in pedidos_se:
            pedidos_se.append(nombre)
    # Quién aporta primero al banco compartido: **el del título y el del
    # arranque**, y detrás la lista tal cual. El del título es la primera
    # pantalla del juego y hasta el 2026-09-12 iba último —`temas_de_la_rom` lo
    # agrega al final para no renumerar el bytecode—, así que era el primero en
    # caerse; un tema de un mapa que el jugador puede no visitar nunca le
    # ganaba la ARAM. Ningún tema se cae de la lista: ver `build_varios`.
    driver, muestras, hechos, banco, afuera = snes_music.build_varios(
        pedidos, args.game_dir, pedidos_se,
        prioridad=([] if args.banco_sin_prioridad
                   else [t for t in (tema_titulo, arranque) if t != 0xFF]),
        tope=(1 << 30) if args.banco_entero else None)
    # El paquete de audio de cada mapa, en el orden de la tabla de mapas: los
    # temas que sus páginas pueden prender —más, en el de arranque, el que
    # suena desde el principio— y las muestras de sus efectos, en el orden en
    # que aparecen, que es la prioridad con que la ROM los sube si no entran
    # todos. Ver `paquete_cargar` en main.s.
    efectos = getattr(banco, "efectos", {})
    paquetes = []
    for i, _mapa in enumerate(mapas):
        pide = temas.por_mapa.get(i, {"temas": [], "sonidos": []})
        suyos = list(pide["temas"])
        if i == args.inicial and arranque != 0xFF and arranque not in suyos:
            suyos.insert(0, arranque)
        paquetes.append((suyos, [efectos[n][0] for n in pide["sonidos"]
                                 if n in efectos]))
    # Y el paquete de la pelea, detrás de los mapas: el tema de batalla y sus
    # efectos, que la ROM sube al abrir la pelea y descarga al cerrarla. Va
    # aparte y no adentro del paquete del mapa porque el tema de batalla son
    # 51.480 B de los 64.512 de ARAM; ver `eventos.PAQUETE_BATALLA`.
    pide = temas.por_mapa.get(eventos.PAQUETE_BATALLA)
    if pide:
        assert len(paquetes) == len(mapas), (
            "el paquete de la pelea tiene que quedar en el índice que emitió "
            "`emit` como PAQUETE_BATALLA")
        paquetes.append((list(pide["temas"]),
                         [efectos[n][0] for n in pide["sonidos"]
                          if n in efectos]))
        print("  paquete de audio de la pelea: %d tema(s), %d efecto(s)"
              % (len(pide["temas"]), len(paquetes[-1][1])))
    snes_music.emit(musica, hechos, driver, muestras, arranque, tema_titulo,
                    snes_music.tabla_de_sonidos(temas.sonidos, banco),
                    paquetes)
    for i, (suyos, suyas) in enumerate(paquetes[:len(mapas)]):
        if suyos or suyas:
            print("  paquete de audio del mapa %d: %d tema(s), %d efecto(s)"
                  % (mapas[i]["id"], len(suyos), len(suyas)))
    if pedidos_se:
        print("  efectos de sonido: %d, %d B en el cartucho"
              % (len(efectos), sum(len(e.data) for _s, e in efectos.values())))
    print("música -> %s: %s"
          % (musica, ", ".join(t["nombre"] for t in hechos)
             or "ninguna, sale muda"))

    # **Y recién acá se decide el acomodo de bancos**, con los dos archivos ya
    # escritos: depende de todo lo que haya antes en RODATA, y el orden es el
    # de los `.include` de main.s —la música primero—. Ver `tools/ensamblado/bancos.py`.
    resueltos, rellenaron = bancos.resolver([musica, args.output])
    print("acomodo de bancos: %d bloque(s), %d empiezan banco"
          % (resueltos, rellenaron))
    # Y el mapa de memoria para `ld65`, al lado: sale de acá y no de un
    # archivo a mano para que en qué banco arrancan los datos esté escrito
    # una sola vez, en `bancos.PRIMER_BANCO`.
    with open(os.path.join(os.path.dirname(os.path.abspath(args.output)),
                           "memoria.cfg"), "w") as handle:
        handle.write(bancos.cfg())
    for i, tema in enumerate(hechos):
        # El porcentaje de notas que llegan al stream va acá y no escondido:
        # es lo que se oye como "le faltan voces", y hasta el 2026-09-14 no lo
        # decía nadie. Ver "Varios temas en el cartucho" en el README.
        suenan = tema["resumen"].get("notas")
        print("  %d. %-16s %4.0f s, %6d B de stream, %s de las notas%s"
              % (i, tema["nombre"], tema["segundos"], len(tema["stream"]),
                 "todas" if suenan is None or suenan > 0.999
                 else "%.0f%%" % (100 * suenan),
                 ", suena desde el arranque" if i == arranque else ""))
    if hechos:
        print("  banco compartido: %d muestras, %d B de los %d de ARAM"
              % (len(banco.voces), banco.bytes, snes_music.ARAM_LIBRE))
    if afuera:
        print("  no aportan muestras al banco: %s" % ", ".join(afuera))
        con_pista = [t for t in afuera if t in snes_music.PISTAS_MSU]
        print("    (existen igual, y suenan con lo que otros temas ya "
              "pusieron: el porcentaje de arriba dice cuánto)")
        # Cuáles de ésos tienen pista de MSU-1 se dice acá y no de memoria: el
        # 2026-09-14 esta línea afirmaba "hoy ninguno de éstos tiene" y en el
        # mismo commit habían pasado a tenerla todos.
        if con_pista:
            print("    con MSU-1 suenan enteros %d de ellos: %s"
                  % (len(con_pista), ", ".join(con_pista)))
        if len(con_pista) < len(afuera):
            print("    sin pista de MSU-1, o sea recortados siempre: %s"
                  % ", ".join(t for t in afuera
                              if t not in snes_music.PISTAS_MSU))


def temas_de_la_rom(map_id, temas, game_dir, forzado=None, titulo=None):
    """Qué temas pide el cartucho y cuál suena al arrancar.

    Se piden **todos**: los que los `PlayBGM` compilados nombran, más el del
    mapa donde la ROM arranca, que es el que suena sin que pase nada. **Y
    entran todos**: el índice lo da la lista y no cuesta ARAM. Lo que la ARAM
    limita son las muestras, y eso lo reparte `snes_music.build_varios`, que
    puede dejar a un tema sin las suyas —mudo por el SPC700, entero por
    MSU-1— pero nunca sin número.

    Los índices son los de `Temas` y no se tocan: el bytecode ya los lleva
    emitidos. Por eso el del mapa se agrega **al final**, que es lo único que
    no renumera a los demás; que ir último no signifique perder la ARAM lo
    arregla la prioridad que se le pasa a `build_varios`.
    """
    propio = forzado or snes_music.tema_del_mapa(map_id, game_dir)
    if propio:
        temas.indice(propio)            # lo agrega al final si no estaba
    # El de la pantalla de título va después, por lo mismo: agregar al final es
    # lo único que no renumera a los que el bytecode ya nombra. Sale del LDB
    # —`title_music`, que en el ABL es Fantasia_Of_The_Wind— y no de la línea
    # de comandos: es un dato del juego, no una elección nuestra.
    if titulo:
        temas.indice(titulo)
    nombres = list(temas.nombres)
    return (nombres, (nombres.index(propio) if propio else 0xFF),
            (nombres.index(titulo) if titulo else 0xFF))


def inicio_del_mapa(renderer, map_id, passable, width, height, ocupadas=()):
    """Dónde se para el héroe al entrar a este mapa, en celdas de 16x16.

    En el mapa donde el juego arranca de verdad, lo dice el LCF y no hay nada
    que elegir: A Blurred Line empieza en Map0004, que es una habitación vacía
    cuyo único trabajo es disparar un evento y teletransportar. Esa habitación
    no tiene ni una celda abierta por los cuatro lados, así que la heurística de
    abajo no tendría dónde poner a nadie.

    En cualquier otro mapa todavía no hay una respuesta real —se llega por
    teletransporte, y de dónde viene uno depende de por dónde entró—, así que se
    usa el tile abierto más cercano al centro, que es lo que las pruebas
    necesitan: un lugar desde el cual se pueda caminar.

    Está acá y no en cada llamador porque la referencia con la que se compara
    tiene que pararlo en el mismo lugar que la ROM.

    **Y hay mapas donde ninguna celda está abierta por los cuatro lados**: los
    cuartos de cinemática, que son una pantalla negra a la que siempre se llega
    por teletransporte con las coordenadas puestas. `LasheCityVehicle` —el mapa
    36, el que pregunta a dónde ir con el auto— es uno, y sin él no compila el
    teletransporte del 34 y se cae la cadena entera del auto. Ahí el número que
    se emite no lo usa nadie, pero la tabla lo lleva igual, así que se pone el
    centro geométrico en vez de cortar. El error de `hero_start` sigue valiendo
    para quien le pregunte por un mapa donde sí se va a caminar.
    """
    if map_id == renderer.tree.start_map_id:
        return renderer.tree.start_x, renderer.tree.start_y
    try:
        return hero_start(passable, width, height, ocupadas)
    except ValueError:
        return width // 2, height // 2


def images_de(renderer, args, charset):
    """El CharSet de un actor, cargado y cacheado."""
    if charset not in _charsets:
        _charsets[charset] = renderer.charsets.get(charset)
        if _charsets[charset] is None:
            sys.exit("no encuentro el CharSet %r" % charset)
    return _charsets[charset]


_charsets = {}


def lideres_posibles(renderer, map_ids, grupo):
    """Los actores que pueden llegar a dibujarse como héroe en esta ROM.

    El grupo con el que se arranca, más todos los que agregue un
    `ChangePartyMembers` de alguna página que compile. Sacar a alguien también
    cambia el líder, pero al siguiente de la lista, que ya está contado.

    Se compila con un bloque de textos, igual que la compilación de verdad:
    una página que agregue a alguien al grupo después de un cuadro de texto
    compila sólo con él. Filtrar distinto acá que allá dejaría a ese actor sin
    sus tiles en la VRAM y la ROM lo dibujaría con los del anterior. El bloque de textos que se arma es de
    descarte: acá sólo importa el sí o el no.

    Hace falta porque los tiles del héroe viven en VRAM y no se cargan en
    caliente: si el líder puede cambiar a mitad de mapa, los sprites de todos
    los candidatos tienen que estar puestos desde el principio.

    **Y son los que pueden ir primeros, no todos los que entran al grupo.** El
    gráfico del héroe es el del primero; alguien que siempre entra detrás de
    otro no se dibuja nunca, y sus doce poses son 192 tiles que no entran. Se
    nota en la cinemática de apertura, que saca al 10 y mete al 11, al 12 y al
    13: con los cuatro son 628 tiles de sprite y el reparto da 512.

    Quién va primero se sabe simulando: se aplican los `ChangePartyMembers` de
    las páginas que compilan, en el orden en que aparecen, con las mismas reglas
    que `Estado.cambiar_grupo`. Es una aproximación —qué página corre y cuándo
    depende de switches que acá no se saben— y por eso el orden importa: si
    alguna vez una ROM dibuja al héroe sin gráfico, empezar mirando acá.

    **El grupo se reinicia en cada mapa**, y ésa es la parte que costó. Antes se
    arrastraba de un mapa al siguiente en el orden de los archivos, que no es el
    orden en que se juegan: la página del "1 year earlier" del mapa 4 pone a
    Talan, y como el 4 va antes que el 1, cuando la simulación llegaba a la
    apertura el grupo ya tenía a Talan. El `pone Kersh` de la apertura lo metía
    **detrás**, así que Kersh nunca era líder, no entraba en la tabla de actores
    y el héroe se dibujaba sin gráfico. taro lo vio jugando: Core y Manta
    aparecían al final de la escalera y Kersh no.

    Reiniciar por mapa no es más correcto en general —sigue sin saberse con qué
    grupo se llega a cada uno— pero es la aproximación que corresponde: la tabla
    de actores es **por mapa**, así que la pregunta es quién puede liderar
    mientras ese mapa está cargado, y no qué pasó en los mapas anteriores del
    directorio.
    """
    actores = list(grupo[:1])
    indices = {m: i for i, m in enumerate(map_ids)}
    for map_id in map_ids:
        estado = eventos.Estado(grupo)
        game_map = lcf.Map(os.path.join(args_game_dir[0],
                                        "Map%04d.lmu" % map_id))
        del_mapa = eventos.Eventos(game_map)
        for evento in game_map.events:
            for page in evento.pages:
                # Con el contexto del mapa, que es el mismo que usa el filtro de
                # verdad. Sin él, una página que mande a caminar a otro evento no
                # compila acá aunque sí compile allá, y los actores que agregue
                # se pierden: la cinemática de apertura suma a Kersh al grupo
                # justo después de mandar a caminar al evento 8, así que el héroe
                # se quedaba sin tabla de poses y no se dibujaba.
                # **Con el mismo contexto que la compilación de verdad**, y
                # no sólo con el bloque de textos. Faltaban `Temas`,
                # `Graficos` e `Imagenes`, y sin ellos una página que empieza
                # con un `PlayBGM` no compila **acá** y sí compila allá: los
                # actores que meta al grupo se pierden. Es exactamente lo que
                # le pasaba al auto de la persecución —`RaceController1` del
                # mapa 49 arranca con `PlayBGM` y después mete a `CarRED`—, y
                # el síntoma era que el héroe no se dibujaba: `hero_poses` en
                # cero porque el actor no estaba en la tabla del mapa.
                if eventos.compilar_pagina(
                        page, indices.get,
                        eventos.Mensajes(),
                        del_mapa.para(evento.id), eventos.Temas(),
                        eventos.Graficos(), eventos.Imagenes(
                            args_game_dir[0])) is None:
                    continue
                for cmd in page.commands:
                    if cmd.code != eventos.CHANGE_PARTY_MEMBERS:
                        continue
                    p = cmd.parameters
                    if len(p) < 3 or p[1] != eventos.GRUPO_ID_FIJO:
                        continue
                    estado.cambiar_grupo(p[0], p[2])
                    lider = estado.lider()
                    if lider is not None and lider not in actores:
                        actores.append(lider)
    return actores


# El directorio del juego, para `lideres_posibles`. Es feo pero es un solo
# lugar: la alternativa era pasarlo por tres funciones que no lo usan.
args_game_dir = [GAME_DIR]


def items_posibles(map_ids, actores=(), db=None, extra=()):
    """Los ítems que pueden estar en el inventario con estos mapas en la ROM:
    los que da algún `ChangeItems` de cualquier página, compile o no, los que
    vende alguna `OpenShop`, el equipo con el que arrancan los `actores` y los
    que da la página de prueba. Es un superconjunto, como `miembros_posibles`,
    y por la misma razón: un ítem de más cuesta su texto en el cartucho, uno
    de menos no se ve en la lista. `extra` son los comandos de las páginas de
    prueba, que se barren igual que los de los mapas."""
    items = set()
    for actor in actores:
        if db is not None and actor in db.actors:
            items.update(i for i in db.actors[actor].initial_equipment if i)

    def barrer(comandos):
        for cmd in comandos:
            p = cmd.parameters
            if (cmd.code == eventos.CHANGE_ITEMS and len(p) >= 5
                    and p[0] == 0 and p[1] == 0):
                items.add(p[2])
            elif cmd.code == eventos.OPEN_SHOP:
                items.update(p[4:])

    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(args_game_dir[0],
                                        "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                barrer(page.commands)
    barrer(extra)
    return sorted(i for i in items if 0 < i < eventos.ITEMS_N)


def miembros_posibles(map_ids, grupo, extra=()):
    """Los actores que pueden estar en el grupo con estos mapas en la ROM.

    Los de arranque más los que agrega cualquier `ChangePartyMembers` de
    cualquier página de estos mapas. No se mira si la página compila: es para
    la pantalla de ranuras, que necesita la cara y el nombre de quien pueda
    aparecer en una partida guardada, y una cara de más no cuesta nada que
    importe. `extra` son los comandos de las páginas de prueba.

    `grupo` puede traer repetidos —el del cartucho más el de cada caso de
    prueba, que suele ser el mismo— y se cuentan una vez: repetido, un actor
    ocupaba una cara por cada caso que lo pedía.
    """
    actores = list(dict.fromkeys(grupo))

    def barrer(comandos):
        for cmd in comandos:
            if cmd.code != eventos.CHANGE_PARTY_MEMBERS:
                continue
            p = cmd.parameters
            if len(p) < 3 or p[1] != eventos.GRUPO_ID_FIJO:
                continue
            if p[0] == 0 and p[2] not in actores:
                actores.append(p[2])

    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(args_game_dir[0],
                                        "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                barrer(page.commands)
    barrer(extra)
    return sorted(actores)


def grupo_de_la_pagina(caso, grupo):
    """Con qué grupo sigue la prueba después de su página, si la página lo
    toca: los `ChangePartyMembers` del caso aplicados al grupo del cartucho,
    con las mismas reglas que el intérprete. None si no lo toca."""
    estado = eventos.Estado(grupo)
    toca = False
    for cmd in caso.comandos:
        p = cmd.parameters
        if (cmd.code == eventos.CHANGE_PARTY_MEMBERS and len(p) >= 3
                and p[1] == eventos.GRUPO_ID_FIJO):
            estado.cambiar_grupo(p[0], p[2])
            toca = True
    return estado.grupo if toca else None


def separar_del_heroe(renderer, game_map, args, comandos=()):
    """Si algo destella al héroe, los NPCs con su gráfico van con otra paleta.

    En la consola el destello se hace sobre la paleta del personaje, y un líder
    que además está como NPC en el mapa comparte paleta con ese NPC —para que el
    NPC no se dibuje con los colores de otro líder—, así que destellaban los
    dos. Se resuelve contando el gráfico de esos NPCs como otro, con el sufijo
    `rm2k.COPIA_SUFIJO`: el mismo dibujo, con su propia paleta. Cuesta una
    paleta por gráfico, y sólo en los mapas donde algo destella al héroe.
    `comandos` son los de las páginas de prueba.
    """
    destella = any(
        cmd.code == eventos.FLASH_SPRITE and cmd.parameters
        and cmd.parameters[0] == eventos.RUTA_HEROE
        for cmd in list(comandos) + [cmd for ev in game_map.events
                                     for page in ev.pages
                                     for cmd in page.commands])
    if not destella:
        return
    de_lider = set()
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        de_lider.add((a.charset, a.charset_index))
    for ev in game_map.events:
        for page in ev.pages:
            if (page.character_name, page.character_index) in de_lider:
                page.character_name += rm2k.COPIA_SUFIJO


# Los flags que describen **un caso** de prueba —lo que hace su página— y no
# el cartucho. Son los que pueden ir detrás de un `--caso`; los demás son del
# cartucho entero y van antes del primero. Desde el corte 3 del paso 9d es uno
# solo, el archivo con la página: lo que la página hace es dato de RM2k, no
# flags. `--grafico-de-prueba` es del cartucho a propósito: dice qué gráficos
# hay en el banco de sprites de los mapas donde corren los casos, no qué hace
# la página. Y dónde corre un caso tampoco es flag: lo dice el `Teleport` con
# que empieza, ver `mapa_del_caso`.
FLAGS_DE_CASO = ("comandos_de_prueba",)


def partir_en_casos(argv):
    """La línea de comandos partida en `--caso`: lo del cartucho, y los flags
    de cada caso que va detrás."""
    tramos = [[]]
    for token in argv:
        if token == "--caso":
            tramos.append([])
        else:
            tramos[-1].append(token)
    return tramos[0], tramos[1:]


def casos_de_prueba(parser, args, tramos):
    """Las páginas de prueba del cartucho, una por caso, en el orden de sus
    páginas. Cada una es una copia de `args` con los flags de su caso.

    El caso 0 son los flags de antes del primer `--caso`, así que un cartucho
    de un solo caso se arma como antes de que existiera esto. Si no hay, el
    primer `--caso` pasa a ser el 0. Cada caso se lleva los comandos de su
    archivo en `comandos`.
    """
    import copy
    casos = [args] if pide_pagina_de_prueba(args) else []
    defecto = parser.parse_args([])
    for tramo in tramos:
        suelto = parser.parse_args(tramo)
        for dest, valor in vars(suelto).items():
            if dest not in FLAGS_DE_CASO and valor != getattr(defecto, dest):
                sys.exit("--%s es del cartucho y no de un caso: va antes del "
                         "primer --caso" % dest.replace("_", "-"))
        caso = copy.copy(args)
        for dest in FLAGS_DE_CASO:
            setattr(caso, dest, getattr(suelto, dest))
        if not pide_pagina_de_prueba(caso):
            sys.exit("un --caso sin nada que la página de prueba haga")
        casos.append(caso)
    for caso in casos:
        with open(caso.comandos_de_prueba, encoding="utf-8") as archivo:
            caso.comandos = lcf.comandos(json.load(archivo))
    return casos


def comandos_de_casos(args, map_id=None):
    """Los comandos de todas las páginas de prueba, seguidos.

    Es lo que barren las funciones que miran las páginas del mapa para
    decidir qué lleva el cartucho —variables, ítems, miembros, lluvia—: una
    página de prueba es una página más.

    Con `map_id`, sólo los de los casos que **corren** en ese mapa —ver
    `mapa_del_caso`—: son los que deciden lo que es de cada mapa, como quién
    camina o qué gráficos van en su banco de sprites.
    """
    return [cmd for caso in args.casos
            if map_id is None or caso.mapa == map_id
            for cmd in caso.comandos]


def mapa_del_caso(caso, orden, inicial):
    """El mapa donde corre un caso: el de su `Teleport`, si empieza con uno, y
    si no el mapa donde arranca la ROM.

    Es como un caso elige dónde arrancar desde el paso 9e, en vez de un
    `--map-id` y un `--inicio` por cartucho: con el `Teleport` de RM2k, que
    es dato y no flag. La página vive igual en el evento 0 del mapa de
    arranque —ahí la encuentra la ROM y ahí corre primero—, pero lo que viene
    después del salto corre en el otro mapa, así que se compila con su
    contexto: sus eventos, las variables que miran sus páginas, sus gráficos.
    Compilada con el del mapa de arranque, una escritura a una variable que
    sólo mira el destino no pedía refresco, y el cofre del mapa 133 no
    aparecía aunque la variable ya valía lo que su página pide.
    """
    primero = caso.comandos[0] if caso.comandos else None
    if primero is None or primero.code != eventos.TELEPORT:
        return orden[inicial]
    destino = primero.parameters[0]
    if destino not in orden:
        sys.exit("%s: el caso salta al mapa %d, que no está en el cartucho "
                 "(lleva %s)" % (caso.comandos_de_prueba, destino,
                                 " ".join(str(m) for m in orden)))
    return destino


def mapas_de_prueba(args):
    """Los mapas donde corre algún caso, que son los que llevan en su banco
    los gráficos de `--grafico-de-prueba`."""
    if args.casos:
        return {caso.mapa for caso in args.casos}
    return {orden_de_mapas(args)[args.inicial]}


def pagina_de_caso(caso, mapa, temas, graficos, mensajes, indices, imagenes):
    """El bytecode de la página de prueba de un caso.

    Se compila como cualquier página del juego, con el contexto del mapa donde
    corre —ver `mapa_del_caso`—; lo único que el conversor le antepone es el
    `ControlSwitches` que la apaga, que es convención del arnés y no del caso
    —ver `eventos.SWITCH_DE_PRUEBA`—. Las tropas no se anotan acá sino al
    final, en `main`: la de la prueba va última.
    """
    apagar = lcf.EventCommand(
        eventos.CONTROL_SWITCHES, 0, "",
        [eventos.SWITCH_UNICO, eventos.SWITCH_DE_PRUEBA,
         eventos.SWITCH_DE_PRUEBA, eventos.SWITCH_ON])
    codigo = eventos.compilar_pagina(
        eventos._Comandos([apagar] + list(caso.comandos)), indices.get,
        mensajes, eventos.Eventos(mapa["game_map"]).para(0), temas,
        graficos, imagenes)
    if codigo is None:
        sys.exit("%s: la página de prueba no compila"
                 % caso.comandos_de_prueba)
    return codigo

def pide_pagina_de_prueba(args):
    """Si hay una página de prueba antes del primer `--caso`."""
    return bool(args.comandos_de_prueba)

def convertir(renderer, map_id, args, inicio=None):
    """Un mapa entero: tiles, colores, sprites, colisión y bloques."""
    game_map = renderer.cargar_mapa(
        os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    if args.casos and map_id == orden_de_mapas(args)[args.inicial]:
        # El evento de la página de prueba va **primero**: la ROM recorre los
        # eventos de menor a mayor, y la página de prueba tiene que correr
        # antes que las del juego. Arma el grupo con el que arranca la prueba,
        # y un mapa cuya página toca el grupo al entrar —el 21 agrega a Talan—
        # lo encontraba ya cambiado. Es un evento sin páginas: no se dibuja ni
        # compila nada, sólo ocupa el índice 0 para que todo lo que numera
        # eventos después de leer el mapa numere igual.
        vacio = lcf.Event.__new__(lcf.Event)
        vacio.id, vacio.name, vacio.x, vacio.y, vacio.pages = (
            0, "prueba", 0, 0, [])
        game_map.events.insert(0, vacio)
    separar_del_heroe(renderer, game_map, args,
                      comandos_de_casos(args, map_id))
    name = renderer.tree.map_names.get(map_id, "?")

    base, _above, variantes = renderer.capas_animadas(game_map)

    if base is None:
        sys.exit("no encuentro el chipset del mapa %d" % map_id)

    (tile_data, cram, tilemap, summary), above_data = convert_layers(
        base, _above, variantes=variantes)

    # Los personajes: el héroe con sus 12 poses porque camina, y cada NPC con la
    # que declara su página. Si un NPC usa el mismo personaje que el héroe,
    # comparten paleta y tiles sin que haya que hacer nada.
    #
    # Los dígitos del cronómetro se llevan una de las ocho paletas de sprite,
    # así que el techo baja a siete. Los eventos dibujados con un tile del
    # chipset entran mientras quepan en ese techo; la referencia dibuja
    # exactamente los mismos, con la misma función.
    # Quiénes van a caminar y a qué gráficos cambian las rutas. Va **antes**
    # del reparto de paletas porque un gráfico de la orden 34 es un personaje
    # más y pide paleta como cualquiera: repartiendo sin contarlo, entraría
    # después y podía no haber lugar.
    orden = orden_de_mapas(args)
    movibles, graficos_de_ruta, anima_quieto, giran = eventos_movibles(
        game_map, {m: i for i, m in enumerate(orden)}.get,
        asociaciones=args.asociaciones)
    # Y los de `--grafico-de-prueba`, que van sólo en los mapas donde corre
    # algún caso, y por lo mismo que sus páginas se compilan con el contexto
    # de ese mapa. Se agregan **después** de los del juego, que es el orden
    # en que los numera la compilación de verdad.
    if args.grafico_de_prueba and map_id in mapas_de_prueba(args):
        for charset, index in graficos_de_prueba(args.grafico_de_prueba):
            if (charset, index) not in graficos_de_ruta:
                graficos_de_ruta.append((charset, index))
    if comandos_de_casos(args, map_id):
        # Y los que mandan a caminar las páginas de prueba, que no salen de
        # `paginas_del_mapa`: hay que sumarlos a mano o el NPC caminaría con
        # una sola pose. Va **antes** del reparto de paletas: desde que la
        # paleta se elige sobre las poses que se ven, saber quién camina es
        # parte de elegir los colores y no sólo de repartir la VRAM. El evento
        # va por su id de RM2k y lo traduce el mismo `Eventos` que usa la
        # compilación.
        del_mapa = eventos.Eventos(game_map)
        for cmd in comandos_de_casos(args, map_id):
            if cmd.code == eventos.MOVE_EVENT and cmd.parameters \
                    and cmd.parameters[0] != eventos.RUTA_HEROE:
                blanco = del_mapa.blanco(cmd.parameters[0])
                if blanco:
                    movibles = movibles | {blanco - 1}
    # Y con eso, qué poses puede mostrar cada gráfico: es lo que decide sobre
    # qué píxeles se eligen sus quince colores. Ver `poses_del_mapa`.
    poses_por_grafico = poses_del_mapa(renderer, game_map, args.lideres,
                                       movibles, giran, graficos_de_ruta,
                                       anima_quieto)

    # Las ocho, con o sin cronómetro: sus dos colores entran en la paleta de
    # algún personaje. Reservarle una acá le sacaba eventos al mapa, porque este
    # número es el que decide cuáles se dibujan.
    #
    # **Menos una en los mapas que muestran animaciones de batalla**, desde el
    # 2026-09-12: la caja necesita una paleta entera para ella sola —sus quince
    # colores son de la animación y se pisan cuando empieza otra— y los mapas
    # 2 y 3, que son los de la intro, llenaban las ocho. Sin esto la escena del
    # Emitter Room se quedaba sin dibujo, que es justo lo que se estaba
    # haciendo. Lo que cuesta —qué personajes fusionan más colores— lo dice el
    # informe de cada mapa.
    muestra_animacion = mapa_muestra_animacion(
        game_map, renderer,
        comandos_de_casos(args, map_id))
    # Los colores del cronómetro se pasan al reparto y no sólo al empaquetado:
    # en un mapa que llene las ocho paletas hay que decidir a quién bajarle un
    # color para hacerle lugar, y eso cambia cómo se cuantiza a ese personaje.
    timer_colores = ()
    if map_id in args.timer_en:
        from port import ventana as ventana_mod
        timer_colores = sorted(colores_del_timer(ventana_mod.skin(
            args.game_dir, renderer.database.system_name)))
    solos = {c for c, n in getattr(args, "mapas_por_personaje", {}).items()
             if n == 1}
    tope_de_paletas = tope_de_paletas_del_mapa(
        renderer, game_map, args.lideres, graficos_de_ruta, timer_colores,
        solos, poses_por_grafico, muestra_animacion)

    npcs, descartados, reparto = npcs_dibujables(renderer, game_map,
                                                 args.lideres, tope_de_paletas,
                                                 graficos_de_ruta,
                                                 timer_colores,
                                                 solos,
                                                 poses_por_grafico)
    prestadas = reparto[5]
    if prestadas:
        print("  mapa %d: %d gráfico(s) sin paleta propia, dibujados con una "
              "ajena: %s" % (map_id, len(prestadas),
                             ", ".join(sorted("%s:%d" % k for k in prestadas))))
    for evento, tile in descartados:
        aviso_de_descarte(
            "mapa %d: el evento %d, dibujado con el tile %s, no entra en "
            "las %d paletas de sprite y no se dibuja"
            % (map_id, evento + 1, tile[len(rm2k.TILE_PREFIX):],
               tope_de_paletas),
            cambia_de_grafico(game_map.events[evento]))
    # Quiénes cambian de pose y por lo tanto llevan sus doce al cartucho: los
    # candidatos a líder con gráfico y los NPCs que caminan. En ese orden, con
    # el líder inicial primero, que es el orden que espera el resto.
    actores_con_grafico = []
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        if not sprite_colors(images_de(renderer, args, a.charset),
                             a.charset_index):
            continue            # no tiene un solo pixel opaco: no se dibuja
        actores_con_grafico.append(actor)
    primero = renderer.database.lider(args.lideres)   # (CharSet, índice)
    animados = []
    for actor in actores_con_grafico:
        a = renderer.database.actors[actor]
        if (a.charset, a.charset_index) not in animados:
            animados.append((a.charset, a.charset_index))
    animados.sort(key=lambda par: par != primero)   # el líder inicial primero
    for npc in npcs:
        if npc["evento"] in movibles \
                and (npc["charset"], npc["index"]) not in animados:
            animados.append((npc["charset"], npc["index"]))
    # Y los gráficos a los que una orden 34 cambia. Van al banco por lo mismo
    # que los que caminan: después de cambiar, el evento sigue caminando, así
    # que le hacen falta las doce poses del gráfico nuevo y no la que declaraba
    # su página.
    #
    # Los que no tienen **un solo pixel opaco** no entran, y no es un caso
    # raro: `nobodyhere` son 185 de las 437 órdenes 34 del juego. Un CharSet
    # transparente no tiene colores, así que no tiene paleta que pedirle al
    # banco; y no hace falta, porque lo que la orden hace ahí es esconder la
    # fila. Es el mismo `sprite_colors` con que se descarta a un actor sin
    # gráfico.
    grafico_se_ve = []
    for charset, index in graficos_de_ruta:
        # Se dibuja si tiene un pixel opaco **y** entró en el reparto de
        # paletas. Lo segundo casi siempre es que sí; cuando no, la orden lo
        # esconde igual que a un transparente, que es lo que hace la ROM con
        # cualquier gráfico que no entró.
        grafico_se_ve.append(
            bool(sprite_colors(images_de(renderer, args, charset), index))
            and (charset, index) in reparto[1])
        if grafico_se_ve[-1] and (charset, index) not in animados:
            animados.append((charset, index))
    # Y los que giran hacia el héroe: sus doce poses, para subir la que mira
    # hacia él. Van al final para no mover el índice de nadie más.
    for pares in giran.values():
        for par in sorted(pares):
            if par in reparto[1] and par not in animados:
                animados.append(par)
    afuera_de_ruta = [par for par, se_ve in zip(graficos_de_ruta, grafico_se_ve)
                      if not se_ve and sprite_colors(
                          images_de(renderer, args, par[0]), par[1])]
    for charset, index in afuera_de_ruta:
        aviso_de_descarte(
            "mapa %d: el gráfico %s:%d, al que cambia una ruta, no entra "
            "en las %d paletas de sprite: esa orden esconde al evento en vez "
            "de cambiarlo" % (map_id, charset, index, tope_de_paletas),
            # Una orden 34 **es** un cambio de gráfico, así que siempre cuenta.
            True)

    # Las ranuras del banco de VRAM, una pose cada una: el héroe en el bloque
    # 0 —si algún candidato a líder tiene gráfico—, después cada NPC que camina
    # con la suya, y los quietos compartidas por (CharSet, índice, pose), que
    # nunca cambian. Un NPC que camina no comparte ni con otro igual: cambian
    # de pose cada uno por su cuenta.
    ranuras = []
    if actores_con_grafico:
        charset, index = animados[0]
        ranuras.append(("heroe", charset, index, POSE_INICIAL))
    for npc in npcs:
        if npc["evento"] in movibles:
            if npc["cambia"]:
                # Dos mecanismos sobre la misma fila: las doce poses del
                # cartucho y el gráfico de la página. La ROM no sabe las dos a
                # la vez, así que **gana caminar** y su gráfico deja de seguir a
                # la página. Es lo mismo que hacía antes de que `collect_npcs`
                # contara el "nada" como un estado —ver `cambia` allá—, o sea
                # que no se pierde nada que antes anduviera.
                #
                # Esto era un `sys.exit`, y estaba bien mientras ningún evento
                # lo pidiera. Al contar el estado "nada" lo pide el evento 10
                # del mapa 8, y cortar por eso sería no armar la ROM por un
                # detalle de un NPC que camina.
                # Lo que **sí** sigue a la página es si la fila se ve: eso es
                # el bit 4 y no pisa el tile. Sin separarlos, un evento que
                # camina y aparece con la página no aparecía nunca, porque la
                # fila nace escondida cuando al cargar el mapa ninguna página
                # cumple. Ver `grafico_de_pagina` en main.s.
                npc["aparece"] = True
                npc["cambia"] = False
            ranuras.append((("ev", npc["evento"]), npc["charset"],
                            npc["index"], npc["pose"]))
        else:
            # La pose de su fila y, si el gráfico sigue a la página, la de
            # cada página: el refresco de la ROM elige entre ranuras que ya
            # están en la VRAM.
            poses = [(npc["charset"], npc["index"], npc["pose"])]
            if npc["cambia"]:
                poses += [g for g in npc["graficos"]
                          if g is not None and g[:2] not in npc["afuera"]]
            for clave in poses:
                if clave not in {r[0] for r in ranuras}:
                    ranuras.append((clave,) + clave)
    # La ranura de giro: una pose más, para el quieto que se da vuelta hacia
    # el héroe. Los quietos comparten ranura por (CharSet, índice, pose), así
    # que girar la suya giraría también a los demás que la usan; el que gira
    # se muda a ésta mientras dura su página. Es una sola porque sólo gira el
    # evento que el héroe disparó, y hay uno a la vez. Los que caminan o
    # animan no la necesitan: tienen la suya. Ver GIRO en eventos.py.
    quietos_que_giran = [npc for npc in npcs
                         if npc["evento"] in giran
                         and npc["evento"] not in movibles
                         and any(par in reparto[1]
                                 for par in giran[npc["evento"]])]
    if quietos_que_giran:
        npc = quietos_que_giran[0]
        ranuras.append(("giro", npc["charset"], npc["index"], npc["pose"]))
    personajes = list(animados)
    for _clave, charset, index, _pose in ranuras:
        if (charset, index) not in personajes:
            personajes.append((charset, index))

    images = {}
    for charset, _index in personajes:
        if charset not in images:
            # Por el cargador del renderer, que también fabrica el CharSet de
            # un evento dibujado con un tile del chipset.
            images[charset] = renderer.charsets.get(charset)
            if images[charset] is None:
                sys.exit("no encuentro el CharSet %r" % charset)

    tiles, palettes, where, paleta_de, colores = build_characters(
        images, personajes, ranuras, reparto)
    # Se cuenta acá y no adentro porque el mensaje tiene que nombrar al
    # culpable, que es el mapa. Con `npcs_dibujables` arriba esto ya no
    # tendría que fallar por un tile; si falla es por los CharSets.
    if len(palettes) > tope_de_paletas:
        sys.exit("el mapa usa %d personajes en %d paletas y hay %d de sprite"
                 % (len(personajes), len(palettes), tope_de_paletas))
    bancos = banco_de_poses(images, animados, colores)
    indice_animado = {p: k for k, p in enumerate(animados)}
    # La tabla de la orden 34: por cada gráfico que una ruta pide, en qué
    # entrada de `npc_poses` está y con qué paleta. $FF en la entrada es
    # "esconder la fila", que es lo que hace un CharSet transparente.
    ruta_graficos = [
        (indice_animado[par], paleta_de[par]) if se_ve else (0xFF, 0)
        for par, se_ve in zip(graficos_de_ruta, grafico_se_ve)]
    # El cronómetro, si esta ROM lo lleva: sus glifos van al final del banco y
    # comparten paleta con quien tenga lugar, que casi siempre hay.
    timer_base, timer_pal = 0, None
    if map_id in args.timer_en:
        from port import ventana as ventana_mod
        sys_img = ventana_mod.skin(args.game_dir, renderer.database.system_name)
        tiles, timer_base, timer_pal = digitos_del_timer(
            sys_img, tiles, palettes, reparto[3],
            tope_de_paletas)
    lluvia_base, lluvia_pal = 0, 0
    if args.con_lluvia:
        tiles, lluvia_base, lluvia_pal = gotas_de_lluvia(
            tiles, palettes, reparto[3],
            timer_base, tope_de_paletas)
        if not lluvia_base:
            print("  mapa %d: AVISO, las gotas de lluvia no entran en las "
                  "paletas de sprite y acá no llueve" % map_id)
    # El cartel del `ShowPicture`, si el suyo es de este mapa. La ranura la
    # elige `Imagenes.elegir` **en el orden de la tabla de mapas**, que es este
    # mismo lazo, y la referencia elige igual mirando todos los mapas de una.
    imagen_base, imagen_pal = 0, 0
    registro = getattr(args, "imagenes", None)
    if registro is not None:
        info = registro.elegir([game_map])
        if info is not None and registro.mapa is None:
            registro.mapa = map_id
        if info is not None and registro.mapa == map_id:
            tiles, imagen_base, imagen_pal = cartel_de_imagen(
                info, tiles, palettes, lluvia_base or timer_base)
            if not imagen_base:
                sys.exit("mapa %d: el cartel %r no entra: el mapa ya usa las "
                         "%d paletas de sprite y el fundido necesita una "
                         "entera. Ver `cartel_de_imagen`."
                         % (map_id, registro.nombre, OBJ_PALETTES))
            print("  mapa %d: el cartel %r, %d objetos en %d tiles desde el "
                  "%d, paleta %d" % (map_id, registro.nombre,
                                     info["objetos"],
                                     imagen.tiles_reservados(info),
                                     imagen_base, imagen_pal))
    # Y la caja de la animación de batalla, si alguna página de este mapa
    # puede mostrar una que se dibuje. Va última porque se lleva el final del
    # banco y la paleta que quede libre después del cartel. El criterio de
    # que entre es una cuenta y la emite el conversor: si no hay paleta o no
    # hay VRAM, **este mapa no dibuja animaciones** y lo dice.
    anim_base, anim_pal = 0, 0
    if muestra_animacion:
        probando, probando_base, probando_pal = animacion_de_mapa(
            tiles, palettes, 1 if imagen_base else 0)
        if not probando_base:
            # Sin paleta este mapa no dibuja animaciones. Es lo mismo que se
            # hace con las gotas de lluvia: se declara y se sigue.
            print("  mapa %d: AVISO, las animaciones de batalla no se dibujan "
                  "acá: el mapa ya usa las %d paletas de sprite y la caja "
                  "necesita una entera" % (map_id, OBJ_PALETTES))
        else:
            # La VRAM, en cambio, **corta**: que entre o no depende del reparto
            # de tiles y no de las paletas, y la referencia no lo puede
            # recalcular sin rehacer el banco entero. Antes que dibujar de un
            # lado y del otro no, se dice cuál es el mapa.
            cuantos = len(probando) // 32
            try:
                layout = vram_layout(len(tile_data) // BYTES_PER_TILE, cuantos)
            except SystemExit:
                layout = None
            if layout is None or cuantos > layout["sprites"][1]:
                sys.exit(
                    "mapa %d: muestra animaciones de batalla y los %d tiles de "
                    "su caja no entran en el banco de sprites: gasta %d de %d. "
                    "Ver `animacion_de_mapa`."
                    % (map_id, animacion_mod.TILES, cuantos,
                       layout["sprites"][1] if layout else 0))
            tiles, anim_base, anim_pal = probando, probando_base, probando_pal
            print("  mapa %d: las animaciones de batalla se dibujan en %d "
                  "tiles desde el %d, paleta %d"
                  % (map_id, animacion_mod.TILES, anim_base, anim_pal))
    table = npc_table(npcs, where, movibles, indice_animado, anima_quieto)
    # Por cada candidato a líder, su paleta y en qué banco de poses están las
    # doce suyas. La ROM no calcula nada a partir de la pose: busca el puntero
    # acá y lo encola.
    actores = []
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        if actor not in actores_con_grafico:
            # Un actor con el gráfico vacío. `DummyHero`, el 10, es así: sus
            # ocho poses no tienen un pixel opaco, y RM2k no dibuja nada. Va con
            # el puntero centinela y la ROM se saltea el objeto.
            actores.append((actor, 0, None, []))
            continue
        # Sus colores, en el mismo orden que el `lookup` con que se empaquetaron
        # sus poses: `paleta_del_personaje` devuelve la paleta ordenada y
        # `build_characters` indexa 1..15 sobre ella. Si los dos órdenes se
        # fueran, el héroe saldría con los colores cambiados de lugar.
        propia, _, _ = paleta_del_personaje(
            images[a.charset], a.charset_index)
        actores.append((actor, paleta_de[(a.charset, a.charset_index)],
                        indice_animado[(a.charset, a.charset_index)],
                        [cgram_word(c) for c in propia]))
    giro_tile = (block_tile(where["giro"][0]) if "giro" in where
                 else GIRO_NINGUNO)
    sprite = (tiles, palettes, where, table, actores, timer_base, timer_pal,
              animados, bancos, ruta_graficos, lluvia_base, lluvia_pal,
              giro_tile, imagen_base, imagen_pal, anim_base, anim_pal)

    # La colisión: un byte por celda de 16x16 con los cuatro bits de dirección
    # ya resueltos. Toda la lógica de RM2k —que la capa alta manda salvo que sea
    # decorado, que las caras de pared se cruzan siempre— se decide acá, no en
    # la consola.
    chipset = renderer.database.chipsets[game_map.chipset_id]
    flags = build_passability(chipset)
    passable = passability_map(game_map, flags)
    # Las celdas con un NPC quedan afuera: si el héroe arrancara sobre uno, los
    # dos tendrían la misma clave de orden y cuál queda encima dependería de un
    # desempate que no tiene por qué coincidir entre la consola y el render.
    # Con **todos** los que se dibujan en alguna página, que es lo que mira
    # la referencia: un tile que quedó afuera de las paletas igual ocupa.
    ocupadas = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
    start_x, start_y = inicio or inicio_del_mapa(
        renderer, map_id, passable, game_map.width, game_map.height, ocupadas)
    collision = (passable, start_x, start_y, game_map.width, game_map.height)

    if len(table) > NPC_MAX:
        sys.exit("el mapa %d tiene %d NPCs y en OAM entran %d"
                 % (map_id, len(table), NPC_MAX))
    if len(ruta_graficos) > RUTA_GRAF_MAX:
        sys.exit("el mapa %d tiene %d gráficos de orden 34 y entran %d: ver "
                 "RUTA_GRAF_MAX" % (map_id, len(ruta_graficos), RUTA_GRAF_MAX))

    print("Mapa %d %r: %dx%d celdas de %dx%d px"
          % (map_id, name, len(tilemap[0]), len(tilemap),
             CELL, CELL))
    print("  %d colores distintos, %d en CGRAM de %d disponibles, %d fusionados"
          % (summary["colores"], summary["usados"], summary["presupuesto"],
             summary["fusionados"]))
    print("  %d tiles únicos de %d celdas (%.0f%% de reuso)"
          % (summary["tiles"], summary["celdas"],
             100.0 * (1 - summary["tiles"] / summary["celdas"])))

    print("  sprites: %d personajes, %d ranuras, %d tiles en VRAM, %d paletas; "
          "%d con sus doce poses en el cartucho"
          % (len(personajes), len(where), len(tiles) // 32, len(palettes),
             len(animados)))
    print("  %d NPCs con CharSet de %d eventos" % (len(table), len(game_map.events)))

    abiertos = sum(1 for b in passable if b == 0x0F)
    print("  colisión: %d celdas, %d abiertas por los cuatro lados (%.0f%%), "
          "el héroe arranca en (%d,%d)"
          % (len(passable), abiertos, 100.0 * abiertos / len(passable),
             start_x, start_y))

    print("  capa por encima del héroe: %d tiles, %d colores en %d paleta(s) "
          "desde la %d, %d fusionados"
          % (len(above_data[0]) // 32, len(above_data[1]) // 2,
             BG_PALETTES - above_data[3], above_data[3], above_data[4]))

    celdas, bloques, block_pass = build_blocks(tilemap, above_data[2], passable,
                                               game_map.width, game_map.height)
    print("  el mapa entra en %d bloques de 16x16 para %d celdas: %d B de "
          "grilla más %d B de tabla, contra los %d B del tilemap expandido"
          % (len(bloques) // BLOCK_BYTES, len(celdas), 2 * len(celdas),
             len(bloques), 2 * summary["celdas"]))
    ventanas_x = (len(tilemap[0]) + WINDOW_W - 1) // WINDOW_W
    ventanas_y = (len(tilemap) + WINDOW_H - 1) // WINDOW_H
    if ventanas_x > 1 or ventanas_y > 1:
        print("  no entra en la ventana de %dx%d: la ROM va a ir redibujando"
              % (WINDOW_W, WINDOW_H))

    words = bytearray()
    for cell in celdas:
        words += cell.to_bytes(2, "little")
    colors = bytearray()
    for word in cram:
        colors += word.to_bytes(2, "little")

    return {
        "id": map_id, "nombre": name,
        "tiles": tile_data, "cram": bytes(colors), "cram_words": cram,
        "tilemap": tilemap, "above": above_data, "sprite": sprite,
        # Los gráficos de la orden 34 tal como los numeró la pasada que arma
        # el banco. `main()` compara contra los que junte compilando de
        # verdad: si las dos pasadas se fueran, el bytecode llevaría índices
        # de una tabla que dice otra cosa.
        "graficos_de_ruta": graficos_de_ruta,
        "collision": collision, "celdas": bytes(words),
        "ev_pos": ev_pos_bytes(game_map),
        "bloques": bloques, "pass": block_pass,
        "layout": vram_layout(
            len(tile_data) // BYTES_PER_TILE,
            len(sprite[0]) // 32 if sprite else 0),
        "resumen": summary,
        "anim": anim_bytes(summary["animacion"]),
        "imagenes_fondo": summary["imagenes"],
        "puertas_crudas": rm2k.collect_doors(game_map),
        # Se guarda el mapa entero porque las puertas y los eventos no se
        # pueden resolver hasta que estén todos: los dos traducen ids de mapa a
        # índices de la tabla.
        "game_map": game_map,
        # Para la tabla de páginas: dónde quedó cada (CharSet, índice, pose)
        # en el banco de sprites, qué eventos cambian de gráfico con la
        # página y qué gráficos suyos quedaron afuera de las paletas.
        "where": where,
        # Para el giro hacia el héroe: en qué entrada de `npc_poses` están las
        # doce poses de cada gráfico, que es el +30 de la página.
        "giro_k": {par: indice_animado[par] for par in animados},
        "giran": set(giran),
        "cambian": {npc["evento"] for npc in npcs if npc["cambia"]},
        # Y los que sólo aparecen y desaparecen con ella: los que caminan, a
        # los que el gráfico se les fijó más arriba.
        "aparecen": {npc["evento"] for npc in npcs if npc.get("aparece")},
        "afuera": {npc["evento"]: npc["afuera"] for npc in npcs},
    }


if __name__ == "__main__":
    main()
