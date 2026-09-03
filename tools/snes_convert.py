#!/usr/bin/env python3
"""Convierte un mapa de A Blurred Line a datos que consume el PPU de la SNES.

Es el equivalente de md_convert.py, y comparte con él todo lo que no depende del
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
    python3 tools/snes_convert.py --map-id 7 -o snes/src/mapdata.inc
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eventos
import lcf
import md_convert
from md_convert import (CELL, collect_npcs, cut_tiles, flips, hero_start,
                        passability_map, reduce_colors, tile_colors, to_indices)
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
    groups = md_convert.try_pack(sets, limite) if sets else []
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
        grid, groups, merged, _ = md_convert.reduce_colors(grid, limite)
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
        mapping, merged = md_convert.merge_least_used(counts, OBJ_COLORS)
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
            mapping, _ = md_convert.merge_least_used(counts, OBJ_COLORS)
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


def npc_table(npcs, where):
    """Los NPCs listos para la ROM, ya ordenados como los dibuja RM2k.

    El orden de dibujado es primero por capa y recién después por Y: uno "below"
    queda debajo del héroe aunque esté más adelante en pantalla. En la consola,
    el objeto con índice más bajo de OAM es el que se ve encima, así que la
    tabla va del frente hacia el fondo.
    """
    rows = []
    for npc in sorted(npcs, key=lambda n: (n["layer"], n["y"]), reverse=True):
        block, slot = where[(npc["charset"], npc["index"], npc["pose"])]
        rows.append({
            "x": npc["x"] * 16, "y": npc["y"] * 16,
            "tile": block_tile(block), "palette": slot,
            "layer": npc["layer"], "blocks": npc["blocks"],
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

    mapping, merged = md_convert.merge_least_used(counts, bg_colors)
    grid = [[tuple(tuple(mapping.get(p) for p in line) for line in tile)
             for tile in row] for row in grid]
    return sorted({c for c in mapping.values()}), grid, merged


def convert_layers(base, above_img):
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
    return convert(base, bg_budget(above[3]), grid=base_grid), above


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
VRAM_MAP = 0x7000
VRAM_ABOVE_MAP = 0x7800

# La tabla de bloques se lee con `lda tabla, x`, o sea que vive en el banco 0
# junto con el código.
MAX_BLOCKS = 1024


def vram_layout(tiles):
    """Cuál de los dos repartos de VRAM le toca a un mapa de estos tiles."""
    if tiles > LAYOUT_ANCHO["tiles"][1]:
        return LAYOUT_FONDO
    return LAYOUT_ANCHO


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
    ("MAP_TILES", "cuántos tiles de fondo, para el DMA"),
    ("MAP_CGRAM", "cuántas palabras de CGRAM"),
    ("ABOVE_TILES", ""),
    ("ABOVE_CGRAM", ""),
    ("SPRITE_TILES", ""),
    ("SPRITE_CGRAM", ""),
    ("NPC_COUNT", "cuántos NPCs con CharSet"),
    ("PUERTA_COUNT", "cuántas puertas salen de este mapa"),
    ("PAGINA_COUNT", "cuántas páginas de evento hay que resolver"),
]
MAPA_BYTES = [
    ("OBSEL_VALUE", "objetos de 8x8 y 32x32, y la página de sus tiles"),
    ("BG12NBA_VALUE", "las páginas de tiles de BG1 y BG2"),
    ("ABOVE_FIRST", "en qué entrada de CGRAM arranca la capa de encima"),
]
MAPA_PUNTEROS = ["map_tiles", "map_cgram", "above_tiles", "above_cgram",
                 "sprite_tiles", "sprite_cgram", "map_celdas", "map_bloques",
                 "bloque_pass", "npc_table", "puertas", "paginas"]
MAPA_PTR_BASE = 48                       # dónde arrancan los punteros
MAPA_PTR_PASO = 4

# Una puerta: dónde está, a qué mapa lleva y a qué celda. El paso es potencia de
# dos para que buscarla sea un corrimiento, y sobra lugar para la dirección en
# la que RM2k te deja mirando, que todavía no se usa.
PUERTA_BYTES = 16

# Una página de evento: a qué evento pertenece, qué la activa, y dónde está su
# código. Las páginas de un mismo evento van seguidas y en orden, que es lo que
# le permite a la ROM elegir la última que cumple sus condiciones en una sola
# pasada, sin llevar una tabla por evento.
PAGINA_BYTES = 16

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
        "MAP_TILES": len(mapa["tiles"]) // BYTES_PER_TILE,
        "MAP_CGRAM": len(mapa["cram"]) // 2,
        "ABOVE_TILES": len(above[0]) // 32,
        "ABOVE_CGRAM": len(above[1]) // 2,
        "SPRITE_TILES": len(sprite[0]) // 32 if sprite else 0,
        # Una más que los colores: el índice 0 del sprite es transparente y
        # también ocupa su lugar en CGRAM.
        "SPRITE_CGRAM": COLORS_PER_PALETTE * len(sprite[1]) if sprite else 0,
        "NPC_COUNT": len(sprite[3]) if sprite else 0,
        "PUERTA_COUNT": len(mapa["puertas"]) // PUERTA_BYTES,
        "PAGINA_COUNT": len(mapa["paginas"]),
        "OBSEL_VALUE": 0x20 | (layout["sprites"][0] // 0x2000),
        "BG12NBA_VALUE": ((layout["encima"][0] // 0x1000) << 4)
                         | (layout["tiles"][0] // 0x1000),
        "ABOVE_FIRST": above[3] * COLORS_PER_PALETTE,
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
        out.append("    .byte " + ",".join(["$00"] * (PAGINA_BYTES - 11)))
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
        ("puertas", mapa["puertas"]),
        ("evcodigo", mapa["evcodigo"]),
    ]
    out = [bloque("%s_%d" % (nombre, numero), datos) for nombre, datos in pares]
    # La grilla va aparte porque es la única que no se sube por DMA.
    out.append(bloque("map_celdas_%d" % numero, mapa["celdas"], alinear=2))
    out.append(tabla_de_paginas(mapa, numero))
    return "\n".join(out)


def emit(path, mapas, inicial=0, heroe_encima=False):
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
        "PUERTA_BYTES = %d\n"
        "PAGINA_BYTES = %d\n"
        "; Los opcodes del intérprete de eventos.\n"
        "OP_FIN      = $%02X\n"
        "OP_SWITCH   = $%02X\n"
        "OP_TELEPORT = $%02X\n"
        "OP_ESPERAR  = $%02X\n"
        "OP_TINTE    = $%02X\n"
        "TRIGGER_AUTOMATICO = %d\n"
        "TINTE_NEUTRO = %d\n"
        "; Un bit por switch. El más alto que el juego consulta es el 1003.\n"
        "SWITCH_BYTES = %d\n"
        "; La capa del héroe, para ordenarlo contra los NPCs.\n"
        "HERO_LAYER  = %d\n"
        "; Su prioridad de objeto. $10 —debajo de la capa de encima— en\n"
        "; toda ROM que no sea la de `snes-encima`, que la sube a $20\n"
        "; para ejercitar la prioridad 2. Ningún evento del juego llega\n"
        "; a ejercitarla: ver 'Cómo se verifica' en snes/LEEME.md.\n"
        "HERO_PRIORITY = $%02X\n\n"
        % (", ".join("%d %s" % (m["id"], m["nombre"]) for m in mapas),
           len(mapas), MAPA_STRIDE, inicial,
           VRAM_MAP, VRAM_ABOVE_MAP, MAP_LAYOUT, NPC_STRIDE, NPC_MAX,
           PUERTA_BYTES, PAGINA_BYTES,
           eventos.OP_FIN, eventos.OP_SWITCH, eventos.OP_TELEPORT,
           eventos.OP_ESPERAR, eventos.OP_TINTE,
           eventos.TRIGGER_AUTOMATICO, eventos.TINTE_NEUTRO, SWITCH_BYTES,
           md_convert.LAYER_SAME,
           OBJ_PRIORITY_ABOVE if heroe_encima else OBJ_PRIORITY))

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
        handle.write('\n.segment "TABLAS"\n')
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


NPC_STRIDE = 8

# La tabla de NPCs del mapa que está cargado se copia a RAM, porque build_oam la
# recorre con un índice y eso direcciona el banco de datos. El tope no es una
# elección: en OAM entran 128 objetos y uno es el héroe, así que ningún mapa
# puede mostrar más. El que más tiene en todo el juego son 89.
NPC_MAX = 127


def sort_key(layer, y):
    """Cómo ordena RM2k: primero la capa y recién después la Y.

    Un evento "below" queda debajo del héroe aunque esté más adelante en la
    pantalla, y uno "above" lo tapa siempre. Meter la capa en los bits altos
    hace que una sola comparación de 16 bits decida las dos cosas.
    """
    return (layer << 12) | (y & 0x0FFF)


def npc_bytes(table):
    """La tabla de NPCs: ocho bytes por cada uno.

    Posición en el mapa, la clave con la que se ordena contra el héroe, qué tile
    de sprite le toca, y el byte de atributos ya armado con su paleta. La ROM
    sólo resta la cámara y lo copia a OAM.
    """
    out = bytearray()
    for npc in table:
        out += npc["x"].to_bytes(2, "little")
        out += npc["y"].to_bytes(2, "little")
        # La clave va con la Y en pixeles, que es como la calcula la ROM a
        # partir de la posición del héroe. Con la Y en celdas, la del héroe
        # sería siempre mayor y quedaría siempre adelante de todos.
        out += sort_key(npc["layer"], npc["y"] * 16).to_bytes(2, "little")
        out.append(npc["tile"] & 0xFF)
        # vhoopppN: la prioridad son los bits 5 y 4, así que el valor va corrido
        # cuatro lugares. Los eventos marcados "above" van en prioridad 2, que
        # es lo único que queda por encima de BG2 1; el resto comparten con el
        # héroe la prioridad 1, y como esa capa los tapa, caminan por debajo.
        prioridad = (OBJ_PRIORITY_ABOVE
                     if npc["layer"] == md_convert.LAYER_ABOVE
                     else OBJ_PRIORITY)
        out.append(prioridad | ((npc["palette"] & 0x07) << 1)
                   | ((npc["tile"] >> 8) & 0x01))
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=7)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("-o", "--output",
                        default=os.path.join(REPO, "snes/src/mapdata.inc"))
    parser.add_argument("--heroe-encima", action="store_true",
                        help="el héroe en prioridad 2 de objeto, por "
                             "encima de la capa que debería taparlo. "
                             "Es la única forma de ejercitarla: el "
                             "único evento above del juego no llega a "
                             "pisar la capa de encima")
    parser.add_argument("--charset", default="Future1",
                        help="CharSet del personaje (default: el de Talan)")
    parser.add_argument("--charset-index", type=int, default=0,
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

    renderer = Renderer(args.game_dir)
    mapas = [convertir(renderer, map_id, args,
                       inicio=args.inicio if map_id == args.map_id else None)
             for map_id in ([args.map_id] + [m for m in (args.mapas or [])
                                             if m != args.map_id])]
    # Las puertas se resuelven cuando están todos los mapas: una puede llevar a
    # cualquier otro, así que el índice de destino no se sabe hasta el final.
    indices = {mapa["id"]: numero for numero, mapa in enumerate(mapas)}
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
        paginas = eventos.paginas_del_mapa(mapa["game_map"], indices.get)
        codigo = bytearray()
        for pagina in paginas:
            pagina["offset"] = len(codigo)
            if pagina["codigo"]:
                codigo += pagina["codigo"]
        mapa["paginas"] = paginas
        mapa["evcodigo"] = bytes(codigo)
        corribles = sum(1 for p in paginas if p["codigo"])
        if paginas:
            print("  mapa %d: %d página(s) de evento automático, %d ejecutable(s)"
                  % (mapa["id"], len(paginas), corribles))

    if not 0 <= args.inicial < len(mapas):
        sys.exit("--inicial %d pero hay %d mapas" % (args.inicial, len(mapas)))
    emit(args.output, mapas, args.inicial, args.heroe_encima)
    print("%d mapa(s) -> %s, arranca en el %d (mapa %d)"
          % (len(mapas), args.output, args.inicial, mapas[args.inicial]["id"]))

    if args.reference:
        mapas[args.inicial]["base"].save(args.reference)
        print("referencia -> %s" % args.reference)


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


def convertir(renderer, map_id, args, inicio=None):
    """Un mapa entero: tiles, colores, sprites, colisión y bloques."""
    game_map = lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    name = renderer.tree.map_names.get(map_id, "?")

    base, _above = renderer.render_layers(game_map)

    if base is None:
        sys.exit("no encuentro el chipset del mapa %d" % map_id)

    (tile_data, cram, tilemap, summary), above_data = convert_layers(base, _above)

    # Los personajes: el héroe con sus 12 poses porque camina, y cada NPC con la
    # que declara su página. Si un NPC usa el mismo personaje que el héroe,
    # comparten paleta y tiles sin que haya que hacer nada.
    npcs = collect_npcs(game_map)
    poses = collections.defaultdict(set)
    poses[(args.charset, args.charset_index)] = set(range(SPRITE_POSES))
    for npc in npcs:
        poses[(npc["charset"], npc["index"])].add(npc["pose"])

    images, characters = {}, []
    for charset, index in sorted(poses, key=lambda k: k != (args.charset,
                                                            args.charset_index)):
        if charset not in images:
            path = find_resource([REPO, args.game_dir, RTP_DIR],
                                 "CharSet", charset)
            if not path:
                sys.exit("no encuentro el CharSet %r" % charset)
            images[charset] = load_image(path)
        characters.append((charset, index, sorted(poses[(charset, index)])))

    if len(characters) > 8:
        sys.exit("el mapa usa %d personajes y hay 8 paletas de sprite"
                 % len(characters))

    tiles, palettes, where = build_characters(images, characters)
    table = npc_table(npcs, where)
    sprite = (tiles, palettes, where, table)

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
        "bloques": bloques, "pass": block_pass,
        "layout": vram_layout(len(tile_data) // BYTES_PER_TILE),
        "resumen": summary, "base": base,
        "puertas_crudas": md_convert.collect_doors(game_map),
        # Se guarda el mapa entero porque las puertas y los eventos no se
        # pueden resolver hasta que estén todos: los dos traducen ids de mapa a
        # índices de la tabla.
        "game_map": game_map,
    }


if __name__ == "__main__":
    main()
