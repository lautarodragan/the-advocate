#!/usr/bin/env python3
"""
Genera un ChipSet y un CharSet con el layout REAL de RPG Maker 2000, para poder
probar el pipeline sin tener los assets de A Blurred Line a mano.

ChipSet: 480x256
  x=  0..191  -> autotiles / animados (no los usamos todavia)
  x=192..287  -> lower layer, 6x16 = 96 tiles de 16x16   <-- usamos este bloque
  x=288..479  -> upper layer, 12x16 = 192 tiles de 16x16

CharSet: 288x256
  8 personajes en grilla 4x2, cada uno de 72x128
  cada personaje: 3 columnas (frames) x 4 filas (abajo, izq, der, arriba)
  cada celda: 24x32
  el color del pixel (0,0) del bloque es el transparente
"""
import random
from PIL import Image, ImageDraw

random.seed(1234)

# ---------------------------------------------------------------- ChipSet

def noisy(draw, x, y, base, spots, n=26):
    draw.rectangle([x, y, x + 15, y + 15], fill=base)
    for _ in range(n):
        px, py = x + random.randrange(16), y + random.randrange(16)
        draw.point((px, py), fill=random.choice(spots))


def tile_grass(d, x, y):
    noisy(d, x, y, (72, 132, 56), [(96, 160, 72), (56, 108, 44), (120, 180, 88)])


def tile_path(d, x, y):
    noisy(d, x, y, (168, 144, 104), [(192, 172, 132), (140, 116, 84)])


def tile_water(d, x, y):
    d.rectangle([x, y, x + 15, y + 15], fill=(48, 88, 168))
    for row in (3, 9):
        d.line([x + 2, y + row, x + 8, y + row], fill=(96, 144, 216))
        d.line([x + 9, y + row + 2, x + 13, y + row + 2], fill=(80, 120, 200))


def tile_stone(d, x, y):
    noisy(d, x, y, (128, 128, 136), [(152, 152, 160), (104, 104, 112)], 18)
    d.line([x, y, x + 15, y], fill=(96, 96, 104))
    d.line([x, y, x, y + 15], fill=(96, 96, 104))


def tile_brick(d, x, y):
    d.rectangle([x, y, x + 15, y + 15], fill=(152, 72, 56))
    for row in range(0, 16, 8):
        d.line([x, y + row, x + 15, y + row], fill=(96, 44, 36))
        off = 0 if row == 0 else 8
        d.line([x + off, y + row, x + off, y + row + 7], fill=(96, 44, 36))


def tile_tree(d, x, y):
    tile_grass(d, x, y)
    d.ellipse([x + 1, y, x + 14, y + 12], fill=(40, 104, 48),
              outline=(24, 72, 32))
    d.rectangle([x + 6, y + 11, x + 9, y + 15], fill=(88, 60, 36))


def tile_flower(d, x, y):
    tile_grass(d, x, y)
    for cx, cy, c in ((4, 5, (216, 208, 96)), (11, 10, (208, 96, 128))):
        d.point((x + cx, y + cy), fill=c)
        d.point((x + cx + 1, y + cy), fill=c)
        d.point((x + cx, y + cy + 1), fill=c)




def tile_ice(d, x, y):
    noisy(d, x, y, (168, 208, 232), [(200, 232, 248), (128, 176, 216)], 14)
    d.line([x + 2, y + 4, x + 9, y + 11], fill=(232, 248, 255))


def tile_lava(d, x, y):
    noisy(d, x, y, (200, 64, 24), [(248, 168, 40), (248, 224, 96), (120, 24, 8)], 30)


def tile_wood(d, x, y):
    d.rectangle([x, y, x + 15, y + 15], fill=(136, 96, 56))
    for row in range(0, 16, 5):
        d.line([x, y + row, x + 15, y + row], fill=(96, 64, 36))
    d.line([x + 3, y, x + 3, y + 15], fill=(160, 120, 72))


def tile_sand(d, x, y):
    noisy(d, x, y, (224, 208, 152), [(240, 232, 192), (192, 168, 112)], 20)


def tile_cave(d, x, y):
    noisy(d, x, y, (56, 48, 64), [(88, 80, 104), (32, 24, 40)], 16)


def tile_roof(d, x, y):
    d.rectangle([x, y, x + 15, y + 15], fill=(176, 56, 72))
    for row in (0, 8):
        d.line([x, y + row, x + 15, y + row], fill=(112, 32, 44))
    d.line([x + 7, y, x + 7, y + 15], fill=(216, 112, 120))

LOWER = [tile_grass, tile_path, tile_water, tile_stone,
         tile_brick, tile_tree, tile_flower,
         tile_ice, tile_lava, tile_wood, tile_sand, tile_cave, tile_roof]


def make_chipset(path):
    img = Image.new("RGB", (480, 256), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, fn in enumerate(LOWER):
        col, row = i % 6, i // 6
        fn(d, 192 + col * 16, row * 16)
    # el resto del bloque lower en negro plano
    img.convert("P", palette=Image.ADAPTIVE, colors=256).save(path)
    print("chipset ->", path)


# ---------------------------------------------------------------- CharSet

SKIN = (232, 192, 152)
HAIR = (72, 48, 32)
SHIRT = (56, 96, 176)
PANTS = (48, 48, 64)
SHOE = (32, 32, 40)
KEY = (255, 0, 255)          # color transparente


def draw_char(d, ox, oy, direction, frame):
    """24x32, personaje bottom-aligned estilo RM2k."""
    cx = ox + 12
    top = oy + 4
    # cabeza
    d.ellipse([cx - 6, top, cx + 5, top + 11], fill=SKIN)
    if direction == 3:                       # de espaldas: todo pelo
        d.ellipse([cx - 6, top, cx + 5, top + 11], fill=HAIR)
    else:
        d.rectangle([cx - 6, top, cx + 5, top + 3], fill=HAIR)
        if direction == 0:                   # de frente: ojos
            d.point((cx - 3, top + 6), fill=(24, 24, 32))
            d.point((cx + 2, top + 6), fill=(24, 24, 32))
        elif direction == 1:                 # izquierda
            d.point((cx - 4, top + 6), fill=(24, 24, 32))
        else:                                # derecha
            d.point((cx + 3, top + 6), fill=(24, 24, 32))
    # torso
    d.rectangle([cx - 5, top + 12, cx + 4, top + 20], fill=SHIRT)
    # piernas: frame 0 y 2 alternan, frame 1 es el idle
    swing = (-2, 0, 2)[frame]
    d.rectangle([cx - 5, top + 21, cx - 1, top + 26 + swing], fill=PANTS)
    d.rectangle([cx, top + 21, cx + 4, top + 26 - swing], fill=PANTS)
    d.rectangle([cx - 5, top + 26 + swing, cx - 1, top + 27 + swing], fill=SHOE)
    d.rectangle([cx, top + 26 - swing, cx + 4, top + 27 - swing], fill=SHOE)


def make_charset(path):
    img = Image.new("RGB", (288, 256), KEY)
    d = ImageDraw.Draw(img)
    for direction in range(4):
        for frame in range(3):
            draw_char(d, frame * 24, direction * 32, direction, frame)
    img.convert("P", palette=Image.ADAPTIVE, colors=256).save(path)
    print("charset ->", path)


if __name__ == "__main__":
    make_chipset("assets/ChipSet_placeholder.png")
    make_charset("assets/CharSet_placeholder.png")
