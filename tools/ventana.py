"""La ventana de mensaje de RM2k, armada desde el System del juego.

Las reglas salen de `Window::RefreshBackground` y `Window::RefreshFrame` de
easyrpg-player, y el texto de `Font::Render`. No se inventa nada acá: si algo
no coincide con el original, se arregla mirando esas funciones.

El System es una imagen de 160x80 con todo adentro:

    (0,0,32,32)     el fondo, que se **estira** al tamaño de la ventana
    (32,0,8,8)      la esquina de arriba a la izquierda del marco
    (40,0,16,8)     el borde de arriba, que se repite hasta el ancho
    (56,0,8,8)      la esquina de arriba a la derecha
    (32,8,8,16)     el borde izquierdo, que se repite hasta el alto
    (56,8,8,16)     el borde derecho
    (56,0,8,8)      la esquina de arriba a la derecha
    (...,24,...)    lo mismo de abajo
    (16,32,16,16)   el color de la sombra del texto
    (c%10*16, c//10*16+48, 16, 16)   el color de texto número c

Los colores de texto y de sombra son **bloques de 16x16**, no colores sueltos:
cada pixel del glifo toma el color de su misma posición dentro del bloque, así
que una letra sale con un degradé vertical. Es lo que hace `MaskedBlit`.
"""
import os

from PIL import Image

# El tamaño y el lugar de la ventana de mensaje. En RM2k la pantalla es de
# 320x240 y la ventana ocupa 320x80 abajo; acá la pantalla son 256x224, así que
# la ventana es de 256x80 y el texto pierde 64 px de ancho. Lo que no entra se
# trunca: es la decisión de la fase 1, escrita en ESTADO.md.
ANCHO, ALTO = 256, 80
BORDE = 8                       # `border_x` y `border_y` de Window
ALTO_LINEA = 16                 # `contents_y += 16` de Window_Message
TEXTO_Y = 2                     # el `contents_y = 2` de la primera línea
LINEAS = 4


def skin(game_dir, nombre):
    """El System del juego, en RGB."""
    for base in (os.path.join(game_dir, "System"), game_dir):
        ruta = os.path.join(base, nombre + ".png")
        if os.path.exists(ruta):
            return Image.open(ruta).convert("RGB")
    raise FileNotFoundError("no está el System %r en %s" % (nombre, game_dir))


def color_de_texto(sys_img, numero):
    """El bloque de 16x16 del color de texto número `numero`."""
    x, y = numero % 10 * 16, numero // 10 * 16 + 48
    return sys_img.crop((x, y, x + 16, y + 16))


def color_de_sombra(sys_img):
    return sys_img.crop((16, 32, 32, 48))


def _repetido(origen, ancho, alto):
    """`TiledBlit`: repetir un recorte hasta llenar ancho x alto."""
    salida = Image.new("RGB", (ancho, alto))
    for y in range(0, alto, origen.height):
        for x in range(0, ancho, origen.width):
            salida.paste(origen, (x, y))
    return salida.crop((0, 0, ancho, alto))


def ventana(sys_img, ancho=ANCHO, alto=ALTO):
    """La ventana vacía: el fondo estirado y el marco encima."""
    # El fondo se estira, no se repite: es el `stretch` que RM2k trae prendido.
    fondo = sys_img.crop((0, 0, 32, 32)).resize((ancho, alto), Image.NEAREST)
    marco = fondo.copy()
    # Los bordes de arriba y de abajo, repetidos entre las esquinas.
    marco.paste(_repetido(sys_img.crop((40, 0, 56, 8)), ancho - 16, 8), (8, 0))
    marco.paste(_repetido(sys_img.crop((40, 24, 56, 32)), ancho - 16, 8),
                (8, alto - 8))
    # Los de los costados.
    marco.paste(_repetido(sys_img.crop((32, 8, 40, 24)), 8, alto - 16), (0, 8))
    marco.paste(_repetido(sys_img.crop((56, 8, 64, 24)), 8, alto - 16),
                (ancho - 8, 8))
    # Y las cuatro esquinas, que van últimas porque pisan a los bordes.
    marco.paste(sys_img.crop((32, 0, 40, 8)), (0, 0))
    marco.paste(sys_img.crop((56, 0, 64, 8)), (ancho - 8, 0))
    marco.paste(sys_img.crop((32, 24, 40, 32)), (0, alto - 8))
    marco.paste(sys_img.crop((56, 24, 64, 32)), (ancho - 8, alto - 8))
    return marco


# De dónde sale el color de cada pixel del glifo, según `Font::Render` de
# easyrpg-player. No es un color plano: el glifo se usa como máscara sobre el
# bloque de 16x16 del System, así que la letra sale con degradé.
#
#   texto   (color%10*16 + 2, color//10*16 + 48 + 16 - 12)
#   sombra  (16, 32), y dibujada primero, corrida un pixel en x y en y
#
# El `16 - 12` es lo que apoya el glifo de 12 filas contra el pie del bloque de
# 16. Ninguno de estos números se adivina: salen de font.cpp.
TEXTO_OFS = (2, 4)
SOMBRA_ORIGEN = (16, 32)


def dibujar_linea(destino, sys_img, x, y, texto, color=0):
    """Una línea de texto sobre `destino`, con su sombra, como RM2k.

    Devuelve en qué x quedó. Lo que se pase del ancho de `destino` se recorta
    solo: en la fase 1 las líneas que no entran se truncan, que es la decisión
    escrita en ESTADO.md.
    """
    import fuente
    bloque = color_de_texto(sys_img, color)
    sombra = color_de_sombra(sys_img)
    ox, oy = TEXTO_OFS
    for ch in texto:
        for px, py in fuente.pixeles(ch):
            # La sombra va primero y corrida uno, así el texto la pisa donde se
            # superponen. Es el orden de easyrpg y se nota en las diagonales.
            for dx, dy, fuente_color, fx, fy in (
                    (1, 1, sombra, px, py), (0, 0, bloque, ox + px, oy + py)):
                dx, dy = x + px + dx, y + py + dy
                if 0 <= dx < destino.width and 0 <= dy < destino.height:
                    destino.putpixel((dx, dy), fuente_color.getpixel((fx, fy)))
        x += fuente.ANCHO
    return x


def pagina(sys_img, lineas, ancho=ANCHO, alto=ALTO):
    """La ventana con hasta cuatro líneas de texto adentro."""
    vista = ventana(sys_img, ancho, alto)
    for n, texto in enumerate(lineas[:LINEAS]):
        dibujar_linea(vista, sys_img, BORDE, BORDE + TEXTO_Y + n * ALTO_LINEA,
                      texto)
    return vista
