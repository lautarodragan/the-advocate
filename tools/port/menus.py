"""The menus: the save slots, the pause menu, the item screen and the
choose-whom screen, with the font and the frames they share.
"""

import collections

import numpy

from port import allocator
from port import experience
from port import font
from port.constants import HEIGHT, WIDTH, CELL, COLS, ROWS, MENU_CGRAM
from port.palette import BLACK
from port.rules import level_of, param_of


# --- the slot screen ---------------------------------------------------------
#
# Both ends use it: "Resume the Story" on the title, and the Lashe City save
# point. It is a screen of its own and not a layer over the title, so it has
# VRAM all to itself and everything can go at 4bpp.
#
# **The text that does not depend on the save is pre-rendered**, including
# the two variants of each slot —empty and taken— and the level term. What
# does depend on it —the leader's name and level— is composed one letter per
# cell with loose glyphs, like the timer digits; see "what depends on the
# actor" below. Until 2026-09-20 it was baked too, with one block per actor,
# and that made the bank grow with every actor that could be in the party.
#
# What the ROM does do on the fly is **choose which block of cells it writes
# on each row**: per slot there are four —empty or full, with cursor or
# without— and moving the cursor is rewriting two rows of 96 cells. There is
# no full tilemap per combination because there would be 64.
# The row is **48 pixels, six cells**, which is the size of a FaceSet face:
# `Window_SaveFile::Refresh` in easyrpg draws, per file, the file name, the
# leader's, the level and the hit points, and the faces of up to four of the
# party at 48x48. Here there are three lines of text on the left and up to
# three faces on the right: the fourth does not fit in 256 pixels without
# eating the border, which is not visible on a CRT. Four rows of 48 plus the
# header end at line 216 of the 224.
RANURA_Y = 24                   # where the first row starts, in pixels
# And how far apart the next one is. **A multiple of 8 on purpose**: each row
# is uploaded to the tilemap as a block of whole cells, so if the step did not
# land on a cell the text of one row would be written into the next row's
# block and get cut.
RANURA_SALTO = 48
RANURA_FILAS = 6                # 8 px tall cells each one takes
RANURA_X = 56                   # where the text starts
LINEA = 16                      # how far apart the text lines in the row are
CABECERA_Y = 4
CABECERA_FILAS = 2
# What a slot without a save says. RM2k has no term for this —its menu shows
# the empty gap— so the text is ours, and that is why it is written here and
# not taken from the LDB, so it shows that we made it up.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
VACIA = "- Empty -"
# The faces: where the first one goes, in cells from the left edge, and how
# far apart the next one is. Six wide by six tall, touching.
CARA = 48
CARA_CELDAS = CARA // CELL      # 6
CARA_COL = 14                   # that is x = 112
CARA_PASO = CARA_CELDAS         # touching: 112, 160, 208
CARAS_MAX = 3
# The leader's name, on the second line: seven cells wide, from the edge of
# the text to where the first face starts.
NOMBRE_COL = RANURA_X // CELL   # 7
NOMBRE_COLS = CARA_COL - NOMBRE_COL     # 7
NOMBRE_FILA = LINEA // CELL     # 2: the second line starts at y+16
# And the third line, the level: the two digits after the term "L ", which
# is baked because it is the same for everyone.
NIVEL_FILA = 2 * LINEA // CELL  # 4
NIVEL_CIFRAS = 2                # "%2d", which is what RM2k shows
# Which cell the number starts at: the one after the term, which is two font
# characters wide. It is not `RANURA_X + 12` rounded by hand because the term
# comes from the LDB and its width is the font's.
NIVEL_COL = (RANURA_X + 2 * font.WIDTH) // CELL       # 8
# And which palette the faces use: 0 is the text's, and each face carries its
# own from 1. They are the palettes of BG2 at 4bpp, which are eight on the
# console.
CARAS_PALETAS_MAX = 7
# How many tiles fit in the screen's bank: the converter checks it against
# the VRAM layout, see RANURA_MAP there.
RANURA_TILES_MAX = 448

# --- what depends on the actor, composed with glyphs ---------------------------
#
# The name, the level and the max HP **are composed one letter per cell** and
# not baked into one block per actor. The reason is that the bank is a single
# one and deduplicated: baked, each actor's text added some seven tiles it
# shares with nobody, so the bank grew with every actor that could be in the
# party and the whole game did not fit. With glyphs the text costs once —the
# letters the names use— and the only thing that keeps growing per actor is
# the faces.
#
# It is the same the gold digits, the current HP and the item screen already
# do. The price is the same they pay and it is declared: the letters go at an
# 8-pixel pitch and not at the font's 6, so the text that depends on the
# actor comes out a bit wider than before. What does not depend on it —"File
# 1", "- Empty -", the level term, "Normal", "HP"— is still baked with the
# font, so it comes out the same as always.
#
# The glyphs are drawn **in the same cell and with the same offset as the
# gold digits** —one in x, two in y—, so the ten digits come from here and the
# screen does not carry two sets of digits.
GLIFO_COL = 3                   # the column where the loose glyph is drawn
GLIFO_FILA = 25                 # and its row; both are arbitrary
GLIFO_DX = 1                    # centered in the cell: 6 px of font in 8
GLIFO_DY = 2


def _bloque_de_celdas(capa, fila0, filas, tiles, donde, indice, col0=0,
                      cols=COLS, paleta=0):
    """The cells of a rectangle of `capa`, adding new tiles.

    Returns the list of tilemap words, `cols` per row: the tile index with
    the three bits of `paleta` on top. The tiles are shared with everything
    else on the screen: there is a single bank and the blocks index it, so
    deduplicating separately would give indices that do not match. They are
    deduplicated by their indices and not by their colors, so a tile with the
    same drawing in two palettes is a single one.

    `indice` maps a 15-bit color to a palette index; what is not there is an
    error and not a similar color, so that an extra color gets noticed.
    """
    px = capa.load()
    celdas = []
    for fila in range(filas):
        for col in range(col0, col0 + cols):
            celda = []
            for y in range(CELL):
                renglon = []
                for x in range(CELL):
                    sx = col * CELL + x
                    sy = (fila0 + fila) * CELL + y
                    if sy >= HEIGHT or sx >= WIDTH:
                        renglon.append(0)
                        continue
                    r, g, b, a = px[sx, sy]
                    renglon.append(indice[(r >> 3, g >> 3, b >> 3)] if a else 0)
                celda.append(tuple(renglon))
            celda = tuple(celda)
            if celda not in donde:
                donde[celda] = len(tiles)
                tiles.append(celda)
            celdas.append(donde[celda] | (paleta << 10))
    return celdas


def _texto_de_ranura(numero, db, llena):
    """The first two lines of a slot, with the game's terms. The second of a
    full slot is the leader's name, which goes separately because it depends
    on the save; the third is the level, which is written in two colors and
    also goes separately."""
    if not llena:
        return ["%s %d" % (db.term_file, numero + 1), VACIA]
    return ["%s %d" % (db.term_file, numero + 1), ""]


def _escribir_termino_nivel(destino, sys_img, x, y, db, font_id):
    """The level term, like `Window_SaveFile::Refresh`: `lvl_short` padded
    to two characters and in system color 1. In ABL it is "L ". The hit
    points RM2k puts next to it do not go: this port does not have them.

    It is copied from the EasyRPG capture of 2026-09-10, not from the code
    alone.

    **The number does not go here**: the ROM composes it with glyphs,
    because it is the only thing on this line that depends on the actor
    —with Kersh as leader it says 20 and with Core 15—. The term is baked,
    since it is the same for everyone.
    """
    from port import window as ventana_mod
    ventana_mod.draw_line(destino, sys_img, x, y,
                          (db.term_lvl_short or "")[:2].ljust(2), color=1,
                          font_id=font_id)


def texto_de_nombre(db, actor, cols=None):
    """The actor's name as the ROM composes it: one letter per cell, with the
    ones the font lacks turned into '?' and padded with spaces.

    The padding is not decoration: the ROM always writes the same cells, so
    what is left over on the right has to erase whatever was there."""
    cols = MENU_NOMBRE_COLS if cols is None else cols
    nombre = db.actors[actor].name if actor in db.actors else ""
    return texto_de_item(nombre, cols).ljust(cols)


def texto_de_nivel(db, actor, nivel=None):
    """The two digits of the level, as RM2k says them: right-aligned. Without
    `nivel`, the starting one; the ROM composes the current one with the
    same, `texto_nivel`."""
    if nivel is None:
        nivel = level_of(db.actors[actor]) if actor in db.actors else 0
    return ("%*d" % (NIVEL_CIFRAS, nivel))[-NIVEL_CIFRAS:]


