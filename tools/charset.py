"""Sprites de personaje de RPG Maker 2000.

Un CharSet es una grilla de 288x256 con 8 personajes: 4 de ancho por 2 de alto.
Cada personaje ocupa un bloque de 72x128 que contiene sus 12 poses, 3 frames de
caminata (24px de ancho) por 4 direcciones (32px de alto).

Las direcciones van 0=arriba, 1=derecha, 2=abajo, 3=izquierda, y el frame del
medio (patrón 1) es la pose parada.
"""

from chipset import TILE, blit

SPRITE_WIDTH = 24
SPRITE_HEIGHT = 32
BLOCK_WIDTH = SPRITE_WIDTH * 3
BLOCK_HEIGHT = SPRITE_HEIGHT * 4
COLUMNS = 4

# El sprite es más ancho y más alto que la celda de 16x16 sobre la que se para:
# se centra horizontalmente y se apoya por los pies.
OFFSET_X = -(SPRITE_WIDTH - TILE) // 2
OFFSET_Y = -(SPRITE_HEIGHT - TILE)


def draw(dst, image, tile_x, tile_y, index, direction, pattern):
    """Dibuja una pose del personaje `index` parado en la celda (tile_x, tile_y)."""
    blit(dst,
         tile_x * TILE + OFFSET_X,
         tile_y * TILE + OFFSET_Y,
         image,
         (index % COLUMNS) * BLOCK_WIDTH + pattern * SPRITE_WIDTH,
         (index // COLUMNS) * BLOCK_HEIGHT + direction * SPRITE_HEIGHT,
         SPRITE_WIDTH, SPRITE_HEIGHT)
