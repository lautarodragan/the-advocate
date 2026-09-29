"""Expansion of an RPG Maker 2000 ChipSet into an atlas of already resolved tiles.

An RM2k ChipSet is a 480x256 image whose left half is not tiles ready to
draw but "autotiles": edge blocks the engine combines at run time according
to the neighbors. The editor stores in the map the ID of the already
computed combination, so to render it is enough to pre-generate the 1419
possible combinations in a 32x45-tile atlas and index it.

Direct port of EasyRPG Tools, lmu2png/src/chipset.cpp. The magic offsets
come from there; the original comment says it was easier to hardcode them
than to deduce the algorithm, and there is no reason not to believe it.
"""

from PIL import Image

from rpgmaker.rm2k import TILE, common_box, terrain_box

HALF = TILE // 2
ATLAS_COLS = 32
ATLAS_ROWS = 45

CHIPSET_WIDTH = 480
CHIPSET_HEIGHT = 256

# Tile ID ranges as they appear in the .lmu layers
ANIMATED = 0x0BB8   # 3000
TERRAIN = 0x0FA0    # 4000
LOWER = 0x1388      # 5000
UPPER = 0x2710      # 10000


def blit(dst, dx, dy, src, sx, sy, w, h):
    """Copies honoring the color key: transparent pixels overwrite nothing.

    Clips against the destination's edges: the 24x32 sprites are anchored
    off the grid and stick out of the map at the edges.
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
        # Pad in case the chipset comes cropped; the offsets assume 480x256.
        self.base = Image.new("RGBA", (CHIPSET_WIDTH, CHIPSET_HEIGHT), (0, 0, 0, 0))
        self.base.paste(base.convert("RGBA"), (0, 0))
        self.atlas = Image.new("RGBA", (ATLAS_COLS * TILE, ATLAS_ROWS * TILE), (0, 0, 0, 0))

        tile = 0
        # Water A/B/C: 3 variants x 3 frames x 47 edge combinations.
        for kind in "abc":
            border = 1 if kind == "b" else 0
            water = 3 if kind == "c" else 0
            for frame in range(3):
                for comb in range(47):
                    self._water_tile(tile, frame, border, water, comb)
                    tile += 1

        # Water depth (the shore edges), 2 levels x 48.
        for depth in (1, 3):
            for i in range(48):
                self._depth_tile(tile, i, depth)
                tile += 1

        # Animated tiles: 3 groups of 4 frames, copied as is.
        for j in range(3):
            for i in range(4):
                self._draw_full(tile, 48 + j * TILE, 64 + i * TILE)
                tile += 1

        # Terrains: 12 autotiles x 50 combinations.
        for terrain in range(12):
            for comb in range(50):
                self._terrain_tile(tile, terrain, comb)
                tile += 1

        # Common tiles: the 3 pages of 96 in the right half, uncombined.
        for i in range(288):
            x, y, _, _ = common_box(i)
            self._draw_full(tile, x, y)
            tile += 1

    # --- drawing helpers on the atlas ------------------------------------

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
        """The 4 inner corners, one per bit of the combination."""
        if comb & 1:
            self._draw_quarter(t, sx, sy)                          # top left
        if comb & 2:
            self._draw_quarter(t, sx + HALF, sy, HALF, 0)          # top right
        if comb & 4:
            self._draw_quarter(t, sx + HALF, sy + HALF, HALF, HALF)  # bottom right
        if comb & 8:
            self._draw_quarter(t, sx, sy + HALF, 0, HALF)          # bottom left

    # --- autotile generators ---------------------------------------------

    def _water_tile(self, t, frame, border, water, comb):
        sx = frame * 16 + border * 48
        comb &= 0x3F

        # Background: the plain water of the corresponding frame.
        self._draw_full(t, frame * 16, 64 + water * 16)

        if comb & 0x20:
            if comb > 0x29:
                # Combinations with several edges at once.
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
                # Wall + inner corners.
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
            # One wall, plus the corners on the opposite side.
            case = (comb >> 2) & 0x03
            if case == 0:      # left wall
                self._draw_tall(t, sx, 16)
                if comb & 1:
                    self._draw_quarter(t, sx + HALF, 48, HALF, 0)
                if comb & 2:
                    self._draw_quarter(t, sx + HALF, 48 + HALF, HALF, HALF)
            elif case == 1:    # top wall
                self._draw_wide(t, sx, 32)
                if comb & 1:
                    self._draw_quarter(t, sx + HALF, 48 + HALF, HALF, HALF)
                if comb & 2:
                    self._draw_quarter(t, sx, 48 + HALF, 0, HALF)
            elif case == 2:    # right wall
                self._draw_tall(t, sx + HALF, 16, HALF, 0)
                if comb & 1:
                    self._draw_quarter(t, sx, 48 + HALF, 0, HALF)
                if comb & 2:
                    self._draw_quarter(t, sx, 48)
            elif case == 3:    # bottom wall
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
        sx, sy, _, _ = terrain_box(terrain)

        # Background: the terrain's plain fill.
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
            if case == 0:      # left wall
                self._draw_full(t, sx, sy + 32)
                if comb & 1:
                    self._draw_quarter(t, sx + 40, sy, HALF, 0)
                if comb & 2:
                    self._draw_quarter(t, sx + 40, sy + HALF, HALF, HALF)
            elif case == 1:    # top wall
                self._draw_full(t, sx + 16, sy + 16)
                if comb & 1:
                    self._draw_quarter(t, sx + 40, sy + HALF, HALF, HALF)
                if comb & 2:
                    self._draw_quarter(t, sx + 32, sy + HALF, 0, HALF)
            elif case == 2:    # right wall
                self._draw_full(t, sx + 32, sy + 32)
                if comb & 1:
                    self._draw_quarter(t, sx + 32, sy + HALF, 0, HALF)
                if comb & 2:
                    self._draw_quarter(t, sx + 32, sy)
            elif case == 3:    # bottom wall
                self._draw_full(t, sx + 16, sy + 48)
                if comb & 1:
                    self._draw_quarter(t, sx + 32, sy)
                if comb & 2:
                    self._draw_quarter(t, sx + 40, sy, HALF, 0)
        else:
            self._draw_edges(t, sx + 32, sy, comb)

    # --- usage -------------------------------------------------------------

    def render_tile(self, dst, tile_x, tile_y, tile, paso_agua=0,
                    paso_animado=0):
        """Draws the tile with the ID the map layer carries at (tile_x, tile_y).

        The two steps are the ChipSet's two animations, which run at
        different cadences and over different tile families: `paso_agua`
        —0, 1 or 2— picks the drawing of the water autotiles and
        `paso_animado` —0 to 3— that of the "animated tiles". Which one is
        due at each tick is said by rm2k.py's `animated_step` and, for the
        water, `WATER_CYCLE` with `WATER_FRAMES_SLOW`; here only the atlas
        cell is picked.
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
