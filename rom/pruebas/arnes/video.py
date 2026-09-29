#!/usr/bin/env -S python3 -O
"""Un video con sonido de una ROM jugando, para que taro la vea sin correrla.

No trae una jugada propia: juega **las del recorrido**, llamando a las funciones
de `pruebas/abl/test_recorrido_golden.py` tal cual, con una fábrica de `recorrido` que
apunta a la ROM que se le pida. Así la jugada es una sola y
esperan por RAM, no por cuadros contados: ver `recorrido.py`. Lo que se graba
se toma de `retro.Consola.correr`, parcheado desde acá: cada cuadro de hardware
va a ffmpeg y su audio a un wav, y al final se juntan.

    pruebas/arnes/video.py build/release salida.mp4 apertura talan

Las jugadas se nombran por lo que tienen después de `test_`, sin tener que
escribir el nombre entero: `apertura` es `test_la_apertura_termina_...`.
`quieto:N` es arrancar y no tocar nada durante N ticks: la apertura se queda en
su primer cuadro de texto y su evento paralelo sigue, que es como se escuchan la
lluvia y los truenos sin nada encima.

**Se corre con `python3 -O` —lo pone el hashbang—, y es a propósito.** Las
jugadas son pruebas, y algunas verifican cosas que sólo valen a la velocidad
del recorrido: con `--leer` el cronómetro de Talan ya bajó de 10:00 cuando la
prueba lo mira, y el `assert` cortaba el video ahí. `-O` saca los `assert`; un atasco de verdad
—`Trabado`— se sigue levantando, porque no es un `assert`.

**Suena con el MSU-1, si el build tiene pistas**, al revés que las pruebas: el
video es para escuchar la ROM como se juega, y `release/` las lleva al lado
del `.sfc`. `--sin-msu` es para oír lo que toca el SPC700 solo, que es lo que
suena en una consola sin la extensión y lo que miden las pruebas.
"""

import argparse
import glob
import os
import subprocess
import sys
import tempfile
import wave

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for ruta in (os.path.join(os.pardir, "tools"), "pruebas",
             os.path.join("pruebas", "arnes"), os.path.join("pruebas", "abl")):
    sys.path.insert(0, os.path.join(RAIZ, ruta))

import lugares                                         # noqa: E402,F401
from emulador import retro                              # noqa: E402
import consola                                          # noqa: E402
from recorrido import Mundo, Recorrido                  # noqa: E402
import test_recorrido_golden                            # noqa: E402

# Los cuadros por segundo de la SNES NTSC: si no coinciden con los de la
# consola, el sonido se corre del video. La tasa del audio no va acá: la dice
# el core, y snes9x la cambia con el MSU-1. Ver `retro.Consola.tasa`.
CUADROS_POR_SEGUNDO = "60.0988"
ANCHO, ALTO = 256, 224
ESCALA = 3                      # con vecino más cercano: se ven los pixeles


def jugada(nombre):
    """La función de `test_recorrido_golden` que empieza con `test_` y
    contiene `nombre`. Tiene que ser una sola."""
    candidatas = [n for n in dir(test_recorrido_golden)
                  if n.startswith("test_") and nombre in n]
    if len(candidatas) != 1:
        raise SystemExit("la jugada %r no nombra una sola de "
                         "test_recorrido_golden: %s"
                         % (nombre, candidatas or "ninguna"))
    return getattr(test_recorrido_golden, candidatas[0])


def leer_despacio(ticks):
    """Que `Recorrido.esperar` apriete A cada `ticks` en vez de cada 8, así
    cada cuadro de texto se queda en pantalla. Los topes se estiran en la misma
    proporción: están pensados para 8."""
    original = Recorrido.esperar

    def esperar(self, que, cond, tope, a_cada=8, mirando=None):
        if a_cada:
            return original(self, que, cond, tope * ticks // a_cada, ticks,
                            mirando)
        return original(self, que, cond, tope, a_cada, mirando)
    Recorrido.esperar = esperar


