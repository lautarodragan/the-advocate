#!/usr/bin/env python3
"""What things mean in RPG Maker 2000, with no console in between.

Where one can walk, which layer covers which, which graphic an event gets,
which of them are drawn. They are the original engine's rules, and they hold
the same for any port —and for any RM2k game—.

What these rules say is checked against liblcf and easyrpg-player; none of
these numbers was written from memory.
"""

import os

from common import perillas
from rpgmaker import lcf

CELL = 8

# --- the ChipSet's geometry --------------------------------------------------
#
# Where each thing lives in a ChipSet's image, which is 480x256. The offsets
# are those of EasyRPG Tools' lmu2png, same as those of `render/chipset.py`,
# which is what expands the ChipSet with them.

TILE = 16


def caja_de_terreno(n):
    """Where, in the ChipSet's image, the block of terrain autotile `n` lives
    —0 to 11, the one the map names with ids 4000 + n * 50—.

    It is 48x64 pixels with the pieces `ChipsetAtlas._terrain_tile`
    combines. It is here and not in whoever uses it because the offsets are
    lmu2png's and have no reason to be written twice:
    `ChipsetAtlas._terrain_tile` computes its corner with this same
    calculation.
    """
    terrain = n + 4
    sx = (terrain % 2) * 48 + (terrain // 8) * 96
    sy = ((terrain // 2) % 4) * 64
    return (sx, sy, sx + 48, sy + 64)


def caja_de_comun(i):
    """Where common tile `i` lives —0 to 287, the three pages of 96 in the
    right half—. The first 144 are the lower layer (ids 5000 + i) and the 144
    after them the upper one (ids 10000 + i - 144)."""
    x = 192 + (i % 6) * TILE + (i // 96) * 96
    y = ((i // 6) % TILE) * TILE
    return (x, y, x + TILE, y + TILE)


# --- collision ---------------------------------------------------------------
#
# Each RM2k tile has four bits that say from which sides it can be crossed.
# Moving from a tile to the next one asks both for permission: the origin has
# to let you out on that side and the destination let you in on the opposite
# one.
#
# The upper layer overrides the lower one, unless it has the "Above" bit
# —which means "drawn above the hero", that is, decoration— in which case the
# lower one decides. Port of EasyRPG's Game_Map::IsPassableTile.

PASS_DOWN = 0x01
PASS_LEFT = 0x02
PASS_RIGHT = 0x04
PASS_UP = 0x08
PASS_ABOVE = 0x10
PASS_WALL = 0x20
PASS_ALL = PASS_DOWN | PASS_LEFT | PASS_RIGHT | PASS_UP

# The combinations of a terrain autotile that are the face of a wall. With
# the Wall bit set, those can always be crossed.
WALL_FACES = frozenset(list(range(20, 24)) + list(range(33, 38))
                       + [42, 43, 45, 46])


def lower_passable(flags, raw, bit):
    if 4000 <= raw < 5000 and (flags[raw] & PASS_WALL):
        if (raw - 4000) % 50 in WALL_FACES:
            return True
    return bool(flags[raw] & bit)


def pasa_de_celda(flags, lower, upper):
    """A cell's four direction bits, given its two tiles."""
    byte = 0
    for bit in (PASS_DOWN, PASS_LEFT, PASS_RIGHT, PASS_UP):
        if not (flags[upper] & bit):
            continue                       # the upper layer blocks
        if not (flags[upper] & PASS_ABOVE):
            byte |= bit                    # the upper layer decides, and allows
        elif lower_passable(flags, lower, bit):
            byte |= bit                    # it is decoration: the lower decides
    return byte


def passability_map(game_map, flags):
    """One byte per map tile with the four direction bits already resolved.

    All of RM2k's logic is resolved here; the ROM only looks at the table.
    """
    result = bytearray(game_map.width * game_map.height)
    for i in range(len(result)):
        result[i] = pasa_de_celda(flags, game_map.lower_layer[i],
                                  game_map.upper_layer[i])
    return bytes(result)


def hero_start(passable, width, height, blocked=()):
    """The tile open on all four sides closest to the center of the map."""
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
        # `sys.exit` without `import sys`, which is what was here, turned a
        # message written on purpose into a `NameError` that says nothing.
        # And this branch is really reached: there are maps in the game —44
        # among them— where no cell is open on all four sides, and the
        # converter has to be able to say so.
        raise ValueError(
            "the map has no cell open on all four sides, so there is "
            "nowhere to put the hero")
    return best[1], best[2]


# --- the ChipSet's animation -------------------------------------------------
#
# Two animations that have nothing to do with each other and run at the same
# time, both in easyrpg's `TilemapLayer::Draw` (tilemap_layer.cpp:289):
#
#   the A/B/C water autotiles   3 drawings, one every `AGUA_CUADROS` frames
#   the "animated tiles"        4 drawings, one every `ANIMADO_CUADROS`
#
# The water does not cycle through its three drawings in a circle: the step
# goes from 0 to 3 and 3 **draws 1 again**, so the cycle is 0,1,2,1 and lasts
# four steps. That is with `animation_type` at 0, which is the default and
# what every chipset in this game has except two that none of the port's
# maps use; with the other type it is three steps in a circle.
#
# `animation_speed` picks between 24 and 12 frames per step —`Game_Map::
# GetAnimationSpeed`— and it is also at the default throughout the game.
#
# The clock is the system's frame counter, which is not reset when changing
# maps. Here that clock is the tick, which in the ROM is `vueltas` —see
# `Partida` in rom/pruebas/arnes/consola.py, which is what reads it—. The
# absolute phase against the original game means nothing, because our boot
# does not take the same time; what has to match is the cadence and that both
# sides look at the same tick.
# The two families, with how many drawings each one has. The order is that of
# the tile runs in VRAM; see `convert` in snes_convert.py.
FAMILIAS_ANIMADAS = (("agua", 3), ("animado", 4))
# The ROM's clock is `vueltas`, sixteen bits, so it wraps around every 65536
# ticks —eighteen minutes— and there the cycle skips a drawing; RM2k's is
# thirty-two bits. The reference wraps around the same way on purpose: what
# has to match is what both sides draw, and losing one water step once every
# eighteen minutes is seen by nobody. It is declared in
# workflow/divergencias/el-chipset-se-saltea-un-dibujo-cada-18-minutos.md.
TICK_MASCARA = 0xFFFF
AGUA_CUADROS_LENTO, AGUA_CUADROS_RAPIDO = 24, 12
# Three drawings walked in four steps, with the fourth repeating the second.
# It is the same shape in both places of RM2k where it shows up: the
# ChipSet's water —`animation_step_ab`— and a character's walk cycle, which
# has three columns and `Game_Character::columna` draws column 1 when the
# step is 3.
CICLO_TRES = (0, 1, 2, 1)
AGUA_CICLO = CICLO_TRES
ANIMADO_CUADROS = 6
ANIMADO_PASOS = 4


def paso_animado(tick):
    """Which of the four drawings of the animated tiles is due at that tick."""
    return ((tick & TICK_MASCARA) // ANIMADO_CUADROS) % ANIMADO_PASOS


# --- the character sprite ----------------------------------------------------
#
# An RM2k CharSet is 4 characters wide by 2 high; each one takes 72x128 and
# has 12 poses: 3 walking columns by 4 directions. Each pose is 24x32, that
# is, 3x4 cells of 8x8.

SPRITE_CELLS_W = 3
SPRITE_CELLS_H = 4
SPRITE_POSES = 12
POSE_W = SPRITE_CELLS_W * CELL
POSE_H = SPRITE_CELLS_H * CELL

SPRITE_WIDTH = 24
SPRITE_HEIGHT = 32

# The sprite is wider and taller than the 16x16 cell it stands on: it is
# centered horizontally and rests on its feet.
OFFSET_X = -(SPRITE_WIDTH - TILE) // 2
OFFSET_Y = -(SPRITE_HEIGHT - TILE)


# --- the NPCs ----------------------------------------------------------------
#
# They are the map's events that have a CharSet, on the page the engine would
# show when starting a game: the highest-numbered one without conditions.
# Their scripts are not evaluated, so each one stays still in the pose its
# page declares. Events without a CharSet —doors, chests, triggers— are left
# out for now.

# An event's three layers. RM2k's drawing order is first by layer and only
# then by Y: a "below" event stays under the hero even if it is further down
# the screen, and an "above" one always covers him. It comes from
# Game_Character::GetScreenZ, where the z is L- YY XX II with the layer in
# the highest byte.
FACE_DOWN = 2      # the CharSet row the hero starts with

LAYER_BELOW = 0
LAYER_SAME = 1     # the hero's, and the only one that collides with him
LAYER_ABOVE = 2


# An event without a CharSet is drawn with a tile from the chipset's upper
# page: that is how doors, chests and a good part of the decoration are
# made. For the rest of the program it is one more CharSet, with this made-up
# name, which carries the chipset and the tile's index;
# `render_map.Charsets` knows how to build its image.
TILE_PREFIX = "@tile:"


# A **translucent** event —the page's "Trans", `translucent`— is drawn in
# RM2k with opacity 160 out of 255. The console has real transparency —color
# math— but applies it to every sprite of palettes 4 to 7, and a map like 9,
# with eleven characters in the eight palettes, cannot leave four for the
# translucent ones alone. So it goes **dithered**: half the pixels in a
# checkerboard, which is what games of the era did and on a CRT TV looks
# like semi-transparency. For the port it is another CharSet, with this
# suffix in the name: the reader sticks it on translucent pages —see
# `decorar_translucido`, which `snes_convert` turns on— and
# `render_map.Charsets` builds the dithered image. Everything else —palettes,
# slots, poses, the reference— treats it like any other.
TRAMA_SUFIJO = "~trama"

# A CharSet with this suffix is **the same drawing, counted as another
# graphic**: the allocator gives it its own palette. It exists because of
# the hero's flash, which on the console is done on the character's palette:
# an NPC drawn with the graphic of a possible leader shared its palette and
# flashed too. See `convertir` in snes_convert.py.
COPIA_SUFIJO = "~aparte"

# Which dither. The options are in `render_map.TRAMAS`; it is chosen by
# looking at a CRT TV, which is where this shows.
TRAMA_PATRON = os.environ.get("TRAMA_PATRON", "cinco_de_ocho")


# The opacity RM2k draws a translucent page with: 160 out of 255.
OPACIDAD_TRANSLUCIDO = 160

# The other way out, and today's: **bake the blend into the graphic**. The
# game's 70 translucent events are all static —`move_type` 0 and no route of
# their own, measured over the 35 maps—, so neither the object nor the
# background moves and the 160/255 blend against the real background can be
# computed once, in the converter, and stay baked into the sprite: exact, no
# dither and no color math spent. The price is that the sprite becomes
# **opaque** —nobody shows through from behind— and that the graphic is no
# longer the same for two events standing on different backgrounds, so each
# one gets its own palette.
#
# For the rest of the program it is, again, another CharSet: the name carries
# this suffix with the map and the cell where the event stands, which is all
# that is needed to rebuild the background. The reader sticks it on —see
# `lcf.DECORAR_TRANSLUCIDO`, which the converter turns on— and
# `render_map.Charsets` builds the image.
HORNEADO_SUFIJO = "~horneado"

# Which of the two paths runs. It is switched with MODO_TRANSLUCIDO=trama to
# be able to compare both on the same tree.
MODO_TRANSLUCIDO = os.environ.get("MODO_TRANSLUCIDO", "horneado")


def nombre_horneado(nombre, map_id, x, y):
    return "%s%s:%d:%d:%d" % (nombre, HORNEADO_SUFIJO, map_id, x, y)


def parte_horneada(nombre):
    """(base name, (map, x, y)) of a baked CharSet, or (name, None).

    Everything that looks at *which* graphic it is —the tile's passability,
    which is a tile and which a real CharSet— has to ask about the base: the
    suffix carries where it stands, not what it draws.
    """
    base, marca, resto = nombre.partition(HORNEADO_SUFIJO + ":")
    if not marca:
        return nombre, None
    return base, tuple(int(n) for n in resto.split(":"))


def sin_horneado(nombre):
    return parte_horneada(nombre)[0]


def sin_trama():
    """The CharSets that are drawn **opaque even though their page says
    translucent**, lowercase: a deliberate divergence from RM2k that the game
    decides, in `[graphics] opaque` of the project file."""
    return frozenset(n.lower() for n in perillas.valor(
        "graphics", "opaque", tipo=list))


def decorar_translucido(nombre, map_id, x, y):
    """The name the graphic of a translucent page carries.

    Three ways out, and the first one wins: those in `sin_trama()` are drawn
    **opaque** even though their page says translucent —taro's decision, see
    the list—, the rest go baked against their cell's background, and
    `MODO_TRANSLUCIDO=trama` goes back to the checkerboard to be able to
    compare both on the same tree.
    """
    if nombre.lower() in sin_trama():
        return nombre
    if MODO_TRANSLUCIDO == "trama":
        return nombre + TRAMA_SUFIJO
    return nombre_horneado(nombre, map_id, x, y)



def nombre_de_tile(chipset, indice):
    return "%s%s:%d" % (TILE_PREFIX, chipset, indice)


# The page conditions the ROM knows how to check. An event with a page that
# asks for something else is left out entirely: without its pages in the
# table, the ROM cannot know which one is active, so it neither changes
# graphic nor blocks. "variable" since the night of 2026-09-10: the page
# carries the slot, the comparison and the value, and the ROM checks them in
# `condiciones_ok`. The timer is missing, which only one page of the game
# asks for, page 81 of map 312.
CONDICIONES_SOPORTADAS = ("switch_a", "switch_b", "actor", "variable", "item")
# And the ones the port **can never meet**. The item one was for a day:
# without an inventory, `ChangeItems` was accepted doing nothing and the
# party never had any item, so the page was emitted as one that is never
# active —see `SWITCH_IMPOSIBLE` in eventos.py— and the event's other pages
# ran as they should. Since the night of 2026-09-10 there is an inventory and
# the item condition is evaluated; the machinery stays in case another
# condition like that shows up.
CONDICIONES_IMPOSIBLES = ()


def pagina_imposible(page):
    """Whether the page asks for something this port never meets."""
    return any(c in CONDICIONES_IMPOSIBLES for c in page.condition.active)


def condiciones_soportadas(event):
    return not any(c not in CONDICIONES_SOPORTADAS
                   and c not in CONDICIONES_IMPOSIBLES
                   for page in event.pages for c in page.condition.active)


def grafico_de_pagina(page, chipset):
    """(CharSet, index, pose) of what the page draws, or None if nothing.

    Those drawn with a chipset tile go with a made-up CharSet —see
    `nombre_de_tile`—, as long as whoever loaded the map set
    `chipset_nombre` on it; tile 0 is "no graphic".
    """
    if not page.character_name and (page.character_index == 0
                                    or chipset is None):
        return None
    # The walk is four phases over three columns: the middle one goes twice,
    # so the fourth draws the same as the second.
    column = 1 if page.character_pattern == 3 else page.character_pattern
    return (page.character_name or nombre_de_tile(chipset, page.character_index),
            page.character_index if page.character_name else 0,
            page.character_direction * 3 + column)


def pasabilidad_del_tile(game_map, charset, layer):
    """The four passage bits an event drawn with `charset` on layer `layer`
    imposes on its cell, or None if it imposes nothing.

    It is `Game_Map::IsPassableTile`'s rule: an event on the lower layer with
    a tile graphic replaces the terrain's passability with its tile's, unless
    the tile is one of those that go above. That is how a door "opens" in
    this game: the cell is wall, and with the switch on the page shows the
    rubble tile, which can be stepped on. The bits come from the same table
    as the map's upper layer, which whoever loaded the map leaves in
    `pasabilidad_tiles`.
    """
    flags = getattr(game_map, "pasabilidad_tiles", None)
    base = sin_horneado(charset)
    if flags is None or layer != LAYER_BELOW \
            or not base.startswith(TILE_PREFIX):
        return None
    valor = flags[UPPER_BASE + int(base.rsplit(":", 1)[1])]
    if valor & PASS_ABOVE:
        return None
    return valor & PASS_ALL


UPPER_BASE = 10000      # the first tile of the upper layer, in the map and in the table
# And the first of the loose tiles of the lower layer: the format's "block
# E", the 144 the editor's palette shows below the autotiles. They are the two
# ranges `TileSubstitution` speaks in, numbering from the first of each. The
# autotiles are left out: not even RM2k substitutes them.
LOWER_BASE = 5000
TILES_POR_CAPA = 144

# The format's six tile id blocks, as in easyrpg's `map_data.h`: (first id,
# how many, how much each one takes, first index). The **index** is what the
# ChipSet's terrain table and passability table are read with, and it is not
# the id: autotiles take 50 or 1000 ids each —the edge combinations— and a
# single index.
BLOQUES_DE_CHIP = ((0, 2, 1000, 0), (2000, 1, 1000, 2), (3000, 3, 50, 3),
                   (4000, 12, 50, 6), (LOWER_BASE, 144, 1, 18),
                   (UPPER_BASE, 144, 1, 162))
# How many entries the terrain table has: those of the lower layer.
TERRENOS_POR_CHIPSET = 162


def indice_de_chip(chip_id):
    """`ChipIdToIndex`: from a map tile id to its ChipSet entry."""
    for base, cuantos, paso, indice in BLOQUES_DE_CHIP:
        if base <= chip_id < base + cuantos * paso:
            return indice + (chip_id - base) // paso
    return 0


def terreno_de(chipset, chip_id):
    """The terrain of a lower-layer tile, as `GetTerrainTag`.

    A ChipSet whose terrain is all 1 **does not store the table**: it is an
    RPG_RT optimization the format lets show, and the answer then is 1. Every
    ChipSet in this game is like that.
    """
    if not chipset.terrain:
        return 1
    return chipset.terrain[indice_de_chip(chip_id)]

# The `animation_type` values that ask for continuous animation:
# "Continuous" and "Fixed Dir/Continuous". Lashe City's save point is of the
# second type.
ANIMA_CONTINUO = (1, 3)


def collect_npcs(game_map):
    """The events that are drawn, with their pose and whether they block the
    way.

    Every event with a graphic on **some** page gets in, even if the one
    active at load has none: this game's doors are exactly that, a page
    without a graphic and another with the rubble tile. `visible` says
    whether it is seen at load, and `cambia` whether the graphic follows the
    active page: it is what the ROM refreshes with the switches, and it only
    applies to events whose conditions it understands. `graficos` carries
    each page's graphic, or None, and `capas` each one's layer.
    """
    npcs = []
    chipset = getattr(game_map, "chipset_nombre", None)
    for numero, event in enumerate(game_map.events):
        # An impossible page is never drawn: its graphic does not count.
        graficos = [None if pagina_imposible(p) else grafico_de_pagina(p, chipset)
                    for p in event.pages]
        if not any(graficos):
            continue
        # What this event may end up drawing over the course of the game. It
        # is not only each page's graphic: if the **first** one has a
        # condition, there may be none active, and then it draws nothing.
        # That "nothing" is one more state.
        #
        # Without counting it, an event with a single conditioned page ends
        # up with a single possible graphic, `cambia` comes out false, and
        # since it is not visible when the map loads either, it is skipped
        # entirely: there is no row to update when the switch turns on. taro
        # saw it on 2026-09-07 with map 8's `TalDoorBottom`, which can be
        # used and runs its commands but is never drawn. That is **350
        # events in 68 maps**.
        posibles = set(graficos)
        if event.pages and event.pages[0].condition.active:
            posibles.add(None)
        cambia = len(posibles) > 1 and condiciones_soportadas(event)
        page = event.active_page()
        visible = page is not None and grafico_de_pagina(page, chipset) is not None
        if not visible and not cambia:
            continue                # no graphic at load and no change: it is not there
        if not visible:
            # The row exists hidden: its fields come from the first page with
            # a graphic, which is where it will come from when it appears.
            page = next(p for p, g in zip(event.pages, graficos)
                        if g is not None)
        charset, index, pose = grafico_de_pagina(page, chipset)
        npcs.append({
            # The index in the map's event table, which is what the bytecode
            # of a forced route carries. **It is not the RM2k id**: there are
            # maps with gaps in the numbering.
            "evento": numero,
            "x": event.x, "y": event.y,
            "charset": charset, "index": index, "pose": pose,
            "layer": page.layer,
            "blocks": page.layer == LAYER_SAME,
            # Its page's speed, which is what a forced route on it carries:
            # RM2k sets it in `SetupFromPage` and `ForceMoveRoute` does not
            # touch it. By default it is 3, sixteen frames per cell.
            "velocidad": page.move_speed,
            # Whether its page asks for continuous animation. Those that also
            # walk carry it inside their route slot; this is for the still
            # ones.
            "anima": page.animation_type in ANIMA_CONTINUO,
            "visible": visible,
            "cambia": cambia,
            "graficos": graficos,
            "capas": [p.layer for p in event.pages],
            "tile_pasa": pasabilidad_del_tile(game_map, charset, page.layer)
                         if visible else None,
        })
    return npcs


# The `Teleport` command code, from liblcf. The harness's route planner uses
# it to know where an event's page leads.
TELEPORT = 10810
