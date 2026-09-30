#!/usr/bin/env python3
"""Corre `menu-modo-5.sfc` en los emuladores y compara cada pantalla con su
maqueta, pixel por pixel a 15 bits.

    verificar.py <menu-modo-5.sfc> [<capturas>]

Con la marca escondida (B) cada pantalla tiene que ser la maqueta entera, y
con la marca, la maqueta salvo el cuadrado del número. Lo que capture lo
deja en `<capturas>`, si se da: `<core>-<n>.png` con la marca y
`<core>-<n>-sin-marca.png` sin ella, a la resolución que da el core.

Sale con 1 si alguna difiere. Un core que no está instalado se saltea con
un aviso; si no hay ninguno, es un error.
"""
import os
import sys

from PIL import Image

from emulator import retro

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from armar import PANTALLAS, MARCA_X, MARCA_Y  # noqa: E402

CORES = ["snes9x", "bsnes", "mesen-s"]


def a15(imagen):
    datos = imagen.convert("RGB").tobytes()
    return [(datos[i] >> 3, datos[i + 1] >> 3, datos[i + 2] >> 3)
            for i in range(0, len(datos), 3)]


def pantalla(consola):
    """El cuadro como lo pinta la consola: 224 líneas, 512 o 256 de ancho.

    mesen-s entrega 478 líneas, las 239 de su ventana dobladas, aunque no
    haya entrelazado: se toma una de cada dos y se recorta al centro, que
    es lo que hace `retro.image` con las 239 de siempre."""
    datos, ancho, alto, _ = consola.frame
    if alto > 2 * retro.HEIGHT:
        guardado = retro.HEIGHT
        retro.HEIGHT = alto
        try:
            completa = consola.image()
        finally:
            retro.HEIGHT = guardado
        completa = completa.resize((ancho, alto // 2), Image.NEAREST)
        arriba = (alto // 2 - retro.HEIGHT) // 2
        return completa.crop((0, arriba, ancho, arriba + retro.HEIGHT))
    return consola.image()


def a_la_maqueta(captura, ancho):
    """La captura al ancho de la maqueta. Un core puede entregar una
    pantalla de 256 a 512, con cada pixel dos veces: se toma uno de cada
    dos, y si el par no es igual, se deja como está y la comparación lo
    cobra."""
    if captura.width == ancho:
        return captura
    if captura.width == 2 * ancho:
        pix = captura.load()
        if all(pix[x, y] == pix[x + 1, y] for y in range(captura.height)
               for x in range(0, captura.width, 2)):
            return captura.resize((ancho, captura.height), Image.NEAREST)
    return captura


def diferencias(captura, maqueta, salvo=None):
    if captura.size != maqueta.size:
        return "mide %dx%d y la maqueta %dx%d" % (captura.size + maqueta.size)
    ancho = maqueta.width
    escala = ancho // 256
    malos = 0
    for i, (a, b) in enumerate(zip(a15(captura), a15(maqueta))):
        x, y = i % ancho, i // ancho
        if salvo and salvo[0] * escala <= x < (salvo[0] + 8) * escala \
                and salvo[1] <= y < salvo[1] + 8:
            continue
        malos += a != b
    return malos


def correr(core, rom, capturas):
    ruta = "/usr/lib/libretro/%s_libretro.so" % core
    if not os.path.exists(ruta):
        print("%s: no está instalado, se saltea" % core)
        return None
    consola = retro.Console(rom, core=ruta)
    consola.run(30)
    fallas = 0

    def apretar(boton):
        consola.hold(boton)
        consola.run(2)
        consola.hold()
        consola.run(20)

    for n, (archivo, modo, marca) in enumerate(PANTALLAS):
        maqueta = Image.open(os.path.join(AQUI, "maqueta", archivo)).convert("RGB")
        con_marca = a_la_maqueta(pantalla(consola), maqueta.width)
        apretar("b")
        sin_marca = a_la_maqueta(pantalla(consola), maqueta.width)
        apretar("b")
        if capturas:
            con_marca.save(os.path.join(capturas, "%s-%d.png" % (core, n + 1)))
            sin_marca.save(os.path.join(capturas, "%s-%d-sin-marca.png" % (core, n + 1)))
        entera = diferencias(sin_marca, maqueta)
        afuera = diferencias(con_marca, maqueta, (MARCA_X, MARCA_Y))
        marca_se_ve = diferencias(con_marca, sin_marca) != 0
        bien = entera == 0 and afuera == 0 and marca_se_ve
        fallas += not bien
        print("%s, pantalla %d (%s, modo %d): %s" % (
            core, n + 1, archivo, modo,
            "igual a la maqueta" if bien else
            "sin marca: %s pixeles distintos; con marca, fuera de ella: %s; "
            "la marca %s" % (entera, afuera, "se ve" if marca_se_ve else "NO se ve")))
        apretar("right")
    # Derecha dio la vuelta: tiene que estar otra vez en la primera, y
    # izquierda tiene que llevar a la última.
    primera = Image.open(os.path.join(AQUI, "maqueta", PANTALLAS[0][0])).convert("RGB")
    if diferencias(pantalla(consola), primera, (MARCA_X, MARCA_Y)) != 0:
        print("%s: derecha desde la última no vuelve a la primera" % core)
        fallas += 1
    apretar("left")
    ultima = Image.open(os.path.join(AQUI, "maqueta", PANTALLAS[-1][0])).convert("RGB")
    if diferencias(a_la_maqueta(pantalla(consola), ultima.width), ultima,
                   (MARCA_X, MARCA_Y)) != 0:
        print("%s: izquierda desde la primera no va a la última" % core)
        fallas += 1
    return fallas


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    rom = sys.argv[1]
    capturas = sys.argv[2] if len(sys.argv) == 3 else None
    if capturas:
        os.makedirs(capturas, exist_ok=True)
    resultados = [correr(core, rom, capturas) for core in CORES]
    corridos = [r for r in resultados if r is not None]
    if not corridos:
        sys.exit("no hay ningún core instalado")
    if sum(corridos):
        sys.exit(1)


if __name__ == "__main__":
    main()
