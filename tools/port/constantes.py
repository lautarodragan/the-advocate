"""Port numbers that several modules use and that belong to none of them.

They live here so that whoever needs them does not have to import the module
that uses them most, and with it everything that one imports: `eventos` used
to ask `pantallas` how many equipment slots there are, and `pantallas` imports
`eventos`.
"""

# The console screen, in pixels and in 8x8 cells.
CELL = 8
ANCHO = 256
ALTO = 224
COLS = ANCHO // CELL            # 32
FILAS = ALTO // CELL            # 28

# How many CGRAM entries the menu takes, since it sits on BG2 at four bits per
# pixel: one palette of sixteen, palette 0. They are the **first** ones in
# CGRAM because a 4bpp BG only reaches the low ones, so the image cannot keep
# them and starts shifted.
MENU_CGRAM = 16

# How many colors are left for the image. Going from 256 to 240 does not
# show: it already came down from 369, and the ones that get merged are the
# ones that appear in a handful of pixels.
COLORES = 256 - MENU_CGRAM

# How many lines of text fit in the message window. See `ventana.py`.
LINEAS = 4

# How many characters fit on a line, and where the number comes from. It is
# not the width of the window: it is the tile bank. The text area of the
# window is 30 cells of 8x8 wide, and its tiles are not deduplicated because
# the ROM rewrites them, so they are 30x8 = 240 fixed tiles which, with the 12
# of the empty window, reach 252 of the 256 available. With 40 characters the
# shadow of the last one spills into cell 31 and eight more tiles would be
# needed.
#
# Measured over the 18,808 message lines of the game: truncating at 39 loses
# 1.58% of the characters, against 1.09% when truncating at 40.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
COLUMNAS = 39

# How many equipment slots an RM2k actor has.
RANURAS_EQUIPO = 5              # weapon, shield, armor, helmet, accessory

# How many enemies fit in a battle: what fits on the text screen without
# covering anything of the party. The largest troop in the game has eight
# members, so with eight none is lost.
ENEMIGOS_MAX = 8
