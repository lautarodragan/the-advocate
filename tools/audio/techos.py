#!/usr/bin/env python3
"""Measures each song's volume ceiling and writes `rom/parches/auto/musica/techos.toml`.

    rm2k-snes-volume-ceilings            measures, writes the table and
                                         rebuilds `release` with it:
                                         `just techos`
    rm2k-snes-volume-ceilings --medir    only measures the `release` that
                                         is built, and writes nothing

The reason for the table is in `leer_techos` (tools/audio/snes_music.py).
This is how it comes out:

1. **A copy of `release` with every song at half the headroom**
   (`AIRE_DE_MEDIDA`), in `rom/build/techos/`. With that none clips, so the
   peak measured is the true one, and since each voice's volume is linear in
   the ceiling, each song's with the full headroom is double.
2. **Each whole song on the title screen**, in snes9x without MSU-1, and its
   peak. Each one's headroom is the highest that keeps that peak `MARGEN`
   below the cap, without going past `sdsp.AIRE`: the ones that do not clip
   stay as they were.
3. **The table is written, `release` is rebuilt and measured again**. Each
   voice's volume is rounded to an integer, so the arithmetic is
   approximate: if some song still clipped, it is lowered by as much as it
   went over and the round repeats.

What stays in the table, besides the headroom: each song's peak and level
(LUFS) with it, **up to which frame it has to be played to go through its
peak** —with that the test does not play the whole songs— and the
fingerprint of its mix, which is how the test knows the table is stale. See
`test_musica_techos.py`.
"""

import argparse
import math
import os
import re
import subprocess
import sys
import tempfile
import wave
from multiprocessing import Pool

# `realpath` and not `abspath`: `just herramientas` installs this script on the
# PATH as a symlink, and what matters is where the real file is.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from audio import sdsp, snes_music                      # noqa: E402
from comun import ambiente                              # noqa: E402
from comun import perillas                              # noqa: E402
from comun import proyecto                              # noqa: E402

# Half the usual headroom: measured on 2026-09-26, with 0.25 none of the 32
# songs of `release` clips, and the loudest one stays 3.9 dB below the cap.
AIRE_DE_MEDIDA = sdsp.AIRE / 2

# What the measured ROM is called: the game's, in its project file.
NOMBRE_DE_LA_ROM = perillas.valor("rom", "name", tipo=str)

# How far the peak is allowed to go: 0.5 dB below the cap. What it absorbs is
# the rounding of each voice's volume to an integer, which makes the peak not
# scale exactly with the headroom.
MARGEN = 10 ** (-0.5 / 20)

# Where the cap lies in what comes out of the console: the DSP saturates the
# sum of the voices at 16 bits and then multiplies it by the master volume,
# MVOL/128.
TOPE = 32767 * sdsp.MASTER >> 7

# How many frames before the end of boot —`BOOT_CUADROS`, read from the ROM—
# recording starts: the title screen starts its song afterwards, so it is
# slack. It used to be a fixed 90 frames from power-on, with boot at 112,
# which is what the script that measured step 5 expected; since boot got
# shorter, a fixed number would cut off the start of each song.
ANTES_DEL_TITULO = 22

# How many frames past the peak the test plays.
DESPUES_DEL_PICO = 60

def temas_de(directorio):
    """The names of the cartridge's songs, in the order of their indices."""
    with open(os.path.join(directorio, "musicdata.inc")) as archivo:
        inc = archivo.read()
    nombres = re.search(r"^; Temas: (.*)$", inc, re.M).group(1).split(", ")
    return ["" if n == "sin música" else n for n in nombres]


def simbolos_de(sfc):
    tabla = {}
    with open(sfc + ".sym") as archivo:
        for linea in archivo:
            nombre, valor = linea.split()
            tabla[nombre] = int(valor)
    return tabla


def con_el_tema_en_el_titulo(rom, simbolos, tema):
    """The ROM with the title screen playing `tema`: the immediate of the
    `lda #TEMA_TITULO` it starts it with is changed. It is the only way for a
    song to play on its own, with its samples uploaded, without playing
    anything."""
    patron = bytes([0xA9, simbolos["TEMA_TITULO"], 0xC9, 0xFF, 0xF0])
    donde = rom.find(patron)
    assert donde >= 0 and rom.find(patron, donde + 1) < 0, (
        "cannot find the title screen's `lda #TEMA_TITULO`: how it starts "
        "its song has changed, and this has to change too")
    parchada = bytearray(rom)
    parchada[donde + 1] = tema
    return bytes(parchada)


