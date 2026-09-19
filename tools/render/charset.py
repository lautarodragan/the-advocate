"""Sprites de personaje de RPG Maker 2000.

Un CharSet es una grilla de 288x256 con 8 personajes: 4 de ancho por 2 de alto.
Cada personaje ocupa un bloque de 72x128 que contiene sus 12 poses, 3 frames de
caminata (24px de ancho) por 4 direcciones (32px de alto).

Las direcciones van 0=arriba, 1=derecha, 2=abajo, 3=izquierda, y el frame del
medio (patrón 1) es la pose parada.
"""

from render.chipset import TILE, blit

SPRITE_WIDTH = 24
SPRITE_HEIGHT = 32

# El sprite es más ancho y más alto que la celda de 16x16 sobre la que se para:
# se centra horizontalmente y se apoya por los pies.
OFFSET_X = -(SPRITE_WIDTH - TILE) // 2
OFFSET_Y = -(SPRITE_HEIGHT - TILE)
