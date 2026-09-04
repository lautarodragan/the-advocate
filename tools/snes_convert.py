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


def bg_budget(first):
    """Los colores que le quedan al fondo debajo de la capa de encima.

    El 0 no cuenta: es el color de fondo de la pantalla y ningún tile lo usa.
    """
    return first * COLORS_PER_PALETTE - 1


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
VENTANA_TILE_BASE = 256

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
# donde un tile usa el índice 0. Magenta, que no aparece en ningún mapa, así que
# si asoma dentro de la pantalla es que algo está mal.
BACKDROP = (31, 0, 31)


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

    Los tres bits de paleta no se usan: en 8 bits por pixel el índice ya
    alcanza CGRAM entero y el PPU los ignora.
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
SPRITE_PALETTE = 8                 # los sprites usan las paletas 8 a 15

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


def build_characters(images, characters):
    """El banco de sprites de varios personajes, cada uno con su paleta.

    `characters` es una lista de (charset, índice, poses). El héroe pide sus 12
    poses porque camina; cada NPC, sólo la que declara.

    Devuelve (tiles, paletas, ubicación), donde ubicación mapea
    (charset, índice, pose) a (bloque, número de paleta).
    """
    tiles = bytearray()
    palettes = []
    where = {}
    block = 0

    for charset, index, poses in characters:
        image = images[charset]
        counts = sprite_colors(image, index)
        if len(counts) <= OBJ_COLORS:
            mapping = {c: c for c in counts}
        else:
            mapping, _ = pixeles.merge_least_used(counts, OBJ_COLORS)
        palette = sorted(set(mapping.values()))
        lookup = {color: i + 1 for i, color in enumerate(palette)}
        slot = len(palettes)
        palettes.append(palette)

        for pose in poses:
            where[(charset, index, pose)] = (block, slot)
            ox, oy = pose_origin(index, pose)
            first = block_tile(block)
            # El bloque no ocupa 16 tiles seguidos: es un cuadrado de 4x4 dentro
            # de una grilla de 16 de ancho, así que hay que dejar el hueco.
            needed = (first + 3 * OBJ_ROW + 4) * 32
            if len(tiles) < needed:
                tiles += bytes(needed - len(tiles))
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
                    number = first + ty * OBJ_ROW + tx
                    tiles[number * 32:(number + 1) * 32] = pack_tile(
                        tuple(cell), planes=4)
            block += 1

    return bytes(tiles), palettes, where


# El cronómetro: once glifos de 8x16 en el System, a partir de (32, 32). Diez
# dígitos y los dos puntos, que es todo lo que `Sprite_Timer::Draw` dibuja.
TIMER_GLIFOS = 11
TIMER_GLIFO_W, TIMER_GLIFO_H = 8, 16
TIMER_ORIGEN = (32, 32)
# Dónde se dibuja en pantalla. `Sprite_Timer` lo pone en
# `menu_offset_x + 4` y `menu_offset_y + 4`, y con una pantalla más angosta que
# el menú los dos desplazamientos dan cero.
TIMER_X, TIMER_Y = 4, 4