def tocar(sfc, tema, cuadros):
    """(the samples, interleaved stereo, and the rate): `cuadros` frames of
    the song from when the title starts it, in snes9x without MSU-1."""
    import numpy as np
    from emulador import retro
    simbolos = simbolos_de(sfc)
    with open(sfc, "rb") as archivo:
        rom = con_el_tema_en_el_titulo(archivo.read(), simbolos, tema)
    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "tema.sfc")
        with open(ruta, "wb") as archivo:
            archivo.write(rom)
        consola = retro.Consola(ruta, msu=False)
        tasa = consola.tasa()
        consola.correr(simbolos["BOOT_CUADROS"] - ANTES_DEL_TITULO)
        consola.audio = bytearray()
        partes = []
        for _ in range(cuadros):
            consola.correr(1)
            if len(consola.audio) > 1 << 20:
                partes.append(bytes(consola.audio))
                consola.audio = bytearray()
        partes.append(bytes(consola.audio))
    return np.frombuffer(b"".join(partes), dtype="<i2"), tasa


def recortes(muestras):
    """How many samples ended up at the cap."""
    return int(((muestras >= TOPE) | (muestras <= -TOPE - 1)).sum())


def cuadros_del_tema(directorio, tema):
    """How long one pass of the song lasts, from the writes the converter
    emitted —they are measured in the same process that built it—, plus one
    second."""
    return _largos[directorio][tema] + 60


_largos = {}


def _medir_uno(trabajo):
    import numpy as np
    directorio, tema, cuadros, lufs = trabajo
    x, tasa = tocar(os.path.join(directorio, NOMBRE_DE_LA_ROM + ".sfc"),
                    tema, cuadros)
    absoluto = np.abs(x.astype(np.int32))
    pico = int(absoluto.max()) if len(x) else 0
    # The frame of the peak: the samples are left/right pairs.
    cuadro = int(absoluto.argmax()) // 2 * 60 // int(round(tasa))
    fila = {"recortes": recortes(x), "pico": pico, "cuadro": cuadro}
    if lufs:
        fila["lufs"] = _lufs(x, tasa)
    return tema, fila


