#!/usr/bin/env python3
"""Corre `exhirom.sfc` en los emuladores y dice, por franja, qué vio cada
uno: lo que la ROM dejó en la WRAM —o en la SRAM, en Mednafen—, el color
de la pantalla, y qué tramo dio otra cosa. Qué es cada franja, en
`prueba.s`.

    verificar.py <exhirom.sfc>

Cada emulador arranca la ROM **dos veces** sin borrar la SRAM —un reset en
los de libretro, otra corrida en Mednafen—: la segunda tiene que encontrar
la marca de la primera (la franja 7 en blanco).

Lo que se espera de cada uno, en `DISTINTO`: todo en verde, como la
consola, salvo

* **mesen-s** y el módulo **`snes`** de Mednafen —el que usa por
  omisión—: la 5 en **amarillo**. Ponen la SRAM de LoROM en
  `$70-$7D:0000-7FFF` también en ExHiROM, donde el cartucho tiene ROM.
  Mesen2 hace lo mismo salvo con "strict board mappings" (`BaseCartridge`
  de los dos), y es el depurador de taro: por eso el juego no usa esas
  mitades.
* **Mednafen con `snes_faust`**, el que juega taro: la 4 en **amarillo**.
  Lee `$80-$BF:8000` de los segundos 4 MB y no de los primeros
  (`cart.cpp`, que le suma 4 MB a todo banco menor que `$C0`); el juego no
  lo nota porque sus dos bancos de código están en los dos lugares.

Sale con 1 si alguno no dio lo que tiene que dar. Un core o un Mednafen
que no está instalado se saltea con un aviso.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time

from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
# Corre como script, como `menu-modo-5/verificar.py`: el emulador es un
# paquete de las herramientas y la receta no puede nombrarlas.
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(RAIZ, os.pardir, "tools"))
sys.path.insert(0, AQUI)
from emulator import retro  # noqa: E402
from armar import CHEQUEOS, consola as en_la_consola, suma  # noqa: E402

CORES = ["snes9x", "bsnes", "mesen-s"]
# Lo que se deja correr a Mednafen: la ROM termina en unos tres segundos.
SEGUNDOS = 8

# Lo de `prueba.s`.
RESULTADOS = 0x0200
LARGO = 0x01E0
COPIA = 0x1E00
MARCA = 0x1FF0
FRANJAS = 9
ALTO = 24                       # 18 de color y 6 negras
ROJO, VERDE, AMARILLO, BLANCO, GRIS = range(5)
NOMBRES = ["rojo", "verde", "amarillo", "blanco", "gris"]
# A 5 bits por canal, como los escribe la ROM.
COLORES = [(31, 0, 0), (0, 31, 0), (31, 31, 0), (31, 31, 31), (15, 15, 15)]
QUE = ["todo", "primeros 4 MB ($C0-$FF)", "segundos 4 MB ($40-$7D)",
       "mitades altas por $00-$3F", "mitades altas por $80-$BF",
       "mitades bajas de $70-$7D", "SRAM", "SRAM de un arranque al otro",
       "FastROM"]
# Lo que cada emulador no hace como la consola; lo demás, en verde. Ver el
# docstring.
DISTINTO = {
    "mesen-s": {5: AMARILLO},
    "mednafen snes_faust": {4: AMARILLO},
    "mednafen snes": {5: AMARILLO},
}


def esperadas(nombre, primera):
    barras = [VERDE] * FRANJAS
    barras[7] = GRIS if primera else BLANCO
    for franja, color in DISTINTO.get(nombre, {}).items():
        barras[franja] = color
    return barras


def franjas_de(imagen):
    """El color de cada franja, a 5 bits, en el medio de cada una."""
    imagen = imagen.convert("RGB")
    ancho, alto = imagen.size
    out = []
    for i in range(FRANJAS):
        y = (i * ALTO + 9) * alto // 224
        out.append(tuple(c >> 3 for c in imagen.getpixel((ancho // 2, y))))
    return out


def informe(nombre, rom, datos, colores, primera):
    """Dice qué dio y devuelve si es lo esperado. `datos` son los LARGO
    bytes desde RESULTADOS; `colores`, los de la pantalla o None."""
    barras = list(datos[8:8 + FRANJAS])
    rapido = int.from_bytes(datos[4:6], "little")
    lento = int.from_bytes(datos[6:8], "little")
    malos = int.from_bytes(datos[2:4], "little")
    esperado = esperadas(nombre, primera)
    bien = datos[0] == 1 and barras == esperado
    print("%s, arranque %d: %s" % (nombre, 1 if primera else 2,
                                   "como corresponde" if bien else "NO ES LO ESPERADO"))
    for i, (b, e) in enumerate(zip(barras, esperado)):
        nota = "" if b == e else "   (se esperaba %s)" % NOMBRES[e]
        print("    %d %-30s %s%s" % (i, QUE[i], NOMBRES[b] if b < 5 else b, nota))
    print("    bucle: %d líneas desde $C0 y %d desde $40; SRAM: %d bytes malos; "
          "arranques anotados: %d" % (rapido, lento, malos, datos[1]))
    otros = []
    for k, (direccion, largo, franja) in enumerate(CHEQUEOS):
        vista = int.from_bytes(datos[32 + 2 * k:34 + 2 * k], "little")
        desde = en_la_consola(direccion)
        if vista != suma(rom[desde:desde + largo]):
            otros.append("    tramo $%06X (%d bytes, franja %d): suma $%04X"
                         % (direccion, largo, franja, vista))
    for linea in otros[:3]:
        print(linea)
    if len(otros) > 3:
        print("    y %d tramos más con otra suma" % (len(otros) - 3))
    if colores is not None:
        quiere = [COLORES[b] for b in esperado]
        if colores != quiere:
            bien = False
            print("    LA PANTALLA NO COINCIDE: %s" % colores)
        else:
            print("    la pantalla coincide")
    return bien


def pantalla(consola):
    """El cuadro en 224 líneas. mesen-s entrega 478, las 239 de su ventana
    dobladas: se toma una de cada dos y se recorta al centro, como
    `menu-modo-5/verificar.py`."""
    _, ancho, alto, _ = consola.frame
    if alto <= 2 * retro.HEIGHT:
        return consola.image()
    guardado = retro.HEIGHT
    retro.HEIGHT = alto
    try:
        completa = consola.image()
    finally:
        retro.HEIGHT = guardado
    completa = completa.resize((ancho, alto // 2), Image.NEAREST)
    arriba = (alto // 2 - retro.HEIGHT) // 2
    return completa.crop((0, arriba, ancho, arriba + retro.HEIGHT))


def esperar(consola):
    for _ in range(900):
        consola.run(1)
        if consola.ram(RESULTADOS, 1)[0] == 1:
            consola.run(3)
            return True
    return False


def correr_libretro(core, sfc, rom):
    ruta = "/usr/lib/libretro/%s_libretro.so" % core
    if not os.path.exists(ruta):
        print("%s: no está instalado, se saltea" % core)
        return None
    consola = retro.Console(sfc, ruta)
    bien = True
    for primera in (True, False):
        if not primera:
            consola.reset()
        if not esperar(consola):
            print("%s: la ROM no terminó" % core)
            return False
        datos = consola.ram(RESULTADOS, LARGO)
        bien &= informe(core, rom, datos, franjas_de(pantalla(consola)), primera)
    try:
        sram = consola.sram()
    except RuntimeError:
        # bsnes no la muestra por libretro: la franja 6 ya dijo que está.
        return bien
    if len(sram) != 0x2000 or sram[MARCA:MARCA + 8] != b"EXHIROM!":
        print("%s: la SRAM que guarda el core no es la esperada (%d bytes)" % (core, len(sram)))
        bien = False
    return bien


def correr_mednafen(modulo, sfc, home):
    """Mednafen no se puede manejar desde acá: se lo corre en un X virtual
    propio, grabando video, y se lo termina con SIGTERM, que es cuando
    guarda la SRAM. Lo que dejó la ROM se lee de la copia que hace en la
    SRAM, y los colores, del último cuadro del video."""
    video = os.path.join(home, "video.mov")
    cuadro = os.path.join(home, "cuadro.png")
    # Mednafen no pisa un video que ya está, y uno viejo daría colores viejos.
    for viejo in (video, cuadro):
        if os.path.exists(viejo):
            os.remove(viejo)
    leer, escribir = os.pipe()
    xvfb = subprocess.Popen(["Xvfb", "-displayfd", str(escribir), "-screen", "0", "1024x768x24"],
                            pass_fds=(escribir,), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    os.close(escribir)
    pantalla_x = os.read(leer, 16).decode().strip()
    os.close(leer)
    entorno = dict(os.environ, MEDNAFEN_HOME=home, SDL_AUDIODRIVER="dummy",
                   DISPLAY=":" + pantalla_x)
    try:
        # El sonido apagado hace fallar la grabación: va prendido, a la nada.
        emulador = subprocess.Popen(
            ["mednafen", "-force_module", modulo, "-sound", "1", "-sound.driver", "sdl",
             "-qtrecord", video, "-qtrecord.vcodec", "png", sfc],
            env=entorno, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(SEGUNDOS)
        emulador.terminate()
        emulador.wait(timeout=30)
    finally:
        xvfb.terminate()
        xvfb.wait()
    guardadas = glob.glob(os.path.join(home, "sav", "*.srm"))
    if not guardadas:
        return None, None
    with open(guardadas[0], "rb") as f:
        sram = f.read()
    colores = None
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-sseof", "-0.5", "-i", video,
                        "-frames:v", "1", cuadro], check=False)
        if os.path.exists(cuadro):
            colores = franjas_de(Image.open(cuadro))
    return sram[COPIA:COPIA + LARGO], colores


def mednafen(modulo, sfc, rom):
    if not (shutil.which("mednafen") and shutil.which("Xvfb")):
        print("mednafen: no está instalado, se saltea")
        return None
    nombre = "mednafen %s" % modulo
    home = tempfile.mkdtemp(prefix="mednafen-")
    try:
        bien = True
        for primera in (True, False):
            datos, colores = correr_mednafen(modulo, sfc, home)
            if datos is None:
                print("%s: no guardó la SRAM" % nombre)
                return False
            bien &= informe(nombre, rom, datos, colores, primera)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    return bien


def main():
    sfc = os.path.abspath(sys.argv[1])
    with open(sfc, "rb") as f:
        rom = f.read()
    corridos = [correr_libretro(c, sfc, rom) for c in CORES]
    corridos += [mednafen(m, sfc, rom) for m in ("snes_faust", "snes")]
    hechos = [r for r in corridos if r is not None]
    if not hechos:
        sys.exit("ningún emulador instalado")
    sys.exit(0 if all(hechos) else 1)


if __name__ == "__main__":
    main()