def grabar(build, salida, jugadas, leer=None, msu=True):
    # El único `.sfc` del directorio: el nombre no se deduce del directorio,
    # porque la de release se llama `abl.sfc` adentro de `release/`.
    sfcs = glob.glob(os.path.join(build, "*.sfc"))
    if len(sfcs) != 1:
        raise SystemExit("en %s tiene que haber un .sfc y hay %d"
                         % (build, len(sfcs)))
    sfc = sfcs[0]
    simbolos = consola.Simbolos(sfc + ".sym")
    mapas = consola.mapas_de(os.path.join(build, "mapdata.inc"))
    if leer:
        leer_despacio(leer)

    temporal = tempfile.mkdtemp(prefix="video-")
    crudo = os.path.join(temporal, "video.mkv")
    audio = os.path.join(temporal, "audio.wav")
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-s", "%dx%d" % (ANCHO, ALTO),
         "-r", CUADROS_POR_SEGUNDO, "-i", "-", "-c:v", "ffv1", crudo],
        stdin=subprocess.PIPE)
    # Se abre con la primera consola, que es la que sabe a qué tasa entrega.
    wav = []
    cuadros = [0]

    # De a un cuadro aunque pidan más: si no, se graba un cuadro de video
    # por varios de audio y los dos se desfasan.
    correr = retro.Consola.correr

    def correr_grabando(self, n=1):
        for _ in range(n):
            correr(self, 1)
            imagen = self.imagen()
            if imagen.size != (ANCHO, ALTO):
                imagen = imagen.resize((ANCHO, ALTO))
            ffmpeg.stdin.write(imagen.tobytes())
            if not wav:
                wav.append(wave.open(audio, "wb"))
                wav[0].setnchannels(2)
                wav[0].setsampwidth(2)
                wav[0].setframerate(int(round(self.tasa())))
            wav[0].writeframes(bytes(self.audio))
            self.audio = bytearray()
            cuadros[0] += 1
    retro.Consola.correr = correr_grabando

    def recorrido(_nombre, switch=()):
        partida = consola.Partida(sfc, simbolos, mapas, switches=switch,
                                  titulo=consola.EMPEZAR, msu=msu)
        return Recorrido(partida, Mundo(), fotos=None)

    try:
        for pedido in jugadas:
            if pedido.startswith("quieto:"):
                recorrido("quieto").p.correr(int(pedido.split(":", 1)[1]))
            else:
                jugada(pedido)(recorrido)
            print("%s: grabada" % pedido)
    finally:
        retro.Consola.correr = correr
        ffmpeg.stdin.close()
        ffmpeg.wait()
        if wav:
            wav[0].close()

    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", crudo, "-i", audio,
         "-vf", "scale=%d:%d:flags=neighbor" % (ANCHO * ESCALA, ALTO * ESCALA),
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", salida],
        check=True)
    os.remove(crudo)
    os.remove(audio)
    os.rmdir(temporal)
    print("%s: %.1f s" % (salida, cuadros[0] / float(CUADROS_POR_SEGUNDO)))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("build", help="el directorio de la ROM: build/release")
    parser.add_argument("salida", help="el .mp4")
    parser.add_argument("jugadas", nargs="+",
                        help="parte del nombre de una jugada de "
                             "test_recorrido_golden, o quieto:N")
    parser.add_argument("--leer", type=int, metavar="TICKS",
                        help="apretar A cada TICKS en vez de cada 8, para "
                             "que se lean los textos")
    parser.add_argument("--sin-msu", action="store_true",
                        help="que el core no vea las pistas de MSU-1: suena "
                             "sólo el SPC700")
    args = parser.parse_args()
    if __debug__:
        raise SystemExit("corré esto con python3 -O: ver el comentario de "
                         "arriba de video.py")
    grabar(args.build, args.salida, args.jugadas, args.leer,
           msu=not args.sin_msu)


if __name__ == "__main__":
    main()