def _lufs(x, tasa):
    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "t.wav")
        w = wave.open(ruta, "wb")
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(int(round(tasa)))
        w.writeframes(x.tobytes())
        w.close()
        hecho = subprocess.run(["ffmpeg", "-nostats", "-i", ruta, "-af",
                                "ebur128", "-f", "null", "-"],
                               capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", hecho.stderr)[-1])


def medir(directorio, lufs=False):
    """{song: {recortes, pico, cuadro[, lufs]}}: each whole song, once."""
    nombres = temas_de(directorio)
    hechos = temas_armados(directorio)
    _largos[directorio] = {i: t["largo"]
                           for i, t in enumerate(hechos) if t["largo"]}
    trabajos = [(directorio, i, cuadros_del_tema(directorio, i), lufs)
                for i, n in enumerate(nombres) if n and i in _largos[directorio]]
    with Pool(int(os.environ.get("PROCESOS", "8"))) as pool:
        filas = dict(pool.map(_medir_uno, trabajos))
    return {nombres[i]: fila for i, fila in filas.items()}


def temas_armados(directorio):
    """The cartridge's songs as the converter built them, in the order of
    their indices: the name, the length in frames and the fingerprint of
    each. The converter writes them in `musica.json`, next to
    `musicdata.inc`.

    Until 2026-09-26 they were rebuilt here with `build_varios`, which gave
    the same result because the bank depended only on the songs. Since the
    per-package budget it also depends on each map's packages and on which
    song may be playing in each one, which come from compiling the pages:
    rebuilding it here would be a second way of answering the same thing."""
    import json
    with open(os.path.join(directorio, "musica.json")) as archivo:
        return json.load(archivo)["temas"]


def db(pico):
    return 20 * math.log10(max(pico, 1) / float(TOPE))


def escribir(techos, medido, huellas, ruta=None):
    """The table, with its reason on top."""
    ruta = ruta or snes_music.ruta_de_techos()
    lineas = [
        "# The volume ceiling of each song of `release`: the headroom",
        "# `build_varios` builds its stream with, instead of `sdsp.AIRE`.",
        "#",
        "# **Not edited by hand**: `just techos` writes it, playing each song",
        "# in the ROM and giving it the highest headroom that does not clip.",
        "# The reason, in `leer_techos`, which is where the converter reads it;",
        "# how it is measured, in `rm2k-snes-volume-ceilings`.",
        "# `test_musica_techos.py` fails if any song clips or if the mix of",
        "# any of them is no longer the one measured: the fingerprint. Any",
        "# change to the mix —the samples, the envelopes, the allocation—",
        "# calls for running `just techos` again.",
        "#",
        "# Per song: `aire`, the ceiling; `pico`, in dB against the cap, and",
        "# `lufs`, the level, both measured with that headroom; `hasta`, how",
        "# many frames from the start it has to be played to go through its",
        "# peak; and `huella`, that of `huella_de_la_mezcla`.",
        "",
        "[medida]",
        "aire_de_medida = %s" % AIRE_DE_MEDIDA,
        "margen_db = -0.5",
        "",
    ]
    for nombre in sorted(techos):
        fila = medido[nombre]
        lineas += [
            "[temas.\"%s\"]" % nombre,
            "aire = %.3f" % techos[nombre],
            "pico = %.1f" % db(fila["pico"]),
            "lufs = %.1f" % fila["lufs"],
            "hasta = %d" % (fila["cuadro"] + DESPUES_DEL_PICO),
            'huella = "%s"' % huellas[nombre],
            "",
        ]
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w") as archivo:
        archivo.write("\n".join(lineas))


def imprimir(medido, techos=None):
    for nombre in sorted(medido):
        fila = medido[nombre]
        print("  %-45s %s peak %+5.1f dB, %5d clipped%s" % (
            nombre[:45], "headroom %.3f," % techos[nombre] if techos else "",
            db(fila["pico"]), fila["recortes"],
            ", %.1f LUFS" % fila["lufs"] if "lufs" in fila else ""))


def main():
    proyecto.desde_la_linea_de_comandos()
    from ensamblado import cartuchos
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    proyecto.argumento(parser)
    ambiente.argumentos(parser, *cartuchos.AL_CONVERSOR)
    parser.add_argument("--medir", action="store_true",
                        help="only measure the built `release`: clipping, "
                             "peak and LUFS of each song")
    args = parser.parse_args()
    ambiente.desde_argumentos(args, *cartuchos.AL_CONVERSOR)
    release = cartuchos.directorio(cartuchos.RELEASE)
    if args.medir:
        imprimir(medir(release, lufs=True))
        return

    # The half-volume copy, in its own build directory.
    medida = os.path.join(proyecto.build(), "techos")
    print("a copy of release with the headroom at %s, in %s"
          % (AIRE_DE_MEDIDA, medida))
    cartuchos.convertir(cartuchos.RELEASE, medida,
                        os.path.join(medida, NOMBRE_DE_LA_ROM + ".sfc"),
                        ["--aire-de-medida", str(AIRE_DE_MEDIDA)])
    a_medias = medir(medida)
    recortan = [n for n, f in a_medias.items() if f["recortes"]]
    if recortan:
        sys.exit("with the headroom at %s these clip: %s: lower AIRE_DE_MEDIDA"
                 % (AIRE_DE_MEDIDA, ", ".join(recortan)))
    techos = {}
    for nombre, fila in a_medias.items():
        entero = fila["pico"] * sdsp.AIRE / AIRE_DE_MEDIDA
        techos[nombre] = min(sdsp.AIRE, math.floor(
            1000 * sdsp.AIRE * TOPE * MARGEN / max(entero, 1)) / 1000.0)

    for vuelta in range(4):
        escribir(techos, {n: dict(f, lufs=0.0) for n, f in a_medias.items()},
                 {n: "" for n in techos})
        print("release with the table, round %d" % (vuelta + 1))
        cartuchos.armar(cartuchos.RELEASE, cartuchos.huella())
        medido = medir(release, lufs=True)
        recortan = {n: f for n, f in medido.items() if f["recortes"]}
        if not recortan:
            break
        for nombre, fila in recortan.items():
            techos[nombre] = math.floor(
                1000 * techos[nombre] * TOPE * MARGEN / fila["pico"]) / 1000.0
    else:
        sys.exit("after four rounds these still clip: %s"
                 % ", ".join(recortan))
    huellas = {t["nombre"]: t["huella"]
               for t in temas_armados(release) if t["largo"]}
    # What is rewritten now —the peaks, the fingerprints— does not change the
    # headrooms, so the cartridge just measured is still up to date: its
    # stamp looks only at the table's headrooms (see `cartuchos.huella`).
    escribir(techos, medido, huellas)
    imprimir(medido, techos)
    print("-> %s" % os.path.relpath(snes_music.ruta_de_techos()))


if __name__ == "__main__":
    main()
