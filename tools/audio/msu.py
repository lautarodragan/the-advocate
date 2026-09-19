"""Las pistas de MSU-1 del cartucho, desde los MIDI del juego.

El MSU-1 no es hardware de la Super Nintendo: es una extensión que soportan el
FX Pak Pro y los emuladores, con la música en archivos PCM al lado de la ROM.
Cuando un tema tiene pista —`PISTAS_MSU` en snes_music.py— la ROM calla el
SPC700 y la toca; sin MSU-1 la firma no está y todo suena como siempre. Ver
"El MSU-1" en el README.

Una pista es `<rom>-<número>.pcm`: la firma "MSU1", el punto de loop en
muestras —cuatro bytes— y el audio crudo, estéreo de 16 bits con signo a
44,1 kHz. Y al lado tiene que estar `<rom>.msu`, que es lo que enciende el
MSU-1; puede estar vacío.

El audio sale de renderizar el MIDI con fluidsynth y **el mismo soundfont con
el que el juego sonaba en la PC**, que es el que ya usa `snes_samples.py` para
sacar las muestras del SPC700: la idea no es cambiar el arreglo sino dejar de
sintetizarlo con ocho voces y muestras recortadas.

    python3 tools/msu.py rom/build/demo-ciudad/demo-ciudad.sfc
"""
import argparse
import array
import os
import struct
import subprocess
import sys
import wave

# Corrido como script, Python pone en el `sys.path` la carpeta de este archivo
# y no `tools/`, que es de donde se importan los paquetes: ver el mismo
# arranque en `port/snes_convert.py`.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from audio import snes_music                                # noqa: E402
from audio import snes_samples                              # noqa: E402
from render.render_map import GAME_DIR, find_resource       # noqa: E402

# La ganancia de fluidsynth. Con 1.0 los temas con muchas voces saturan, así
# que se renderiza bajo y después se normaliza: el pico de la pista queda en
# `PICO`, que es casi la escala entera. Sin esto la pista sonaba a un cuarto
# del volumen de la música del SPC700 —medido: pico 4632 contra 17012— y el
# cambio de un tema a otro daba un salto de volumen.
GANANCIA = 0.6
PICO = 0.97


def render(midi, salida, soundfont, ganancia=GANANCIA):
    """El MIDI a WAV de 44,1 kHz estéreo, con fluidsynth."""
    subprocess.run(["fluidsynth", "-ni", "-r", "44100", "-g", str(ganancia),
                    "-F", salida, soundfont, midi],
                   check=True, stdout=subprocess.DEVNULL)


def pista(wav, salida, loop=0, pico=PICO):
    """El WAV como pista de MSU-1, normalizado, con su punto de loop."""
    con = wave.open(wav)
    if (con.getnchannels(), con.getsampwidth(), con.getframerate()) != (2, 2, 44100):
        raise SystemExit("%s no es estéreo de 16 bits a 44100" % wav)
    datos = array.array("h", con.readframes(con.getnframes()))
    if sys.byteorder == "big":
        datos.byteswap()
    alto = max(abs(v) for v in datos) or 1
    escala = pico * 32767.0 / alto
    if escala < 1.0 or escala > 1.02:
        datos = array.array("h", (max(-32768, min(32767, int(v * escala)))
                                  for v in datos))
    with open(salida, "wb") as handle:
        handle.write(b"MSU1")
        handle.write(struct.pack("<I", loop))
        if sys.byteorder == "big":
            datos.byteswap()
        handle.write(datos.tobytes())
    return con.getnframes(), escala


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rom", help="la ROM: las pistas van al lado, con su "
                                    "nombre y el número de pista")
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--soundfont", default=snes_samples.SOUNDFONT)
    parser.add_argument("--ganancia", type=float, default=GANANCIA)
    args = parser.parse_args()

    base = os.path.splitext(args.rom)[0]
    # El archivo que enciende el MSU-1. Vacío alcanza: no leemos datos.
    abierto = open(base + ".msu", "ab")
    abierto.close()
    for nombre, numero in sorted(snes_music.PISTAS_MSU.items(),
                                 key=lambda par: par[1]):
        midi = find_resource([args.game_dir], "Music", nombre, (".mid",))
        if not midi:
            sys.exit("no encuentro el MIDI de %s" % nombre)
        salida = "%s-%d.pcm" % (base, numero)
        temporal = salida + ".wav"
        render(midi, temporal, args.soundfont, args.ganancia)
        muestras, escala = pista(temporal, salida)
        os.remove(temporal)
        print("pista %d: %-22s %6.1f s, %d MB, normalizada x%.2f -> %s"
              % (numero, nombre, muestras / 44100.0,
                 os.path.getsize(salida) // (1 << 20), escala, salida))


if __name__ == "__main__":
    main()
