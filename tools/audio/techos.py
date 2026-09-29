#!/usr/bin/env python3
"""Mide el techo de cada tema y escribe `rom/parches/auto/musica/techos.toml`.

    rm2k-snes-volume-ceilings            mide, escribe la tabla y rearma
                                         `release` con ella: `just techos`
    rm2k-snes-volume-ceilings --medir    sólo mide el `release` que está
                                         armado, y no escribe nada

El porqué de la tabla está en `leer_techos` (tools/audio/snes_music.py). Esto
es cómo sale:

1. **Una copia de `release` con todos los temas a la mitad del aire**
   (`AIRE_DE_MEDIDA`), en `rom/build/techos/`. Con eso no recorta ninguno,
   así que el pico que se mide es el verdadero, y como el volumen de cada voz
   es lineal en el techo, el de cada tema con el aire entero es el doble.
2. **Cada tema entero en la pantalla de título**, en snes9x sin MSU-1, y su
   pico. El aire de cada uno es el más alto que deja ese pico por debajo de
   `MARGEN` del tope, sin pasar de `sdsp.AIRE`: los que no recortan quedan
   como estaban.
3. **Se escribe la tabla, se rearma `release` y se lo vuelve a medir**. El
   volumen de cada voz se redondea a un entero, así que la cuenta es
   aproximada: si algún tema recortara todavía, se lo baja lo que se pasó y
   se repite.

Lo que queda en la tabla, además del aire: el pico y el nivel (LUFS) de cada
tema con él, **hasta qué cuadro hay que tocarlo para pasar por su pico** —con
eso la prueba no toca los temas enteros— y la huella de su mezcla, que es cómo
la prueba sabe que la tabla quedó vieja. Ver `test_musica_techos.py`.
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

# `realpath` y no `abspath`: `just herramientas` instala este script en el PATH
# como symlink, y lo que importa es dónde está el archivo de verdad.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from audio import sdsp, snes_music                      # noqa: E402
from comun import perillas                              # noqa: E402
from comun import proyecto                              # noqa: E402

# La mitad del aire de siempre: medido el 2026-09-26, con 0,25 no recorta
# ninguno de los 32 temas del `release`, y el que más suma queda a 3,9 dB
# del tope.
AIRE_DE_MEDIDA = sdsp.AIRE / 2

# Cómo se llama la ROM que se mide: la del juego, en su archivo de proyecto.
NOMBRE_DE_LA_ROM = perillas.valor("rom", "name", tipo=str)

# Hasta dónde se deja llegar el pico: 0,5 dB bajo el tope. Lo que absorbe es
# el redondeo del volumen de cada voz a un entero, que hace que el pico no
# escale exacto con el aire.
MARGEN = 10 ** (-0.5 / 20)

# Dónde queda el tope en lo que sale de la consola: el DSP satura la suma de
# las voces a 16 bits y después la multiplica por el volumen general, MVOL/128.
TOPE = 32767 * sdsp.MASTER >> 7

# Cuántos cuadros antes del fin del arranque —`BOOT_CUADROS`, que se lee de
# la ROM— se empieza a grabar: la pantalla de título prende su tema después,
# así que es aire. Eran 90 cuadros fijos desde el encendido, con el arranque
# en 112, que es lo que esperaba el script que midió el paso 5; desde que el
# arranque bajó, un número fijo cortaría el principio de cada tema.
ANTES_DEL_TITULO = 22

# Cuántos cuadros más allá del pico toca la prueba.
DESPUES_DEL_PICO = 60

def temas_de(directorio):
    """Los nombres de los temas del cartucho, en el orden de sus índices."""
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
    """La ROM con la pantalla de título tocando `tema`: se le cambia el
    inmediato del `lda #TEMA_TITULO` con que la prende. Es la única manera de
    que un tema suene solo, con sus muestras subidas, sin jugar nada."""
    patron = bytes([0xA9, simbolos["TEMA_TITULO"], 0xC9, 0xFF, 0xF0])
    donde = rom.find(patron)
    assert donde >= 0 and rom.find(patron, donde + 1) < 0, (
        "no encuentro el `lda #TEMA_TITULO` de la pantalla de título: "
        "cambió cómo prende su tema, y hay que cambiar esto")
    parchada = bytearray(rom)
    parchada[donde + 1] = tema
    return bytes(parchada)


def tocar(sfc, tema, cuadros):
    """(las muestras, estéreo intercaladas, y la tasa): `cuadros` cuadros del
    tema desde que el título lo prende, en snes9x sin MSU-1."""
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
    """Cuántas muestras quedaron en el tope."""
    return int(((muestras >= TOPE) | (muestras <= -TOPE - 1)).sum())


def cuadros_del_tema(directorio, tema):
    """Cuánto dura una vuelta del tema, de las escrituras que emitió el
    conversor —se miden en el mismo proceso que lo armó—, más un segundo."""
    return _largos[directorio][tema] + 60


_largos = {}


def _medir_uno(trabajo):
    import numpy as np
    directorio, tema, cuadros, lufs = trabajo
    x, tasa = tocar(os.path.join(directorio, NOMBRE_DE_LA_ROM + ".sfc"),
                    tema, cuadros)
    absoluto = np.abs(x.astype(np.int32))
    pico = int(absoluto.max()) if len(x) else 0
    # El cuadro del pico: las muestras son pares izquierda/derecha.
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
    """{tema: {recortes, pico, cuadro[, lufs]}}: cada tema entero, una vez."""
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
    """Los temas del cartucho como los armó el conversor, en el orden de sus
    índices: el nombre, el largo en cuadros y la huella de cada uno. Los
    escribe el conversor en `musica.json`, al lado de `musicdata.inc`.

    Hasta el 2026-09-26 se volvían a armar acá con `build_varios`, que daba
    lo mismo porque el banco dependía sólo de los temas. Desde el
    presupuesto por paquete depende también de los paquetes de cada mapa y
    de qué tema puede venir sonando en cada uno, que salen de compilar las
    páginas: rearmarlo acá sería una segunda manera de contestar lo mismo."""
    import json
    with open(os.path.join(directorio, "musica.json")) as archivo:
        return json.load(archivo)["temas"]


def db(pico):
    return 20 * math.log10(max(pico, 1) / float(TOPE))


def escribir(techos, medido, huellas, ruta=None):
    """La tabla, con su porqué arriba."""
    ruta = ruta or snes_music.ruta_de_techos()
    lineas = [
        "# El techo de volumen de cada tema del `release`: el aire con que",
        "# `build_varios` le arma el stream, en vez de `sdsp.AIRE`.",
        "#",
        "# **No se edita a mano**: lo escribe `just techos`, que toca cada",
        "# tema en la ROM y le da el aire más alto que no recorta. El porqué,",
        "# en `leer_techos`, que es donde el conversor la lee; cómo se mide,",
        "# en `rm2k-snes-volume-ceilings`. `test_musica_techos.py` falla si",
        "# algún tema recorta o si la mezcla de alguno ya no es la que se",
        "# midió: la huella. Cualquier cambio de la mezcla —las muestras, las",
        "# envolventes, el reparto— pide volver a correr `just techos`.",
        "#",
        "# Por tema: `aire`, el techo; `pico`, en dB contra el tope, y `lufs`,",
        "# el nivel, los dos medidos con ese aire; `hasta`, cuántos cuadros",
        "# desde que arranca hay que tocarlo para pasar por su pico; y",
        "# `huella`, la de `huella_de_la_mezcla`.",
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
        print("  %-45s %s pico %+5.1f dB, %5d recortes%s" % (
            nombre[:45], "aire %.3f," % techos[nombre] if techos else "",
            db(fila["pico"]), fila["recortes"],
            ", %.1f LUFS" % fila["lufs"] if "lufs" in fila else ""))


def main():
    proyecto.desde_la_linea_de_comandos()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    proyecto.argumento(parser)
    parser.add_argument("--medir", action="store_true",
                        help="sólo medir el `release` armado: recortes, pico "
                             "y LUFS de cada tema")
    args = parser.parse_args()
    from ensamblado import cartuchos
    release = cartuchos.directorio(cartuchos.RELEASE)
    if args.medir:
        imprimir(medir(release, lufs=True))
        return

    # La copia a medio volumen, en su propio directorio del build.
    medida = os.path.join(proyecto.build(), "techos")
    print("una copia de release con el aire en %s, en %s"
          % (AIRE_DE_MEDIDA, medida))
    cartuchos.convertir(cartuchos.RELEASE, medida,
                        os.path.join(medida, NOMBRE_DE_LA_ROM + ".sfc"),
                        ["--aire-de-medida", str(AIRE_DE_MEDIDA)])
    a_medias = medir(medida)
    recortan = [n for n, f in a_medias.items() if f["recortes"]]
    if recortan:
        sys.exit("con el aire en %s recortan %s: bajar AIRE_DE_MEDIDA"
                 % (AIRE_DE_MEDIDA, ", ".join(recortan)))
    techos = {}
    for nombre, fila in a_medias.items():
        entero = fila["pico"] * sdsp.AIRE / AIRE_DE_MEDIDA
        techos[nombre] = min(sdsp.AIRE, math.floor(
            1000 * sdsp.AIRE * TOPE * MARGEN / max(entero, 1)) / 1000.0)

    for vuelta in range(4):
        escribir(techos, {n: dict(f, lufs=0.0) for n, f in a_medias.items()},
                 {n: "" for n in techos})
        print("release con la tabla, vuelta %d" % (vuelta + 1))
        cartuchos.armar(cartuchos.RELEASE, cartuchos.huella())
        medido = medir(release, lufs=True)
        recortan = {n: f for n, f in medido.items() if f["recortes"]}
        if not recortan:
            break
        for nombre, fila in recortan.items():
            techos[nombre] = math.floor(
                1000 * techos[nombre] * TOPE * MARGEN / fila["pico"]) / 1000.0
    else:
        sys.exit("después de cuatro vueltas siguen recortando: %s"
                 % ", ".join(recortan))
    huellas = {t["nombre"]: t["huella"]
               for t in temas_armados(release) if t["largo"]}
    # Lo que se reescribe ahora —los picos, las huellas— no cambia los
    # aires, así que el cartucho que se acaba de medir sigue al día: su sello
    # mira sólo los aires de la tabla (ver `cartuchos.huella`).
    escribir(techos, medido, huellas)
    imprimir(medido, techos)
    print("-> %s" % os.path.relpath(snes_music.ruta_de_techos()))


if __name__ == "__main__":
    main()
