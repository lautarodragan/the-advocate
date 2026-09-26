#!/usr/bin/env python3
"""El cartel de un `ShowPicture` en la pantalla de la consola.

Vive aparte de `snes_convert.py` por la misma razón que `titulo.py`: no es un
mapa. Es una imagen suelta que hay que meter en la pantalla, y lo único que
hay que decidir es **exactamente dónde cae y de qué color es cada pixel**.

Tres decisiones, y las tres se pagan:

**Va en objetos de OAM, no en una capa.** En modo 3 las dos capas son del mapa,
y la alternativa —prestarle una al cartel mientras dura— obliga a recargar el
mapa al borrarlo: 30 KB de DMA y dos cuadros negros, que es lo que cuesta
`volver_al_mapa`. Con objetos el cartel se pone y se saca sin tocar nada de lo
que hay debajo, que además es lo que hace RM2k: la imagen se compone encima.
El precio son **quince colores**, los de una paleta de sprite, contra los 226
del PNG; y el presupuesto de objetos por línea, que en las 29 líneas del cartel
baja de 34 tiles a 10.

**La pantalla de RM2k mide 320x240 y la de la consola 256x224**, así que el
cartel se escala como la imagen del título: las dos esquinas de su rectángulo
pasan por la misma cuenta y la imagen se lleva al tamaño que queda. Es el mismo
20% más angosto que ya tiene la pantalla de título, y por la misma razón: el
aspecto del original no es el de la consola.

**La posición de RM2k es el centro de la imagen**, no su esquina: `Sprite_Picture`
hace `SetOx(width / 2)`. El cartel del "One year previously" está centrado en
(100, 175) de 320x240 y mide 233x31, o sea que **arranca en -16 y se le come el
borde izquierdo**. Eso no es un error nuestro: es lo que el juego muestra.

Lo que **no** se hace, y por lo tanto tampoco se acepta —ver `Imagenes.cabe` en
eventos.py—: mover la imagen de lugar, escalarla, hacerla translúcida
(`top_trans`), el color transparente, la saturación y los efectos de rotación y
onda. De los tres `Picture` de la página del "1 year earlier" ninguno pide nada
de eso: lo único que cambia entre uno y otro es el **tono**, que es lo que
dibuja el fundido.
"""

import collections

# La pantalla de RM2k y la de la consola.
ANCHO_RM, ALTO_RM = 320, 240
ANCHO, ALTO = 256, 224

# El objeto grande de este port, que es el que `OBSEL_VALUE` deja fijo en 32x32.
OBJ = 32
# Los tiles de 8x8 que mide de lado, y cuántos hay en una fila de la grilla de
# nombres de OAM.
OBJ_LADO = OBJ // 8
GRILLA = 16
# Los quince de una paleta de sprite: el índice 0 no se dibuja.
COLORES = 15
# Cuántos objetos de ancho se aceptan. Ocho son 256 pixeles, o sea la pantalla
# entera, y 128 tiles de sprite; más que eso no es un cartel.
OBJETOS_MAX = 8
NEGRO = (0, 0, 0)


def escalar_x(v):
    """Una coordenada horizontal de la pantalla de RM2k, en la de la consola.

    División entera hacia abajo **también con negativos**, que es lo que hace
    `//` en Python: el cartel arranca en -16 y las dos puntas tienen que sacar
    el mismo -13.
    """
    return v * ANCHO // ANCHO_RM


def escalar_y(v):
    return v * ALTO // ALTO_RM


def caja(ancho, alto, cx, cy):
    """Dónde cae en la pantalla de la consola una imagen de `ancho` x `alto`
    centrada en (cx, cy) de las de RM2k: (x, y, ancho, alto).

    Las dos esquinas pasan por la misma cuenta y el tamaño sale de restarlas.
    Escalar el tamaño por su lado daría 28 de alto donde las esquinas dan 29, y
    un pixel de diferencia entre las dos puntas es una comparación que falla.
    """
    x0, y0 = cx - ancho // 2, cy - alto // 2
    ex0, ey0 = escalar_x(x0), escalar_y(y0)
    return ex0, ey0, escalar_x(x0 + ancho) - ex0, escalar_y(y0 + alto) - ey0


def _quince(imagen, ancho, alto):
    """La imagen escalada y con los colores a 15 bits, fila por fila.

    LANCZOS como `titulo._quince`, y por lo mismo: es el que menos ensucia los
    bordes del texto.
    """
    from PIL import Image
    chica = imagen.convert("RGB").resize((ancho, alto), Image.LANCZOS)
    datos = [(r >> 3, g >> 3, b >> 3) for r, g, b in chica.get_flattened_data()]
    return [datos[y * ancho:(y + 1) * ancho] for y in range(alto)]


