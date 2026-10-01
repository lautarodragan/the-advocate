#!/usr/bin/env python3
"""Corre `msu-puerto.sfc` en los emuladores y dice, por prueba, cuánto
tardó la búsqueda, cuánto cada DMA de 32 KB, y si lo que llegó a la WRAM es
lo que hay en el `.msu`. Qué hace cada prueba, en `puerto.s`.

    medir.py <msu-puerto.sfc>

Sale con 1 si en algún core un tramo no llegó bien o no hay MSU-1. Un core
que no está instalado se saltea con un aviso.

**Lo que esto no mide es lo que importa en la consola**: los emuladores
buscan en el acto y entregan cada byte a la velocidad del DMA, así que acá
sale el techo del bus, 8 ciclos maestros por byte. En el FX Pak la búsqueda
fuera de su búfer lee la tarjeta SD, y la lectura seguida depende de que el
firmware rellene el búfer antes de que la consola lo alcance: eso lo dice
el color de la pantalla en la consola (ver `puerto.s`).
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
# Corre como script, como `menu-modo-5/verificar.py`: el emulador es un
# paquete de las herramientas y la receta no puede nombrarlas.
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(RAIZ, os.pardir, "tools"))
sys.path.insert(0, AQUI)
from emulator import retro  # noqa: E402
from armar import TRAMOS, TRAMO  # noqa: E402

CORES = ["snes9x", "bsnes", "mesen-s"]
RESULTADOS = 0x0200
FILAS = RESULTADOS + 16
PRUEBAS = 10
LINEAS = 262                    # por cuadro, NTSC
CICLOS_POR_LINEA = 1364
MAESTRO = 21477272              # Hz


def lineas(a, b):
    return (b - a) % LINEAS


def palabras(datos):
    return [int.from_bytes(datos[i:i + 2], "little") for i in range(0, len(datos), 2)]


def correr(core, sfc, msu):
    ruta = "/usr/lib/libretro/%s_libretro.so" % core
    if not os.path.exists(ruta):
        print("%s: no está instalado, se saltea" % core)
        return None
    consola = retro.Console(sfc, ruta, msu=True)
    for _ in range(600):
        consola.run(1)
        estado = consola.ram(RESULTADOS, 1)[0]
        if estado:
            break
    if estado != 1:
        print("%s: %s" % (core, "no hay MSU-1" if estado == 2 else "no terminó"))
        return False
    # Y lo que vería taro en la consola: el color de fondo, unos cuadros
    # después de prender la pantalla.
    consola.run(3)
    color = consola.image().getpixel((128, 112))
    malos = palabras(consola.ram(RESULTADOS + 2, 2))[0]
    esperado = (0, 248, 0) if malos == 0 else (248, 0, 0)
    pantalla = tuple(c & 0xF8 for c in color[:3]) == esperado
    print("%s: la pantalla es %s %s" % (core, color[:3],
                                        "como corresponde" if pantalla else "Y NO DEBERÍA"))
    filas = [palabras(consola.ram(FILAS + 16 * k, 16)) for k in range(PRUEBAS)]
    # Lo último que quedó en la WRAM: el último par de tramos.
    ultimo = consola.ram(0x10000, 0x10000)
    bien_wram = ultimo == msu[TRAMOS[-2]:TRAMOS[-2] + 2 * TRAMO]
    print("%s: %d tramo(s) malo(s); la WRAM tiene el último par %s"
          % (core, malos, "igual al .msu" if bien_wram else "DISTINTO del .msu"))
    print("    prueba  vueltas  búsqueda  DMA 1  DMA 2   (líneas)   KB por cuadro")
    dmas = []
    for k, (vueltas, v0, v1, d0, d1, d2, _, _) in enumerate(filas):
        busqueda = lineas(v0, v1) if k in (0, 1, 2) else 0
        l1 = lineas(d0, d1)
        l2 = lineas(d1, d2) if k >= 2 else None
        dmas.append(l1)
        if l2 is not None:
            dmas.append(l2)
        print("    %6d  %7d  %8d  %5d  %5s   %12.1f"
              % (k, vueltas if k in (0, 1, 2) else 0, busqueda, l1,
                 "-" if l2 is None else l2, 32 * LINEAS / l1))
    media = sum(dmas) / len(dmas)
    segundos = media * CICLOS_POR_LINEA / MAESTRO
    print("    32 KB en %.1f líneas de media: %.2f MB/s, %.1f KB por cuadro"
          % (media, TRAMO / segundos / 1e6, 32 * LINEAS / media))
    return malos == 0 and bien_wram and pantalla


def main():
    sfc = sys.argv[1]
    with open(os.path.splitext(sfc)[0] + ".msu", "rb") as f:
        msu = f.read()
    corridos = [correr(c, sfc, msu) for c in CORES]
    hechos = [r for r in corridos if r is not None]
    if not hechos:
        sys.exit("ningún core instalado")
    sys.exit(0 if all(hechos) else 1)


if __name__ == "__main__":
    main()