def texto_de_maximo(db, actor, nivel=None):
    """The actor's max HP after its slash: "/168". They go next to the
    current HP, which the ROM writes with the same glyphs. Without `nivel`,
    those of the starting one; the ROM composes those of the current one,
    `texto_maximo`."""
    maximo = (param_of(db.actors[actor], "maxhp", nivel)
              if actor in db.actors else 0)
    return ("/%d" % maximo).ljust(MENU_MAX_CIFRAS)[:MENU_MAX_CIFRAS]


def texto_de_exp(db, actor, nivel=None, exp=None):
    """The experience as `DrawActorExp` writes it: `"%6d/%6d"`, the current
    one and the one the next level asks for —`GetNextExp`—, or dashes at the
    cap. Without `nivel` or `exp`, the starting ones, like
    `texto_de_nivel`."""
    a = db.actors[actor]
    if nivel is None:
        nivel = experience.initial_level(a)
    if exp is None:
        exp = experience.initial_exp(a)
    siguiente = experience.next_exp(a, nivel)
    if siguiente == -1:
        return "-" * MENU_EXP_CIFRAS + "/" + "-" * MENU_EXP_CIFRAS
    return "%*d/%*d" % (MENU_EXP_CIFRAS, exp, MENU_EXP_CIFRAS, siguiente)


def glifos_de(db, actores, otras=""):
    """Which letters the bank needs: those of what is composed, plus the ten
    digits, which always go because the gold and the current HP use them,
    and those of `otras` —the names of the medicines, which the actor choice
    writes: see `OBJETIVO_VENTANAS`—.

    It comes from the texts themselves and not from an alphabet written by
    hand: a cartridge with three actors does not pay for the others'
    letters."""
    letras = set("0123456789 ") | set(otras)
    letras |= set("/-")         # the experience's, which it always has
    for actor in actores:
        letras |= set(texto_de_nombre(db, actor) + texto_de_nivel(db, actor)
                      + texto_de_maximo(db, actor))
    return sorted(letras)


def cara_de(db, actor, game_dir):
    """The actor's face, 48x48 in RGBA, or None if it has none.

    It goes through `render_map.load_image` and not `Image.open`, like the
    skin: in RM2k palette index 0 is transparent in a FaceSet too, and in
    `ABLFaces` it is a red that fills almost the whole face. Drawn opaque,
    each face was a red square with a figure inside.
    """
    import os
    from render import render_map
    a = db.actors[actor]
    if not a.face_name:
        return None
    hoja = render_map.load_image(os.path.join(game_dir, "FaceSet",
                                              a.face_name + ".png"))
    col, fila = a.face_index % 4, a.face_index // 4
    return hoja.crop((col * CARA, fila * CARA, (col + 1) * CARA,
                      (fila + 1) * CARA))


def _paleta_de_cara(cara):
    """Fifteen colors for a face, and where each color of the image goes.

    ABL's faces use between 22 and 29 15-bit colors, and a 4bpp palette fits
    15. Index 0 is the transparent one, and black goes there: over the
    screen's black background it makes no difference and does not spend an
    entry.

    The reduction is `allocator.merge_least_visible` and **not** `reducir`,
    which is what the title image uses. `reducir` keeps the fifteen most
    used colors and sends the rest to the nearest, and at 48x48 pixels that
    flattens everything: a face has a handful of skin tones covering almost
    all of it and a dozen details of two or three pixels each —the glint of
    an eye, the edge of a lock of hair—, so the fifteen winners were fifteen
    variants of the same tone and the face came out flat. taro reported it
    as "Talan and Core look gray".

    On the title the difference does not exist —it is 240 colors out of
    369, and the ones merged barely appear— and it costs the quadratic, so
    `reducir` stays there.
    """
    pixeles_de_cara = [(r >> 3, g >> 3, b >> 3) if a else BLACK
                       for r, g, b, a in cara.get_flattened_data()]
    usados = collections.Counter(p for p in pixeles_de_cara if p != BLACK)
    if len(usados) > 15:
        mapa = allocator.merge_least_visible(usados, 15)[0]
        paleta = sorted(set(mapa.values()))
        destino = mapa
    else:
        paleta = sorted(usados, key=lambda c: (-usados[c], c))
        destino = {c: c for c in usados}
    colores = [BLACK] + list(paleta)
    indice = {BLACK: 0}
    for color, a_donde in destino.items():
        indice[color] = colores.index(a_donde)
    return colores, indice


def _cara_prestada(colores, indice_cara, paletas):
    """Which of the existing palettes a face that did not get its own hangs
    on to, and for each color of the face which index of that palette it
    goes to.

    The palette missing the fewest colors is chosen —counting distinct
    colors and not pixels, which is what can be known here without walking
    the image again— and each color goes to the nearest by luma, which is
    exactly what `cabe` does in the converter with the sprites.

    The first two palettes are the text's and are not touched: painting the
    face over the text would make it illegible, which is worse than a face
    with its tone changed.
    """
    candidatas = list(range(2, len(paletas)))
    cual = min(candidatas,
               key=lambda n: (sum(1 for c in colores if c not in paletas[n]), n))
    destino = paletas[cual]
    donde = {}
    for color in colores:
        if color in destino:
            donde[color] = destino.index(color)
        else:
            donde[color] = destino.index(
                min(destino, key=lambda p, c=color: (
                    allocator.luma_distance(p, c), p)))
    return cual, {c: donde[colores[k]] for c, k in indice_cara.items()}


# --- the pause menu ----------------------------------------------------------
#
# It is RM2k's `Scene_Menu` at 256x224 and not 320x240, so the geometry is
# ours and not theirs: the command column on the left, the gold at the bottom
# left and the party on the right, **without the windows** —black background,
# like the slot screen— and without what does not fit: the actor's title, the
# experience and the SP. Of the party one sees the face, the name, the level,
# the status and the HP. It is cosmetic and declared: it looks right or it
# does not, and taro says which by playing.
#
# It lives in the **same tile bank and the same palette** as the slot screen:
# the faces are the same, and the save screen is opened from the menu.
# Everything is aligned to 8-pixel cells so the blocks work on any row.
MENU_OPCIONES = 5
MENU_OPC_Y = 8                  # the first command, in pixels
MENU_OPC_SALTO = 16             # and how far apart the next one is
MENU_OPC_COL = 3                # the command's text, x = 24
MENU_OPC_COLS = 9               # up to x = 96, where the party starts
MENU_CURSOR_COL = 1             # the ">", x = 8
# Which commands do something. The others are drawn in the "cannot" color,
# which is system color 3, the way RM2k draws "Save" when it is forbidden:
# today that is only techniques. Using items opens the item screen since
# 2026-09-11. Number 3, saving, depends on `ChangeSaveAccess`. Number 4, End
# Game, opens the fin_del_juego.py screen since 2026-09-28: until then it was
# gray because "ending the game requires going back to the title without
# resetting the SPC700", and that stopped being needed when Game Over started
# going back to the title with a reset.
MENU_ITEMS = 0
MENU_EQUIPO = 2
MENU_GUARDAR = 3
MENU_FIN = 4
MENU_HECHAS = (MENU_ITEMS, MENU_EQUIPO, MENU_GUARDAR, MENU_FIN)
# The gold, at the bottom left: up to six digits **one cell each** —not at the
# font's 6 pixels, so the ROM writes them one at a time without rebuilding
# tiles— and the currency term after them, in color 1.
MENU_ORO_Y = 200
MENU_ORO_COL = 3
MENU_ORO_CIFRAS = 6
MENU_MONEDA_COL = MENU_ORO_COL + MENU_ORO_CIFRAS    # 9, x = 72
MENU_MONEDA_COLS = 3
# The party: a row of seven cells per actor, with the face on the left and
# the text beside it. Four rows are exactly 224 pixels.
MENU_ACTOR_COL = 12             # x = 96
MENU_ACTOR_COLS = COLS - MENU_ACTOR_COL
MENU_ACTOR_FILAS = 7
MENU_TEXTO_X = MENU_ACTOR_COL * CELL + CARA + 8     # 152
MENU_ESTADO_DX = 42             # "Normal" goes 42 from the level, as in RM2k
MENU_FILAS_GRUPO = 4
# The current HP: three digits **one cell each**, for the same reason as the
# gold —so the ROM writes them one at a time without rebuilding tiles—. They
# go on the third line of the actor's row, that is rows 4 and 5 of the block,
# which is where the gold digits land aligned: both are drawn two pixels from
# the top edge of their cell. The maximum goes after, with the slash, and
# that one is baked: it never changes.
MENU_HP_CIFRAS = 3              # no actor in the game goes past 999
MENU_HP_COL = 21                # x = 168, right after the "HP" on the left
MENU_HP_FILA = 4                # the third line, inside the block
MENU_MAX_X = (MENU_HP_COL + MENU_HP_CIFRAS) * CELL      # 192
# And where, inside the actor's row, the three strips that depend on it and
# that the ROM composes with glyphs land: the name on the first line, the two
# level digits after the term on the second, and the maximum after the
# current HP on the third. See "what depends on the actor" up there.
MENU_NOMBRE_COL = MENU_TEXTO_X // CELL                  # 19
MENU_NOMBRE_COLS = COLS - MENU_NOMBRE_COL               # 13
MENU_NOMBRE_FILA = 0
MENU_NIVEL_COL = (MENU_TEXTO_X + 2 * font.WIDTH) // CELL      # 20
MENU_NIVEL_FILA = LINEA // CELL                         # 2
MENU_MAX_COL = MENU_MAX_X // CELL                       # 24
MENU_MAX_CIFRAS = 4             # the slash and up to three digits: "/168"
# The experience, which is the third line of `Window_MenuStatus`: the term
# —"Ex" in ABL— in color 1, and twelve pixels on the current one and the next
# level's, six digits each with the slash in between, `"%6d/%6d"` like
# `DrawActorExp`. With the level at the cap both are dashes, which is what
# easyrpg's comment says RPG_RT does.
#
# **It goes in sprites, not in the tilemap**, and it is the only line on this
# screen that is not on the grid. It did not fit anywhere else: RM2k puts the
# HP to the right of the level and the experience below, in two columns that
# do not fit in 256 pixels, and a fourth line of cells does not fit in the
# row's 56 pixels. In sprites it goes wherever needed: twelve pixels below
# the HP, which is the font's pitch, and at the font's six pixels and not the
# cells' eight —at eight, the thirteen letters went off the screen—. The
# tiles are the bank's own glyphs: the sprites read VRAM from `RANURA_VRAM`,
# so a glyph's tile is the same number.
#
# Twelve and not sixteen pixels below the HP leaves one pixel of space above
# and two below, and on the fourth row the digits' shadow lands exactly on
# the last line of the screen.
MENU_EXP_X = MENU_TEXTO_X
MENU_EXP_Y = 2 + 2 * LINEA + 11         # where the letter starts, in the row
MENU_EXP_NUM_DX = 12
MENU_EXP_CIFRAS = 6
MENU_EXP_LETRAS = 2 * MENU_EXP_CIFRAS + 1
MENU_EXP_TERM_CELDAS = 2        # "Ex": twelve pixels, two cells wide


