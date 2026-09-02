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

import lcf
import md_convert
from md_convert import (CELL, cut_tiles, flips, reduce_colors, tile_colors,
                        to_indices)
from render_map import (GAME_DIR, REPO, RTP_DIR, Renderer, find_resource,
                        load_image)

# El PPU direcciona 1024 tiles por capa: diez bits en cada celda del tilemap.
MAX_TILES = 1024

# CGRAM tiene 256 entradas; la mitad de arriba es de los sprites. El 0 es el
# color de fondo y ningún tile lo usa, así que quedan 127 para el mapa.
BG_COLORS = 127
BYTES_PER_TILE = 64                      # 8 planos de bits, 8 filas cada uno

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


# --- conversión -------------------------------------------------------------

def build_palette(grid):
    """Los colores del mapa, en una sola tabla, fusionando sólo si sobran.

    Con 8 bits por pixel el único límite es cuántas entradas de CGRAM hay
    libres. Map0007 usa 60 de las 127, así que no se fusiona nada; el camino de
    fusión existe para mapas más cargados y es el mismo de la Mega Drive.
    """
    counts = collections.Counter(p for row in grid for tile in row
                                 for line in tile for p in line
                                 if p is not None)
    if len(counts) <= BG_COLORS:
        return sorted(counts), grid, []

    mapping, merged = md_convert.merge_least_used(counts, BG_COLORS)
    grid = [[tuple(tuple(mapping.get(p) for p in line) for line in tile)
             for tile in row] for row in grid]
    return sorted({c for c in mapping.values()}), grid, merged


def convert(image):
    """La imagen del mapa a tiles, paleta y tilemap.

    Devuelve (datos de tiles, palabras de CGRAM, tilemap, resumen).
    """
    grid = cut_tiles(quantize(image))
    before = len({p for row in grid for tile in row
                  for line in tile for p in line if p is not None})
    palette, grid, merged = build_palette(grid)

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
        "fusionados": len(merged),
        "tiles": len(pool),
        "celdas": sum(len(row) for row in tilemap),
    }
    return bytes(tile_data), cram, tilemap, summary


# El tilemap del PPU se arma con "pantallas" de 32x32 celdas encadenadas en
# VRAM: una sola, dos al lado, dos abajo, o cuatro. El valor va en los dos bits
# bajos de BG1SC.
SCREEN = 32
LAYOUTS = {(1, 1): 0, (2, 1): 1, (1, 2): 2, (2, 2): 3}


