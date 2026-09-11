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
    python3 tools/snes_convert.py --map-id 7 -o rom/src/mapdata.inc
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import event_codes
import eventos
import lcf
import rm2k
import pixeles
import titulo as titulo_mod
import pantallas as pantallas_mod
import snes_music
from pixeles import CELL, cut_tiles, flips, reduce_colors, tile_colors, to_indices
from rm2k import collect_npcs, hero_start, passability_map
from render_map import (GAME_DIR, REPO, RTP_DIR, Renderer, build_passability,
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
# pantalla, los mismos números que `tools/ventana.py`.
VENTANA_COLS_INC, VENTANA_FILAS_INC = 32, 10

# El glifo, que es lo que la ROM compone. Los mismos números que
# `tools/fuente.py`, que se genera desde easyrpg-player.
FUENTE_ANCHO, FUENTE_ALTO = 6, 12

# Y las de los objetos, ya corridas a su lugar en el byte vhoopppN: la
# prioridad son los bits 5 y 4. Estos dos valores son los únicos del
# programa: la ROM recibe el del héroe en HERO_PRIORITY y el de cada NPC
# viene armado en su byte de atributos.
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
# El color con que `render_above` dibuja lo que la capa de encima no toca, para
# recortarlo: uno que ningún tile del juego usa.
CLAVE_RECORTE = (31, 0, 31)


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


def convert_above(image, palettes=None, grid=None):
    """La capa que va por encima del héroe: tiles de 4 bits y su tilemap.

    Es mucho más chica que la de abajo —en Map0073 son 419 celdas de 900, con
    siete colores— así que casi siempre entra en una o dos paletas. Las celdas
    vacías apuntan al tile 0, que se deja transparente a propósito.

    `palettes` es cuántas le concede el reparto; sin él se lleva las que pida
    hasta el tope. Si no le alcanzan, fusiona.

    Devuelve (tiles, palabras de CGRAM, tilemap, primera paleta, fusionados).
    """
    if grid is None:
        grid = cut_tiles(quantize(image))
    limite = MAX_ABOVE_PALETTES if palettes is None else palettes
    sets = {tile_colors(t) for row in grid for t in row}
    sets = {s for s in sets if s}
    groups = pixeles.try_pack(sets, limite) if sets else []
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
        grid, groups, merged, _ = pixeles.reduce_colors(grid, limite)
    palettes = [sorted(g) for g in groups]
    # Sin capa de encima no se reserva nada, pero el DMA igual manda una paleta
    # vacía (ver abajo), así que el corte se cuenta como si hubiera una.
    above_first = above_split(max(1, len(palettes)))

    blank = tuple(tuple(0 for _ in range(CELL)) for _ in range(CELL))
    pool = {(0, blank): 0}
    tiles = bytearray(32)
    tilemap = []
    for row in grid:
        line = []
        colors_of = tile_colors
        for tile in row:
            colors = colors_of(tile)
            if not colors:
                line.append(entry(0, 0, 0))
                continue
            index = next(i for i, pal in enumerate(palettes)
                         if colors <= set(pal))
            indices = to_indices(tile, palettes[index])

            placed = None
            for oriented, horizontal, vertical in flips(indices):
                if (index, oriented) in pool:
                    placed = entry(pool[(index, oriented)], horizontal, vertical,
                                   PRIORITY_ABOVE)
                    placed |= (above_first + index) << 10
                    break
            if placed is None:
                number = len(pool)
                pool[(index, indices)] = number
                tiles += bytes(32)
                tiles[number * 32:(number + 1) * 32] = pack_tile(indices, planes=4)
                placed = entry(number, 0, 0, PRIORITY_ABOVE)
                placed |= (above_first + index) << 10
            line.append(placed)
        tilemap.append(line)

    cram = bytearray()
    for palette in palettes:
        cram += cgram_word(BACKDROP).to_bytes(2, "little")
        for color in palette:
            cram += cgram_word(color).to_bytes(2, "little")
        cram += bytes(2 * (COLORS_PER_PALETTE - 1 - len(palette)))

    # Nunca cero: en la consola un DMA de tamaño cero transfiere 65536 bytes, no
    # ninguno. Un mapa sin capa de encima mandaba una paleta vacía y arrasaba
    # CGRAM entera, paletas de sprites incluidas. Se emite una paleta vacía.
    if not cram:
        cram = bytearray(2 * COLORS_PER_PALETTE)
    return bytes(tiles), bytes(cram), tilemap, above_first, len(merged)


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
SPRITE_PALETTE = 8                 # los sprites usan las paletas 8 a 15
OBJ_PALETTES = 8                   # y son ocho, con cronómetro o sin él

# La tabla de nombres de OAM tiene 16 tiles de ancho, así que un objeto de
# 32x32 no ocupa 16 tiles seguidos sino un bloque de 4x4 dentro de esa grilla.
OBJ_ROW = 16


def pose_origin(index, pose):
    """Dónde empieza una pose dentro del CharSet."""
    return ((index % 4) * SPRITE_W * 3 + (pose % 3) * SPRITE_W,
            (index // 4) * SPRITE_H * 4 + (pose // 3) * SPRITE_H)


def sprite_colors(image, index):
    """Los colores del personaje, con cuántos pixeles usa cada uno."""
    base_x = (index % 4) * SPRITE_W * 3
    base_y = (index // 4) * SPRITE_H * 4
    counts = collections.Counter()
    for y in range(SPRITE_H * 4):
        for x in range(SPRITE_W * 3):
            red, green, blue, alpha = image.getpixel((base_x + x, base_y + y))
            if alpha:
                counts[(red >> 3, green >> 3, blue >> 3)] += 1
    return counts


def build_sprite(image, index=0):
    """Las 12 poses del personaje como tiles de 4 bits, más su paleta.

    Devuelve (tiles, paleta, cuántos colores se fusionaron).
    """
    counts = sprite_colors(image, index)
    if len(counts) <= OBJ_COLORS:
        mapping = {c: c for c in counts}
        merged = []
    else:
        mapping, merged = pixeles.merge_least_used(counts, OBJ_COLORS)
    palette = sorted(set(mapping.values()))
    lookup = {color: i + 1 for i, color in enumerate(palette)}

    # Cada pose es un bloque de 4x4 tiles dentro de una grilla de 16 de ancho,
    # así que entran cuatro poses por fila de bloques y hacen falta tres filas.
    block_rows = (SPRITE_POSES + 3) // 4
    tiles = bytearray(block_rows * 4 * OBJ_ROW * 32)
    for pose in range(SPRITE_POSES):
        ox, oy = pose_origin(index, pose)
        block = (pose // 4) * 4 * OBJ_ROW + (pose % 4) * 4
        for ty in range(4):
            for tx in range(4):
                cell = []
                for y in range(CELL):
                    row = []
                    for x in range(CELL):
                        # La pose de 24 se centra en el objeto de 32.
                        sx = tx * CELL + x - (OBJ_W - SPRITE_W) // 2
                        sy = ty * CELL + y
                        if 0 <= sx < SPRITE_W and 0 <= sy < SPRITE_H:
                            r, g, b, a = image.getpixel((ox + sx, oy + sy))
                            row.append(lookup[mapping[(r >> 3, g >> 3, b >> 3)]]
                                       if a else 0)
                        else:
                            row.append(0)
                    cell.append(tuple(row))
                number = block + ty * OBJ_ROW + tx
                tiles[number * 32:(number + 1) * 32] = pack_tile(tuple(cell),
                                                                planes=4)
    return bytes(tiles), palette, len(merged)


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


def paleta_del_personaje(image, index, tope=None):
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
    """
    tope = OBJ_COLORS if tope is None else tope
    counts = sprite_colors(image, index)
    if len(counts) <= tope:
        mapping = {c: c for c in counts}
    else:
        mapping, _ = pixeles.merge_least_used(counts, tope)
    palette = sorted(set(mapping.values()))
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


def aviso_de_descarte(args, texto, peligroso):
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

    `--descartar-eventos` deja seguir igual, y entonces es una decisión escrita
    en el comando y no un renglón que se pasa de largo.
    """
    if not peligroso:
        print("  " + texto)
        return
    if getattr(args, "descartar_eventos", False):
        print("  DESCARTADO Y CAMBIA DE GRÁFICO: " + texto)
        return
    sys.exit(
        "%s\n\n"
        "No se arma la ROM: ese evento **cambia de gráfico entre sus páginas**, o\n"
        "sea que es un mecanismo y no un adorno. Sin dibujarse, el cambio no se ve\n"
        "nunca, y como el evento igual cierra el paso y dispara, lo que queda es\n"
        "una pared invisible donde el juego esperaba una puerta.\n\n"
        "Si es lo que se quiere, `--descartar-eventos` deja seguir y los marca." % texto)


def npcs_dibujables(renderer, game_map, lideres, tope, graficos_de_ruta=(),
                    timer_colores=(), solo_aqui=None):
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

    def cabe(charset, index, forzar, lider=False):
        palette, _, _ = paleta_del_personaje(renderer.charsets.get(charset),
                                             index)
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
    for npc in npcs:
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
            # Y sólo si no está en ningún otro mapa de la ROM: el banco de poses
            # es global, así que cuantizarlo distinto acá que allá no da una
            # imagen fea sino un corte al emitir.
            if solo_aqui is not None and clave not in solo_aqui:
                continue
            cuenta = sprite_colors(renderer.charsets.get(clave[0]), clave[1])
            if not cuenta:
                continue
            faltan = len([c for c in timer_colores if c not in paletas[n]])
            nuevo_tope = OBJ_COLORS - faltan
            m, _ = pixeles.merge_least_used(cuenta, nuevo_tope)
            movidos = sum(v for c, v in cuenta.items() if m[c] != c)
            costo = movidos / float(sum(cuenta.values()))
            if mejor is None or costo < mejor[0]:
                mejor = (costo, clave, n, nuevo_tope, sorted(set(m.values())))
        if mejor is not None:
            _costo, clave, n, nuevo_tope, paleta_nueva = mejor
            print("  para que entre el cronómetro, %s:%d baja a %d colores "
                  "(%.2f%% de sus pixeles)"
                  % (clave[0], clave[1], nuevo_tope, 100 * _costo))
            paletas[n] = paleta_nueva
            topes[clave] = nuevo_tope

    # El reparto se devuelve para que `build_characters` lo use tal cual: un
    # segundo primer-lugar-que-entre en otro orden puede dar otra cuenta, y
    # dio: el mapa 8 entraba acá en ocho paletas y allá pedía nueve.
    return salida, descartados, (paletas, paleta_de, propios, de_lider,
                                 topes, prestadas)


def build_characters(images, personajes, ranuras, reparto=None):
    """El banco de sprites que va a VRAM: una pose por ranura.

    `personajes` es la lista de (charset, índice) que necesitan paleta, en el
    orden en que se las reparte; `ranuras` la de (clave, charset, índice,
    pose), un bloque de 16 tiles por cada una y en ese orden. Desde el
    2026-09-05 acá va **una pose por ranura** y nada más: las doce de los que
    caminan viven en el cartucho —ver `banco_de_poses`— y se suben en caliente.
    Antes iban todas acá, y la escena de apertura pedía 768 tiles de los 512
    que direcciona la PPU.

    Devuelve (tiles, paletas, ubicación, paleta_de): ubicación mapea la clave
    de la ranura a (bloque, paleta), y paleta_de cada (charset, índice) a su
    paleta.
    """
    tiles = bytearray()
    palettes = []
    paleta_de = {}
    colores = {}
    if reparto is not None:
        # El reparto que ya hizo `npcs_dibujables`, con los mismos personajes:
        # las paletas y a cuál va cada uno. Acá sólo se arma el índice de cada
        # color adentro de la suya.
        palettes = [list(p) for p in reparto[0]]
        paleta_de = dict(reparto[1])
        # Los que comparten la ranura del líder: su `lookup` sale de **su**
        # paleta y no de la de la ranura, porque la ROM va a subir sus colores
        # ahí cuando le toque liderar. Ver `npcs_dibujables`.
        propios = set(reparto[2]) if len(reparto) > 2 else set()
        # Y a quién se le bajó el número de colores para que entrara el
        # cronómetro. Tiene que ser el mismo número que usó `npcs_dibujables`:
        # si acá se cuantizara con quince, las poses del cartucho no
        # coincidirían con la paleta que la ROM sube a CGRAM.
        topes = dict(reparto[4]) if len(reparto) > 4 else {}
    for charset, index in personajes:
        if (charset, index) in colores:
            continue
        palette, lookup, mapping = paleta_del_personaje(
            images[charset], index,
            topes.get((charset, index)) if reparto is not None else None)
        if reparto is not None:
            if (charset, index) not in paleta_de:
                sys.exit("%s:%d no está en el reparto de paletas" % (charset, index))
            if (charset, index) in propios:
                colores[(charset, index)] = (lookup, mapping)
                continue
            union = palettes[paleta_de[(charset, index)]]
            # Los colores que no estén en la paleta que le tocó van al más
            # cercano de los que hay. Pasa cuando el mapa se quedó sin paletas y
            # `npcs_dibujables` le prestó una ajena: se ve mal, pero se ve. La
            # cuenta de "más cercano" es la misma de allá, así que los dos
            # lados eligen igual.
            lookup = {}
            for color in palette:
                if color in union:
                    lookup[color] = union.index(color) + 1
                else:
                    cerca = min(union,
                                key=lambda p, c=color: pixeles.luma_distance(p, c))
                    lookup[color] = union.index(cerca) + 1
            colores[(charset, index)] = (lookup, mapping)
            continue
        # Si sus colores caben en una paleta ya armada, va ahí: se le suman
        # los que falten y se le da el índice de cada uno. Ningún color se
        # fusiona por esto, así que la referencia no se entera. Existe por
        # los eventos dibujados con un tile del chipset —las puertas del
        # mapa 2—, que son cada uno un personaje y comparten casi todos los
        # colores: sin esto el mapa 2 pedía nueve paletas de las ocho.
        for numero, existente in enumerate(palettes):
            union = list(existente) + [c for c in palette if c not in existente]
            if len(union) <= OBJ_COLORS:
                palettes[numero] = union
                lookup = {color: union.index(color) + 1 for color in palette}
                paleta_de[(charset, index)] = numero
                break
        else:
            paleta_de[(charset, index)] = len(palettes)
            palettes.append(list(palette))
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


def digitos_del_timer(sys_img, tiles, palettes, de_lider=()):
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
        if len(palettes) >= OBJ_PALETTES:
            raise SystemExit(
                "el cronómetro no entra: el mapa ya usa las %d paletas de "
                "sprite y ninguna tiene lugar para sus %d colores"
                % (OBJ_PALETTES, len(quiere)))
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


def gotas_de_lluvia(tiles, palettes, de_lider=(), timer_base=None):
    """Los seis tiles de las gotas —arriba y abajo de la raya, en los tres
    grises— y la paleta donde entran sus colores. Ver OP_CLIMA en eventos.py.

    Es lo mismo que `digitos_del_timer`: los colores van en la primera paleta
    de personaje con lugar, menos las de líder, y los tiles al final del
    banco. Si el cronómetro está, en su misma fila de dieciséis, que le sobran
    cinco lugares; si no, en una fila de bloques propia. El tono `t` arriba es
    el tile `base + t` y abajo el `base + 16 + t`. Devuelve (tiles, base,
    número de paleta).
    """
    quiere = [c for c in eventos.LLUVIA_COLORES]
    cual = _primer_lugar(palettes, de_lider, quiere)
    if cual is None:
        # No hay lugar: este mapa no dibuja lluvia, y la referencia lo sabe con
        # la misma regla, `lluvia_cabe`. No se le baja un color a nadie para
        # hacerle lugar, como al cronómetro: eso cambiaría el reparto, que es
        # lo que las dos puntas comparten.
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


def _primer_lugar(palettes, de_lider, colores):
    """La primera paleta —menos las de líder— donde entran `colores` sin
    fusionar nada, o una nueva si queda ranura; la agrega o la agranda y
    devuelve su número, o None si no hay lugar."""
    for numero, existente in enumerate(palettes):
        if numero in de_lider:
            continue
        union = list(existente) + [c for c in colores if c not in existente]
        if len(union) <= OBJ_COLORS:
            palettes[numero] = union
            return numero
    if len(palettes) < OBJ_PALETTES:
        palettes.append(list(colores))
        return len(palettes) - 1
    return None


def lluvia_cabe(paletas, de_lider, timer_colores=()):
    """Si las gotas entran en las paletas de sprite de un mapa, después de los
    dígitos del cronómetro: la misma cuenta de `digitos_del_timer` y
    `gotas_de_lluvia`, sobre una copia. La usa la referencia para saber si en
    ese mapa se dibuja la lluvia."""
    copia = [list(p) for p in paletas]
    if timer_colores and _primer_lugar(copia, de_lider,
                                       list(timer_colores)) is None:
        return False
    return _primer_lugar(copia, de_lider,
                         list(eventos.LLUVIA_COLORES)) is not None


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


def hay_lluvia(map_ids):
    """Si alguna página de estos mapas pone lluvia: entonces cada mapa de la
    ROM lleva las gotas, porque el clima sigue al cambiar de mapa."""
    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(args_game_dir[0],
                                        "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                for cmd in page.commands:
                    if (cmd.code == eventos.WEATHER_EFFECTS
                            and cmd.parameters[:1] == [eventos.CLIMA_LLUVIA]):
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

    mapping, merged = pixeles.merge_least_used(counts, bg_colors)

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


def convert_layers(base, above_img, con_ventana=False, ventana_paleta=None,
                   variantes=None):
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
    import cache_disco
    if _VERSION_CAPAS is None:
        _VERSION_CAPAS = cache_disco.version_de("snes_convert.py", "rm2k.py")
    partes = [_VERSION_CAPAS, _huella_de_imagen(base),
              _huella_de_imagen(above_img), str(bool(con_ventana)),
              repr(ventana_paleta)]
    for familia in sorted(variantes or {}):
        partes.append("familia %s" % familia)
        for img in variantes[familia]:
            partes.append(_huella_de_imagen(img))
    en_disco = cache_disco.clave(*partes)
    hecho = cache_disco.leer("capas", en_disco)
    if hecho is None:
        hecho = _convert_layers(base, above_img, con_ventana, ventana_paleta,
                                variantes)
        cache_disco.guardar("capas", en_disco, hecho)
    return hecho


def _convert_layers(base, above_img, con_ventana=False, ventana_paleta=None,
                    variantes=None):
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

    Con `con_ventana` se reserva además la paleta que queda justo debajo de la
    capa de encima, que es donde va la de la ventana de mensaje, y **la paga el
    fondo**: se lo aprieta en las que quedan y fusiona lo que no entre.

    La elección de a quién cobrarle es medida y no de gusto. El fondo va en 8
    bits, así que sus paletas son un pozo común: una menos le saca 16 entradas
    de CGRAM y lo obliga a fusionar sólo el excedente. La capa de encima va en
    4 y empaqueta por tile, así que una paleta menos le puede costar muchísimo
    más. En el mapa 1 —el que descubrió esto— el fondo usa 49 colores y la capa
    de encima 64 justos en 4 paletas: quitándole una al fondo se fusionan 2
    colores, y quitándosela a la capa de encima habría que fusionar 16.

    `ventana_paleta` es esa paleta ya decidida **por la ROM entera** y no por
    este mapa: ver `paleta_de_la_ventana`. Puede quedar más abajo de donde
    este mapa la pondría solo, y entonces el fondo se aprieta debajo de ella
    igual que antes —las paletas que quedan entre el fondo y la capa de encima
    no las usa nadie—. La capa de encima no se mueve: sus celdas llevan la
    paleta adentro y dónde arranca se guarda mapa por mapa.

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

    above = convert_above(above_img, palettes=libres, grid=above_grid)
    # El fondo llega **hasta donde arranca la capa de encima**, sin dejar
    # paletas en el medio: va a 8 bits y no necesita alineación. La ventana ya
    # no le cobra una paleta porque vive abajo de todo, adentro de
    # `CGRAM_RESERVADAS`; `con_ventana` y `ventana_paleta` quedan por
    # compatibilidad de la firma y no cambian el reparto.
    tope = above[3]
    if tope < 1:
        # Inalcanzable con los datos del juego —haría falta una capa de encima
        # que pida las ocho paletas— pero si pasa, el fondo se quedaría sin
        # ninguna y `bg_budget` daría un presupuesto negativo.
        raise SystemExit(
            "la capa de encima se llevó las ocho paletas y no queda ninguna "
            "para el fondo")
    return (convert(base, bg_budget(tope), grid=base_grid,
                    variantes=grillas), above)


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


def convert(image, bg_colors=None, grid=None, variantes=None):
    """La imagen del mapa a tiles, paleta y tilemap.

    `bg_colors` es lo que le dejó libre la capa de encima; sin él se asume el
    reparto de dos paletas arriba, que es el que valía cuando no se elegía.

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
    if bg_colors is None:
        bg_colors = bg_budget(above_split(2))
    if grid is None:
        grid = cut_tiles(quantize(image))
    variantes = variantes or {}
    otras = [g for familia, _ in FAMILIAS for g in variantes.get(familia, ())]
    before = len({p for row in grid for tile in row
                  for line in tile for p in line if p is not None})
    palette, grid, otras, merged = build_palette(grid, bg_colors, otras)
    # De vuelta a su familia, ya fusionadas con el mismo mapeo que `grid`, y con
    # el dibujo 0 adelante: `dibujos[familia][d]` es la grilla del dibujo `d`.
    dibujos, resto = {None: [grid]}, list(otras)
    for familia, _ in FAMILIAS:
        cuantas = len(variantes.get(familia, ()))
        dibujos[familia] = [grid] + resto[:cuantas]
        resto = resto[cuantas:]

    def familia_de(y, x):
        """De qué familia es la celda, o None si dibuja siempre igual.

        Una celda que cambiara con las dos animaciones a la vez —agua abajo y
        un tile animado encima— pediría los doce cruces y no dos corridas. Si
        aparece se corta acá, en vez de emitir un dibujo que acierta la mitad
        del tiempo.
        """
        cuales = [familia for familia, _ in FAMILIAS
                  if any(g[y][x] != grid[y][x] for g in dibujos[familia][1:])]
        if len(cuales) > 1:
            raise SystemExit(
                "la celda (%d, %d) cambia con las dos animaciones del ChipSet "
                "a la vez, y eso no se sabe emitir" % (x, y))
        return cuales[0] if cuales else None

    clases = [[familia_de(y, x) for x in range(len(grid[0]))]
              for y in range(len(grid))]

    # El tile 0 es el vacío, igual que en la capa de encima: es lo que la ROM
    # escribe en el tilemap para lo que queda fuera del mapa —ver
    # `build_column`— y lo que hay en la VRAM que nadie escribió. Un mapa con
    # una celda enteramente transparente lo reusa; los demás gastan un tile.
    blank = tuple(tuple(0 for _ in range(CELL)) for _ in range(CELL))
    tilemap = [[None] * len(grid[0]) for _ in grid]
    pools, corridas, siguiente = {}, {}, 0
    for familia in (None,) + tuple(nombre for nombre, _ in FAMILIAS):
        pool = {}
        if familia is None:
            pool[(blank,)] = 0
            siguiente = 1
        inicio = siguiente
        for y, row in enumerate(grid):
            for x in range(len(row)):
                if clases[y][x] != familia:
                    continue
                # La clave lleva **todos los dibujos de la celda** y no sólo el
                # que se ve al entrar: dos celdas comparten tile sólo si además
                # se animan igual. Y el espejado se prueba sobre los dibujos
                # juntos, porque el PPU espeja el tile y no cada dibujo por su
                # cuenta: si el dibujo 1 no es simétrico de la misma forma que
                # el 0, esa orientación no sirve.
                pasos = tuple(to_indices(g[y][x], palette,
                                         base=CGRAM_RESERVADAS)
                              for g in dibujos[familia])
                placed = None
                for orientaciones in zip(*[flips(t) for t in pasos]):
                    clave = tuple(o for o, _, _ in orientaciones)
                    if clave in pool:
                        _, horizontal, vertical = orientaciones[0]
                        placed = entry(pool[clave], horizontal, vertical)
                        break
                if placed is None:
                    if siguiente >= MAX_TILES:
                        raise SystemExit("el mapa necesita más de %d tiles"
                                         % MAX_TILES)
                    pool[pasos] = siguiente
                    placed = entry(siguiente, 0, 0)
                    siguiente += 1
                tilemap[y][x] = placed
        pools[familia] = pool
        if familia is not None and pool:
            corridas[familia] = (inicio, siguiente - inicio)

    tile_data = bytearray(BYTES_PER_TILE * siguiente)
    for pool in pools.values():
        for pasos, number in pool.items():
            tile_data[number * BYTES_PER_TILE:
                      (number + 1) * BYTES_PER_TILE] = pack_tile(pasos[0])

    # Y los otros dibujos de cada corrida, uno detrás del otro y en el orden de
    # la VRAM: así subirlos es escribir la dirección y disparar el DMA.
    animacion = {}
    for familia, cuantos in FAMILIAS:
        if familia not in corridas:
            continue
        inicio, largo = corridas[familia]
        por_numero = {number: pasos for pasos, number in pools[familia].items()}
        if len(dibujos[familia]) != cuantos:
            raise SystemExit("la familia %r pide %d dibujos y llegaron %d"
                             % (familia, cuantos, len(dibujos[familia])))
        animacion[familia] = {
            "base": inicio,
            "tiles": largo,
            "dibujos": [bytes(b"".join(
                pack_tile(por_numero[number][d])
                for number in range(inicio, inicio + largo)))
                for d in range(cuantos)],
        }

    # CGRAM: el bloque del mapa lleva **sólo sus colores** y se sube a partir de
    # `CGRAM_RESERVADAS`. Lo de abajo —el color de fondo de la pantalla y la
    # paleta de la ventana— es de toda la ROM y lo sube `cgram_base`.
    cram = [cgram_word(c) for c in palette]

    summary = {
        "colores": before,
        "usados": len(palette),
        "presupuesto": bg_colors,
        "fusionados": len(merged),
        "tiles": siguiente,
        "celdas": sum(len(row) for row in tilemap),
        "animacion": animacion,
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
BANK_SIZE = 32 * 1024           # lo que direcciona un banco de LoROM
MAP_LAYOUT = 1                  # dos pantallas de 32x32 al lado, que es 64x32
BLOCK_BYTES = 16                # cuatro celdas de BG1 y cuatro de BG2

# --- el reparto de la VRAM --------------------------------------------------
# Las 64 KB no se reparten como uno quiera: la base de los tiles de los sprites
# va de a 16 KB, la de cada fondo de a 8 KB y la de cada tilemap de a 2 KB. Con
# los dos tilemaps clavados al final —4 KB cada uno, que es lo que mide una
# ventana de 64x32— quedan 56 KB para los tres bancos de tiles, y las
# granularidades dejan exactamente dos cortes posibles:
#
#   ancho    fondo 512 tiles (32 KB) | sprites 512 (16 KB) | encima 256 (8 KB)
#   fondo    fondo 640 tiles (40 KB) | encima 256 (8 KB)   | sprites 256 (8 KB)
#
# Se usa el primero salvo que el mapa pida más de 512 tiles de fondo, que en
# todo el juego son tres. El segundo les da 128 tiles más al fondo a costa de la
# mitad de los sprites, y esos tres mapas tienen pocos personajes.
#
# Cuál toca lo decide el conversor y viaja en el .inc: la ROM no elige nada.
# Sin ventana sobran 10 KB, así que acá la holgura no es problema; lo que cambió
# es dónde caen los tilemaps, que ahora son $5800 y $7800 para los cuatro
# repartos. Los sprites bajan de 512 a 384 para dejarle lugar al de $5800: sobre
# los 318 mapas que convierten, el que más gasta usa **380**.
LAYOUT_ANCHO = {"tiles": (0x0000, 512), "sprites": (0x4000, 384),
                "encima": (0x6000, 256)}
LAYOUT_FONDO = {"tiles": (0x0000, 640), "encima": (0x6000, 128),
                "sprites": (0x6800, 256)}

# Y los dos que hacen lugar para la ventana de mensaje. La ventana necesita 8 KB
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
# segundo y 3 se quedaban sin ventana —el 8, el 66 y el 250—. **El 8 ya no**:
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
# menú —$4400 y $5000— caen en los sprites de LAYOUT_ANCHO, que arrancan en
# $4000: los NPCs volvían del menú con las poses rotas y el héroe también si
# no era el del bloque 0. Las de acá están en la intersección del banco de BG1
# de los cuatro repartos, que es $2000..$4000:
#
#   LAYOUT_ANCHO          $0000..$4000
#   LAYOUT_FONDO          $0000..$5000
#   LAYOUT_VENTANA        $2000..$5800
#   LAYOUT_VENTANA_FONDO  $1000..$4C00
#
# La base de tiles de un BG va de a 4096 palabras y el tilemap de a 1024: los
# tiles en $2000, que con las caras del grupo son unos 300 y pueden llegar a
# 448 —hasta $3C00—, y el tilemap en $3C00. La pantalla de título los pisa —su
# imagen llega a $3E00— y no importa: al volver de las ranuras el título se
# sube entero. `_controlar_ranuras` lo comprueba contra los repartos de
# verdad, para que mover uno no deje esto escrito mal.
RANURA_VRAM = 0x2000
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


def vram_layout(tiles, sprites=0, con_ventana=False):
    """Qué reparto de VRAM le toca a un mapa, según lo que gasta.

    Sin ventana son los dos de siempre y `sprites` no se mira: el reparto ancho
    le da 512 a cada uno y sólo los tres mapas que pasan de 512 tiles de fondo
    necesitan el otro. Con ventana hay que elegir de dónde salen sus 8 KB, y ahí
    sí importan los dos números.
    """
    if not con_ventana:
        return LAYOUT_FONDO if tiles > LAYOUT_ANCHO["tiles"][1] else LAYOUT_ANCHO
    # Los dos números se miran en los dos repartos. Antes se miraba el fondo en
    # uno y los sprites en el otro, y eso dejaba pasar un mapa de 620 tiles de
    # fondo a un banco de 512: ver el comentario de LAYOUT_VENTANA_FONDO.
    for layout in (LAYOUT_VENTANA, LAYOUT_VENTANA_FONDO):
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
    for nombre, layout in (("ANCHO", LAYOUT_ANCHO), ("FONDO", LAYOUT_FONDO),
                           ("VENTANA", LAYOUT_VENTANA),
                           ("VENTANA_FONDO", LAYOUT_VENTANA_FONDO)):
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
    import ventana as ventana_mod
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
    está verificada contra una captura del juego original: ver `snes-oraculo`.
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
    import fuente as fuente_mod
    import ventana as ventana_mod

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

    Es la misma tabla que `tools/fuente.py`, que se genera desde
    easyrpg-player, pero **con los bits dados vuelta**: allá el bit 0 es el
    pixel de la izquierda y en el formato de tiles de la consola el de la
    izquierda es el bit 7. Darlos vuelta acá y no en la ROM sale gratis: es una
    tabla de 1140 bytes que se genera una vez.
    """
    import fuente as fuente_mod
    out = bytearray()
    for code in range(32, 127):
        for fila in fuente_mod.filas(chr(code), font_id):
            invertida = 0
            for px in range(FUENTE_ANCHO):
                if fila >> px & 1:
                    invertida |= 1 << (7 - px)
            out.append(invertida)
    return bytes(out)


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


def unpack_tile(data, planes=8):
    """Un tile de vuelta a índices, para poder reconstruir lo que se ve."""
    rows = []
    for y in range(CELL):
        row = []
        for x in range(CELL):
            bit = 1 << (7 - x)
            value = 0
            for plane in range(planes):
                if data[(plane // 2) * 16 + y * 2 + (plane % 2)] & bit:
                    value |= 1 << plane
            row.append(value)
        rows.append(tuple(row))
    return tuple(rows)


def _filas_de_celda(cell, data, planes, palette):
    """Las ocho filas de una celda del tilemap, ya en RGBA.

    Devuelve, por fila, los 32 bytes y qué columnas pintan: `None` quiere decir
    que pintan todas, que es siempre el caso en 8 bits —ahí el índice 0 es un
    color como cualquier otro— y deja escribir la fila de una rebanada. En 4
    bits el índice 0 es transparente y hay que saltearlo, que es lo que hacía
    el `continue` del lazo viejo.
    """
    number = cell & 0x03FF
    pal = (cell >> 10) & 0x07
    indices = unpack_tile(
        data[number * (planes * 8):(number + 1) * (planes * 8)], planes)
    filas = []
    for y in range(CELL):
        sy = CELL - 1 - y if cell & 0x8000 else y
        fila = bytearray(CELL * 4)
        opacos = [] if planes == 4 else None
        for x in range(CELL):
            sx = CELL - 1 - x if cell & 0x4000 else x
            value = indices[sy][sx]
            if planes == 4:
                if not value:
                    continue                    # transparente
                # En 4 bits el índice se cuenta dentro de la paleta que dice la
                # celda; ésa ya lleva el desplazamiento.
                value += pal * COLORS_PER_PALETTE
                opacos.append(x)
            color = palette[value] if value < len(palette) else (0, 0, 0)
            fila[x * 4:x * 4 + 4] = bytes((color[0] << 3, color[1] << 3,
                                           color[2] << 3, 255))
        filas.append((bytes(fila), tuple(opacos) if opacos is not None else None))
    return filas


def render_converted(tile_data, cram, tilemap, above=None, fondo=None):
    """La imagen que la consola va a mostrar, armada desde los datos convertidos.

    Comparar contra el render original de Python no alcanza: entre uno y otro
    está la fusión de colores, el reparto en paletas, el reuso de tiles y los
    espejados. Si la referencia se arma desde el render, cada una de esas cosas
    aparece como una diferencia aunque la consola esté haciendo exactamente lo
    que se le pidió.

    Armándola desde los datos, lo único que puede diferir es la consola.
    """
    from PIL import Image

    reference = tilemap if tilemap is not None else above[2]
    height, width = len(reference), len(reference[0])
    image = Image.new("RGBA", (width * CELL, height * CELL))

    # CGRAM tal como queda en la consola: abajo de todo el color de fondo de la
    # pantalla y la paleta de la ventana, después el fondo desde
    # `CGRAM_RESERVADAS`, y la capa de encima en las paletas que se haya
    # llevado. Dónde arranca ella lo dice ella, no una constante.
    #
    # Las reservadas quedan en cero acá y no se dibujan: el fondo no las
    # referencia nunca —sus índices arrancan en `CGRAM_RESERVADAS`— y la ventana
    # no la dibuja esta función.
    words = [0] * CGRAM_RESERVADAS + list(cram)
    words += [0] * (128 - len(words))
    if fondo is not None:
        # El color de fondo de la pantalla, que vive en la entrada 0 y no en el
        # bloque del mapa. Sólo lo pisa `render_above`, para recortar.
        words[0] = fondo
    if above:
        colors = above[1]
        first = above[3] * COLORS_PER_PALETTE
        for i in range(len(colors) // 2):
            words[first + i] = int.from_bytes(colors[i * 2:i * 2 + 2], "little")
    palette = [((c & 0x1F), (c >> 5) & 0x1F, (c >> 10) & 0x1F) for c in words]

    # El lienzo es un bytearray de RGBA y no una `Image`: se dibujaba con
    # `putpixel`, uno por pixel, y eran dos millones y medio de llamadas por
    # cada corrida de la referencia —el 40% del tiempo de un caso de la tanda,
    # que son once segundos de los cuales siete son esto—. Un `bytearray` se
    # escribe por rebanadas y la imagen se arma una sola vez al final.
    #
    # Arrancar en cero no es un detalle: `render_above` cuenta con que lo que
    # la capa no toca quede en (0, 0, 0, 0), que es lo que daba `Image.new`.
    ancho = width * CELL
    lienzo = bytearray(ancho * height * CELL * 4)

    def draw(cells, data, planes):
        # Las filas ya en RGBA de cada celda distinta. La clave es la celda
        # entera —número, paleta y los dos espejados—, así que dos celdas
        # iguales se dibujan una sola vez: un mapa de diez mil celdas usa unos
        # pocos cientos de tiles distintos, que es justamente para lo que el
        # conversor los reusa. De acá salen las 80.000 llamadas a
        # `unpack_tile`, que quedan en tantas como celdas distintas haya.
        cache = {}
        for ty, row in enumerate(cells):
            base_y = ty * CELL
            for tx, cell in enumerate(row):
                filas = cache.get(cell)
                if filas is None:
                    filas = _filas_de_celda(cell, data, planes, palette)
                    cache[cell] = filas
                base = (base_y * ancho + tx * CELL) * 4
                for y, (fila, opacos) in enumerate(filas):
                    desde = base + y * ancho * 4
                    if opacos is None:           # todos los pixeles pintan
                        lienzo[desde:desde + CELL * 4] = fila
                        continue
                    for x in opacos:             # 4 bits: el índice 0 no pinta
                        lienzo[desde + x * 4:desde + x * 4 + 4] = \
                            fila[x * 4:x * 4 + 4]

    if tilemap is not None:
        draw(tilemap, tile_data, 8)
    if above:
        draw(above[2], above[0], 4)
    image.frombytes(bytes(lienzo))
    return image


def render_above(cram, above):
    """Sólo la capa de encima, transparente donde no dibuja nada."""
    from PIL import Image

    height, width = len(above[2]), len(above[2][0])
    image = Image.new("RGBA", (width * CELL, height * CELL), (0, 0, 0, 0))
    # Se dibuja con un color de fondo que ningún tile usa —magenta— para
    # recortar después lo que la capa no toca. No puede ser el fondo de
    # verdad, que es negro: los pixeles negros de los tiles de encima se
    # recortarían también, y el 2026-09-05 se recortaron, cuando el fondo pasó
    # de magenta a negro y la sombra de una máquina del mapa 6 se volvió un
    # tramado gris.
    lleno = render_converted(b"", cram, None, above,
                             fondo=cgram_word(CLAVE_RECORTE))
    image.paste(lleno, (0, 0))
    # Lo que la capa no toca quedó del color clave; ahí va transparente.
    fondo = (CLAVE_RECORTE[0] << 3, CLAVE_RECORTE[1] << 3,
             CLAVE_RECORTE[2] << 3, 255)
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            if pixels[x, y] == fondo:
                pixels[x, y] = (0, 0, 0, 0)
    return image


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
PAGINA_BYTES = 30
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
    out = ["; La tabla de mapas: un registro de %d bytes por mapa, con todo lo"
           % MAPA_STRIDE,
           "; que la ROM necesita para cargarlo. Los punteros son de 24 bits",
           "; porque los datos viven repartidos por todos los bancos.",
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
        out.append("    .byte %s ; +%d  relleno hasta los punteros"
                   % (",".join(["$00"] * relleno), usado))
        usado += relleno
        for nombre in MAPA_PUNTEROS:
            etiqueta = etiquetas[numero][nombre]
            out.append("    .byte <(%s), >(%s), ^(%s), $00 ; +%d  %s"
                       % (etiqueta, etiqueta, etiqueta, usado, nombre))
            usado += MAPA_PTR_PASO
        assert usado <= MAPA_STRIDE, usado
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
    out = ["; La animación del ChipSet, una entrada de %d bytes por mapa."
           % ANIM_STRIDE,
           "; Ver `anim_tabla` en tools/snes_convert.py y `anim_flush` en main.s.",
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


def anim_dibujo(tile_data, animacion, pasos):
    """`tile_data` con los dibujos que tocan en ese momento ya pisados.

    Es lo que la consola tiene en la VRAM después de subir el paso, y con esto
    la referencia dibuja **desde los mismos bytes** que la ROM: si la corrida se
    emitiera corrida un tile, las dos se equivocarían distinto y se vería.

    `pasos` es (paso del agua, paso de los tiles animados); ver
    `rm2k.paso_de_agua` y `rm2k.paso_animado`.
    """
    datos = bytearray(tile_data)
    for (familia, _), paso in zip(FAMILIAS, pasos):
        corrida = animacion.get(familia)
        if not corrida:
            continue
        desde = corrida["base"] * BYTES_PER_TILE
        dibujo = corrida["dibujos"][paso]
        datos[desde:desde + len(dibujo)] = dibujo
    return bytes(datos)


def bloque(label, data, per_line=16, alinear=None):
    """Un bloque de datos con su declaración de acomodo.

    Cada bloque se declara antes de emitirlo: casi todos se suben por DMA, y un
    DMA que cruce de banco lee basura de la mitad para adelante. La grilla de
    celdas no se sube por DMA sino que se recorre con un puntero, así que no le
    hace falta el banco entero: sólo que sus palabras no queden partidas entre
    el final de un banco y el principio del siguiente.
    """
    out = [".alinear %d" % alinear if alinear else ".bloque %d" % len(data),
           "%s:" % label]
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
    tanda lo cobró enseguida: `snes-varios` no ensamblaba porque nombraba un
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
        assert PAGINA_BYTES == 30
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
        bloques con los mismos bytes pero distinto `.bloque` o `.alinear` no
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


def emit(path, mapas, inicial=0, heroe_encima=False, grupo_inicial=(),
         ventana=None, titulo=None, ranuras=None):
    """El .inc que arma w65.py junto con main.s.

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

    cabecera = (
        "; Generado por tools/snes_convert.py. No editar.\n"
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
        "; Y cuántos gráficos distintos puede pedir la orden 34 en un mapa:\n"
        "; su tabla se copia a la RAM como la de NPCs.\n"
        "RUTA_GRAF_MAX = %d\n"
        "; Los opcodes del intérprete de eventos.\n"
        "OP_FIN      = $%02X\n"
        "OP_SWITCH   = $%02X\n"
        "OP_TELEPORT = $%02X\n"
        "OP_ESPERAR  = $%02X\n"
        "OP_TINTE    = $%02X\n"
        "OP_GRUPO    = $%02X\n"
        "OP_RUTA     = $%02X\n"
        "OP_MENSAJE  = $%02X\n"
        "OP_RUTAS    = $%02X\n"
        "OP_FLASH    = $%02X\n"
        "OP_TIMER    = $%02X\n"
        "OP_BGM      = $%02X\n"
        "OP_LUGAR    = $%02X\n"
        "OP_TRUEQUE  = $%02X\n"
        "OP_SACUDIR  = $%02X\n"
        "OP_DESTELLO = $%02X\n"
        "OP_FUNDIR_BGM = $%02X\n"
        "OP_PAN      = $%02X\n"
        "OP_SI       = $%02X\n"
        "OP_IR       = $%02X\n"
        "OP_ELEGIR   = $%02X\n"
        "OP_ORO      = $%02X\n"
        "OP_GUARDAR  = $%02X\n"
        "OP_VAR      = $%02X\n"
        "OP_SI_VAR   = $%02X\n"
        "OP_ITEM     = $%02X\n"
        "OP_ACCESO   = $%02X\n"
        "OP_TIENDA   = $%02X\n"
        "OP_CLIMA    = $%02X\n"
        "OP_SONIDO   = $%02X\n"
        "; La lluvia: ver OP_CLIMA en eventos.py.\n"
        "LLUVIA_GOTAS_MAX = %d\n"
        "LLUVIA_GOTAS_0 = %d\n"
        "LLUVIA_GOTAS_1 = %d\n"
        "LLUVIA_GOTAS_2 = %d\n"
        "LLUVIA_VIDA   = %d\n"
        "LLUVIA_NACE   = %d\n"
        "LLUVIA_SEMILLA = $%04X\n"
        "LLUVIA_ALTO   = %d\n"
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
        "AZAR_SEMILLA  = $%04X\n"
        "TIMER_PONER_VAR = %d\n"
        "; Las clases de condición de ConditionalBranch que sabemos,\n"
        "; con el número de RM2k tal cual.\n"
        "COND_ORO    = %d\n"
        "COND_ACTOR  = %d\n"
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
        "; en el primer cuadro negro, que es el %d. Ver `brillo_de_fundido`\n"
        "; en tools/eventos.py, que es de donde salen estos números y la\n"
        "; tabla de más abajo.\n"
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
        "; toda ROM que no sea la de `snes-encima`, que la sube a $20\n"
        "; para ejercitar la prioridad 2. Ningún evento del juego llega\n"
        "; a ejercitarla: ver 'Cómo se verifica' en README.md.\n"
        "HERO_PRIORITY = $%02X\n"
        "; La ventana de mensaje: sus tiles viven en la segunda mitad del\n"
        "; banco de BG2, o sea a partir del índice 256, y sus celdas ya\n"
        "; vienen armadas con ese corrimiento y con la prioridad de la capa\n"
        "; de encima. VENTANA_TILES en 0 quiere decir que esta ROM no lleva\n"
        "; ventana y que el banco no existe.\n"
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
        "; dieciséis, la 0.\n"
        "TITULO_MENU_CGRAM = %d\n\n"
        % (", ".join("%d %s" % (m["id"], m["nombre"]) for m in mapas),
           len(mapas), MAPA_STRIDE, inicial,
           VRAM_MAP, VRAM_ABOVE_MAP, MAP_LAYOUT, NPC_STRIDE, NPC_MAX,
           NPC_QUIETO,
           EV_STRIDE, EV_MAX, RUTA_EV_MAX,
           PUERTA_BYTES, PAGINA_BYTES, RUTA_GRAF_MAX,
           eventos.OP_FIN, eventos.OP_SWITCH, eventos.OP_TELEPORT,
           eventos.OP_ESPERAR, eventos.OP_TINTE, eventos.OP_GRUPO,
           eventos.OP_RUTA, eventos.OP_MENSAJE, eventos.OP_RUTAS,
           eventos.OP_FLASH, eventos.OP_TIMER, eventos.OP_BGM,
           eventos.OP_LUGAR, eventos.OP_TRUEQUE, eventos.OP_SACUDIR,
           eventos.OP_DESTELLO, eventos.OP_FUNDIR_BGM, eventos.OP_PAN,
           eventos.OP_SI, eventos.OP_IR, eventos.OP_ELEGIR,
           eventos.OP_ORO, eventos.OP_GUARDAR,
           eventos.OP_VAR, eventos.OP_SI_VAR,
           eventos.OP_ITEM, eventos.OP_ACCESO, eventos.OP_TIENDA,
           eventos.OP_CLIMA, eventos.OP_SONIDO, max(eventos.LLUVIA_GOTAS),
           eventos.LLUVIA_GOTAS[0], eventos.LLUVIA_GOTAS[1],
           eventos.LLUVIA_GOTAS[2], eventos.LLUVIA_VIDA,
           eventos.LLUVIA_NACE, eventos.LLUVIA_SEMILLA, eventos.LLUVIA_ALTO,
           eventos.CLIMA_LLUVIA,
           eventos.ITEMS_N,
           eventos.ITEM_MAX,
           variables_n(),
           eventos.VAR_SUMAR, eventos.VAR_VARIABLE, eventos.VAR_AZAR,
           eventos.VAR_OTRO, eventos.AZAR_SEMILLA, eventos.TIMER_PONER_VAR,
           eventos.COND_ORO, eventos.COND_ACTOR,
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
           0 if ventana is None else len(ventana["tiles"]) // 32,
           VENTANA_FILAS_INC, VENTANA_COLS_INC,
           0 if ventana is None else ventana["base"],
           VENTANA_TEXTO_FILA, VENTANA_TEXTO_FILAS,
           VENTANA_TEXTO_COL, VENTANA_TEXTO_COLS, _columnas(),
           FUENTE_ALTO, FUENTE_ANCHO,
           0 if ventana is None else ventana["sombra"],
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
        # arriba. La tabla va en TABLAS, o sea el banco 0, porque la ROM la
        # recorre con `lda mapa_tabla + campo, x` y ese modo direcciona el banco
        # de datos. Los datos ya no pueden estar ahí: no entran.
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
        # Las etiquetas se emiten siempre, aunque la ROM no lleve ventana: el
        # ensamblador las necesita resueltas y `VENTANA_TILES = 0` es lo que
        # apaga el código en tiempo de ejecución. Un byte de relleno alcanza.
        con_ventana = ventana is not None
        if ventana is None:
            ventana = {"tiles": b"\x00", "cram": [0] * COLORS_PER_PALETTE,
                       "celdas": [[0]], "base": 0, "fondo": b"\x00",
                       "color": [0] * FUENTE_ALTO, "sombra": 0,
                       "fuente": b"\x00", "mensajes": b"\x00"}
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
            handle.write(bloque("mensajes", ventana["mensajes"]) + "\n")
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
            % (T.MENU_OPCIONES, T.MENU_GUARDAR, bloque_menu_opcion,
               bloque_menu_moneda, T.MENU_OPC_COLS, T.MENU_MONEDA_COLS,
               celda_vram(T.MENU_ORO_Y // T.CELL, T.MENU_MONEDA_COL),
               T.MENU_ACTOR_COLS, T.MENU_ACTOR_FILAS, T.MENU_FILAS_GRUPO,
               menu_actores_n,
               T.OBJETIVO_CURSOR_FILA * 32
               + T.OBJETIVO_CURSOR_COL - T.MENU_ACTOR_COL))
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

        def bytes_asm(etiqueta, valores, formato="%d"):
            handle.write("%s:\n    .byte %s\n" % (etiqueta, ", ".join(
                formato % v for v in valores) or "$FF"))

        def words_asm(etiqueta, valores, formato="%d"):
            handle.write("%s:\n    .word %s\n" % (etiqueta, ", ".join(
                formato % v for v in valores) or "0"))

        bytes_asm("item_k", [k_de.get(n, 0xFF)
                             for n in range(eventos.ITEMS_N)])
        words_asm("item_id", items)
        bytes_asm("item_uso", [
            (1 if T.item_usable(db_items[n]) else 0)
            | (2 if T.item_usable(db_items[n])
               and not T.item_pide_actor(db_items[n])
               and db_items[n].uses else 0)
            | (4 if T.item_pide_actor(db_items[n]) else 0)
            | (8 if db_items[n].two_handed else 0)
            for n in items])
        words_asm("item_switch", [db_items[n].switch_id for n in items])
        for campo, prefijo in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write("item_txt_%s:\n    .byte %s\n" % (campo, ", ".join(
                "%s(item_textos + %d)" % (prefijo, ofs)
                for ofs, _ in item_textos_ofs) or "0"))
        bytes_asm("item_txt_n", [n for _, n in item_textos_ofs])
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
        words_asm("item_puntos", [p & 0xFFFF for n in items
                                  for p in db_items[n].puntos])
        bytes_asm("item_actores", [
            sum(1 << b for b in range(8)
                if 8 * byte + b + 1 < actores_n
                and db_items[n].equipable_por(8 * byte + b + 1))
            for n in items for byte in range(8)])
        words_asm("actor_params", [
            (db.actors[a].params.get(k, [0])[titulo_mod.NIVEL - 1]
             if a in db.actors else 0) & 0xFFFF
            for a in range(actores_n)
            for k in ("attack", "defense", "spirit", "agility")])
        handle.write('\n.segment "RODATA"\n')
        handle.write("equipo_inicial:\n    .word %s\n" % ", ".join(
            str(db.actors[a].initial_equipment[r] if a in db.actors else 0)
            for a in range(actores_n) for r in range(P.RANURAS_EQUIPO)))
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
            % (actores_n, texto_param[0], texto_ranura[0],
               pos(P.EQ_ACTOR_FILA, 1), P.EQ_PARAM_VALOR * 2,
               P.EQ_PARAM_FLECHA * 2, pos(P.EQ_RANURA_FILA0, 0),
               P.EQ_RANURA_TERM_COL * 2, P.EQ_RANURA_NOMBRE_COL * 2,
               P.EQ_RANURA_NOMBRE_ANCHO, pos(P.EQ_LISTA_FILA0, 0),
               P.EQ_LISTA_FILAS, P.EQ_CURSOR_COL * 2,
               T.ITEM_NOMBRE_COL * 2, T.ITEM_DOS_PUNTOS_COL * 2,
               pos(T.ITEM_DESC_Y // T.CELL, T.ITEM_DESC_COL)))
        glifos = ranuras["items_glifos"]
        words_asm("item_glifo_celdas", [
            entry(celda, False, False) for gris in (0, 1)
            for n in range(T.ITEM_CARACTERES)
            for celda in glifos[gris][chr(T.ITEM_PRIMER_CARACTER + n)]],
            "$%04X")
        handle.write("\n")
        # `fuente_color` va en el banco 0 y no con el resto de la ventana: la
        # ROM la lee con `lda fuente_color, y`, y ese modo direcciona el banco
        # de datos. Con ella en RODATA leía basura, y el texto salía en negro.
        handle.write(bloque("fuente_color", bytes(ventana["color"])) + "\n")
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
        handle.write(anim_tabla(mapas))
        handle.write("\n\n")
        handle.write(tabla_de_mapas(mapas, etiquetas))
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
        registro[8] = destino
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
# Cuántos eventos con página paralela puede haber a la vez en un mapa. El más
# cargado de este juego es el 8 —Lashe City— con **ocho**: los cuatro autos y
# los cuatro que los reubican. Medido sobre los 328 contando sólo las páginas
# que compilan; el conversor corta si alguno se pasa. Su estado vive en la RAM
# del banco 1, así que no le cuesta nada a la BSS.
PARALELO_MAX = 12
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


def eventos_movibles(game_map, indice_de_mapa, con_ventana=False):
    """Los eventos con gráfico a los que alguna página compilable manda a
    caminar, y los gráficos a los que alguna ruta cambia con la orden 34.

    `con_ventana` tiene que ser el de la ROM que se está armando, por lo mismo
    que en `lideres_posibles`: decide **qué páginas compilan**. Acá se
    compilaba siempre con un bloque de textos, así que una ROM sin ventana le
    daba las doce poses a los eventos que camina una página que en esa ROM no
    puede correr. No se veía porque esa página tampoco compilaba por otras
    cosas; el día que compiló —la escena de apertura, que camina a cuatro—
    doce casos sin ventana se quedaron sin lugar en VRAM.

    Hace falta antes de armar el banco de sprites: a los que se mueven hay que
    darles **las doce poses** del ciclo de caminata, y a los demás la única que
    declaran. Dárselas a cualquiera que aparezca en un MoveEvent sería más
    simple y no entra: hay mapas con siete, y son 1232 tiles de sprite.

    Los gráficos de la orden 34 salen de la misma pasada y por lo mismo: a un
    evento que cambia de gráfico hay que meterle en el cartucho las doce poses
    del gráfico nuevo, y eso se decide antes de armar el banco. **El orden
    tiene que ser el mismo que el de la compilación de verdad**, porque el
    bytecode lleva el índice: lo garantiza que las dos pasadas compilen las
    mismas páginas, que es lo que `con_ventana` cuida. Sin `Graficos` acá una
    ruta con la 34 no compilaría en esta pasada y sí en la otra, y las dos
    listas se irían.

    Se compilan las páginas para saberlo y se tira lo compilado. Es trabajo
    repetido —main() las vuelve a compilar con el bloque de textos de verdad—
    pero no es una **regla** repetida: la decisión de qué compila la toma la
    misma función las dos veces.
    """
    graficos = eventos.Graficos()
    paginas = eventos.paginas_del_mapa(
        game_map, indice_de_mapa,
        eventos.Mensajes() if con_ventana else None, graficos=graficos)
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
    return con_ruta | animados, list(graficos.pares), animados


def graficos_de_prueba(argumento):
    """Los (CharSet, índice) de `--grafico-de-prueba`, o () si no hay."""
    return tuple((charset, int(indice)) for charset, indice in argumento or ())


def ruta_de_evento(argumento):
    """(blanco, órdenes) desde el flag, o () si no se pidió ninguna.

    El blanco es el byte que va en OP_RUTA: 0 es el héroe y un evento es su
    índice **más uno**. Ver `Eventos.blanco`.
    """
    if not argumento or len(argumento) < 2:
        return ()
    if argumento[0] == 0 and any(o in eventos.RUTA_DIAGONALES
                                 for o in argumento[1:]):
        # El mismo corte que hace `traducir` con un MoveEvent del juego, para
        # que no se pueda armar a mano el caso que la ROM no sabe hacer: la
        # referencia caminaría la diagonal y la ROM se iría hacia la
        # izquierda. Ya pasó al escribir estas pruebas.
        sys.exit("--ruta-de-evento: el héroe no camina en diagonal, y el "
                 "blanco 0 es el héroe (un evento es su índice más uno)")
    return argumento[0], list(argumento[1:])


def variables_n():
    """Cuántas ranuras de variables lleva la ROM: al menos una —un largo cero
    cerraría la tabla de la partida— y hasta 256, que es lo que entra entre
    `FAR_VARIABLES` y `FAR_ITEMS`."""
    n = max(1, len(eventos.VARIABLE_SLOT))
    if n > 256:
        sys.exit("%d variables no entran en la RAM lejana: FAR_ITEMS está a "
                 "512 bytes de FAR_VARIABLES" % n)
    return n


def variables_de_prueba(vars_de_prueba, rama_var_de_prueba):
    """Las variables que nombra la página de prueba, para darles ranura."""
    ids = set()
    if vars_de_prueba:
        if len(vars_de_prueba) % 5:
            sys.exit("--vars-de-prueba pide VARIABLE OPERACION CLASE A B, y se "
                     "puede repetir de a cinco")
        for k in range(0, len(vars_de_prueba), 5):
            ids.add(vars_de_prueba[k])
            if vars_de_prueba[k + 2] == eventos.VAR_VARIABLE:
                ids.add(vars_de_prueba[k + 3])
    if rama_var_de_prueba:
        ids.add(rama_var_de_prueba[0])
    return ids


def pan_de_prueba(argumento):
    """Los PanScreen de la página de prueba, de a cinco números."""
    if not argumento:
        return ()
    if len(argumento) % 5:
        sys.exit("--pan-de-prueba pide OPERACION DIRECCION DISTANCIA VELOCIDAD "
                 "ESPERAR, y se puede repetir de a cinco")
    return tuple(argumento)


def sacudida_de_prueba(argumento):
    """(fuerza, velocidad, décimas, esperar) desde `--sacudida-de-prueba`, o
    () si no hay."""
    if not argumento:
        return ()
    if len(argumento) not in (3, 4):
        sys.exit("--sacudida-de-prueba pide FUERZA VELOCIDAD DECIMAS y, si se "
                 "quiere, ESPERA")
    return (argumento[0], argumento[1], argumento[2],
            argumento[3] if len(argumento) > 3 else 0)


def tabla_de_senos():
    """La tabla de `sacudida_siguiente`, tal cual la usa la referencia."""
    out = ["; El seno a escala 127, para la sacudida de pantalla: es la misma",
           "; lista que usa la referencia, SENO_SACUDIDA en eventos.py.",
           "seno_sacudida:"]
    valores = eventos.SENO_SACUDIDA
    for i in range(0, 256, 16):
        out.append("    .byte " + ",".join("$%02X" % (v & 0xFF)
                                            for v in valores[i:i + 16]))
    return "\n".join(out) + "\n"


def lugar_de_prueba(argumento):
    """(blanco, x, y, espera) desde `--lugar-de-prueba`, o () si no hay."""
    if not argumento:
        return ()
    if len(argumento) not in (3, 4):
        sys.exit("--lugar-de-prueba pide BLANCO X Y y, si se quiere, ESPERA")
    return (argumento[0], argumento[1], argumento[2],
            argumento[3] if len(argumento) > 3 else 0)


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


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=7)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("-o", "--output",
                        default=os.path.join(REPO, "rom/src/mapdata.inc"))
    parser.add_argument("--mensaje-de-prueba", nargs="*", metavar="LINEA",
                        help="mete en el mapa inicial una página automática "
                             "que abre una ventana de mensaje con estas "
                             "líneas y espera a que el jugador apriete A. Es "
                             "lo sintético de siempre —como "
                             "--pagina-de-prueba—: sirve para comparar la "
                             "apertura y el cierre sin depender de qué diga "
                             "el juego. Implica --con-ventana")
    parser.add_argument("--con-ventana", action="store_true",
                        help="la ROM lleva la ventana de mensaje: 8 KB de "
                             "VRAM, una paleta y la fuente. Es lo que hace "
                             "que los ShowMessage del juego compilen, y lo "
                             "que se lo cobra a los tiles del mapa —tres "
                             "mapas del juego no pueden llevarla—")
    parser.add_argument("--guardar-de-prueba", action="store_true",
                        help="la página de prueba guarda la partida en la "
                             "SRAM. El save point del juego está en el mapa 8 "
                             "y hay que caminar hasta él; esto deja probar "
                             "`OP_GUARDAR` desde cualquier mapa. El otro lado "
                             "del mismo flag de snes_expect.py")
    parser.add_argument("--timer-de-prueba", nargs=2, type=int, default=None,
                        metavar=("SEGUNDOS", "VISIBLE"),
                        help="arranca el cronómetro desde la página de prueba. "
                             "Existe por lo mismo que el resto de esa página: "
                             "las seis del juego que lo prenden están cortadas "
                             "por otra cosa, así que sin esto no habría con qué "
                             "comparar. Implica --con-timer")
    parser.add_argument("--con-titulo", action="store_true",
                        help="lleva la pantalla de título del juego, con su "
                             "menú de empezar y cargar. Sin esto la ROM "
                             "arranca directo en el mapa, que es lo que hace "
                             "toda la tanda de regresión: la pantalla de "
                             "título le agregaría cuadros al arranque y los "
                             "96 casos comparan cuadros contados desde el "
                             "reset.")
    parser.add_argument("--con-timer", action="store_true",
                        help="la ROM lleva los dígitos del cronómetro: once "
                             "glifos de la imagen de System al final del banco "
                             "de sprites. Comparten paleta con un personaje")
    parser.add_argument("--descartar-eventos", action="store_true",
                        help="seguir aunque algún evento no entre en las "
                             "paletas de sprite. Sin esto la conversión corta: "
                             "un evento que no se dibuja igual cierra el paso, "
                             "así que descartarlo puede dejar una pared "
                             "invisible. Ver `aviso_de_descarte`")
    parser.add_argument("--switch", nargs="+", type=int, default=None,
                        metavar="N",
                        help="prende estos switches desde la página de prueba, "
                             "que es la forma de poner al mundo en un estado al "
                             "que el juego llega más tarde")
    parser.add_argument("--vars-de-prueba", nargs="+", type=int, default=None,
                        metavar="N",
                        help="ControlVars en la página de prueba, de a cinco: "
                             "VARIABLE OPERACION CLASE A B con los números de "
                             "RM2k (operación 0 pone, 1 suma, 2 resta; clase "
                             "0 constante, 1 variable, 3 azar, 7 otro)")
    parser.add_argument("--rama-var-de-prueba", nargs=5, type=int,
                        default=None,
                        metavar=("VARIABLE", "COMPARACION", "VALOR", "ADENTRO",
                                 "DESPUES"),
                        help="una rama por variable en la página de prueba, "
                             "como --rama-de-prueba: prende ADENTRO si la "
                             "variable cumple la comparación con VALOR, y "
                             "DESPUES siempre")
    parser.add_argument("--acceso-de-prueba", nargs="+", type=int,
                        default=None, metavar="N",
                        help="CUAL PERMITIDO, repetible de a dos: la página "
                             "de prueba cambia el permiso de guardar (0) o "
                             "del menú (1)")
    parser.add_argument("--items-de-prueba", nargs="+", type=int, default=None,
                        metavar="N",
                        help="ITEM CUANTO, repetible de a dos: la página de "
                             "prueba da (o quita, con CUANTO negativo) ese "
                             "ítem con un ChangeItems")
    parser.add_argument("--rama-de-prueba", nargs=3, type=int, default=None,
                        metavar=("SWITCH", "ADENTRO", "DESPUES"),
                        help="una rama en la página de prueba: si SWITCH está "
                             "prendido prende ADENTRO, y prenda o no, después "
                             "prende DESPUES. Con --switch se elige qué rama "
                             "se toma; sin él se toma la otra")
    parser.add_argument("--destello-de-prueba", nargs=5, type=int, default=None,
                        metavar=("R", "G", "B", "POTENCIA", "CUADROS"),
                        help="destella la **pantalla** desde la página de "
                             "prueba: es FlashScreen, que no es lo mismo que "
                             "--flash-de-prueba —aquél destella a un personaje—. "
                             "Ninguna página del juego que compile lo usa sin "
                             "depender de un switch, y hasta que apareció el "
                             "relámpago de la apertura este camino no lo corría "
                             "nadie")
    parser.add_argument("--flash-de-prueba", nargs=6, type=int, default=None,
                        metavar=("BLANCO", "R", "G", "B", "POTENCIA", "CUADROS"),
                        help="hace destellar a alguien desde la página de "
                             "prueba: el blanco es 0 para el héroe o el índice "
                             "del evento más uno, el color va de 0 a 31 y los "
                             "cuadros son cuántos dura")
    parser.add_argument("--ruta-de-evento", nargs="+", type=int, default=None,
                        metavar="N",
                        help="el primer número es sobre quién —el índice del "
                             "evento en la tabla del mapa más uno— y los que "
                             "siguen son las órdenes de la ruta. Detrás va un "
                             "ProceedWithMovement, así que lo que venga "
                             "después de la página no corre hasta que el "
                             "evento termine de caminar")
    parser.add_argument("--ruta-de-prueba", nargs="+", type=int, default=None,
                        metavar="ORDEN",
                        help="agrega a la página de prueba una ruta forzada "
                             "sobre el héroe, con los códigos de "
                             "rpg::MoveCommand::Code: 0..3 mover, 12..15 girar")
    parser.add_argument("--frecuencia", type=int, default=eventos.RUTA_FRECUENCIA,
                        metavar="F",
                        help="la frecuencia de las rutas de prueba, de 2 a 8: "
                             "con la 8 las órdenes van seguidas, con las otras "
                             "el personaje se para entre orden y orden como en "
                             "RM2k")
    parser.add_argument("--sacudida-de-prueba", nargs="+", type=int,
                        default=None, metavar="N",
                        help="FUERZA VELOCIDAD DECIMAS [ESPERA]: agrega a la "
                             "página de prueba una sacudida de pantalla, como "
                             "un ShakeScreen del juego")
    parser.add_argument("--pan-de-prueba", nargs="+", type=int,
                        default=None, metavar="N",
                        help="OPERACION DIRECCION DISTANCIA VELOCIDAD ESPERAR:\n"
                             "agrega a la página de prueba un PanScreen. La\n"
                             "operación es 2 para correr la cámara y 3 para\n"
                             "devolverla; ninguna página del juego que hoy\n"
                             "compile corre la cámara. Se puede repetir de a\n"
                             "cinco para encadenar varios")
    parser.add_argument("--fundir-bgm", type=int, default=0,
                        metavar="MS",
                        help="agrega a la página de prueba un FadeOutBGM de esos\n"
                             "milisegundos. Ninguna página del juego que hoy\n"
                             "compile apaga la música, así que sin esto el\n"
                             "camino no lo corre nada")
    parser.add_argument("--grafico-de-prueba", nargs=2, action="append",
                        default=None, metavar=("CHARSET", "INDICE"),
                        help="registra un gráfico para que la ruta de\n"
                             "--ruta-de-evento pueda cambiarse a él con la\n"
                             "orden 34: en la ruta va `34 N`, donde N es la\n"
                             "posición en la que se pasó éste. Se puede\n"
                             "repetir. Ninguna página que compile hoy cambia\n"
                             "de gráfico, así que sin esto el camino no lo\n"
                             "corre nada")
    parser.add_argument("--tema-de-arranque", default=None, metavar="NOMBRE",
                        help="hace que la ROM arranque tocando ese tema en vez\n"
                             "del que le toca al mapa. Existe para poder\n"
                             "verificar cada tema del cartucho con snes-check,\n"
                             "que escucha desde el arranque: los mapas donde\n"
                             "esto empieza no traen música propia y sin el flag\n"
                             "la ROM sale callada. No cambia el bytecode")
    parser.add_argument("--lugar-de-prueba", nargs="+", type=int, default=None,
                        metavar="N",
                        help="BLANCO X Y [ESPERA]: planta al evento —el índice "
                             "de la tabla más uno— en esa celda desde la página "
                             "de prueba, después de esperar esos cuadros. Es "
                             "ChangeEventLocation, y con --ruta-de-evento la "
                             "espera cae a mitad de la ruta")
    parser.add_argument("--pagina-de-prueba", nargs="+", type=int, default=None,
                        metavar="N",
                        help="ESPERA R G B [SAT]: agrega una página automática "
                             "inventada, en el mapa inicial, que espera N cuadros y "
                             "después tiñe. El otro lado del mismo flag de "
                             "snes_expect.py")
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
    parser.add_argument("--charset", default=None,
                        help="forzar el CharSet del héroe; por defecto sale "
                             "del primero del grupo, que es como lo decide RM2k")
    parser.add_argument("--charset-index", type=int, default=None,
                        help="cuál de los 8 personajes del CharSet")
    parser.add_argument("--reference", help="PNG del render de Python, para comparar")
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
    args = parser.parse_args()
    # Llevar ventana no es lo mismo que traer un mensaje de prueba, pero uno
    # implica al otro. De acá para abajo se pregunta `args.con_ventana` y
    # nada más: era `getattr(args, "mensaje_de_prueba", None)` repetido en
    # cuatro lugares, y con eso el reparto de CGRAM y el de VRAM podían
    # contestar cosas distintas.
    args.con_ventana = args.con_ventana or args.mensaje_de_prueba is not None
    args.con_timer = args.con_timer or args.timer_de_prueba is not None

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
    args.lideres = lideres_posibles(renderer, todos, grupo, args.con_ventana)
    # Si algún mapa pone lluvia, todos llevan las gotas: ver `hay_lluvia`.
    args.con_lluvia = hay_lluvia(todos)
    # Las variables del juego entero, con su ranura, antes de compilar una
    # sola página. La referencia arma el mismo índice.
    eventos.indexar_variables(args.game_dir,
                              variables_de_prueba(args.vars_de_prueba,
                                                  args.rama_var_de_prueba))
    # En cuántos mapas de esta ROM aparece cada personaje. Lo usa el reparto de
    # paletas para elegir a quién puede bajarle un color sin romper nada: el
    # banco de poses es **de la ROM entera**, así que un personaje que está en
    # dos mapas tiene que quedar cuantizado igual en los dos. Cuantizarlo
    # distinto no da una imagen fea sino un `sys.exit` al emitir, que es lo que
    # pasó la primera vez que esto se escribió: `Future1:4` bajaba en un mapa y
    # no en el otro.
    args.mapas_por_personaje = mapas_por_personaje(renderer, todos,
                                                   args.game_dir)

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
    #
    # El mensaje de prueba va **primero**, antes de todos los mapas, y eso no es
    # estético: así su desplazamiento es 0 y no depende de cuántos textos traiga
    # el mapa donde arranca la ROM ni de en qué orden se compilen. Es el único
    # texto que no sale del juego, y el único cuyo desplazamiento alguien podría
    # querer saber de memoria.
    mensajes = eventos.Mensajes() if args.con_ventana else None
    # Los temas que los PlayBGM de las páginas piden, numerados en el orden en
    # que aparecen. La ROM lleva uno solo —ver `Temas`— y lo elige más abajo,
    # cuando ya están todos compilados y se sabe cuáles se piden.
    temas = eventos.Temas()
    prueba = (mensajes.agregar(args.mensaje_de_prueba)
              if args.mensaje_de_prueba is not None else None)

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
        graficos = eventos.Graficos()
        paginas = eventos.paginas_del_mapa(mapa["game_map"], indices.get,
                                           mensajes, temas, graficos)
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
        if args.grafico_de_prueba and mapa is mapas[args.inicial]:
            for charset, index in graficos_de_prueba(args.grafico_de_prueba):
                graficos.indice(charset, index)
        if graficos.pares != mapa["graficos_de_ruta"]:
            # Las dos pasadas compilaron cosas distintas. No puede pasar —las
            # dos usan `paginas_del_mapa` con el mismo `con_ventana`— y si
            # pasara, el bytecode quedaría apuntando a la tabla equivocada sin
            # que nada lo diga.
            sys.exit("mapa %d: las dos pasadas numeraron distinto los gráficos "
                     "de ruta: %s contra %s"
                     % (mapa["id"], graficos.pares, mapa["graficos_de_ruta"]))
        if (args.pagina_de_prueba or args.ruta_de_prueba
                or args.rama_de_prueba or args.guardar_de_prueba
                or args.vars_de_prueba or args.rama_var_de_prueba
                or args.items_de_prueba or args.acceso_de_prueba
                or args.ruta_de_evento or args.flash_de_prueba or args.switch
                or args.destello_de_prueba
                or args.timer_de_prueba or args.lugar_de_prueba
                or args.sacudida_de_prueba or args.fundir_bgm
                or args.pan_de_prueba
                or args.mensaje_de_prueba is not None) \
                and mapa is mapas[args.inicial]:
            # La página inventada, sólo en el mapa donde arranca la ROM. No sale
            # de ningún dato del juego: existe porque ninguna página que compile
            # tiene una espera, así que el intérprete cuadro a cuadro no lo
            # ejercitaba nada. La referencia arma la misma con la misma función.
            # El primer índice libre del mapa; ver `eventos.evento_de_prueba`.
            mapa["EV_COUNT_PRUEBA"] = len(mapa["ev_pos"]) // EV_STRIDE
            espera, tinte = 0, ()
            if args.pagina_de_prueba:
                espera, *tinte = args.pagina_de_prueba
            paginas = paginas + [{
                "evento": mapa["EV_COUNT_PRUEBA"], "pagina": 0,
                "trigger": eventos.TRIGGER_AUTOMATICO,
                "switch_a": 0, "switch_b": 0, "actor": 0, "variable": None,
                "item": 0, "capa": 0,
                "frecuencia": eventos.RUTA_FRECUENCIA, "velocidad": 4,
                "codigo": eventos.pagina_de_prueba(
                    espera, tinte, args.ruta_de_prueba or (), prueba,
                    ruta_de_evento(args.ruta_de_evento),
                    args.flash_de_prueba or (), args.switch or (),
                    args.timer_de_prueba or (),
                    lugar_de_prueba(args.lugar_de_prueba),
                    frecuencia=args.frecuencia,
                    sacudida=sacudida_de_prueba(args.sacudida_de_prueba),
                    fundir_bgm=args.fundir_bgm,
                    pan=pan_de_prueba(args.pan_de_prueba),
                    rama=tuple(args.rama_de_prueba or ()),
                    destello=tuple(args.destello_de_prueba or ()),
                    guardar=args.guardar_de_prueba,
                    variables=tuple(args.vars_de_prueba or ()),
                    rama_var=tuple(args.rama_var_de_prueba or ()),
                    items=tuple(args.items_de_prueba or ()),
                    acceso=tuple(args.acceso_de_prueba or ()))}, {
                # Y la que la apaga: misma idea que en la referencia, ver
                # `PAGINA_DE_PRUEBA_APAGADA`. Sin código, así que en cuanto
                # gana, el evento inventado deja de tener una automática que
                # correr y la primera no se repite.
                "evento": mapa["EV_COUNT_PRUEBA"], "pagina": 1,
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
        blancos = {c[i + 1] for p in paginas if p["codigo"]
                   for i, c in recorrer_codigo(p["codigo"])
                   if c[i] == eventos.OP_RUTA and c[i + 1]}
        # Y que nadie destelle a alguien que comparte gráfico con otro. En la
        # consola el destello se hace sobre la paleta del personaje, así que dos
        # que compartan gráfico destellarían juntos. `eventos.py` ya rechaza el
        # caso de dos eventos; acá se cubre el que allá no se puede ver, que es
        # el del héroe: qué gráfico tiene depende del grupo, y eso lo sabe el
        # conversor y no el compilador.
        graficos = collections.Counter(
            (npc["charset"], npc["index"])
            for npc in rm2k.collect_npcs(mapa["game_map"]))
        for actor in args.lideres:
            a = renderer.database.actors[actor]
            graficos[(a.charset, a.charset_index)] += 1
        for pagina in paginas:
            for i, c in recorrer_codigo(pagina["codigo"] or b""):
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
        # Y a qué mapas de afuera de la ROM apuntan las que no compilan.
        #
        # Un `Teleport` a un mapa que no entró corta la página entera, y una
        # página que no compila no hace **nada**: ni el teletransporte ni lo que
        # venía antes. `snes-evento` lo dice en su comentario desde siempre,
        # pero el conteo de arriba no distingue esta razón de las otras por las
        # que una página se cae, y es la única que se arregla desde afuera
        # —sumando el mapa— y no tocando el compilador. Así se pasó por alto la
        # página del ascensor del mapa 2, que se veía abrirse y no llevaba a
        # ningún lado porque termina saltando al mapa 3. La lista de puertas ya
        # avisa lo mismo; esto es su equivalente para las páginas.
        afuera_de, cuantas = set(), 0
        for pagina in paginas:
            if pagina["codigo"] or pagina["trigger"] not in eventos.TRIGGERS \
                    or pagina["evento"] >= len(mapa["game_map"].events):
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
                deudas |= set(eventos.deudas_de_la_pagina(page))
        for codigo_cmd in sorted(deudas):
            print("  mapa %d: AVISO, una página usa %s y la ROM no lo hace; "
                  "ver ACEPTADOS_SIN_HACER en tools/eventos.py"
                  % (mapa["id"], event_codes.EVENT_CODES.get(codigo_cmd,
                                                             codigo_cmd)))

    if not 0 <= args.inicial < len(mapas):
        sys.exit("--inicial %d pero hay %d mapas" % (args.inicial, len(mapas)))
    ventana_datos = None
    if args.con_ventana:
        import ventana as ventana_mod
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
    # pero no depende de `--con-ventana`: ese flag es un presupuesto de VRAM
    # del mapa, y esta pantalla vive en la VRAM del título, donde no hay mapa.
    import ventana as ventana_mod
    skin = ventana_mod.skin(args.game_dir, renderer.database.system_name)
    # Los actores que pueden estar en el grupo cuando se guarda, para tener
    # su cara y su nombre en el cartucho: los de arranque y todos los que
    # agrega algún `ChangePartyMembers` de estos mapas, compilen sus páginas o
    # no. Es un superconjunto a propósito: una cara de más cuesta 36 tiles y
    # una de menos deja un hueco en el menú.
    miembros = miembros_posibles(todos, grupo)
    # Y los ítems que pueden estar en el inventario, para llevar su nombre y
    # su descripción: ver "la pantalla de ítems" en titulo.py.
    items_rom = items_posibles(todos, args.items_de_prueba, miembros,
                               renderer.database)
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
    informe = emit(args.output, mapas, args.inicial, args.heroe_encima, grupo,
                   ventana_datos, titulo_datos, ranuras_datos)
    print("%d mapa(s) -> %s, arranca en el %d (mapa %d)"
          % (len(mapas), args.output, args.inicial, mapas[args.inicial]["id"]))
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
    driver, muestras, hechos, banco, afuera = snes_music.build_varios(
        pedidos, args.game_dir, pedidos_se)
    if arranque != 0xFF and arranque >= len(hechos):
        arranque = 0xFF             # el del mapa fue uno de los que no entró
    if tema_titulo != 0xFF and tema_titulo >= len(hechos):
        tema_titulo = 0xFF          # el del título tampoco entró en la ARAM
    snes_music.emit(musica, hechos, driver, muestras, arranque, tema_titulo,
                    snes_music.tabla_de_sonidos(temas.sonidos, banco))
    if pedidos_se:
        entraron = getattr(banco, "efectos", {})
        print("  efectos de sonido: %d de %d en %d B; no entran y no suenan: "
              "%s" % (len(entraron), len(pedidos_se),
                      sum(len(e.data) + 4 for _s, e in entraron.values()),
                      ", ".join(n for n in pedidos_se if n not in entraron)
                      or "ninguno"))
    print("música -> %s: %s"
          % (musica, ", ".join(t["nombre"] for t in hechos)
             or "ninguna, sale muda"))
    for i, tema in enumerate(hechos):
        print("  %d. %-16s %4.0f s, %6d B de stream%s"
              % (i, tema["nombre"], tema["segundos"], len(tema["stream"]),
                 ", suena desde el arranque" if i == arranque else ""))
    if hechos:
        print("  banco compartido: %d muestras, %d B de los %d de ARAM"
              % (len(banco.voces), banco.bytes, snes_music.ARAM_LIBRE))
    if afuera:
        print("  no entraron en ARAM y quedan mudos: %s" % ", ".join(afuera))

    if args.reference:
        mapas[args.inicial]["base"].save(args.reference)
        print("referencia -> %s" % args.reference)


def temas_de_la_rom(map_id, temas, game_dir, forzado=None, titulo=None):
    """Qué temas pide el cartucho y cuál suena al arrancar.

    Se piden **todos**: los que los `PlayBGM` compilados nombran, más el del
    mapa donde la ROM arranca, que es el que suena sin que pase nada. Cuántos
    entran de verdad lo decide `snes_music.build_varios`, y no lo limita el
    cartucho sino la ARAM: las muestras las comparten y el banco compartido
    vive en los 64 KB del SPC700.

    Los índices son los de `Temas` y no se tocan: el bytecode ya los lleva
    emitidos, así que uno que no entre simplemente no suena —lo mismo que
    hacían todos menos uno hasta el 2026-09-06—. Por eso el del mapa se agrega
    **al final**, que es lo único que no renumera a los demás.
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
    """
    if map_id == renderer.tree.start_map_id:
        return renderer.tree.start_x, renderer.tree.start_y
    return hero_start(passable, width, height, ocupadas)


def images_de(renderer, args, charset):
    """El CharSet de un actor, cargado y cacheado."""
    if charset not in _charsets:
        _charsets[charset] = renderer.charsets.get(charset)
        if _charsets[charset] is None:
            sys.exit("no encuentro el CharSet %r" % charset)
    return _charsets[charset]


_charsets = {}


def lideres_posibles(renderer, map_ids, grupo, con_ventana=False):
    """Los actores que pueden llegar a dibujarse como héroe en esta ROM.

    El grupo con el que se arranca, más todos los que agregue un
    `ChangePartyMembers` de alguna página que compile. Sacar a alguien también
    cambia el líder, pero al siguiente de la lista, que ya está contado.

    `con_ventana` tiene que ser el de la ROM que se está armando, porque decide
    **qué páginas compilan**: una que agregue a alguien al grupo después de un
    cuadro de texto compila con ventana y no compila sin ella. Filtrar distinto
    acá que allá dejaría a ese actor sin sus tiles en la VRAM y la ROM lo
    dibujaría con los del anterior. El bloque de textos que se arma es de
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
                if eventos.compilar_pagina(
                        page, indices.get,
                        eventos.Mensajes() if con_ventana else None,
                        del_mapa.para(evento.id)) is None:
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


def items_posibles(map_ids, de_prueba=None, actores=(), db=None):
    """Los ítems que pueden estar en el inventario con estos mapas en la ROM:
    los que da algún `ChangeItems` de cualquier página, compile o no, los que
    vende alguna `OpenShop`, el equipo con el que arrancan los `actores` y los
    que da la página de prueba. Es un superconjunto, como `miembros_posibles`,
    y por la misma razón: un ítem de más cuesta su texto en el cartucho, uno
    de menos no se ve en la lista."""
    items = set()
    for actor in actores:
        if db is not None and actor in db.actors:
            items.update(i for i in db.actors[actor].initial_equipment if i)
    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(args_game_dir[0],
                                        "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                for cmd in page.commands:
                    p = cmd.parameters
                    if (cmd.code == eventos.CHANGE_ITEMS and len(p) >= 5
                            and p[0] == 0 and p[1] == 0):
                        items.add(p[2])
                    elif cmd.code == eventos.OPEN_SHOP:
                        items.update(p[4:])
    for k in range(0, len(de_prueba or ()), 2):
        items.add(de_prueba[k])
    return sorted(i for i in items if 0 < i < eventos.ITEMS_N)


def miembros_posibles(map_ids, grupo):
    """Los actores que pueden estar en el grupo con estos mapas en la ROM.

    Los de arranque más los que agrega cualquier `ChangePartyMembers` de
    cualquier página de estos mapas. No se mira si la página compila: es para
    la pantalla de ranuras, que necesita la cara y el nombre de quien pueda
    aparecer en una partida guardada, y una cara de más no cuesta nada que
    importe.
    """
    actores = list(grupo)
    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(args_game_dir[0],
                                        "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                for cmd in page.commands:
                    if cmd.code != eventos.CHANGE_PARTY_MEMBERS:
                        continue
                    p = cmd.parameters
                    if len(p) < 3 or p[1] != eventos.GRUPO_ID_FIJO:
                        continue
                    if p[0] == 0 and p[2] not in actores:
                        actores.append(p[2])
    return sorted(actores)


def convertir(renderer, map_id, args, inicio=None, ventana_paleta=None):
    """Un mapa entero: tiles, colores, sprites, colisión y bloques."""
    game_map = renderer.cargar_mapa(
        os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    name = renderer.tree.map_names.get(map_id, "?")

    base, _above, variantes = renderer.capas_animadas(game_map)

    if base is None:
        sys.exit("no encuentro el chipset del mapa %d" % map_id)

    (tile_data, cram, tilemap, summary), above_data = convert_layers(
        base, _above, con_ventana=args.con_ventana,
        ventana_paleta=ventana_paleta, variantes=variantes)

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
    movibles, graficos_de_ruta, anima_quieto = eventos_movibles(
        game_map, {m: i for i, m in enumerate(orden)}.get,
        con_ventana=args.con_ventana)
    # Y los de `--grafico-de-prueba`, que van sólo en el mapa donde arranca la
    # ROM, igual que la ruta inventada y por lo mismo: es donde el conversor
    # mete la página de prueba. Se agregan **después** de los del juego, que es
    # el orden en que los numera la compilación de verdad.
    if args.grafico_de_prueba and map_id == orden[args.inicial]:
        for charset, index in graficos_de_prueba(args.grafico_de_prueba):
            if (charset, index) not in graficos_de_ruta:
                graficos_de_ruta.append((charset, index))

    # Las ocho, con o sin cronómetro: sus dos colores entran en la paleta de
    # algún personaje. Reservarle una acá le sacaba eventos al mapa, porque este
    # número es el que decide cuáles se dibujan.
    tope_de_paletas = OBJ_PALETTES
    # Los colores del cronómetro se pasan al reparto y no sólo al empaquetado:
    # en un mapa que llene las ocho paletas hay que decidir a quién bajarle un
    # color para hacerle lugar, y eso cambia cómo se cuantiza a ese personaje.
    timer_colores = ()
    if args.con_timer:
        import ventana as ventana_mod
        timer_colores = sorted(colores_del_timer(ventana_mod.skin(
            args.game_dir, renderer.database.system_name)))

    npcs, descartados, reparto = npcs_dibujables(renderer, game_map,
                                                 args.lideres, tope_de_paletas,
                                                 graficos_de_ruta,
                                                 timer_colores,
                                                 {c for c, n in getattr(
                                                     args, "mapas_por_personaje",
                                                     {}).items() if n == 1})
    prestadas = reparto[5] if len(reparto) > 5 else set()
    if prestadas:
        print("  mapa %d: %d gráfico(s) sin paleta propia, dibujados con una "
              "ajena: %s" % (map_id, len(prestadas),
                             ", ".join(sorted("%s:%d" % k for k in prestadas))))
    for evento, tile in descartados:
        aviso_de_descarte(
            args, "mapa %d: el evento %d, dibujado con el tile %s, no entra en "
            "las %d paletas de sprite y no se dibuja"
            % (map_id, evento + 1, tile[len(rm2k.TILE_PREFIX):],
               tope_de_paletas),
            cambia_de_grafico(game_map.events[evento]))
    # Quiénes van a caminar. A ésos les hacen falta las doce poses del ciclo, y
    # el resto se queda con la única que declara su página.
    # La ruta inventada de `--ruta-de-evento` también manda a caminar a alguien,
    # y su página no sale de `paginas_del_mapa`: hay que sumarla a mano o el NPC
    # caminaría con una sola pose. Va sólo en el mapa donde arranca la ROM, que
    # es donde el conversor mete esa página.
    prueba_ev = ruta_de_evento(args.ruta_de_evento)
    if prueba_ev and map_id == orden[args.inicial]:
        movibles = movibles | {prueba_ev[0] - 1}
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
    afuera_de_ruta = [par for par, se_ve in zip(graficos_de_ruta, grafico_se_ve)
                      if not se_ve and sprite_colors(
                          images_de(renderer, args, par[0]), par[1])]
    for charset, index in afuera_de_ruta:
        aviso_de_descarte(
            args, "mapa %d: el gráfico %s:%d, al que cambia una ruta, no entra "
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
    if args.con_timer:
        import ventana as ventana_mod
        sys_img = ventana_mod.skin(args.game_dir, renderer.database.system_name)
        tiles, timer_base, timer_pal = digitos_del_timer(
            sys_img, tiles, palettes, reparto[3] if len(reparto) > 3 else ())
    lluvia_base, lluvia_pal = 0, 0
    if args.con_lluvia:
        tiles, lluvia_base, lluvia_pal = gotas_de_lluvia(
            tiles, palettes, reparto[3] if len(reparto) > 3 else (),
            timer_base)
        if not lluvia_base:
            print("  mapa %d: AVISO, las gotas de lluvia no entran en las "
                  "paletas de sprite y acá no llueve" % map_id)
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
    sprite = (tiles, palettes, where, table, actores, timer_base, timer_pal,
              animados, bancos, ruta_graficos, lluvia_base, lluvia_pal)

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
            len(sprite[0]) // 32 if sprite else 0,
            con_ventana=args.con_ventana),
        "resumen": summary, "base": base,
        "anim": anim_bytes(summary["animacion"]),
        "puertas_crudas": rm2k.collect_doors(game_map),
        # Se guarda el mapa entero porque las puertas y los eventos no se
        # pueden resolver hasta que estén todos: los dos traducen ids de mapa a
        # índices de la tabla.
        "game_map": game_map,
        # Para la tabla de páginas: dónde quedó cada (CharSet, índice, pose)
        # en el banco de sprites, qué eventos cambian de gráfico con la
        # página y qué gráficos suyos quedaron afuera de las paletas.
        "where": where,
        "cambian": {npc["evento"] for npc in npcs if npc["cambia"]},
        # Y los que sólo aparecen y desaparecen con ella: los que caminan, a
        # los que el gráfico se les fijó más arriba.
        "aparecen": {npc["evento"] for npc in npcs if npc.get("aparece")},
        "afuera": {npc["evento"]: npc["afuera"] for npc in npcs},
    }


if __name__ == "__main__":
    main()