# --- the item screen ---------------------------------------------------------
#
# `Scene_Item`: on top the description of the marked item and below the
# inventory list with how many there are. In RM2k the list goes in two
# 144-pixel columns; here they do not fit and it goes in **one**, with the
# quantity on the right, and the description is split into two lines.
#
# The text does not go pre-drawn but **one letter per cell**: the screen
# carries its own tile bank with each font character in two cells —white and
# gray—, and names and descriptions go as text in the ROM, which writes two
# tilemap words per letter. The first attempt drew each item's text into the
# bank shared with the slots and the menu, and with a dozen items it no longer
# fit: four of the suite's ROMs stopped building. This way the cost does not
# depend on how many items there are, and the price is that the letters go at
# 8 pixels and not the font's 6, like the menu's gold digits. It is cosmetic
# and declared.
ITEM_DESC_Y = 8
ITEM_DESC_COL = 1
ITEM_DESC_ANCHO = 30            # letters per line, one per cell
ITEM_DESC_RENGLONES = 2
# The list starts one cell lower and has one row less than until 2026-09-28,
# when the windows arrived —see `ITEM_VENTANAS`—: with eleven rows from 48 the
# last one touched the bottom frame, and the top one was stuck to the
# window's. This way both windows leave the same spacing as RM2k.
ITEM_LISTA_Y = 56
ITEM_FILAS = 10                 # 56 + 10 * 16 = 216, and the frame at 222
ITEM_CURSOR_COL = 1
ITEM_NOMBRE_COL = 3             # x = 24, like the menu's commands
ITEM_NOMBRE_ANCHO = 20          # the longest name in the game
ITEM_DOS_PUNTOS_COL = 27
ITEM_CIFRAS_COL = 28            # two digits, 28 and 29
ITEM_PRIMER_CARACTER = 32       # the ones the font has: from the space
ITEM_CARACTERES = 95            # to the tilde, which is what the items use
# The font variants: the index is what the ROM carries in `temp + 1`, and
# also its palette. Number 2 is system color 2, `Window_EquipStatus`'s "goes
# up" one, and only the equipment screen uses it for a parameter's new value,
# so it carries **only the digits**: the whole font in one more color was
# about 150 tiles, and the battle's bank does not have them —see
# `ITEMS_TILES_MAX`—. Number 3 is color 1, the red of the terms of
# `Window_EquipStatus` and `Window_EquipLeft`, and that one does go **whole**:
# measured on 2026-09-28, the font in that color is ten more tiles and not a
# hundred-odd, because tiles are deduplicated by index and the red's gradient
# lands on the same indices as the white's. Only the letters of the terms
# were thirty-five: with fewer letters the palette order —by frequency— comes
# out different and no longer matches.
ITEM_BLANCO, ITEM_GRIS, ITEM_SUBE, ITEM_ROJO = range(4)
ITEM_SUBE_CARACTERES = "0123456789 "
# How far the font bank can grow: the battle uploads it and then writes its
# scene's tilemap at VRAM word $3800, which is tile 384 counting from
# `RANURA_VRAM`. Whatever goes past there would be overwritten.
ITEMS_TILES_MAX = (0x3800 - 0x2000) // 16

# The screen's windows, like `Scene_Item`: the help one on top and the list
# one below, each with the stretched background and the System's frame
# —`window.window`, the same as the message's—. RM2k puts them right
# against each other, so the separator is the two frames together: four
# pixels. The help one is taller than RM2k's —32— because here the
# description goes on two lines.
#
# They go on **BG1**, which was off on this screen, and the text stays on BG2
# as before: that way the text does not have to know anything about the
# windows, and the description, which is uploaded in whole rows, does not
# erase the frame. The glyphs already carry the priority bit —see
# `item_glifo_celdas` in the converter—, so the text stays above the band of
# the background that crosses it, as in RM2k. At 8bpp a pixel is directly its
# CGRAM entry: the frame's colors go from `ITEM_MARCO_CGRAM`, after the four
# text palettes, and black is 0, the transparent one, which lets the backdrop
# color show through, which is black.
ITEM_AYUDA_ALTO = 48
ITEM_VENTANAS = ((0, 0, WIDTH, ITEM_AYUDA_ALTO),
                 (0, ITEM_AYUDA_ALTO, WIDTH, HEIGHT - ITEM_AYUDA_ALTO))
ITEM_MARCO_CGRAM = 4 * MENU_CGRAM
# The frame's tiles go in the font's bank, after it: BG1's base is the same as
# BG2's, and an 8bpp tile is the size of two 4bpp ones. Everything has to fit
# before BG1's tilemap, which goes at $3800 —where the battle puts its
# scene's, so nothing of this screen is there—.
ITEM_MARCO_MAPA = 0x3800
# The list's cursor is the System's —RM2k's red bar— and not the ">": four
# pixels wider than the text on each side, which is what RM2k leaves.
ITEM_BARRA_X = ITEM_NOMBRE_COL * CELL - 4
ITEM_BARRA_ANCHO = (ITEM_CIFRAS_COL + 2 - ITEM_NOMBRE_COL) * CELL + 8


def ventanas_items(sys_img, barra=None):
    """The item screen's windows, in RGBA and the size of the screen: what
    BG1 draws. With `barra`, the cursor on that row of the list."""
    from PIL import Image
    from port import window as ventana_mod
    fuera = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    for x, y, ancho, alto in ITEM_VENTANAS:
        una = ventana_mod.window(sys_img, ancho, alto)
        fuera.paste(una, (x, y), una)
    if barra is not None:
        una = ventana_mod.cursor(sys_img, ITEM_BARRA_ANCHO, 2 * CELL)
        fuera.paste(una, (ITEM_BARRA_X, ITEM_LISTA_Y + 2 * CELL * barra), una)
    return fuera