def screen_order(tilemap):
    """El tilemap acomodado como lo espera la VRAM, con su valor de BG1SC.

    Las pantallas no van una al lado de la otra en memoria: cada una ocupa sus
    1024 celdas seguidas, primero la de arriba a la izquierda, después la de su
    derecha, y recién ahí las de abajo. Acomodarlo acá le ahorra a la ROM tener
    que copiar fila por fila, y le deja un DMA único.
    """
    height, width = len(tilemap), len(tilemap[0])
    across = 1 if width <= SCREEN else 2
    down = 1 if height <= SCREEN else 2
    if width > 2 * SCREEN or height > 2 * SCREEN:
        raise SystemExit("el mapa no entra en un tilemap de 64x64 celdas; "
                         "para mapas más grandes hace falta ir redibujando")

    cells = [0] * (across * down * SCREEN * SCREEN)
    for y, row in enumerate(tilemap):
        for x, cell in enumerate(row):
            screen = (y // SCREEN) * across + (x // SCREEN)
            cells[screen * SCREEN * SCREEN
                  + (y % SCREEN) * SCREEN + (x % SCREEN)] = cell
    return cells, LAYOUTS[(across, down)]


def emit(path, name, tile_data, cram, tilemap, sprite=None):
    """El .inc que arma w65.py junto con main.s."""
    height, width = len(tilemap), len(tilemap[0])

    def block(label, data, per_line=16):
        out = ["%s:" % label]
        for i in range(0, len(data), per_line):
            out.append("    .byte " + ",".join("$%02X" % b
                                               for b in data[i:i + per_line]))
        return "\n".join(out)

    cells, layout = screen_order(tilemap)
    words = bytearray()
    for cell in cells:
        words += cell.to_bytes(2, "little")

    colors = bytearray()
    for word in cram:
        colors += word.to_bytes(2, "little")

    with open(path, "w") as handle:
        handle.write(
            "; Generado por tools/snes_convert.py. No editar.\n"
            "; Mapa: %s\n\n"
            "MAP_WIDTH   = %d\n"
            "MAP_HEIGHT  = %d\n"
            "MAP_TILES   = %d\n"
            "MAP_CGRAM   = %d\n"
            "MAP_LAYOUT  = %d\n"
            "MAP_CELLS   = %d\n"
            "; Hasta dónde puede llegar la cámara sin salirse del mapa, en\n"
            "; pixeles: el ancho del mapa menos el de la pantalla.\n"
            "CAM_MAX_X   = %d\n"
            "CAM_MAX_Y   = %d\n"
            "; El héroe se para en una celda de 16x16 y no puede salirse del\n"
            "; mapa. Arranca en el centro, alineado a esa grilla.\n"
            "HERO_MAX_X  = %d\n"
            "HERO_MAX_Y  = %d\n"
            "HERO_START_X = %d\n"
            "HERO_START_Y = %d\n"
            "SPRITE_TILES = %d\n"
            "SPRITE_CGRAM = %d\n\n"
            '.segment "RODATA"\n%s\n%s\n%s\n%s\n%s\n'
            % (name, width, height, len(tile_data) // BYTES_PER_TILE, len(cram),
               layout, len(cells),
               max(0, width * CELL - 256), max(0, height * CELL - 224),
               width * CELL - 16, height * CELL - 16,
               (width * CELL // 2) & ~15, (height * CELL // 2) & ~15,
               len(sprite[0]) // 32 if sprite else 0,
               len(sprite[1]) if sprite else 0,
               block("map_tiles", tile_data),
               block("map_cgram", colors),
               block("map_tilemap", words),
               block("sprite_tiles", sprite[0] if sprite else b""),
               block("sprite_cgram", sprite_colors_bytes(sprite))))


def sprite_colors_bytes(sprite):
    """La paleta del sprite como bytes de CGRAM, con el 0 transparente."""
    if not sprite:
        return b""
    out = bytearray(cgram_word(BACKDROP).to_bytes(2, "little"))
    for color in sprite[1]:
        out += cgram_word(color).to_bytes(2, "little")
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=7)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("-o", "--output",
                        default=os.path.join(REPO, "snes/src/mapdata.inc"))
    parser.add_argument("--charset", default="Future1",
                        help="CharSet del personaje (default: el de Talan)")
    parser.add_argument("--charset-index", type=int, default=0,
                        help="cuál de los 8 personajes del CharSet")
    parser.add_argument("--reference", help="PNG del render de Python, para comparar")
    args = parser.parse_args()

    renderer = Renderer(args.game_dir)
    game_map = lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % args.map_id))
    name = renderer.tree.map_names.get(args.map_id, "?")

    base, _above = renderer.render_layers(game_map)
    if base is None:
        sys.exit("no encuentro el chipset del mapa %d" % args.map_id)

    tile_data, cram, tilemap, summary = convert(base)

    charset_path = find_resource([REPO, args.game_dir, RTP_DIR], "CharSet",
                                 args.charset)
    if not charset_path:
        sys.exit("no encuentro el CharSet %r" % args.charset)
    sprite = build_sprite(load_image(charset_path), args.charset_index)

    print("Mapa %d %r: %dx%d celdas de %dx%d px"
          % (args.map_id, name, len(tilemap[0]), len(tilemap),
             CELL, CELL))
    print("  %d colores distintos, %d en CGRAM, %d fusionados"
          % (summary["colores"], summary["usados"], summary["fusionados"]))
    print("  %d tiles únicos de %d celdas (%.0f%% de reuso)"
          % (summary["tiles"], summary["celdas"],
             100.0 * (1 - summary["tiles"] / summary["celdas"])))

    print("  sprite %s: %d tiles, paleta de %d, %d colores fusionados"
          % (args.charset, len(sprite[0]) // 32, len(sprite[1]), sprite[2]))

    emit(args.output, name, tile_data, cram, tilemap, sprite)
    print("  tiles %d B, cgram %d B, tilemap %d B -> %s"
          % (len(tile_data), 2 * len(cram),
             2 * summary["celdas"], args.output))

    if args.reference:
        base.save(args.reference)
        print("  referencia -> %s" % args.reference)


if __name__ == "__main__":
    main()