def convertir(imagen, cx, cy):
    """El cartel listo para las dos puntas.

    Devuelve un diccionario con dónde cae —`x`, `y`, `ancho`, `alto`—, cuántos
    objetos de 32x32 se lleva, su paleta de quince colores de 15 bits y la
    imagen como índices de esa paleta **corridos uno**, que es como los numera
    una paleta de sprite: el 0 es el transparente y no se dibuja.

    Los colores salen de `titulo.reducir`, el mismo de la pantalla de título, y
    por la misma razón: no promedia, así que no inventa colores que haya que
    volver a cuantizar, y no depende de la versión de PIL. De 226 colores a
    quince el degradé del resplandor se escalona; se ve y está declarado.
    """
    from port import titulo
    x, y, ancho, alto = caja(imagen.width, imagen.height, cx, cy)
    filas = _quince(imagen, ancho, alto)
    pixeles = [c for fila in filas for c in fila]
    paleta, mapa = titulo.reducir(pixeles, COLORES)
    donde = {color: i + 1 for i, color in enumerate(paleta)}
    indices = [[donde[mapa[c]] for c in fila] for fila in filas]
    return {
        "x": x, "y": y, "ancho": ancho, "alto": alto,
        "objetos": -(-ancho // OBJ),
        "paleta": paleta,
        "indices": indices,
    }


def cabe(info):
    """Si el cartel entra en el modelo: un objeto de alto y hasta `OBJETOS_MAX`
    de ancho. Lo pregunta `eventos.Imagenes` al elegir el cartel."""
    return 0 < info["alto"] <= OBJ and 0 < info["objetos"] <= OBJETOS_MAX


def celdas(info):
    """El cartel cortado en tiles de 8x8, en el orden en que los numera OAM.

    Un objeto de 32x32 lee cuatro tiles de cuatro filas seguidas de la grilla de
    nombres, que es de dieciséis de ancho: o sea que en una **fila de bloques**
    —64 tiles— entran cuatro objetos y no más. El objeto `o` arranca entonces en
    `(o // 4) * 64 + (o % 4) * 4`, y adentro de él el tile (tx, ty) está `ty`
    filas de la grilla más adelante.

    Devuelve {número de tile relativo a la base: celda de 8x8}. Lo que queda
    afuera de la imagen —los pixeles de relleno hasta los 32 del objeto— es el
    índice 0, o sea transparente: ahí se ve lo que haya debajo, que es lo que
    corresponde.
    """
    salida = {}
    indices = info["indices"]
    for o in range(info["objetos"]):
        arranca = (o // 4) * (4 * GRILLA) + (o % 4) * OBJ_LADO
        for ty in range(OBJ_LADO):
            for tx in range(OBJ_LADO):
                celda = []
                for py in range(8):
                    fila = []
                    for px in range(8):
                        cy = ty * 8 + py
                        cx = o * OBJ + tx * 8 + px
                        fila.append(indices[cy][cx]
                                    if cy < info["alto"] and cx < info["ancho"]
                                    else 0)
                    celda.append(tuple(fila))
                salida[arranca + ty * GRILLA + tx] = tuple(celda)
    return salida


def tiles_reservados(info):
    """Cuántos tiles de 8x8 del banco de sprites se lleva el cartel.

    Filas de bloques enteras, no los 96 que usa: la aritmética de arriba las
    necesita enteras, y `digitos_del_timer` ya redondea a lo mismo y por lo
    mismo. Con seis objetos son dos filas, 128 tiles, de los cuales 96 se usan.
    """
    return -(-info["objetos"] // 4) * (4 * GRILLA)


def render(info, tono):
    """El cartel como se ve en la pantalla, con su tono aplicado: una imagen
    RGBA de `ancho` x `alto` para pegar en (x, y).

    El tono es el de RM2k —(r, g, b, sat), 100 neutro— y pasa por
    `eventos.tenir`, que es la misma cuenta del tinte de pantalla: allá y acá es
    `ToneBlit`. La consola no tiñe pixeles sino las quince entradas de CGRAM del
    cartel, así que teñir la paleta y pintar da exactamente lo mismo.
    """
    from PIL import Image
    from port import eventos
    paleta = [eventos.tenir(c[0] | (c[1] << 5) | (c[2] << 10), tono)
              for c in info["paleta"]]
    colores = [(0, 0, 0, 0)] + [(((p & 0x1F) << 3), (((p >> 5) & 0x1F) << 3),
                                 (((p >> 10) & 0x1F) << 3), 255)
                                for p in paleta]
    salida = Image.new("RGBA", (info["ancho"], info["alto"]))
    salida.putdata([colores[i] for fila in info["indices"] for i in fila])
    return salida


def informe(info):
    """Los números que justifican el reparto, para que la receta los imprima."""
    return {
        "donde": (info["x"], info["y"]),
        "tamano": (info["ancho"], info["alto"]),
        "objetos": info["objetos"],
        "tiles": tiles_reservados(info),
        "colores": len(info["paleta"]),
    }