def capas_items(sys_img):
    """What `marcos` needs from the item screen: the windows without a
    cursor, and with the cursor on each row of the list together with the
    first cell row it takes."""
    return (ventanas_items(sys_img),
            [(ventanas_items(sys_img, k), ITEM_LISTA_Y // CELL + 2 * k)
             for k in range(ITEM_FILAS)])


def marcos(sys_img, primer_tile, pantallas, cgram=None, tope=256):
    """The windows of several screens as the ROM uploads them: 8bpp tiles,
    one 32x28 tilemap per screen, their cursors and the colors.

    `pantallas` is a list of `(ventanas, barras)`, as `capas_items` gives
    them: the screen-sized image without a cursor, and that of each cursor
    position with the first cell row it takes and, if it is not two, how
    many. The tiles and the colors are **a single set for all**: the screens
    are never open at the same time and upload their tiles to the same place
    in VRAM, so each one uploads the whole set and each one's tilemap indexes
    it the same way.

    `primer_tile` is the 8bpp tile number of the first one, counted from
    BG1's base. Returns `(tiles, colores, mapas)`: `tiles[i][y][x]` is the
    CGRAM entry of that pixel; `colores` the 15-bit ones from `cgram`
    —`ITEM_MARCO_CGRAM` if not given—, which cannot go past `tope`; and
    `mapas[p]` is `(mapa, barras)` of screen `p`, with `mapa` the tilemap
    words row by row and `barras[k]` the two cell rows of cursor `k` with
    the cursor on top, which is what the ROM copies over `mapa` to paint it.

    The tiles are also deduplicated mirrored, with the tilemap's flip bits:
    the frame is symmetric, and without that the windows and the cursor did
    not fit in what is left of VRAM —see `_controlar_marco_de_items`—.
    """
    cgram = ITEM_MARCO_CGRAM if cgram is None else cgram
    imagenes = [imagen for fondo, barras in pantallas
                for imagen in [fondo] + [b[0] for b in barras]]
    cuenta = collections.Counter()
    for imagen in imagenes:
        pixeles = numpy.asarray(imagen).reshape(-1, 4)
        rgb = pixeles[pixeles[:, 3] != 0, :3].astype(numpy.int32) >> 3
        for r, g, b in rgb.tolist():
            if (r, g, b) != BLACK:
                cuenta[(r, g, b)] += 1
    colores = sorted(cuenta, key=lambda c: (-cuenta[c], c))
    if cgram + len(colores) > tope:
        raise SystemExit("the windows use %d colors and from %d there is room "
                         "for %d"
                         % (len(colores), cgram, tope - cgram))
    indice = {c: cgram + i for i, c in enumerate(colores)}
    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, donde = [vacio], {vacio: 0}

    def palabras(imagen, filas):
        px = imagen.load()
        salida = []
        for fila in filas:
            for col in range(COLS):
                celda = []
                for y in range(CELL):
                    renglon = []
                    for x in range(CELL):
                        r, g, b, a = px[col * CELL + x, fila * CELL + y]
                        color = (r >> 3, g >> 3, b >> 3)
                        renglon.append(indice[color]
                                       if a and color != BLACK else 0)
                    celda.append(tuple(renglon))
                celda = tuple(celda)
                h = tuple(tuple(reversed(r)) for r in celda)
                for volteo, forma in ((0, celda), (0x4000, h),
                                      (0x8000, tuple(reversed(celda))),
                                      (0xC000, tuple(reversed(h)))):
                    if forma in donde:
                        salida.append((primer_tile + donde[forma]) | volteo)
                        break
                else:
                    donde[celda] = len(tiles)
                    tiles.append(celda)
                    salida.append(primer_tile + donde[celda])
        return salida

    mapas = []
    for fondo, barras in pantallas:
        mapas.append((palabras(fondo, range(ROWS)),
                      [palabras(b[0], range(b[1], b[1] + (b[2] if len(b) > 2
                                                         else 2)))
                       for b in barras]))
    return tiles, colores, mapas


def item_usable(item):
    """Whether the item goes in white and A does something with it on the
    map: it is `Game_Party::IsItemUsable` outside battle. The switch ones
    with `occasion_field2`, and the medicines, which open the actor choice.
    Books, materials and specials not yet: they go in gray."""
    from rpgmaker import lcf
    return ((item.type == lcf.ITEM_TYPE_SWITCH and item.occasion_field2)
            or item.type == lcf.ITEM_TYPE_MEDICINE)


def item_pide_actor(item):
    """Whether using it opens `Scene_ActorTarget`: the medicines."""
    from rpgmaker import lcf
    return item.type == lcf.ITEM_TYPE_MEDICINE


def texto_de_item(texto, ancho):
    """What the screen can write: the characters the font has, with a '?'
    instead of the others, and cut to the width."""
    return "".join(c if ITEM_PRIMER_CARACTER <= ord(c)
                   < ITEM_PRIMER_CARACTER + ITEM_CARACTERES else "?"
                   for c in texto)[:ancho]


def partir_descripcion(texto, ancho=ITEM_DESC_ANCHO):
    """The description in two lines, cut at a space. What does not fit in
    two is lost."""
    renglones, actual = [], ""
    for palabra in texto.split(" "):
        candidato = (actual + " " + palabra) if actual else palabra
        if len(candidato) <= ancho:
            actual = candidato
            continue
        renglones.append(actual)
        actual = palabra[:ancho]
    renglones.append(actual)
    renglones = [texto_de_item(r, ancho) for r in renglones]
    return (renglones + ["", ""])[:ITEM_DESC_RENGLONES]


def lista_de_items(items, inventario):
    """The items the screen shows, in number order like `Game_Party`: the
    ones there are and that the ROM knows."""
    return [i for i in sorted(items) if inventario.get(i, 0) > 0]


def pantalla_items(sys_img, font_id=None):
    """The item screen's bank: each font character in two cells, one above
    the other, in white, in gray and in red, and the digits also in the
    "goes up" color —see `ITEM_SUBE`—.

    Returns `(tiles, paletas, glifos)`: `paletas[v]` and
    `glifos[v][caracter]` —the two tilemap words— per variant: 0 the text, 1
    the gray, 2 the "goes up" one, which only has `ITEM_SUBE_CARACTERES`,
    and 3 the red. The space is two blank cells: it is the one the cursor
    erases.
    """
    from PIL import Image
    from port import window as ventana_mod
    colores = {ITEM_BLANCO: 0, ITEM_GRIS: 3, ITEM_SUBE: 2, ITEM_ROJO: 1}
    capas = []
    for gris in (ITEM_BLANCO, ITEM_GRIS, ITEM_SUBE, ITEM_ROJO):
        for n in range(ITEM_CARACTERES):
            c = chr(ITEM_PRIMER_CARACTER + n)
            if gris == ITEM_SUBE and c not in ITEM_SUBE_CARACTERES:
                continue
            una = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            ventana_mod.draw_line(una, sys_img, 1, 2, c,
                                  color=colores[gris], font_id=font_id)
            capas.append((gris, n, una))
    # The colors of each set, with numpy: it is one screen-sized image per
    # character and per color, with the letter in a corner, and walking them
    # pixel by pixel was almost all this screen cost. The order they are
    # counted in does not matter: the palette comes out sorted.
    vistos = [collections.Counter() for _ in colores]
    for gris, _, una in capas:
        pixeles = numpy.asarray(una).reshape(-1, 4)
        rgb = pixeles[pixeles[:, 3] != 0, :3].astype(numpy.int32) >> 3
        codigos, cuantos = numpy.unique(
            (rgb[:, 0] << 10) | (rgb[:, 1] << 5) | rgb[:, 2],
            return_counts=True)
        for c, k in zip(codigos.tolist(), cuantos.tolist()):
            vistos[gris][(c >> 10, (c >> 5) & 31, c & 31)] += k
    paletas, indices = [], []
    for cuenta in vistos:
        if len(cuenta) > 15:
            raise SystemExit("the item screen's font uses %d colors and 4bpp "
                             "fits 15" % len(cuenta))
        paleta = [BLACK] + sorted(cuenta, key=lambda c: (-cuenta[c], c))
        paletas.append(paleta)
        indices.append({color: i for i, color in enumerate(paleta)})
    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, donde = [vacio], {vacio: 0}
    glifos = [{} for _ in colores]
    for gris, n, una in capas:
        glifos[gris][chr(ITEM_PRIMER_CARACTER + n)] = _bloque_de_celdas(
            una, 0, 2, tiles, donde, indices[gris], 0, 1, gris)
    if len(tiles) > ITEMS_TILES_MAX:
        raise SystemExit("the item screen's font gathers %d tiles and its "
                         "bank fits %d" % (len(tiles), ITEMS_TILES_MAX))
    return tiles, paletas, glifos


def _escribir_menu_fila(destino, sys_img, db, font_id):
    """The text of a party row that **does not depend on the actor**: the
    level term, the status and the HP term.

    It is a single block for the four rows and for all actors, and that is
    the difference with before: the name, the level number and the maximum
    —the only things that changed from one actor to another— are composed by
    the ROM with glyphs, so this block is not multiplied by the number of
    actors.

    The current HP does not go here either, and that is the fix of
    2026-09-13: this block is baked when converting and uploaded as is, so
    whatever number it carried could never change. taro reported it while
    playing —"HP goes down in battle, but the menu always shows 40"—; the 40
    is the maximum of Talan, who leads the intro.
    """
    from port import window as ventana_mod

    def escribir(x, y, texto, color=0):
        return ventana_mod.draw_line(destino, sys_img, x, y, texto,
                                     color=color, font_id=font_id)

    _escribir_termino_nivel(destino, sys_img, MENU_TEXTO_X, 2 + LINEA, db,
                            font_id)
    escribir(MENU_TEXTO_X + MENU_ESTADO_DX, 2 + LINEA, db.term_normal_status)
    escribir(MENU_TEXTO_X, 2 + 2 * LINEA, db.term_hp_short, color=1)


def cifras_de(valor, cuantas):
    """The digits of a number capped at `cuantas`, without leading zeros.

    It is `cifras_del_oro` generalized: the menu's gold and each actor's HP
    use it, which the ROM writes with the same one-cell blocks.
    """
    return [int(c) for c in str(max(0, min(valor, 10 ** cuantas - 1)))]


def hp_de_menu(db, actor, hp=None):
    """The HP the actor's row has to show: those in `hp` if present, and
    otherwise the maximum for its level, which is what the game starts
    with."""
    if hp is not None and actor in hp:
        return hp[actor]
    return param_of(db.actors[actor], "maxhp")


def _pegar_hp(pegar, menu, fila, cuanto):
    """The HP digits of a party row, right-aligned.

    It is what the ROM does in `menu_hp_escribir`, with the same cells and in
    the same columns; what is left over on the left stays blank.
    """
    cifras = cifras_de(cuanto, MENU_HP_CIFRAS)
    _pegar_texto(pegar, menu, "".join(str(c) for c in cifras),
                 fila * MENU_ACTOR_FILAS + MENU_HP_FILA,
                 MENU_HP_COL + MENU_HP_CIFRAS - len(cifras))


def cifras_del_oro(oro):
    """The digits that get written, without leading zeros: 0 is "0"."""
    return cifras_de(oro, MENU_ORO_CIFRAS)


def pantalla_ranuras(sys_img, db, ranuras, font_id=None, actores=(),
                     game_dir=None, letras=""):
    """The slot screen's tiles, its palettes and its cell blocks.

    Returns `(tiles, paletas, cabeceras, filas, caras, menu)`:

    * `paletas[0]` is the text's, `paletas[1]` that of the menu's disabled
      commands, and the ones after, one per face.
    * `cabeceras[modo]` are the cells of the screen's title, with `modo` 0
      for loading and 1 for saving. Both texts come from the LDB
      —`load_game_message` and `save_game_message`, which in ABL say "Load
      which slot?" and "Save in which slot?"—.
    * `filas[ranura][llena][cursor]` are the cells of a whole row, with the
      face, name and level cells blank.
    * `caras[actor]` are the 36 cells of the face, with its palette set, for
      the `actores` that have one. The ROM writes it over the row according
      to the party the save stored, and `render_ranuras` does the same.

    * `menu` are the pause menu's blocks, which shares bank and palette:
      `opciones[orden][deshabilitada]`, `cursor`, `moneda`, `fila` —the text
      of a party row, a single one for all— and `glifos[letra]`, the two
      cells of each letter the ROM composes. The ten digits are there: they
      are the ones that write the gold and the HP.

    All the variants are drawn before deduplicating, for the usual reason:
    there is a single tile bank.
    """
    from PIL import Image
    from port import window as ventana_mod

    def capa():
        return Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

    def escribir(destino, x, y, texto):
        if texto:
            ventana_mod.draw_line(destino, sys_img, x, y, texto,
                                  font_id=font_id)

    # First all the text layers, so the colors can be gathered at once.
    capas = []
    for modo, texto in enumerate((db.term_load_message, db.term_save_message)):
        una = capa()
        escribir(una, RANURA_X, CABECERA_Y, texto)
        capas.append(("cabecera", modo, una))
    for numero in range(ranuras):
        for llena in (0, 1):
            for cursor in (0, 1):
                una = capa()
                y = RANURA_Y + numero * RANURA_SALTO
                if cursor:
                    escribir(una, RANURA_X - 16, y + 2, ">")
                for n, linea in enumerate(_texto_de_ranura(numero, db, llena)):
                    escribir(una, RANURA_X, y + 2 + n * LINEA, linea)
                if llena:
                    # The level term goes in the row and not in the actor's
                    # layer: it is the same for everyone, and a slot without a
                    # save does not show it.
                    _escribir_termino_nivel(una, sys_img, RANURA_X,
                                            y + 2 + 2 * LINEA, db, font_id)
                capas.append(("fila", (numero, llena, cursor), una))
    # The pause menu's, in the same bank. Each on the topmost row it gets: the
    # blocks work on any other because they are aligned.
    from port import window as ventana_mod
    for orden, texto in enumerate(db.term_menu):
        for deshabilitada in (0, 1):
            una = capa()
            ventana_mod.draw_line(
                una, sys_img, MENU_OPC_COL * CELL,
                MENU_OPC_Y + orden * MENU_OPC_SALTO + 2, texto,
                color=3 if deshabilitada else 0, font_id=font_id)
            capas.append(("menu_opcion", (orden, deshabilitada), una))
    una = capa()
    escribir(una, MENU_CURSOR_COL * CELL, MENU_OPC_Y + 2, ">")
    capas.append(("menu_cursor", None, una))
    for letra in glifos_de(db, actores, letras):
        una = capa()
        escribir(una, GLIFO_COL * CELL + GLIFO_DX,
                 GLIFO_FILA * CELL + GLIFO_DY, letra)
        capas.append(("menu_glifo", letra, una))
    una = capa()
    ventana_mod.draw_line(una, sys_img, MENU_MONEDA_COL * CELL,
                          MENU_ORO_Y + 2, db.term_gold, color=1,
                          font_id=font_id)
    capas.append(("menu_moneda", None, una))
    una = capa()
    _escribir_menu_fila(una, sys_img, db, font_id)
    capas.append(("menu_fila", None, una))
    # The experience term, loose like a glyph: sprites draw it. Up to two
    # letters, which are the twelve pixels `DrawActorExp` leaves it before
    # the digits.
    una = capa()
    ventana_mod.draw_line(una, sys_img, GLIFO_COL * CELL,
                          GLIFO_FILA * CELL + GLIFO_DY,
                          (db.term_exp_short or "")[:2], color=1,
                          font_id=font_id)
    capas.append(("menu_exp_termino", None, una))

    # The disabled commands go in **their own palette**, number 1: system
    # color 3 is a gradient that, added to the text's, gives 18 colors, and
    # 4bpp fits 15. It costs the faces one palette.
    def gris(clase, clave):
        return clase == "menu_opcion" and clave[1]

    vistos, vistos_gris = collections.Counter(), collections.Counter()
    for clase, clave, una in capas:
        cuenta = vistos_gris if gris(clase, clave) else vistos
        for r, g, b, a in una.get_flattened_data():
            if a:
                cuenta[(r >> 3, g >> 3, b >> 3)] += 1
    for cuantos, que in ((len(vistos), "the text of the slots and the menu"),
                         (len(vistos_gris), "the disabled commands")):
        if cuantos > 15:
            raise SystemExit("%s uses %d colors and 4bpp fits 15"
                             % (que, cuantos))
    paleta = [BLACK] + sorted(vistos, key=lambda c: (-vistos[c], c))
    indice = {color: i for i, color in enumerate(paleta)}
    paleta_gris = [BLACK] + sorted(vistos_gris,
                                   key=lambda c: (-vistos_gris[c], c))
    indice_gris = {color: i for i, color in enumerate(paleta_gris)}

    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, donde = [vacio], {vacio: 0}
    cabeceras = [None, None]
    filas = [[[None, None], [None, None]] for _ in range(ranuras)]
    menu = {"opciones": [[None, None] for _ in range(MENU_OPCIONES)],
            "cursor": None, "glifos": {}, "moneda": None, "fila": None}
    for clase, clave, una in capas:
        if clase == "menu_opcion":
            orden, deshabilitada = clave
            menu["opciones"][orden][deshabilitada] = _bloque_de_celdas(
                una, (MENU_OPC_Y + orden * MENU_OPC_SALTO) // CELL, 2, tiles,
                donde, indice_gris if deshabilitada else indice,
                MENU_OPC_COL, MENU_OPC_COLS, 1 if deshabilitada else 0)
        elif clase == "menu_cursor":
            menu["cursor"] = _bloque_de_celdas(
                una, MENU_OPC_Y // CELL, 2, tiles, donde, indice,
                MENU_CURSOR_COL, 1)
        elif clase == "menu_glifo":
            menu["glifos"][clave] = _bloque_de_celdas(
                una, GLIFO_FILA, 2, tiles, donde, indice, GLIFO_COL, 1)
        elif clase == "menu_moneda":
            menu["moneda"] = _bloque_de_celdas(
                una, MENU_ORO_Y // CELL, 2, tiles, donde, indice,
                MENU_MONEDA_COL, MENU_MONEDA_COLS)
        elif clase == "menu_fila":
            menu["fila"] = _bloque_de_celdas(
                una, 0, MENU_ACTOR_FILAS, tiles, donde, indice,
                MENU_ACTOR_COL, MENU_ACTOR_COLS)
        elif clase == "menu_exp_termino":
            menu["exp_termino"] = _bloque_de_celdas(
                una, GLIFO_FILA, 2, tiles, donde, indice, GLIFO_COL,
                MENU_EXP_TERM_CELDAS)
        elif clase == "cabecera":
            cabeceras[clave] = _bloque_de_celdas(
                una, CABECERA_Y // CELL, CABECERA_FILAS, tiles, donde, indice)
        else:
            numero, llena, cursor = clave
            fila0 = (RANURA_Y + numero * RANURA_SALTO) // CELL
            filas[numero][llena][cursor] = _bloque_de_celdas(
                una, fila0, RANURA_FILAS, tiles, donde, indice)

    # And the faces, each with its palette, pasted at the top left of the
    # first row to cut them into cells with the same function.
    paletas, caras = [paleta, paleta_gris], {}
    # Which faces had to borrow a palette: it shows in the converter's
    # report, same as with the sprites.
    prestadas_cara = set()
    for actor in actores:
        cara = cara_de(db, actor, game_dir)
        if cara is None:
            continue
        colores, indice_cara = _paleta_de_cara(cara)
        if len(paletas) > CARAS_PALETAS_MAX:
            # No BG2 palette left: **one is lent to it**, which is the same
            # rule `cabe` runs with the sprites and the same reason of taro's
            # —if we cannot include everyone, the whole project falls apart—.
            # Each color of the face goes to the nearest by luma in the
            # palette it is missing the fewest from, and the face shows with
            # colors that are not its own.
            #
            # It was needed when putting in the whole of Lashe City: the faces
            # are one palette each, six are left, and from map 20 on Arden,
            # Saldra, the Rat Tracks Gang Member and AG7-17 can join the party,
            # that is eight. The alternative was leaving out Rat Tracks B2 and
            # the whole car chain, which are the path of the story.
            cual, indice_cara = _cara_prestada(colores, indice_cara, paletas)
            prestadas_cara.add(actor)
        else:
            cual = len(paletas)
            paletas.append(colores)
        una = capa()
        una.paste(cara, (CARA_COL * CELL, RANURA_Y))
        caras[actor] = _bloque_de_celdas(
            una, RANURA_Y // CELL, CARA_CELDAS, tiles, donde, indice_cara,
            CARA_COL, CARA_CELDAS, cual)
    if prestadas_cara:
        print("  faces without a palette of their own, drawn with another's: %s"
              % ", ".join(db.actors[a].name for a in sorted(prestadas_cara)))
    if len(tiles) > RANURA_TILES_MAX:
        raise SystemExit(
            "the slot screen and the menu gather %d tiles and their bank "
            "fits %d" % (len(tiles), RANURA_TILES_MAX))
    return tiles, paletas, cabeceras, filas, caras, menu


def _pintor(fuera, tiles, paletas):
    """A function that pastes a block of cells onto `fuera`, as the ROM does:
    tile and palette of each tilemap word."""
    px = fuera.load()

    def pegar(celdas, fila0, col0=0, cols=COLS):
        for i, palabra in enumerate(celdas):
            tx = (col0 + i % cols) * CELL
            ty = (fila0 + i // cols) * CELL
            celda = tiles[palabra & 0x3FF]
            paleta = paletas[(palabra >> 10) & 7]
            for y in range(CELL):
                if ty + y >= HEIGHT:
                    break
                for x in range(CELL):
                    valor = celda[y][x]
                    if valor:
                        px[tx + x, ty + y] = tuple(v << 3 for v in paleta[valor])
    return pegar


def _pegar_sprite(fuera, tiles, paletas, palabra, x, y):
    """An 8x8 tile at any pixel, like a sprite: what is transparent lets
    what was there show through. The palette is the word's, which the ROM
    copies to the sprites'."""
    px = fuera.load()
    celda = tiles[palabra & 0x3FF]
    paleta = paletas[(palabra >> 10) & 7]
    for dy in range(CELL):
        for dx in range(CELL):
            valor = celda[dy][dx]
            if valor and 0 <= x + dx < WIDTH and 0 <= y + dy < HEIGHT:
                px[x + dx, y + dy] = tuple(v << 3 for v in paleta[valor])


def _pegar_exp(fuera, tiles, paletas, menu, fila, texto):
    """The experience line of a party row, in sprites: the term and the
    thirteen letters of `texto`, at six pixels. It is what `menu_exp_pintar`
    does in the ROM; spaces get no sprite."""
    y = fila * MENU_ACTOR_FILAS * CELL + MENU_EXP_Y - GLIFO_DY
    for n, palabra in enumerate(menu["exp_termino"]):
        _pegar_sprite(fuera, tiles, paletas, palabra,
                      MENU_EXP_X + (n % MENU_EXP_TERM_CELDAS) * CELL,
                      y + (n // MENU_EXP_TERM_CELDAS) * CELL)
    for n, letra in enumerate(texto):
        if letra == " ":
            continue
        x = MENU_EXP_X + MENU_EXP_NUM_DX + n * font.WIDTH - GLIFO_DX
        arriba, abajo = menu["glifos"][letra]
        _pegar_sprite(fuera, tiles, paletas, arriba, x, y)
        _pegar_sprite(fuera, tiles, paletas, abajo, x, y + CELL)


def _pegar_texto(pegar, menu, texto, fila, col):
    """A text composed one letter per cell, as the ROM writes it."""
    for n, letra in enumerate(texto):
        pegar(menu["glifos"][letra], fila, col + n, 1)


def _pegar_fila_de_actor(pegar, menu, caras, db, fila, actor, hp=None,
                         niveles=None):
    """A row of the party panel: the fixed block, the face and the three
    strips that depend on the actor. It is what `menu_grupo_pintar` does, in
    the same order, and that is why the menu and the actor choice share
    it."""
    fila0 = fila * MENU_ACTOR_FILAS
    pegar(menu["fila"], fila0, MENU_ACTOR_COL, MENU_ACTOR_COLS)
    if actor in caras:
        pegar(caras[actor], fila0, MENU_ACTOR_COL, CARA_CELDAS)
    _pegar_texto(pegar, menu, texto_de_nombre(db, actor),
                 fila0 + MENU_NOMBRE_FILA, MENU_NOMBRE_COL)
    nivel = (niveles or {}).get(actor)
    _pegar_texto(pegar, menu, texto_de_nivel(db, actor, nivel),
                 fila0 + MENU_NIVEL_FILA, MENU_NIVEL_COL)
    _pegar_texto(pegar, menu, texto_de_maximo(db, actor, nivel),
                 fila0 + MENU_HP_FILA, MENU_MAX_COL)
    _pegar_hp(pegar, menu, fila, hp_de_menu(db, actor, hp))


def render_menu(sys_img, db, ranuras, grupo, oro, elegida=0,
                guardar_permitido=True, font_id=None, actores=None,
                game_dir=None, hp=None, niveles=None, exps=None):
    """The pause menu as the console has to show it.

    `grupo` are the actors in order, `oro` the gold, `elegida` the command
    with the cursor and `guardar_permitido` what `ChangeSaveAccess` left.
    `actores` is the ROM's list —those who can join the party,
    `miembros_posibles` in the converter—, which decides the tile bank;
    without it, the party. It is built with the same blocks the ROM uploads,
    like `render_ranuras`.

    `hp` is what the save has in `FAR_HP`, from actor to HP: without it they
    are assumed full, which is what the game starts with. It goes apart from
    the actor's block because the block is baked and this changes with every
    battle. `niveles`, from actor to level, is the same for the level and the
    maximum: without it, the starting ones. `exps`, from actor to experience,
    the same for the experience line, which also looks at the level.
    """
    from PIL import Image
    actores = sorted(set(actores if actores is not None else grupo))
    tiles, paletas, _, _, caras, menu = pantalla_ranuras(
        sys_img, db, ranuras, font_id, actores, game_dir)
    fuera = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    pegar = _pintor(fuera, tiles, paletas)
    for orden in range(MENU_OPCIONES):
        hecha = orden in MENU_HECHAS and (orden != MENU_GUARDAR
                                          or guardar_permitido)
        pegar(menu["opciones"][orden][0 if hecha else 1],
              (MENU_OPC_Y + orden * MENU_OPC_SALTO) // CELL, MENU_OPC_COL,
              MENU_OPC_COLS)
    pegar(menu["cursor"], (MENU_OPC_Y + elegida * MENU_OPC_SALTO) // CELL,
          MENU_CURSOR_COL, 1)
    cifras = cifras_del_oro(oro)
    _pegar_texto(pegar, menu, "".join(str(c) for c in cifras),
                 MENU_ORO_Y // CELL, MENU_MONEDA_COL - len(cifras))
    pegar(menu["moneda"], MENU_ORO_Y // CELL, MENU_MONEDA_COL,
          MENU_MONEDA_COLS)
    for fila, actor in enumerate(list(grupo)[:MENU_FILAS_GRUPO]):
        if actor in actores:
            _pegar_fila_de_actor(pegar, menu, caras, db, fila, actor, hp,
                                 niveles)
    # The experience goes on top of everything, like sprites over the
    # background, and only in the menu: `Window_ActorTarget` does not show
    # it.
    for fila, actor in enumerate(list(grupo)[:MENU_FILAS_GRUPO]):
        if actor in actores:
            _pegar_exp(fuera, tiles, paletas, menu, fila, texto_de_exp(
                db, actor, (niveles or {}).get(actor),
                (exps or {}).get(actor)))
    return fuera


# The actor choice, `Scene_ActorTarget`: the menu's party panel, and as in
# RM2k, three System windows on BG1 —like the item and equipment ones, see
# `ITEM_VENTANAS`— and the red bar over the marked row. RM2k puts the help
# with the item's name on the left and "Owned Items" in red with the quantity
# below it, and the party on the right. Here the left column reaches x = 104:
# the bank's faces are 48 wide but what shows of them starts twelve pixels in,
# at x = 108, so the party window can start left of the menu row (x = 96)
# without covering them. At 104 eleven 8-pixel letters fit, and the name goes
# on two lines: eleven is what "Sandwich-HP" needs.
#
# The name is written with the menu bank's glyphs —one letter per cell, like
# the actor's name—, so the bank also carries the medicines' letters. "Owned
# Items" does not: it is **baked into BG1**, in red and at the font's six
# pixels, because at eight its eleven letters fill the window and leave no
# room for the quantity, and because the red has no free palette on BG2. The
# quantity does, with the glyphs, on the right.
#
# To choose whom to equip, the screen is the same without the two windows on
# the left: there is no item.
#
# A uses the medicine on the marked row and the screen stays, with that row's
# HP and the quantity up to date: see `medicina_usar` in
# tools/runtime/medicina.s. This draws the HP passed in `hp`, so after healing
# it is enough to pass the new ones.
OBJETIVO_IZQ = 104
OBJETIVO_NOMBRE_ALTO = 48
OBJETIVO_CUANTOS_ALTO = 32
OBJETIVO_GRUPO = (OBJETIVO_IZQ, 0, WIDTH - OBJETIVO_IZQ, HEIGHT)
OBJETIVO_VENTANAS = ((0, 0, OBJETIVO_IZQ, OBJETIVO_NOMBRE_ALTO),
                     (0, OBJETIVO_NOMBRE_ALTO, OBJETIVO_IZQ,
                      OBJETIVO_CUANTOS_ALTO),
                     OBJETIVO_GRUPO)
OBJETIVO_NOMBRE_COL = 1
OBJETIVO_NOMBRE_FILA = 1        # y = 8, and the second line at y = 24
OBJETIVO_NOMBRE_ANCHO = (OBJETIVO_IZQ - 8) // CELL - OBJETIVO_NOMBRE_COL  # 11
OBJETIVO_CUANTOS_FILA = (OBJETIVO_NOMBRE_ALTO + 8) // CELL                # 7
OBJETIVO_CUANTOS_COL = OBJETIVO_NOMBRE_COL + OBJETIVO_NOMBRE_ANCHO - 2    # 10
# The bar goes over the row's three lines of text, as in RM2k, and not over
# the face: four pixels before the text and up to four from the edge, and
# from two pixels inside the row, so as not to touch the top frame. It ends at
# 48, on a cell boundary, and not at 50, which is where the third line ends:
# with the bottom tip mid-cell it was 64 tiles, which is exactly what fits
# before the tilemap, and this way it is 60. What is left out is the shadow of
# the HP letters.
OBJETIVO_BARRA = (MENU_TEXTO_X - 4, 2, WIDTH - MENU_TEXTO_X, 3 * LINEA - 2)
# BG1's colors go in 128..143: they are those of sprite palette 0, which on
# this screen are off, and which `menu_exp_cerrar` restores on closing the
# menu. There is no room in 0..127: they are the menu bank's palettes.
OBJETIVO_CGRAM = 128
OBJETIVO_COLORES_MAX = 16
# BG1's tiles and tilemap, after the menu's tilemap ($3C00..$4000): BG1 has
# its own base at $4000, so they do not touch BG2's bank. What matters is that
# everything stays in the layouts' BG1 bank, which is what `load_map`
# restores on the way back: see `_controlar_objetivo` in the converter.
OBJETIVO_VRAM = 0x4000
OBJETIVO_MAPA = 0x4800


def nombre_en_renglones(nombre, ancho=OBJETIVO_NOMBRE_ANCHO, renglones=2):
    """The name split into lines of `ancho`, by words; a word that does not
    fit is cut where it reaches. Padded with spaces, which are what erase
    whatever was there."""
    salida, linea = [], ""
    for palabra in nombre.strip().split():
        while len(palabra) > ancho:
            if linea:
                salida.append(linea)
                linea = ""
            salida.append(palabra[:ancho])
            palabra = palabra[ancho:]
        if not linea:
            linea = palabra
        elif len(linea) + 1 + len(palabra) <= ancho:
            linea += " " + palabra
        else:
            salida.append(linea)
            linea = palabra
    if linea:
        salida.append(linea)
    return [r.ljust(ancho) for r in (salida + [""] * renglones)[:renglones]]


def ventanas_objetivo(sys_img, db, con_item=True, barra=None, font_id=None):
    """The actor choice's windows, in RGBA and the size of the screen: what
    BG1 draws. With `con_item`, the two on the left with "Owned Items"; with
    `barra`, the cursor on that party row."""
    from PIL import Image
    from port import window as ventana_mod
    fuera = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    for x, y, ancho, alto in (OBJETIVO_VENTANAS if con_item
                              else (OBJETIVO_GRUPO,)):
        una = ventana_mod.window(sys_img, ancho, alto)
        fuera.paste(una, (x, y), una)
    if con_item:
        ventana_mod.draw_line(
            fuera, sys_img, OBJETIVO_NOMBRE_COL * CELL + GLIFO_DX,
            OBJETIVO_CUANTOS_FILA * CELL + GLIFO_DY,
            lcf_termino_poseidos(db), color=1, font_id=font_id)
    if barra is not None:
        x, y, ancho, alto = OBJETIVO_BARRA
        una = ventana_mod.cursor(sys_img, ancho, alto)
        fuera.paste(una, (x, barra * MENU_ACTOR_FILAS * CELL + y), una)
    return fuera


def lcf_termino_poseidos(db):
    """"Owned Items": `possessed_items` from the LDB terms."""
    from rpgmaker import lcf
    return lcf.to_string(db.terms["possessed_items"])


def capas_objetivo(sys_img, db, font_id=None):
    """What `marcos` needs from the actor choice: with an item and without,
    each without a cursor and with the cursor on each party row, from the
    first cell row of the actor's row."""
    return [(ventanas_objetivo(sys_img, db, con_item, None, font_id),
             [(ventanas_objetivo(sys_img, db, con_item, k, font_id),
               k * MENU_ACTOR_FILAS, MENU_ACTOR_FILAS)
              for k in range(MENU_FILAS_GRUPO)])
            for con_item in (True, False)]


def objetivo_compacto(mapas):
    """What the ROM stores of the tilemaps of
    `marcos(capas_objetivo(...))`, which is much less than what `marcos`
    returns.

    * **A single tilemap**, the with-item one: the without-item one is the
      same with the cells of the two left windows at zero —the columns left
      of `OBJETIVO_IZQ`, down to the bottom of the "Owned Items" one—, and
      the ROM erases them when uploading it.
    * **The bar, only where it changes**: the rectangle covering what differs
      between each party row with the bar and without it, the same for the
      four rows, and which has to be the same with and without an item.

    Returns `(mapa, barras, fila0, filas, col0, cols, borrar_filas,
    borrar_cols)`: `barras[k]` are the `filas` by `cols` words of party row
    `k`, from row `fila0` of the actor's row and column `col0`. If any of
    that does not hold, it is an error and not a different tilemap: the ROM
    assumes both things.
    """
    (con, barras_con), (sin, barras_sin) = mapas
    borrar_cols = OBJETIVO_IZQ // CELL
    borrar_filas = (OBJETIVO_NOMBRE_ALTO + OBJETIVO_CUANTOS_ALTO) // CELL
    esperado = [0 if (i // COLS < borrar_filas and i % COLS < borrar_cols)
                else p for i, p in enumerate(con)]
    if esperado != sin:
        raise SystemExit("the actor choice's without-item tilemap is not the "
                         "with-item one with the left windows erased")
    distintas = set()
    for k, barra in enumerate(barras_con):
        base = con[k * MENU_ACTOR_FILAS * COLS:
                   (k + 1) * MENU_ACTOR_FILAS * COLS]
        distintas |= {(i // COLS, i % COLS)
                      for i, (a, b) in enumerate(zip(base, barra)) if a != b}
    fila0 = min(f for f, _ in distintas)
    filas = max(f for f, _ in distintas) + 1 - fila0
    col0 = min(c for _, c in distintas)
    cols = max(c for _, c in distintas) + 1 - col0
    if col0 < borrar_cols:
        raise SystemExit("the actor choice's bar reaches column %d, which "
                         "belongs to the item windows" % col0)

    def recorte(barra):
        return [barra[(fila0 + f) * COLS + col0 + c]
                for f in range(filas) for c in range(cols)]

    barras = [recorte(b) for b in barras_con]
    if barras != [recorte(b) for b in barras_sin]:
        raise SystemExit("the actor choice's bar is not the same with and "
                         "without an item")
    return con, barras, fila0, filas, col0, cols, borrar_filas, borrar_cols


def render_objetivo(sys_img, db, ranuras, grupo, elegida=0, font_id=None,
                    actores=None, game_dir=None, hp=None, item=None,
                    cantidad=0):
    """The actor choice as the console has to show it.

    It shares the party panel with the menu, so it also writes the HP:
    `menu_grupo_pintar` paints them, which is the same routine on both
    sides. `item` is the medicine being used, with `cantidad` how many are
    left; without it, it is the choice of whom to equip.
    """
    from PIL import Image
    actores = sorted(set(actores if actores is not None else grupo))
    nombre = db.items[item].name if item else ""
    tiles, paletas, _, _, caras, menu = pantalla_ranuras(
        sys_img, db, ranuras, font_id, actores, game_dir, nombre)
    fuera = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    ventanas = ventanas_objetivo(sys_img, db, bool(item), elegida, font_id)
    fuera.paste(ventanas, (0, 0), ventanas)
    pegar = _pintor(fuera, tiles, paletas)
    for fila, actor in enumerate(list(grupo)[:MENU_FILAS_GRUPO]):
        if actor in actores:
            _pegar_fila_de_actor(pegar, menu, caras, db, fila, actor, hp)
    if item:
        for n, renglon in enumerate(nombre_en_renglones(nombre)):
            _pegar_texto(pegar, menu, renglon, OBJETIVO_NOMBRE_FILA + 2 * n,
                         OBJETIVO_NOMBRE_COL)
        _pegar_texto(pegar, menu, "%2d" % min(cantidad, 99),
                     OBJETIVO_CUANTOS_FILA, OBJETIVO_CUANTOS_COL)
    return fuera


def render_items(sys_img, db, inventario, elegida=0, arriba=0, font_id=None,
                 items=None):
    """The item screen as the console has to show it.

    `inventario` maps item number to how many there are; `items` are the
    ones the ROM knows —without it, the inventory's—; `elegida` is the
    cursor's position in the list and `arriba` the first visible one. It is
    built with the same cells the ROM writes.
    """
    from PIL import Image
    items = sorted(items if items is not None
                   else [i for i, n in inventario.items() if n > 0])
    tiles, paletas, glifos = pantalla_items(sys_img, font_id)
    fuera = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    lista = lista_de_items(items, inventario)
    # The cursor is part of the windows: see `ITEM_BARRA_X`.
    ventanas = ventanas_items(sys_img, elegida - arriba if lista else None)
    fuera.paste(ventanas, (0, 0), ventanas)
    pegar = _pintor(fuera, tiles, paletas)

    def escribir(texto, fila0, col0, gris=0):
        for n, c in enumerate(texto):
            pegar(glifos[gris][c], fila0, col0 + n, 1)

    if lista:
        for n, renglon in enumerate(partir_descripcion(
                db.items[lista[elegida]].description)):
            escribir(renglon, ITEM_DESC_Y // CELL + 2 * n, ITEM_DESC_COL)
    for fila in range(ITEM_FILAS):
        k = arriba + fila
        if k >= len(lista):
            break
        item = db.items[lista[k]]
        fila0 = ITEM_LISTA_Y // CELL + 2 * fila
        gris = 0 if item_usable(item) else 1
        escribir(texto_de_item(item.name, ITEM_NOMBRE_ANCHO), fila0,
                 ITEM_NOMBRE_COL, gris)
        escribir(":%2d" % min(inventario[lista[k]], 99), fila0,
                 ITEM_DOS_PUNTOS_COL, gris)
    return fuera


def render_ranuras(sys_img, db, ranuras, llenas, elegida, modo=0, font_id=None,
                   grupos=None, game_dir=None, niveles=None):
    """The slot screen as the console has to show it.

    `llenas` is a sequence of booleans, one per slot; `elegida`, where the
    cursor is; `modo`, 0 for loading and 1 for saving; `grupos`, per full
    slot, the actors of the saved party, which set the first one's name and
    the faces of up to CARAS_MAX; `niveles`, per slot, the level the leader
    had in that save —without it, the starting one—.

    It is built with **the same cell blocks the ROM uploads**, not drawing
    the text again nor pasting the face: if it were drawn here with the font
    and there with the tiles, exactly the step that can go wrong would be
    left out.
    """
    from PIL import Image
    grupos = grupos or {}
    actores = sorted({a for g in grupos.values() for a in g})
    tiles, paletas, cabeceras, filas, caras, menu = pantalla_ranuras(
        sys_img, db, ranuras, font_id, actores, game_dir)
    fuera = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    pegar = _pintor(fuera, tiles, paletas)

    pegar(cabeceras[modo], CABECERA_Y // CELL)
    for numero in range(ranuras):
        fila0 = (RANURA_Y + numero * RANURA_SALTO) // CELL
        llena = bool(llenas[numero]) or numero in grupos
        pegar(filas[numero][1 if llena else 0][
            1 if numero == elegida else 0], fila0)
        if not llena:
            continue
        grupo = list(grupos.get(numero, ()))
        # The leader's name and level, composed with glyphs over the row, and
        # the faces, which are blocks. An actor without a face draws nothing,
        # which is what `DrawFace` does with an empty name.
        if grupo and grupo[0] in actores:
            _pegar_texto(pegar, menu,
                         texto_de_nombre(db, grupo[0], NOMBRE_COLS),
                         fila0 + NOMBRE_FILA, NOMBRE_COL)
            _pegar_texto(pegar, menu,
                         texto_de_nivel(db, grupo[0],
                                        (niveles or {}).get(numero)),
                         fila0 + NIVEL_FILA, NIVEL_COL)
        for lugar, actor in enumerate(grupo[:CARAS_MAX]):
            if actor in caras:
                pegar(caras[actor], fila0, CARA_COL + lugar * CARA_PASO,
                      CARA_CELDAS)
    return fuera
