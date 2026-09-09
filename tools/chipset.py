"""Expansión de un ChipSet de RPG Maker 2000 a un atlas de tiles ya resueltos.

Un ChipSet de RM2k es una imagen de 480x256 donde la mitad izquierda no son
tiles listos para dibujar sino "autotiles": bloques de bordes que el motor
combina en tiempo real según los vecinos. El editor guarda en el mapa el ID de
la combinación ya calculada, así que para renderizar alcanza con pre-generar
las 1419 combinaciones posibles en un atlas de 32x45 tiles e indexarlo.

Puerto directo de EasyRPG Tools, lmu2png/src/chipset.cpp. Los offsets mágicos
vienen de ahí; el comentario original dice que fue más fácil hardcodearlos que
deducir el algoritmo, y no hay razón para no creerle.
"""

from PIL import Image

TILE = 16
HALF = TILE // 2
ATLAS_COLS = 32
ATLAS_ROWS = 45

CHIPSET_WIDTH = 480
CHIPSET_HEIGHT = 256

# Rangos de IDs de tile tal como aparecen en las capas del .lmu
ANIMATED = 0x0BB8   # 3000
TERRAIN = 0x0FA0    # 4000
LOWER = 0x1388      # 5000
UPPER = 0x2710      # 10000


def blit(dst, dx, dy, src, sx, sy, w, h):
    """Copia respetando el color key: los píxeles transparentes no pisan nada.

    Recorta contra los bordes del destino: los sprites de 24x32 se anclan
    fuera de la grilla y se salen del mapa en los bordes.
    """
    left, top = max(0, -dx), max(0, -dy)
    right = w - max(0, dx + w - dst.width)
    bottom = h - max(0, dy + h - dst.height)
    if left >= right or top >= bottom:
        return

    region = src.crop((sx + left, sy + top, sx + right, sy + bottom))
    dst.paste(region, (dx + left, dy + top), region)


