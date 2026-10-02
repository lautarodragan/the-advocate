#!/usr/bin/env python3
"""Corre `zoom-modo-7.sfc` en los emuladores y mira, foto por foto y
variante por variante, que el zoom sea el que mide el original.

    verificar.py <zoom-modo-7.sfc> [<capturas>]

Para cada una:

* **la foto quieta** tiene que ser, pixel por pixel a 15 bits, la que dejó
  `armar.py` en `esperada-<foto>-<cómo>.png`: la textura del modo 7 a escala
  1, o la foto del modo 1 en las híbridas. Eso prueba también que la textura
  llegó entera a la VRAM y que la matriz y el centro están bien;
* **el destello**: el primer cuadro de la foto es blanco;
* **la curva**: en una decena de cuadros del zoom, el rectángulo de lo que
  no es negro mide 256·(1 − t/120) por 224·(1 − t/120), con un pixel de
  tolerancia, y está centrado; en el cuadro 120 ya no hay nada;
* **las híbridas** terminan de subir la textura antes de que empiece el
  zoom, y ningún vblank se pasa de la línea 261.

Y los cuadros que mira tienen que ser iguales en los tres cores: bsnes
arranca la memoria con basura, así que una diferencia es algo sin
inicializar. Con un directorio, deja ahí las capturas.

Sale con 1 si algo falla. Un core que no está instalado se saltea.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
# Corre como script, como `menu-modo-5/verificar.py`: el emulador es un
# paquete de las herramientas y la receta no puede nombrarlas.
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(RAIZ, os.pardir, "tools"))
from emulator import retro  # noqa: E402

CORES = ["snes9x", "bsnes", "mesen-s"]

# La página cero de `zoom.s`, en su orden.
CUADRO, VARIANTE, SUBIDA_FIN, LINEA_MAX = 0, 2, 4, 6
FOTO = 16

# Los dos números de la esquina: se dejan fuera de las comparaciones.
MARCA = (8, 206, 26, 214)               # x0, y0, x1, y1

# Los cuadros del zoom que se miden.
MEDIDOS = [1, 2, 15, 30, 45, 60, 75, 90, 105, 115, 119, 120]


def palabra(consola, direccion):
    r = consola.ram(direccion, 2)
    return r[0] | (r[1] << 8)


def a15(imagen):
    return np.asarray(imagen.convert("RGB")).astype(np.int64) >> 3


def sin_marca(a):
    a = a.copy()
    x0, y0, x1, y1 = MARCA
    a[y0:y1, x0:x1] = 0
    return a


class Corrida:
    def __init__(self, core, rom):
        self.consola = retro.Console(rom, core="/usr/lib/libretro/%s_libretro.so" % core)
        self.consola.run(5)

    def apretar(self, boton):
        self.consola.hold(boton)
        self.consola.run(1)
        self.consola.hold()
        self.consola.run(1)

    def ir_a(self, foto, variante):
        while palabra(self.consola, FOTO) != foto:
            self.apretar("up")
        while palabra(self.consola, VARIANTE) != variante:
            self.apretar("right")
        # Para empezar de cero: izquierda y derecha la recargan.
        self.apretar("left")
        self.apretar("right")

    def ver(self, cuadro):
        """La pantalla del cuadro `cuadro` de la vuelta. La RAM dice el
        cuadro que se va a mostrar en el próximo: se corre hasta que diga
        el siguiente."""
        for _ in range(1000):
            self.consola.run(1)
            if palabra(self.consola, CUADRO) == cuadro + 1:
                return self.consola.image()
        raise RuntimeError("no llegó al cuadro %d" % cuadro)


def caja(a):
    """El rectángulo de lo que no es negro, sin la marca: x0, y0, x1, y1."""
    hay = sin_marca(a).max(2) > 0
    ys, xs = np.nonzero(hay)
    if not len(xs):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def psnr(a, b):
    """Cuánto se parecen dos imágenes de 8 bits, en dB."""
    e = ((a.astype(float) - b.astype(float)) ** 2).mean()
    return float("inf") if e == 0 else 10 * np.log10(255 ** 2 / e)


def correr(core, rom, resumen, capturas, vistos):
    if not os.path.exists("/usr/lib/libretro/%s_libretro.so" % core):
        print("%s: no está instalado, se saltea" % core)
        return None
    linea = resumen["linea"]
    foto_en = linea["negro_antes"]
    zoom_en = foto_en + linea["quieta"] - 1         # el cuadro de t = 0 que sigue a la quieta
    directorio = os.path.dirname(rom)
    corrida = Corrida(core, rom)
    fallas = 0
    for f, foto in enumerate(resumen["fotos"]):
        for v, variante in enumerate(resumen["variantes"]):
            textura = foto["texturas"][variante["textura"]]
            hibrida = variante["quieta"] == 1
            corrida.ir_a(f, v)
            nombre = "%s %d.%d (%s, %s)" % (core, f + 1, v + 1, foto["nombre"], variante["nombre"])
            problemas = []

            destello = a15(corrida.ver(foto_en))
            if sin_marca(destello).mean() < 30:
                problemas.append("el destello no es blanco: %.1f" % sin_marca(destello).mean())

            quieta = corrida.ver(foto_en + 40)
            como = "modo1" if hibrida else variante["textura"]
            esperada = Image.open(os.path.join(directorio, "esperada-%d-%s.png" % (f, como)))
            esperada = esperada.resize((256, 224), Image.NEAREST)
            distintos = int((sin_marca(a15(quieta)) != sin_marca(a15(esperada))).any(2).sum())
            if distintos:
                problemas.append("la foto quieta difiere en %d pixeles" % distintos)

            curva = []
            capturas_zoom = {}
            for t in MEDIDOS:
                imagen = corrida.ver(zoom_en + t)
                capturas_zoom[t] = imagen
                medida = caja(a15(imagen))
                s = 1 - t / linea["zoom"]
                if s <= 0:
                    if medida is not None:
                        problemas.append("en t = %d todavía se ve algo: %s" % (t, medida))
                    continue
                if medida is None:
                    problemas.append("en t = %d no se ve nada" % t)
                    continue
                x0, y0, x1, y1 = medida
                ancho, alto = x1 - x0, y1 - y0
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                curva.append("%d:%dx%d" % (t, ancho, alto))
                if abs(ancho - 256 * s) > 1.5 or abs(alto - 224 * s) > 1.5:
                    problemas.append("en t = %d mide %dx%d y tendría que medir %.1fx%.1f"
                                     % (t, ancho, alto, 256 * s, 224 * s))
                if abs(cx - 128) > 1 or abs(cy - 112) > 1:
                    problemas.append("en t = %d el centro está en (%.1f, %.1f)" % (t, cx, cy))

            subida = palabra(corrida.consola, SUBIDA_FIN)
            linea_max = palabra(corrida.consola, LINEA_MAX)
            if hibrida and not (foto_en <= subida < zoom_en):
                problemas.append("la textura terminó de subir en el cuadro %d" % subida)
            if linea_max > 261:
                problemas.append("un vblank terminó en la línea %d" % linea_max)

            for clave, imagen in [("destello", Image.fromarray((destello << 3).astype(np.uint8))),
                                  ("quieta", quieta)] + \
                    [("t%03d" % t, i) for t, i in capturas_zoom.items()]:
                a = a15(imagen)
                previo = vistos.setdefault((f, v, clave), (core, a))
                if previo[0] != core and not np.array_equal(previo[1], a):
                    problemas.append("%s distinto de %s" % (clave, previo[0]))
                if capturas:
                    imagen.save(os.path.join(capturas, "%s-%d-%d-%s.png" % (core, f + 1, v + 1, clave)))

            print("%s: %s; curva %s%s" % (
                nombre, "bien" if not problemas else "MAL: " + "; ".join(problemas),
                " ".join(curva),
                "; subió la textura en %d cuadros" % (subida - foto_en + 1) if hibrida else ""))
            fallas += bool(problemas)
    print("%s: los vblanks terminan hasta la línea %d de 261"
          % (core, palabra(corrida.consola, LINEA_MAX)))
    return fallas


def forma(a):
    """La imagen promediada de a 4x4: lo que queda sin el grano."""
    return a.astype(float).reshape(56, 4, 64, 4, 3).mean((1, 3))


def calidad(rom, resumen):
    """Cuánto se parece cada manera de mostrar la foto a la foto, en dB, y
    cuánto salta el cambio de las híbridas: el modo 1 contra la textura a
    escala 1. Dos números por cada una: pixel a pixel, y con las dos
    promediadas de a 4x4, que mide la forma y no el grano: la textura "vq"
    elige tiles que conservan el grano aunque no sea el mismo, y pixel a
    pixel eso cuenta como error."""
    directorio = os.path.dirname(rom)
    print("calidad contra la foto recortada, en dB (pixel a pixel / la forma; más es mejor):")
    for f, foto in enumerate(resumen["fotos"]):
        leer = lambda como: np.asarray(Image.open(os.path.join(  # noqa: E731
            directorio, "esperada-%d-%s.png" % (f, como))).convert("RGB").resize(
                (256, 224), Image.NEAREST))
        original, m1, media, vq = (leer(c) for c in ("foto", "modo1", "media", "vq"))
        dos = lambda a, b: "%.1f/%.1f" % (psnr(a, b), psnr(forma(a), forma(b)))  # noqa: E731
        print("    %-16s modo 1 %s, media %s, vq %s; el salto modo 1 → media %s, → vq %s"
              % (foto["nombre"], dos(original, m1), dos(original, media), dos(original, vq),
                 dos(m1, media), dos(m1, vq)))


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    rom = sys.argv[1]
    capturas = sys.argv[2] if len(sys.argv) == 3 else None
    if capturas:
        os.makedirs(capturas, exist_ok=True)
    with open(rom + ".variantes") as f:
        resumen = json.load(f)
    vistos = {}
    resultados = [correr(core, rom, resumen, capturas, vistos) for core in CORES]
    corridos = [r for r in resultados if r is not None]
    calidad(rom, resumen)
    if not corridos:
        sys.exit("no hay ningún core instalado")
    if sum(corridos):
        sys.exit(1)


if __name__ == "__main__":
    main()