def digitos_del_timer(sys_img, tiles, palettes):
    """Los once glifos del cronómetro, al final del banco de sprites.

    Van como dos tiles de 8x8 apilados cada uno, y los once entran en una fila
    de dieciséis: el glifo i ocupa el tile `base + i` y el `base + 16 + i`. La
    base se redondea a una fila para que esa cuenta valga.

    Devuelve (tiles, base, paleta). La paleta es propia y no la de un personaje:
    los dígitos salen del System, que no comparte colores con ningún CharSet.
    """
    colores = collections.Counter()
    for i in range(TIMER_GLIFOS):
        for y in range(TIMER_GLIFO_H):
            for x in range(TIMER_GLIFO_W):
                r, g, b, a = sys_img.getpixel((TIMER_ORIGEN[0] + i * 8 + x,
                                               TIMER_ORIGEN[1] + y))
                if a:
                    colores[(r >> 3, g >> 3, b >> 3)] += 1
    if len(colores) > OBJ_COLORS:
        raise SystemExit("los dígitos del cronómetro usan %d colores y entran %d"
                         % (len(colores), OBJ_COLORS))
    paleta = sorted(colores)
    indice = {color: i + 1 for i, color in enumerate(paleta)}

    tiles = bytearray(tiles)
    base = -(-(len(tiles) // 32) // 16) * 16
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
    return bytes(tiles), base, paleta


def npc_table(npcs, where, movibles=()):
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

    Los de `movibles` llevan además sus doce poses, para que la ROM pueda
    cambiarles el tile mientras caminan.
    """
    rows = []
    for npc in sorted(npcs, key=orden_de_dibujo, reverse=True):
        block, slot = where[(npc["charset"], npc["index"], npc["pose"])]
        rows.append({
            "x": npc["x"] * 16, "y": npc["y"] * 16,
            "tile": block_tile(block), "palette": slot,
            "layer": npc["layer"], "blocks": npc["blocks"],
            "evento": npc["evento"], "dir": npc["pose"] // 3,
            "poses": [block_tile(where[(npc["charset"], npc["index"], pose)][0])
                      for pose in range(SPRITE_POSES)]
            if npc["evento"] in movibles else None,
        })
    return rows


# --- conversión -------------------------------------------------------------

def build_palette(grid, bg_colors):
    """Los colores del mapa, en una sola tabla, fusionando sólo si sobran.

    Con 8 bits por pixel el único límite es cuántas entradas de CGRAM quedan
    libres debajo de la capa de encima. Map0007 usa 60, así que no se fusiona
    nada; el camino de fusión existe para mapas más cargados y es el mismo de
    la Mega Drive.
    """
    counts = collections.Counter(p for row in grid for tile in row
                                 for line in tile for p in line
                                 if p is not None)
    if len(counts) <= bg_colors:
        return sorted(counts), grid, []

    mapping, merged = pixeles.merge_least_used(counts, bg_colors)
    grid = [[tuple(tuple(mapping.get(p) for p in line) for line in tile)
             for tile in row] for row in grid]
    return sorted({c for c in mapping.values()}), grid, merged


def convert_layers(base, above_img, con_ventana=False, ventana_paleta=None):
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

    # Lo que el fondo usa, y por lo tanto las paletas de 16 que necesita. El
    # +1 es el color de fondo de la pantalla, que ocupa la entrada 0.
    usados = len({p for row in base_grid for tile in row
                  for line in tile for p in line if p is not None})
    pide = -(-(usados + 1) // COLORS_PER_PALETTE)
    libres = max(1, min(MAX_ABOVE_PALETTES, BG_PALETTES - pide))

    above = convert_above(above_img, palettes=libres, grid=above_grid)
    tope = above[3] - (1 if con_ventana else 0)
    if ventana_paleta is not None:
        if ventana_paleta >= above[3]:
            raise SystemExit(
                "la ventana de mensaje va en la paleta %d y la capa de encima "
                "de este mapa arranca en la %d: se pisarían"
                % (ventana_paleta, above[3]))
        tope = ventana_paleta
    if tope < 1:
        # Inalcanzable con los datos del juego —haría falta una capa de encima
        # que pida las siete paletas— pero si pasa, el fondo se quedaría sin
        # ninguna y `bg_budget` daría un presupuesto negativo.
        raise SystemExit(
            "no hay paleta libre para la ventana de mensaje: la capa de encima "
            "arranca en la %d y no queda ninguna para el fondo" % above[3])
    return convert(base, bg_budget(tope), grid=base_grid), above


def paleta_de_la_ventana(primeras):
    """En qué paleta va la ventana de mensaje en una ROM de varios mapas.

    Las celdas de la ventana se emiten una sola vez con los tres bits de
    paleta adentro, así que la paleta es una para toda la ROM. Cada mapa la
    pondría justo debajo de su capa de encima, y eso no coincide: en la ROM del
    arranque el mapa 4 la arranca en la 7 y los mapas 1 y 2 en la 4. Se toma la
    más baja de todas, que es la única que no se pisa con ninguna capa de
    encima, y los mapas que la tenían más arriba se vuelven a convertir con el
    fondo apretado debajo de ella. Es la misma cuenta acá y en la referencia:
    `primeras` es el `above[3]` de cada mapa de la ROM.
    """
    return min(primeras) - 1


def convert(image, bg_colors=None, grid=None):
    """La imagen del mapa a tiles, paleta y tilemap.

    `bg_colors` es lo que le dejó libre la capa de encima; sin él se asume el
    reparto de dos paletas arriba, que es el que valía cuando no se elegía.

    Devuelve (datos de tiles, palabras de CGRAM, tilemap, resumen).
    """
    if bg_colors is None:
        bg_colors = bg_budget(above_split(2))
    if grid is None:
        grid = cut_tiles(quantize(image))
    before = len({p for row in grid for tile in row
                  for line in tile for p in line if p is not None})
    palette, grid, merged = build_palette(grid, bg_colors)

    pool, tilemap = {}, []
    for row in grid:
        line = []
        for tile in row:
            indices = to_indices(tile, palette)

            # Si alguna de las cuatro orientaciones ya está en el pool, se
            # reusa: el PPU sabe espejar por su cuenta y sale gratis.
            placed = None
            for oriented, horizontal, vertical in flips(indices):
                if oriented in pool:
                    placed = entry(pool[oriented], horizontal, vertical)
                    break
            if placed is None:
                if len(pool) >= MAX_TILES:
                    raise SystemExit("el mapa necesita más de %d tiles" % MAX_TILES)
                pool[indices] = len(pool)
                placed = entry(pool[indices], 0, 0)
            line.append(placed)
        tilemap.append(line)

    tile_data = bytearray(BYTES_PER_TILE * len(pool))
    for indices, number in pool.items():
        tile_data[number * BYTES_PER_TILE:(number + 1) * BYTES_PER_TILE] = \
            pack_tile(indices)

    # CGRAM: el 0 es el fondo y los colores del mapa arrancan en el 1, que es
    # el mismo orden que usa to_indices.
    cram = [cgram_word(BACKDROP)] + [cgram_word(c) for c in palette]

    summary = {
        "colores": before,
        "usados": len(palette),
        "presupuesto": bg_colors,
        "fusionados": len(merged),
        "tiles": len(pool),
        "celdas": sum(len(row) for row in tilemap),
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
LAYOUT_ANCHO = {"tiles": (0x0000, 512), "sprites": (0x4000, 512),
                "encima": (0x6000, 256)}
LAYOUT_FONDO = {"tiles": (0x0000, 640), "encima": (0x5000, 256),
                "sprites": (0x6000, 256)}

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
# segundo y **3 se quedan sin ventana** —el 8, el 66 y el 250—.
#
# El número viejo que estaba escrito acá era 2, y estaba mal por una razón que
# vale la pena dejar dicha: `vram_layout` no comprobaba que los tiles de fondo
# entraran en el banco del reparto elegido. `MAX_TILES` es 1024, que es el tope
# del índice del tilemap y no el del banco, así que los mapas 66 y 250 —518 y
# 620 tiles de fondo— se llevaban el reparto de 512 y se pasaban por arriba de
# la capa de encima. Nunca se vio porque ninguna receta les pide una ventana.
LAYOUT_VENTANA = {"sprites": (0x0000, 448), "ventana_map": (0x1C00, 1),
                  "tiles": (0x2000, 384),
                  "encima": (0x5000, 256), "ventana": (0x6000, 256)}
LAYOUT_VENTANA_FONDO = {"sprites": (0x0000, 256), "tiles": (0x1000, 480),
                        "ventana_map": (0x4C00, 1),
                        "encima": (0x5000, 256), "ventana": (0x6000, 256)}
VRAM_MAP = 0x7000
VRAM_ABOVE_MAP = 0x7800

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


def render_converted(tile_data, cram, tilemap, above=None):
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

    # CGRAM tal como queda en la consola: el fondo desde el 0 y la capa de
    # encima en las paletas que se haya llevado, que son las de más arriba de
    # la mitad baja. Dónde arranca lo dice ella, no una constante.
    words = list(cram) + [0] * (128 - len(cram))
    if above:
        colors = above[1]
        first = above[3] * COLORS_PER_PALETTE
        for i in range(len(colors) // 2):
            words[first + i] = int.from_bytes(colors[i * 2:i * 2 + 2], "little")
    palette = [((c & 0x1F), (c >> 5) & 0x1F, (c >> 10) & 0x1F) for c in words]

    def draw(cells, data, planes):
        for ty, row in enumerate(cells):
            for tx, cell in enumerate(row):
                number = cell & 0x03FF
                pal = (cell >> 10) & 0x07
                indices = unpack_tile(
                    data[number * (planes * 8):(number + 1) * (planes * 8)],
                    planes)
                for y in range(CELL):
                    for x in range(CELL):
                        sx = CELL - 1 - x if cell & 0x4000 else x
                        sy = CELL - 1 - y if cell & 0x8000 else y
                        value = indices[sy][sx]
                        if planes == 4:
                            if not value:
                                continue        # transparente
                            # En 4 bits el índice se cuenta dentro de la paleta
                            # que dice la celda; ésa ya lleva el desplazamiento.
                            value += pal * COLORS_PER_PALETTE
                        color = palette[value] if value < len(palette) else (0, 0, 0)
                        image.putpixel((tx * CELL + x, ty * CELL + y),
                                       (color[0] << 3, color[1] << 3,
                                        color[2] << 3, 255))

    if tilemap is not None:
        draw(tilemap, tile_data, 8)
    if above:
        draw(above[2], above[0], 4)
    return image


def render_above(cram, above):
    """Sólo la capa de encima, transparente donde no dibuja nada."""
    from PIL import Image

    height, width = len(above[2]), len(above[2][0])
    image = Image.new("RGBA", (width * CELL, height * CELL), (0, 0, 0, 0))
    lleno = render_converted(b"", cram, None, above)
    image.paste(lleno, (0, 0))
    # Lo que la capa no toca quedó del color de fondo; ahí va transparente.
    fondo = (BACKDROP[0] << 3, BACKDROP[1] << 3, BACKDROP[2] << 3, 255)
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
    ("ACTOR_COUNT", "cuántos candidatos a líder del grupo"),
    ("PUERTA_COUNT", "cuántas puertas salen de este mapa"),
    ("PAGINA_COUNT", "cuántas páginas de evento hay que resolver"),
]
MAPA_BYTES = [
    ("OBSEL_VALUE", "objetos de 8x8 y 32x32, y la página de sus tiles"),
    ("BG12NBA_VALUE", "las páginas de tiles de BG1 y BG2"),
    ("ABOVE_FIRST", "en qué entrada de CGRAM arranca la capa de encima"),
    ("TIMER_PAL", "la paleta de sprite de los dígitos del cronómetro"),
]
MAPA_PUNTEROS = ["map_tiles", "map_cgram", "above_tiles", "above_cgram",
                 "sprite_tiles", "sprite_cgram", "map_celdas", "map_bloques",
                 "bloque_pass", "npc_table", "actor_table", "puertas",
                 "paginas", "ev_pos", "npc_poses"]
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
PAGINA_BYTES = 16
ACTOR_BYTES = 26     # id, paleta y doce tiles de 16 bits
ACTOR_INVISIBLE = 0xFFFF   # un actor sin gráfico: la ROM no lo dibuja

# Un bit por switch. El juego consulta hasta el 1003 en las condiciones de
# página, así que con 1024 alcanza y sobra: son 128 bytes de RAM.
SWITCH_BYTES = 128


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
        "ACTOR_COUNT": len(sprite[4]) if sprite else 0,
        "PUERTA_COUNT": len(mapa["puertas"]) // PUERTA_BYTES,
        "PAGINA_COUNT": len(mapa["paginas"]),
        "OBSEL_VALUE": 0x20 | (layout["sprites"][0] // 0x2000),
        "BG12NBA_VALUE": ((layout["encima"][0] // 0x1000) << 4)
                         | (layout["tiles"][0] // 0x1000),
        "ABOVE_FIRST": above[3] * COLORS_PER_PALETTE,
        "TIMER_PAL": (sprite[6] if sprite and sprite[6] is not None else 0),
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


def tabla_de_mapas(mapas):
    """La tabla que la ROM recorre para saber qué cargar."""
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
            etiqueta = "%s_%d" % (nombre, numero)
            out.append("    .byte <(%s), >(%s), ^(%s), $00 ; +%d  %s"
                       % (etiqueta, etiqueta, etiqueta, usado, nombre))
            usado += MAPA_PTR_PASO
        assert usado <= MAPA_STRIDE, usado
        out.append("    .byte " + ",".join(["$00"] * (MAPA_STRIDE - usado)))
    return "\n".join(out)


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


def tabla_de_paginas(mapa, numero):
    """Las páginas de evento del mapa, con el puntero a su código.

    No pasa por `bloque()` porque sus punteros son simbólicos: apuntan adentro
    del bloque de código, que el enlazador ubica.
    """
    out = ["paginas_%d:" % numero]
    for pagina in mapa["paginas"]:
        if pagina["codigo"]:
            destino = "evcodigo_%d + %d" % (numero, pagina["offset"])
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
        out.append("    .byte " + ",".join(["$00"] * (PAGINA_BYTES - 12)))
    if not mapa["paginas"]:
        out.append("    .byte $00")     # una etiqueta no puede quedar vacía
    return "\n".join(out)


def datos_del_mapa(mapa, numero):
    """Los bloques de datos de un mapa, con el número pegado a cada etiqueta."""
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
        ("npc_poses", npc_poses_bytes(sprite[3]) if sprite else b""),
        ("ev_pos", mapa["ev_pos"]),
        ("actor_table", actor_bytes(sprite[4]) if sprite else b""),
        ("puertas", mapa["puertas"]),
        ("evcodigo", mapa["evcodigo"]),
    ]
    out = [bloque("%s_%d" % (nombre, numero), datos) for nombre, datos in pares]
    # La grilla va aparte porque es la única que no se sube por DMA.
    out.append(bloque("map_celdas_%d" % numero, mapa["celdas"], alinear=2))
    out.append(tabla_de_paginas(mapa, numero))
    return "\n".join(out)


def emit(path, mapas, inicial=0, heroe_encima=False, grupo_inicial=(),
         ventana=None):
    """El .inc que arma w65.py junto con main.s."""
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
        "; La tabla de posiciones de eventos, y cuántas rutas forzadas\n"
        "; pueden estar corriendo a la vez sobre ellos.\n"
        "EV_STRIDE   = %d\n"
        "EV_MAX      = %d\n"
        "RUTA_EV_MAX = %d\n"
        "PUERTA_BYTES = %d\n"
        "PAGINA_BYTES = %d\n"
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
        "TRIGGER_AUTOMATICO = %d\n"
        "TRIGGER_ACCION     = %d\n"
        "TRIGGER_TOCA_HEROE = %d\n"
        "; Cuántos cuadros dura un paso de una celda. Sale del modelo y no de\n"
        "; una cuenta en la ROM: es lo que los dos lados tienen que contar\n"
        "; igual para que una ruta forzada termine en el mismo cuadro.\n"
        "CUADROS_POR_CELDA = %d\n"
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
        "; La capa del héroe, para ordenarlo contra los NPCs.\n"
        "HERO_LAYER  = %d\n"
        "; Su prioridad de objeto. $10 —debajo de la capa de encima— en\n"
        "; toda ROM que no sea la de `snes-encima`, que la sube a $20\n"
        "; para ejercitar la prioridad 2. Ningún evento del juego llega\n"
        "; a ejercitarla: ver 'Cómo se verifica' en rom/LEEME.md.\n"
        "HERO_PRIORITY = $%02X\n"
        "; La ventana de mensaje: sus tiles viven en la segunda mitad del\n"
        "; banco de BG2, o sea a partir del índice 256, y sus celdas ya\n"
        "; vienen armadas con ese corrimiento y con la prioridad de la capa\n"
        "; de encima. VENTANA_TILES en 0 quiere decir que esta ROM no lleva\n"
        "; ventana y que el banco no existe.\n"
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
        "FUENTE_SOMBRA  = %d\n\n"
        % (", ".join("%d %s" % (m["id"], m["nombre"]) for m in mapas),
           len(mapas), MAPA_STRIDE, inicial,
           VRAM_MAP, VRAM_ABOVE_MAP, MAP_LAYOUT, NPC_STRIDE, NPC_MAX,
           EV_STRIDE, EV_MAX, RUTA_EV_MAX,
           PUERTA_BYTES, PAGINA_BYTES,
           eventos.OP_FIN, eventos.OP_SWITCH, eventos.OP_TELEPORT,
           eventos.OP_ESPERAR, eventos.OP_TINTE, eventos.OP_GRUPO,
           eventos.OP_RUTA, eventos.OP_MENSAJE, eventos.OP_RUTAS,
           eventos.OP_FLASH, eventos.OP_TIMER, eventos.OP_BGM,
           eventos.TIMER_PONER, eventos.TIMER_ARRANCAR,
           TIMER_X, TIMER_Y, TIMER_GLIFO_W, TIMER_GLIFOS - 1,
           eventos.CUADROS_POR_SEGUNDO, eventos.TIMER_CUADROS_DE_MAS,
           FLASH_MAX,
           eventos.TRIGGER_AUTOMATICO, eventos.TRIGGER_ACCION,
           eventos.TRIGGER_TOCA_HEROE,
           eventos.CUADROS_POR_CELDA, eventos.CUADROS_DE_ESPERA_DE_RUTA,
           eventos.SALTO_PASO, eventos.SALTO_VELOCIDAD,
           eventos.TINTE_NEUTRO,
           eventos.LUZ_R, eventos.LUZ_G, eventos.LUZ_B, SWITCH_BYTES,
           eventos.GRUPO_MAX, len(grupo_inicial), ACTOR_BYTES,
           rm2k.LAYER_SAME,
           OBJ_PRIORITY_ABOVE if heroe_encima else OBJ_PRIORITY,
           paleta_de_la_ventana(m["above"][3] for m in mapas)
           * COLORS_PER_PALETTE,
           0 if ventana is None else len(ventana["tiles"]) // 32,
           VENTANA_FILAS_INC, VENTANA_COLS_INC,
           0 if ventana is None else ventana["base"],
           VENTANA_TEXTO_FILA, VENTANA_TEXTO_FILAS,
           VENTANA_TEXTO_COL, VENTANA_TEXTO_COLS, _columnas(),
           FUENTE_ALTO, FUENTE_ANCHO,
           0 if ventana is None else ventana["sombra"]))

    with open(path, "w") as handle:
        handle.write(cabecera)
        handle.write(desplazamientos())
        handle.write("\n\n")
        # Los datos van en RODATA, que el enlazador reparte por los bancos de
        # arriba. La tabla va en TABLAS, o sea el banco 0, porque la ROM la
        # recorre con `lda mapa_tabla + campo, x` y ese modo direcciona el banco
        # de datos. Los datos ya no pueden estar ahí: no entran.
        handle.write('.segment "RODATA"\n')
        for numero, mapa in enumerate(mapas):
            handle.write("; --- %d: mapa %d %r ---\n"
                         % (numero, mapa["id"], mapa["nombre"]))
            handle.write(datos_del_mapa(mapa, numero))
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
            # ventana se lleva la que queda justo debajo de la capa de encima
            # más baja de la ROM, y tiene que ser la misma para todos los
            # mapas: las celdas se emiten una sola vez. Que el fondo de cada
            # mapa quede debajo lo garantiza main(), que los reconvierte; acá
            # se controla, porque si un fondo la pisara la ventana saldría
            # con los colores del mapa y ninguna comparación de un solo mapa
            # lo vería.
            paleta = paleta_de_la_ventana(m["above"][3] for m in mapas)
            for m in mapas:
                if con_ventana and len(m["cram_words"]) > \
                        paleta * COLORS_PER_PALETTE:
                    raise SystemExit(
                        "el fondo del mapa %d usa %d entradas de CGRAM y pisa "
                        "la paleta %d de la ventana: falta reconvertirlo"
                        % (m["id"], len(m["cram_words"]), paleta))
            handle.write("\n; --- la ventana de mensaje ---\n")
            handle.write(bloque("ventana_tiles", ventana["tiles"]) + "\n")
            handle.write(bloque("ventana_cgram",
                                b"".join(w.to_bytes(2, "little")
                                         for w in ventana["cram"])) + "\n")
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
        handle.write('\n.segment "TABLAS"\n')
        # `fuente_color` va en el banco 0 y no con el resto de la ventana: la
        # ROM la lee con `lda fuente_color, y`, y ese modo direcciona el banco
        # de datos. Con ella en RODATA leía basura, y el texto salía en negro.
        handle.write(bloque("fuente_color", bytes(ventana["color"])) + "\n")
        handle.write("grupo_inicial:\n    .byte %s\n\n"
                     % ",".join("%d" % a for a in grupo_inicial) or "0")
        handle.write(tabla_de_mapas(mapas))
        handle.write("\n")


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
# Cuántos eventos guarda la RAM. El mapa más poblado de este juego tiene 114;
# el conversor corta si alguno se pasa, así que el número no puede quedar corto
# en silencio.
EV_MAX = 128
# Cuántas rutas forzadas pueden estar corriendo a la vez sobre eventos. La
# página que más manda a caminar de este juego mueve cuatro eventos distintos, y
# una ruta sobrevive al final de su página, así que puede haber otra corriendo
# encima. Ocho da margen y cuesta 88 bytes de RAM.
RUTA_EV_MAX = 8
# Cuántos destellos pueden estar corriendo a la vez. Las páginas de este juego
# los encadenan de a uno —casi todos esperan a que termine— así que cuatro sobra;
# el conversor no lo puede comprobar porque depende de qué corra cuándo, y una
# ranura que falte hace que el destello no se vea.
FLASH_MAX = 4
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
NPC_STRIDE = 12
NPC_QUIETO = 0xFF        # en +8 y +9: este NPC no camina

# La tabla de NPCs del mapa que está cargado se copia a RAM, porque build_oam la
# recorre con un índice y eso direcciona el banco de datos. El tope no es una
# elección: en OAM entran 128 objetos y uno es el héroe, así que ningún mapa
# puede mostrar más. El que más tiene en todo el juego son 89.
NPC_MAX = 127


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


def actor_bytes(actores):
    """Los candidatos a líder: id, paleta, y el tile de cada una de sus poses.

    Veintiséis bytes por actor. La ROM recorre la tabla buscando el id del
    primero del grupo; son dos o tres entradas, así que buscar linealmente sale
    más barato que indexar por id, que pediría 256 huecos.
    """
    out = bytearray()
    for actor, paleta, tiles in actores:
        out.append(actor & 0xFF)
        out.append(paleta & 0x07)
        for tile in tiles:
            out += (tile & 0xFFFF).to_bytes(2, "little")
    return bytes(out)


# Cuánto ocupa cada opcode, para recorrer el bytecode sin ejecutarlo. Los que
# llevan largo variable van con None y se miden aparte.
LARGO_DE_OPCODE = {
    eventos.OP_FIN: 1, eventos.OP_SWITCH: 4, eventos.OP_TELEPORT: 6,
    eventos.OP_ESPERAR: 3, eventos.OP_TINTE: 5, eventos.OP_GRUPO: 3,
    eventos.OP_MENSAJE: 3, eventos.OP_RUTAS: 1, eventos.OP_FLASH: 7,
    eventos.OP_TIMER: 5, eventos.OP_BGM: 2, eventos.OP_RUTA: None,
}


def recorrer_codigo(codigo):
    """(desplazamiento, código) de cada opcode de una página ya compilada."""
    i = 0
    while i < len(codigo):
        yield i, codigo
        op = codigo[i]
        if op == eventos.OP_RUTA:
            i += 3 + codigo[i + 2]
        else:
            largo = LARGO_DE_OPCODE.get(op)
            if largo is None:
                raise SystemExit("opcode %d que no sé medir" % op)
            i += largo


def orden_de_mapas(args):
    """Los mapas de la ROM, en el orden de la tabla y sin repetidos.

    Está en una función y no escrito tres veces porque **el orden es el
    contrato**: un teletransporte compilado guarda el índice en esta tabla, no
    el id de RM2k. Dos listas que se armen distinto llevarían el mismo bytecode
    a mapas distintos.
    """
    return [args.map_id] + [m for m in (args.mapas or []) if m != args.map_id]


def eventos_movibles(game_map, indice_de_mapa):
    """Los eventos con gráfico a los que alguna página compilable manda a
    caminar, por índice de la tabla de eventos.

    Hace falta antes de armar el banco de sprites: a los que se mueven hay que
    darles **las doce poses** del ciclo de caminata, y a los demás la única que
    declaran. Dárselas a cualquiera que aparezca en un MoveEvent sería más
    simple y no entra: hay mapas con siete, y son 1232 tiles de sprite.

    Se compilan las páginas para saberlo y se tira lo compilado. Es trabajo
    repetido —main() las vuelve a compilar con el bloque de textos de verdad—
    pero no es una **regla** repetida: la decisión de qué compila la toma la
    misma función las dos veces.
    """
    paginas = eventos.paginas_del_mapa(game_map, indice_de_mapa,
                                       eventos.Mensajes())
    visibles = {npc["evento"] for npc in rm2k.collect_npcs(game_map)}
    return eventos.blancos_de_ruta(paginas) & visibles


def ruta_de_evento(argumento):
    """(blanco, órdenes) desde el flag, o () si no se pidió ninguna."""
    if not argumento or len(argumento) < 2:
        return ()
    return argumento[0], list(argumento[1:])


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
    movibles = [n for n in table if n["poses"] is not None]
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
        out.append(NPC_QUIETO if npc["poses"] is None
                   else movibles.index(npc))
        # Hacia dónde mira su página. Una ruta forzada que todavía no dio
        # ninguna orden de girar lo deja mirando para acá, que es de donde sale
        # la primera pose que se dibuja.
        out.append(npc["dir"])
        out.append(0)               # relleno hasta NPC_STRIDE
    assert len(out) == NPC_STRIDE * len(table)
    return bytes(out)


def npc_poses_bytes(table):
    """Las doce poses de cada NPC que camina: el tile de cada una.

    Es la misma tabla que la de los candidatos a líder y por la misma razón: la
    ROM no calcula el tile a partir de la pose, lo busca. Van sólo los que
    caminan, que son pocos —el mapa que más tiene de este juego mueve tres—.
    """
    out = bytearray()
    for npc in table:
        if npc["poses"] is None:
            continue
        for tile in npc["poses"]:
            out += (tile & 0xFFFF).to_bytes(2, "little")
    return bytes(out)


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
    parser.add_argument("--timer-de-prueba", nargs=2, type=int, default=None,
                        metavar=("SEGUNDOS", "VISIBLE"),
                        help="arranca el cronómetro desde la página de prueba. "
                             "Existe por lo mismo que el resto de esa página: "
                             "las seis del juego que lo prenden están cortadas "
                             "por otra cosa, así que sin esto no habría con qué "
                             "comparar. Implica --con-timer")
    parser.add_argument("--con-timer", action="store_true",
                        help="la ROM lleva los dígitos del cronómetro: once "
                             "glifos de la imagen de System al final del banco "
                             "de sprites, y una paleta")
    parser.add_argument("--switch", nargs="+", type=int, default=None,
                        metavar="N",
                        help="prende estos switches desde la página de prueba, "
                             "que es la forma de poner al mundo en un estado al "
                             "que el juego llega más tarde")
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

    mapas = [convertir(renderer, map_id, args,
                       inicio=args.inicio if map_id == args.map_id else None)
             for map_id in todos]
    if args.con_ventana:
        # La paleta de la ventana es de la ROM y no de cada mapa: ver
        # `paleta_de_la_ventana`. Sólo se reconvierten los mapas que la tenían
        # más arriba, y son los de pocas paletas encima, que es lo barato: en
        # la ROM del arranque es el mapa 4 solo, una habitación de un color.
        paleta = paleta_de_la_ventana(m["above"][3] for m in mapas)
        for numero, mapa in enumerate(mapas):
            if mapa["above"][3] - 1 == paleta:
                continue
            print("  mapa %d: la ventana de mensaje va en la paleta %d de toda "
                  "la ROM y no en la %d; el fondo se aprieta debajo"
                  % (mapa["id"], paleta, mapa["above"][3] - 1))
            mapas[numero] = convertir(
                renderer, mapa["id"], args,
                inicio=args.inicio if mapa["id"] == args.map_id else None,
                ventana_paleta=paleta)
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
        paginas = eventos.paginas_del_mapa(mapa["game_map"], indices.get,
                                           mensajes, temas)
        if (args.pagina_de_prueba or args.ruta_de_prueba
                or args.ruta_de_evento or args.flash_de_prueba or args.switch
                or args.timer_de_prueba
                or args.mensaje_de_prueba is not None) \
                and mapa is mapas[args.inicial]:
            # La página inventada, sólo en el mapa donde arranca la ROM. No sale
            # de ningún dato del juego: existe porque ninguna página que compile
            # tiene una espera, así que el intérprete cuadro a cuadro no lo
            # ejercitaba nada. La referencia arma la misma con la misma función.
            espera, tinte = 0, ()
            if args.pagina_de_prueba:
                espera, *tinte = args.pagina_de_prueba
            paginas = paginas + [{
                "evento": 9999, "pagina": 0,
                "trigger": eventos.TRIGGER_AUTOMATICO,
                "switch_a": 0, "switch_b": 0, "actor": 0,
                "codigo": eventos.pagina_de_prueba(
                    espera, tinte, args.ruta_de_prueba or (), prueba,
                    ruta_de_evento(args.ruta_de_evento),
                    args.flash_de_prueba or (), args.switch or (),
                    args.timer_de_prueba or ())}]
        codigo = bytearray()
        for pagina in paginas:
            pagina["offset"] = len(codigo)
            if pagina["codigo"]:
                codigo += pagina["codigo"]
        mapa["paginas"] = paginas
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
    emit(args.output, mapas, args.inicial, args.heroe_encima, grupo,
         ventana_datos)
    print("%d mapa(s) -> %s, arranca en el %d (mapa %d)"
          % (len(mapas), args.output, args.inicial, mapas[args.inicial]["id"]))

    # La música sale de acá y no de una receta aparte. `musicdata.inc` era
    # estado global como lo fue `mapdata.inc`, con el agravante de que nadie lo
    # regeneraba: una ROM armada para los mapas 4, 7, 19 y 1 —que no tienen
    # música— sonaba con el tema del mapa 348, que era el último que alguien
    # había generado a mano. Emitirlos juntos es lo único que garantiza que los
    # dos describan la misma ROM.
    #
    # Suena el tema del mapa donde la ROM arranca. Que la música siga al mapa
    # cuando uno se teletransporta pide varios bancos de muestras en el
    # cartucho, y no está: ver 'Lo que falta' en rom/LEEME.md.
    musica = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                          "musicdata.inc")
    elegido, indice, al_arrancar = tema_de_la_rom(
        mapas[args.inicial]["id"], temas, args.game_dir)
    nombre, driver, muestras, stream, segundos, _resumen = \
        snes_music.build_nombre(elegido, args.game_dir)
    snes_music.emit(musica, nombre, driver, muestras, stream,
                    indice if nombre else 0xFF, al_arrancar)
    print("música -> %s: %s" % (musica, nombre or "ninguna, sale muda"))
    if nombre:
        print("  %.0f s, %d B de muestras y %d B de stream, %s"
              % (segundos, len(muestras), len(stream),
                 "suena desde el arranque" if al_arrancar
                 else "lo prende un PlayBGM (índice %d)" % indice))
    if len(temas.nombres) > 1:
        print("  los otros %d que piden los PlayBGM quedan mudos: %s"
              % (len(temas.nombres) - 1,
                 ", ".join(n for n in temas.nombres if n != elegido)))

    if args.reference:
        mapas[args.inicial]["base"].save(args.reference)
        print("referencia -> %s" % args.reference)


def tema_de_la_rom(map_id, temas, game_dir):
    """Cuál de los temas se lleva el cartucho, con qué índice, y si suena desde
    el arranque.

    Entra uno solo, y no por espacio de cartucho sino de ARAM: el banco de
    muestras vive en los 64 KB del SPC700 y se sube una sola vez, con el
    protocolo del IPL, que después de saltar al driver ya no está. Llevar dos
    pide o que entren los dos bancos juntos —el de `escape_newyork` son 32 KB—
    o un driver que sepa recibir datos, y ninguna de las dos cosas está.

    Gana el tema del mapa donde la ROM arranca, porque es el que suena sin que
    pase nada. Si ese mapa no tiene, gana el primero que pida un `PlayBGM` de
    los que se compilaron, y entonces no suena hasta que el evento lo prenda.
    """
    propio = snes_music.tema_del_mapa(map_id, game_dir)
    if propio:
        return propio, (temas.indice(propio) if propio in temas.nombres
                        else 0xFF), True
    if temas.nombres:
        return temas.nombres[0], 0, False
    return "", 0xFF, True


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
        path = find_resource([REPO, args.game_dir, RTP_DIR], "CharSet", charset)
        if not path:
            sys.exit("no encuentro el CharSet %r" % charset)
        _charsets[charset] = load_image(path)
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
    """
    estado = eventos.Estado(grupo)
    actores = list(grupo[:1])
    indices = {m: i for i, m in enumerate(map_ids)}
    for map_id in map_ids:
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


def convertir(renderer, map_id, args, inicio=None, ventana_paleta=None):
    """Un mapa entero: tiles, colores, sprites, colisión y bloques."""
    game_map = lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    name = renderer.tree.map_names.get(map_id, "?")

    base, _above = renderer.render_layers(game_map)

    if base is None:
        sys.exit("no encuentro el chipset del mapa %d" % map_id)

    (tile_data, cram, tilemap, summary), above_data = convert_layers(
        base, _above, con_ventana=args.con_ventana,
        ventana_paleta=ventana_paleta)

    # Los personajes: el héroe con sus 12 poses porque camina, y cada NPC con la
    # que declara su página. Si un NPC usa el mismo personaje que el héroe,
    # comparten paleta y tiles sin que haya que hacer nada.
    npcs = collect_npcs(game_map)
    # Quiénes van a caminar. A ésos les hacen falta las doce poses del ciclo, y
    # el resto se queda con la única que declara su página.
    orden = orden_de_mapas(args)
    movibles = eventos_movibles(game_map,
                                {m: i for i, m in enumerate(orden)}.get)
    # La ruta inventada de `--ruta-de-evento` también manda a caminar a alguien,
    # y su página no sale de `paginas_del_mapa`: hay que sumarla a mano o el NPC
    # caminaría con una sola pose. Va sólo en el mapa donde arranca la ROM, que
    # es donde el conversor mete esa página.
    prueba_ev = ruta_de_evento(args.ruta_de_evento)
    if prueba_ev and map_id == orden[args.inicial]:
        movibles = movibles | {prueba_ev[0] - 1}
    poses = collections.defaultdict(set)
    # Cada candidato a líder con sus doce poses, porque cualquiera puede
    # terminar caminando. El primero de la lista va primero en el banco, que es
    # el orden que espera el resto: `sorted` de más abajo lo respeta.
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        if not sprite_colors(images_de(renderer, args, a.charset),
                             a.charset_index):
            continue            # no tiene un solo pixel opaco: no se dibuja
        poses[(a.charset, a.charset_index)] |= set(range(SPRITE_POSES))
    for npc in npcs:
        if npc["evento"] in movibles:
            poses[(npc["charset"], npc["index"])] |= set(range(SPRITE_POSES))
        else:
            poses[(npc["charset"], npc["index"])].add(npc["pose"])

    images, characters = {}, []
    primero = renderer.database.lider(args.lideres)
    for charset, index in sorted(poses, key=lambda k: k != primero):
        if charset not in images:
            path = find_resource([REPO, args.game_dir, RTP_DIR],
                                 "CharSet", charset)
            if not path:
                sys.exit("no encuentro el CharSet %r" % charset)
            images[charset] = load_image(path)
        characters.append((charset, index, sorted(poses[(charset, index)])))

    # Los dígitos del cronómetro se llevan una de las ocho paletas de sprite,
    # así que el techo baja a siete. Se cuenta acá y no después de armarlas
    # porque el mensaje tiene que nombrar al culpable, que es el mapa.
    tope_de_personajes = 7 if args.con_timer else 8
    if len(characters) > tope_de_personajes:
        sys.exit("el mapa usa %d personajes y hay %d paletas de sprite%s"
                 % (len(characters), tope_de_personajes,
                    " con el cronómetro puesto" if args.con_timer else ""))

    tiles, palettes, where = build_characters(images, characters)
    # El cronómetro, si esta ROM lo lleva: sus glifos van al final del banco y
    # se llevan una paleta de sprite propia.
    timer_base, timer_pal = 0, None
    if args.con_timer:
        import ventana as ventana_mod
        sys_img = ventana_mod.skin(args.game_dir, renderer.database.system_name)
        tiles, timer_base, colores = digitos_del_timer(sys_img, tiles, palettes)
        timer_pal = len(palettes)
        palettes.append(colores)
    table = npc_table(npcs, where, movibles)
    # Por cada candidato a líder, dónde caen sus doce poses y con qué paleta. La
    # ROM no calcula el tile a partir de la pose —eso valía cuando el héroe era
    # siempre el personaje 0 del banco—: lo busca acá.
    actores = []
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        if (a.charset, a.charset_index, 0) not in where:
            # Un actor con el gráfico vacío. `DummyHero`, el 10, es así: sus
            # ocho poses no tienen un pixel opaco, y RM2k no dibuja nada. Va con
            # el tile centinela y la ROM se saltea el objeto, que además evita
            # gastarle doce bloques del banco a algo invisible.
            actores.append((actor, 0, [ACTOR_INVISIBLE] * SPRITE_POSES))
            continue
        bloques = [where[(a.charset, a.charset_index, pose)]
                   for pose in range(SPRITE_POSES)]
        actores.append((actor, bloques[0][1],
                        [block_tile(b) for b, _slot in bloques]))
    sprite = (tiles, palettes, where, table, actores, timer_base, timer_pal)

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
    ocupadas = {(n["x"], n["y"]) for n in npcs}
    start_x, start_y = inicio or inicio_del_mapa(
        renderer, map_id, passable, game_map.width, game_map.height, ocupadas)
    collision = (passable, start_x, start_y, game_map.width, game_map.height)

    if len(table) > NPC_MAX:
        sys.exit("el mapa %d tiene %d NPCs y en OAM entran %d"
                 % (map_id, len(table), NPC_MAX))

    print("Mapa %d %r: %dx%d celdas de %dx%d px"
          % (map_id, name, len(tilemap[0]), len(tilemap),
             CELL, CELL))
    print("  %d colores distintos, %d en CGRAM de %d disponibles, %d fusionados"
          % (summary["colores"], summary["usados"], summary["presupuesto"],
             summary["fusionados"]))
    print("  %d tiles únicos de %d celdas (%.0f%% de reuso)"
          % (summary["tiles"], summary["celdas"],
             100.0 * (1 - summary["tiles"] / summary["celdas"])))

    print("  sprites: %d personajes, %d poses, %d tiles, %d paletas"
          % (len(characters), len(where), len(tiles) // 32, len(palettes)))
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
        "collision": collision, "celdas": bytes(words),
        "ev_pos": ev_pos_bytes(game_map),
        "bloques": bloques, "pass": block_pass,
        "layout": vram_layout(
            len(tile_data) // BYTES_PER_TILE,
            len(sprite[0]) // 32 if sprite else 0,
            con_ventana=args.con_ventana),
        "resumen": summary, "base": base,
        "puertas_crudas": rm2k.collect_doors(game_map),
        # Se guarda el mapa entero porque las puertas y los eventos no se
        # pueden resolver hasta que estén todos: los dos traducen ids de mapa a
        # índices de la tabla.
        "game_map": game_map,
    }


if __name__ == "__main__":
    main()