class ChipsetAtlas:
    def __init__(self, base):
        # Padeamos por si el chipset viene recortado; los offsets asumen 480x256.
        self.base = Image.new("RGBA", (CHIPSET_WIDTH, CHIPSET_HEIGHT), (0, 0, 0, 0))
        self.base.paste(base.convert("RGBA"), (0, 0))
        self.atlas = Image.new("RGBA", (ATLAS_COLS * TILE, ATLAS_ROWS * TILE), (0, 0, 0, 0))

        tile = 0
        # Agua A/B/C: 3 variantes x 3 frames x 47 combinaciones de borde.
        for kind in "abc":
            border = 1 if kind == "b" else 0
            water = 3 if kind == "c" else 0
            for frame in range(3):
                for comb in range(47):
                    self._water_tile(tile, frame, border, water, comb)
                    tile += 1

        # Profundidad de agua (los bordes de la orilla), 2 niveles x 48.
        for depth in (1, 3):
            for i in range(48):
                self._depth_tile(tile, i, depth)
                tile += 1

        # Tiles animados: 3 grupos de 4 frames, copiados tal cual.
        for j in range(3):
            for i in range(4):
                self._draw_full(tile, 48 + j * TILE, 64 + i * TILE)
                tile += 1

        # Terrenos: 12 autotiles x 50 combinaciones.
        for terrain in range(12):
            for comb in range(50):
                self._terrain_tile(tile, terrain, comb)
                tile += 1

        # Tiles comunes: las 3 páginas de 96 de la mitad derecha, sin combinar.
        for i in range(288):
            self._draw_full(tile,
                            192 + (i % 6) * TILE + (i // 96) * 96,
                            ((i // 6) % TILE) * TILE)
            tile += 1

    # --- helpers de dibujo sobre el atlas ---------------------------------

    def _draw(self, t, sx, sy, w, h, dx=0, dy=0):
        x = (t % ATLAS_COLS) * TILE + dx
        y = (t // ATLAS_COLS) * TILE + dy
        blit(self.atlas, x, y, self.base, sx, sy, w, h)

    def _draw_full(self, t, sx, sy, dx=0, dy=0):
        self._draw(t, sx, sy, TILE, TILE, dx, dy)

    def _draw_quarter(self, t, sx, sy, dx=0, dy=0):
        self._draw(t, sx, sy, HALF, HALF, dx, dy)

    def _draw_wide(self, t, sx, sy, dx=0, dy=0):
        self._draw(t, sx, sy, TILE, HALF, dx, dy)

    def _draw_tall(self, t, sx, sy, dx=0, dy=0):
        self._draw(t, sx, sy, HALF, TILE, dx, dy)

    def _draw_edges(self, t, sx, sy, comb):
        """Las 4 esquinas interiores, una por bit de la combinación."""
        if comb & 1:
            self._draw_quarter(t, sx, sy)                          # arriba izq
        if comb & 2:
            self._draw_quarter(t, sx + HALF, sy, HALF, 0)          # arriba der
        if comb & 4:
            self._draw_quarter(t, sx + HALF, sy + HALF, HALF, HALF)  # abajo der
        if comb & 8:
            self._draw_quarter(t, sx, sy + HALF, 0, HALF)          # abajo izq

    # --- generadores de autotiles ----------------------------------------

    def _water_tile(self, t, frame, border, water, comb):
        sx = frame * 16 + border * 48
        comb &= 0x3F

        # Fondo: el agua lisa del frame correspondiente.
        self._draw_full(t, frame * 16, 64 + water * 16)

        if comb & 0x20:
            if comb > 0x29:
                # Combinaciones con varios bordes a la vez.
                if comb == 0x2A:
                    self._draw_wide(t, sx, 0)
                    self._draw_wide(t, sx, 24, 0, HALF)
                elif comb == 0x2B:
                    self._draw_tall(t, sx, 0)
                    self._draw_tall(t, sx + HALF, 32, HALF, 0)
                elif comb == 0x2C:
                    self._draw_wide(t, sx, 8, 0, HALF)
                    self._draw_wide(t, sx, 16)
                elif comb == 0x2D:
                    self._draw_tall(t, sx + HALF, 0, HALF, 0)
                    self._draw_tall(t, sx, 32)
                elif comb == 0x2E:
                    self._draw_full(t, sx, 0)
            else:
                # Pared + esquinas interiores.
                case = (comb >> 1) & 0x07
                if case == 0:
                    self._draw_full(t, sx, 32 if comb & 1 else 16)
                elif case == 1:
                    self._draw_quarter(t, sx, 0)
                    self._draw_quarter(t, sx, 24, 0, HALF)
                    self._draw_quarter(t, sx + HALF, 32, HALF, 0)
                    if comb & 1:
                        self._draw_quarter(t, sx + HALF, 48 + HALF, HALF, HALF)
                elif case == 2:
                    self._draw_quarter(t, sx + HALF, 0, HALF, 0)
                    self._draw_quarter(t, sx + HALF, 24, HALF, HALF)
                    self._draw_quarter(t, sx, 32)
                    if comb & 1:
                        self._draw_quarter(t, sx, 48 + HALF, 0, HALF)
                elif case == 3:
                    self._draw_quarter(t, sx + HALF, HALF, HALF, HALF)
                    self._draw_quarter(t, sx + HALF, TILE, HALF, 0)
                    self._draw_quarter(t, sx, 40, 0, HALF)
                    if comb & 1:
                        self._draw_quarter(t, sx, 48)
                elif case == 4:
                    self._draw_quarter(t, sx, HALF, 0, HALF)
                    self._draw_quarter(t, sx, TILE)
                    self._draw_quarter(t, sx + HALF, 40, HALF, HALF)
                    if comb & 1:
                        self._draw_quarter(t, sx + HALF, 48, HALF, 0)
        elif comb & 0x10:
            # Una pared, más las esquinas del lado opuesto.
            case = (comb >> 2) & 0x03
            if case == 0:      # pared izquierda
                self._draw_tall(t, sx, 16)
                if comb & 1:
                    self._draw_quarter(t, sx + HALF, 48, HALF, 0)
                if comb & 2:
                    self._draw_quarter(t, sx + HALF, 48 + HALF, HALF, HALF)
            elif case == 1:    # pared superior
                self._draw_wide(t, sx, 32)
                if comb & 1:
                    self._draw_quarter(t, sx + HALF, 48 + HALF, HALF, HALF)
                if comb & 2:
                    self._draw_quarter(t, sx, 48 + HALF, 0, HALF)
            elif case == 2:    # pared derecha
                self._draw_tall(t, sx + HALF, 16, HALF, 0)
                if comb & 1:
                    self._draw_quarter(t, sx, 48 + HALF, 0, HALF)
                if comb & 2:
                    self._draw_quarter(t, sx, 48)
            elif case == 3:    # pared inferior
                self._draw_wide(t, sx, 32 + HALF, 0, HALF)
                if comb & 1:
                    self._draw_quarter(t, sx, 48)
                if comb & 2:
                    self._draw_quarter(t, sx + HALF, 48, HALF, 0)
        else:
            self._draw_edges(t, sx, 48, comb)

    def _depth_tile(self, t, number, depth):
        frame = number // 16
        self._draw_edges(t, frame * 16, 64 + depth * 16, number % 16)

    def _terrain_tile(self, t, terrain, comb):
        terrain += 4
        sx = (terrain % 2) * 48 + (terrain // 8) * 96
        sy = ((terrain // 2) % 4) * 64

        # Fondo: el relleno liso del terreno.
        self._draw_full(t, sx + 16, sy + 32)

        if comb & 0x20:
            if comb > 0x29:
                if comb == 0x2A:
                    self._draw_tall(t, sx, sy + 16)
                    self._draw_tall(t, sx + 40, sy + 16, HALF, 0)
                elif comb == 0x2B:
                    self._draw_wide(t, sx, sy + 16)
                    self._draw_wide(t, sx, sy + 56, 0, HALF)
                elif comb == 0x2C:
                    self._draw_tall(t, sx, sy + 48)
                    self._draw_tall(t, sx + 40, sy + 48, HALF, 0)
                elif comb == 0x2D:
                    self._draw_wide(t, sx + 32, sy + 16)
                    self._draw_wide(t, sx + 32, sy + 56, 0, HALF)
                elif comb == 0x2E:
                    self._draw_quarter(t, sx, sy + 16)
                    self._draw_quarter(t, sx + 40, sy + 16, HALF, 0)
                    self._draw_quarter(t, sx, sy + 56, 0, HALF)
                    self._draw_quarter(t, sx + 40, sy + 56, HALF, HALF)
                elif comb == 0x31:
                    self._draw_full(t, sx, sy)
            else:
                case = (comb >> 1) & 0x07
                if case == 0:
                    if comb & 1:
                        self._draw_wide(t, sx + 16, sy + 16)
                        self._draw_wide(t, sx + 16, sy + 56, 0, HALF)
                    else:
                        self._draw_tall(t, sx, sy + 32)
                        self._draw_tall(t, sx + 40, sy + 32, HALF, 0)
                elif case == 1:
                    self._draw_full(t, sx, sy + 16)
                    if comb & 1:
                        self._draw_quarter(t, sx + 40, sy + HALF, HALF, HALF)
                elif case == 2:
                    self._draw_full(t, sx + 32, sy + 16)
                    if comb & 1:
                        self._draw_quarter(t, sx + 32, sy + HALF, 0, HALF)
                elif case == 3:
                    self._draw_full(t, sx + 32, sy + 48)
                    if comb & 1:
                        self._draw_quarter(t, sx + 32, sy)
                elif case == 4:
                    self._draw_full(t, sx, sy + 48)
                    if comb & 1:
                        self._draw_quarter(t, sx + 40, sy, HALF, 0)
        elif comb & 0x10:
            case = (comb >> 2) & 0x03
            if case == 0:      # pared izquierda
                self._draw_full(t, sx, sy + 32)
                if comb & 1:
                    self._draw_quarter(t, sx + 40, sy, HALF, 0)
                if comb & 2:
                    self._draw_quarter(t, sx + 40, sy + HALF, HALF, HALF)
            elif case == 1:    # pared superior
                self._draw_full(t, sx + 16, sy + 16)
                if comb & 1:
                    self._draw_quarter(t, sx + 40, sy + HALF, HALF, HALF)
                if comb & 2:
                    self._draw_quarter(t, sx + 32, sy + HALF, 0, HALF)
            elif case == 2:    # pared derecha
                self._draw_full(t, sx + 32, sy + 32)
                if comb & 1:
                    self._draw_quarter(t, sx + 32, sy + HALF, 0, HALF)
                if comb & 2:
                    self._draw_quarter(t, sx + 32, sy)
            elif case == 3:    # pared inferior
                self._draw_full(t, sx + 16, sy + 48)
                if comb & 1:
                    self._draw_quarter(t, sx + 32, sy)
                if comb & 2:
                    self._draw_quarter(t, sx + 40, sy, HALF, 0)
        else:
            self._draw_edges(t, sx + 32, sy, comb)

    # --- uso ---------------------------------------------------------------

    def render_tile(self, dst, tile_x, tile_y, tile, paso_agua=0,
                    paso_animado=0):
        """Dibuja el tile con el ID que trae la capa del mapa en (tile_x, tile_y).

        Los dos pasos son las dos animaciones del ChipSet, que corren a
        cadencias distintas y sobre familias de tiles distintas: `paso_agua`
        —0, 1 o 2— elige el dibujo de los autotiles de agua y `paso_animado`
        —0 a 3— el de los "tiles animados". Cuál toca en cada tick lo dicen
        `paso_de_agua` y `paso_animado` de rm2k.py; acá sólo se elige la celda
        del atlas.
        """
        if tile >= UPPER:
            index = tile - UPPER + 0x04FB
        elif tile >= LOWER:
            index = tile - LOWER + 0x046B
        elif tile >= TERRAIN:
            index = tile - TERRAIN + 0x0213
        elif tile >= ANIMATED:
            index = (0x0207 + (((tile - ANIMATED) // 50) << 2)
                     + paso_animado % 4)
        else:
            index = ((tile // 50 // 20) * 141 + tile % 50
                     + (paso_agua % 3) * 47)

        blit(dst, tile_x * TILE, tile_y * TILE, self.atlas,
              (index & 0x1F) * TILE, (index >> 5) * TILE, TILE, TILE)
