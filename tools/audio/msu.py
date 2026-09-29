#!/usr/bin/env python3
"""Las pistas de MSU-1 del cartucho, desde los MIDI del juego.

El MSU-1 no es hardware de la Super Nintendo: es una extensión que soportan el
FX Pak Pro y los emuladores, con la música en archivos PCM al lado de la ROM.
Todo tema tiene pista —el número lo da `pista_msu`, en snes_music.py—, y con
MSU-1 la ROM calla el SPC700 y la toca; sin MSU-1 la firma no está y todo
suena como siempre. Ver
`workflow/tasks/done/audio-msu-1.md`, y para los fondos de batalla que viajan
en el `.msu`, `docs/port/msu-datos.md`.

Una pista es `<rom>-<número>.pcm`: la firma "MSU1", el punto de loop en
muestras —cuatro bytes— y el audio crudo, estéreo de 16 bits con signo a
44,1 kHz. Y al lado tiene que estar `<rom>.msu`, que es lo que enciende el
MSU-1. Ése no lo escribe esto sino el conversor, con los fondos de batalla que
el MSU-1 le sirve a la ROM —ver `port/msu_datos.py`—; para las pistas puede
estar vacío.

El audio sale de renderizar el MIDI con fluidsynth y **el mismo soundfont con
el que el juego sonaba en la PC**, que es el que ya usa `snes_samples.py` para
sacar las muestras del SPC700: la idea no es cambiar el arreglo sino dejar de
sintetizarlo con ocho voces y muestras recortadas. Un tema que en el juego es
un WAV —el SPC700 no lo toca: sale mudo— tiene pista igual, decodificado con
ffmpeg como un reemplazo.

**Se arman las pistas de los temas del cartucho, y nada más**: las que dice
el `musica.json` que el conversor deja al lado de la ROM, con el número de
cada tema. Los del juego entero son más de doscientos, y la mayoría no suena
en ningún mapa convertido. Un `<rom>-N.pcm` que ya no es de ningún tema se
borra: `just entregar` copia a la tarjeta todos los que encuentre.

    python3 tools/audio/msu.py rom/build/release/abl.sfc

No hace falta correrlo a mano: `just build release` lo corre siempre —ver
`pistas` en `cartuchos.py`—, porque la ROM que se juega lleva sus pistas.
Que estén al lado de la ROM no cambia las pruebas: el arnés le esconde las
pistas al core, ver `retro.Consola`.

**Una pista puede salir de un archivo de audio en vez del MIDI.** Si en el
directorio de reemplazos —`/extras/msu` si no se dice otro— hay un
`<tema>.mp3`, `.ogg`, `.flac` o `.wav`, la pista es ese audio, decodificado
con ffmpeg: por ejemplo `escape_newyork.mp3`. Es sólo para el MSU-1: sin él
el tema sigue sonando por el SPC700 desde el MIDI. Los reemplazos viven en
`/extras` y no en el repo por la misma razón que el arte del juego: la música
no es nuestra para redistribuir.

**Una pista que ya está no se vuelve a renderizar.** Cuesta un minuto y medio
para las del cartucho y no depende de él: depende del MIDI, del soundfont, del
sintetizador y de cómo se normaliza, y todo eso entra en la clave —ver
`clave_de_la_pista`—. Lo guardado en `rom/build/cache/msu/` es el sha256 del
`.pcm`, no el `.pcm`: las pistas pesan cientos de megas y ya están en el
disco, al lado de la ROM; guardarlas sería tener dos copias de lo mismo.
Con `SIN_CACHE=1` se rehacen todas, que es como se comprueba que salen iguales.
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import wave

import numpy

# Corrido como script, Python pone en el `sys.path` la carpeta de este archivo
# y no `tools/`, que es de donde se importan los paquetes: ver el mismo
# arranque en `port/snes_convert.py`.
# `realpath` y no `abspath`: `just herramientas` lo instala en el PATH como
# symlink, y la carpeta que sirve es la del archivo de verdad.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    # Y si el directorio actual es otro checkout, corre el de ahí: ver
    # `comun/ejecutable.py`.
    from comun import ejecutable
    ejecutable.usar_el_del_checkout(__file__)

from audio import snes_music                                # noqa: E402
from audio import snes_samples                              # noqa: E402
from comun import cache_disco                               # noqa: E402
from render.render_map import GAME_DIR                      # noqa: E402

# La ganancia de fluidsynth. Con 1.0 los temas con muchas voces saturan, así
# que se renderiza bajo y después se normaliza: el pico de la pista queda en
# `PICO`, que es casi la escala entera. Sin esto la pista sonaba a un cuarto
# del volumen de la música del SPC700 —medido: pico 4632 contra 17012— y el
# cambio de un tema a otro daba un salto de volumen.
GANANCIA = 0.6
PICO = 0.97

_fluidsynth = None
_ffmpeg = None

# Dónde se buscan los reemplazos, y con qué extensiones, en este orden.
REEMPLAZOS = "/extras/msu"
EXTENSIONES = (".mp3", ".ogg", ".flac", ".wav")


def huella_de_fluidsynth():
    """Qué sintetizador produjo la pista: el binario del PATH y su versión.

    Va el binario porque es lo que produce los bytes —la misma razón por la
    que `muestras_brr.version()` lleva el de `gunter`— y va el texto de
    `--version` porque el grueso de la síntesis vive en `libfluidsynth`, que
    el binario no contiene: actualizar la biblioteca sin que cambie el
    ejecutable tiene que caducar las pistas igual.
    """
    global _fluidsynth
    if _fluidsynth is None:
        ruta = shutil.which("fluidsynth")
        if ruta is None:
            sys.exit("falta fluidsynth: en Arch, pacman -S fluidsynth")
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(1 << 20), b""):
                h.update(bloque)
        # **Sólo el stdout.** Por el stderr salen los avisos de PipeWire y de
        # ALSA de una caja sin placa de sonido, y adentro va la dirección de
        # un puntero: con ASLR cambia en cada corrida y la clave no repetía
        # nunca. Medido: dos corridas seguidas daban dos claves distintas y no
        # se saltó una sola pista.
        version = subprocess.run(["fluidsynth", "--version"],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True)
        h.update(version.stdout.encode("utf-8"))
        _fluidsynth = h.hexdigest()
    return _fluidsynth


def huella_de_ffmpeg():
    """Qué decodificador produjo la pista de un reemplazo: el binario del
    PATH y su versión, por lo mismo que `huella_de_fluidsynth`."""
    global _ffmpeg
    if _ffmpeg is None:
        ruta = shutil.which("ffmpeg")
        if ruta is None:
            sys.exit("falta ffmpeg: en Arch, pacman -S ffmpeg")
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(1 << 20), b""):
                h.update(bloque)
        version = subprocess.run(["ffmpeg", "-version"],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True)
        h.update(version.stdout.encode("utf-8"))
        _ffmpeg = h.hexdigest()
    return _ffmpeg


def reemplazo(directorio, nombre):
    """El archivo de audio que reemplaza al MIDI de este tema, o None."""
    for extension in EXTENSIONES:
        ruta = os.path.join(directorio, nombre + extension)
        if os.path.isfile(ruta):
            return ruta
    return None


def clave_del_reemplazo(audio, pico=PICO):
    """Como `clave_de_la_pista`, para una pista que sale de un archivo de
    audio: un reemplazo, o un tema que en el juego es un WAV."""
    with open(audio, "rb") as f:
        crudo = f.read()
    return cache_disco.clave(cache_disco.version_de("audio/msu.py"),
                             huella_de_ffmpeg(), "%.17g" % pico, crudo)


def decodificar(audio, salida):
    """Un archivo de audio a WAV de 44,1 kHz estéreo de 16 bits, con ffmpeg."""
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", audio,
                    "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", salida],
                   check=True)


def clave_de_la_pista(midi, soundfont, ganancia, pico=PICO):
    """Todo lo que cambia los bytes de la pista, como una clave.

    El MIDI, el soundfont y el sintetizador son de dónde sale el audio; la
    ganancia y el pico, cómo se escala; y `version_de` es el código de acá,
    que es el que normaliza y arma el archivo. **El número de pista no va**:
    no cambia ni una muestra, sólo el nombre del archivo, y por eso con una
    sola demo renumerar dejó de rehacer nada.
    """
    with open(midi, "rb") as f:
        crudo = f.read()
    return cache_disco.clave(cache_disco.version_de("audio/msu.py"),
                             huella_de_fluidsynth(),
                             snes_samples.huella_del_soundfont(soundfont),
                             "%.17g %.17g" % (ganancia, pico),
                             crudo)


def huella_del_archivo(ruta):
    """El sha256 de un archivo ya escrito, o None si no está."""
    h = hashlib.sha256()
    try:
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(1 << 20), b""):
                h.update(bloque)
    except OSError:
        return None
    return h.hexdigest()


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
    # Con numpy y no muestra por muestra: son la misma cuenta —el producto en
    # doble precisión, truncado hacia el cero como `int()`, y recortado—, y
    # las pistas salen iguales byte por byte. En Python puro era casi todo el
    # tiempo de rehacer una pista. El `int32` es por el -32768, cuyo valor
    # absoluto no entra en 16 bits.
    datos = numpy.frombuffer(con.readframes(con.getnframes()), dtype="<i2")
    alto = int(numpy.abs(datos.astype(numpy.int32)).max()) or 1
    escala = pico * 32767.0 / alto
    if escala < 1.0 or escala > 1.02:
        datos = numpy.clip(numpy.trunc(datos.astype(numpy.float64) * escala),
                           -32768, 32767)
    with open(salida, "wb") as handle:
        handle.write(b"MSU1")
        handle.write(struct.pack("<I", loop))
        handle.write(datos.astype("<i2").tobytes())
    return con.getnframes(), escala


def pistas_del_cartucho(rom):
    """[(nombre, número)] de los temas del cartucho que tienen pista, en orden
    de número: del `musica.json` que el conversor deja al lado de la ROM."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(rom)), "musica.json")
    try:
        with open(ruta, encoding="utf-8") as archivo:
            temas = json.load(archivo)["temas"]
    except OSError:
        sys.exit("no está %s: las pistas son las de los temas del cartucho, "
                 "así que primero hay que armarlo" % ruta)
    # Por número y no por nombre: dos temas que difieren sólo en mayúsculas
    # son el mismo archivo, y dos hilos escribiendo la misma pista se pisan.
    por_numero = {t["pista"]: t["nombre"] for t in temas if t.get("pista")}
    return [(por_numero[n], n) for n in sorted(por_numero)]


def armar(rom, game_dir=GAME_DIR, soundfont=snes_samples.SOUNDFONT,
          ganancia=GANANCIA, reemplazos=REEMPLAZOS, charlar=True):
    """Deja al lado de `rom` el `.msu` y una pista por tema del cartucho, y
    borra las que ya no son de ningún tema.

    Devuelve cuántas pistas rehízo y cuántas ya estaban. `charlar` en falso
    calla las que ya estaban: `cartuchos.py` la llama en cada `just pruebas`.
    """
    base = os.path.splitext(rom)[0]
    # El archivo que enciende el MSU-1. Lo escribe el conversor con sus datos,
    # así que acá se crea sólo si falta —una ROM suelta, armada a mano—, y
    # vacío: sin la firma que espera, la ROM lee los fondos de sí misma. El
    # modo "ab" no lo trunca si ya está.
    abierto = open(base + ".msu", "ab")
    abierto.close()
    pistas = pistas_del_cartucho(rom)
    numeros = {numero for _nombre, numero in pistas}
    for vieja in glob.glob(glob.escape(base) + "-*.pcm"):
        numero = vieja[len(base) + 1:-len(".pcm")]
        if numero.isdigit() and int(numero) not in numeros:
            os.remove(vieja)
            print("pista %s: ya no es de ningún tema, borrada" % numero)
    # Las pistas a la vez, en hilos: cada una escribe su archivo, lo pesado
    # corre en fluidsynth o ffmpeg y en numpy, y una por una eran lo que más
    # tardaba un build en frío. Lo que se imprime sigue en orden.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 1) as hilos:
        hechos = [hilos.submit(_una_pista, base, nombre, numero, game_dir,
                               soundfont, ganancia, reemplazos)
                  for nombre, numero in pistas]
        hechas = estaban = 0
        for (nombre, numero), hecho in zip(pistas, hechos):
            linea = hecho.result()
            if linea is None:
                estaban += 1
                if charlar:
                    print("pista %d: %-22s ya estaba -> %s-%d.pcm"
                          % (numero, nombre, base, numero))
            else:
                hechas += 1
                print(linea)
    return hechas, estaban


def _una_pista(base, nombre, numero, game_dir, soundfont, ganancia,
               reemplazos):
    """Una pista de `armar`. Devuelve la línea que la cuenta, o None si ya
    estaba."""
    salida = "%s-%d.pcm" % (base, numero)
    audio = reemplazo(reemplazos, nombre)
    midi = None
    if not audio:
        fuente = snes_music.ruta_del_tema(nombre, game_dir)
        if not fuente:
            sys.exit("no encuentro la música de %s" % nombre)
        if fuente.lower().endswith(".mid"):
            midi = fuente
        else:
            audio = fuente
    if audio:
        clave = clave_del_reemplazo(audio)
    else:
        clave = clave_de_la_pista(midi, soundfont, ganancia)
    # La pista que ya está, si la escribió este mismo código con estas
    # mismas fuentes. Lo guardado es el sha256 del `.pcm`, así que una
    # corrida cortada a la mitad —el `.pcm` se escribe de una sola vez, y
    # pesa decenas de megas— no se da por buena: no coincide y se rehace.
    guardado = cache_disco.leer("msu", clave)
    # El `is not None` no sobra: sin caché `leer` da `None`, y un `.pcm`
    # que no está da `None` también, así que compararlos sin más daría
    # "ya estaba" justo cuando no hay nada.
    if guardado is not None and guardado == huella_del_archivo(salida):
        return None
    temporal = salida + ".wav"
    if audio:
        decodificar(audio, temporal)
    else:
        render(midi, temporal, soundfont, ganancia)
    # Se escribe al lado y se reemplaza, en vez de pisar el `.pcm` en su
    # lugar: truncarlo le cambiaría el contenido a quien lo tenga abierto
    # —un emulador tocándolo— o enlazado con otro nombre.
    muestras, escala = pista(temporal, salida + ".nuevo")
    os.replace(salida + ".nuevo", salida)
    os.remove(temporal)
    cache_disco.guardar("msu", clave, huella_del_archivo(salida))
    return ("pista %d: %-22s %6.1f s, %d MB, normalizada x%.2f -> %s%s"
            % (numero, nombre, muestras / 44100.0,
               os.path.getsize(salida) // (1 << 20), escala, salida,
               "  (de %s)" % audio if audio else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rom", help="la ROM: las pistas van al lado, con su "
                                    "nombre y el número de pista")
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--soundfont", default=snes_samples.SOUNDFONT)
    parser.add_argument("--ganancia", type=float, default=GANANCIA)
    parser.add_argument("--reemplazos", default=REEMPLAZOS,
                        help="dónde buscar un <tema>.mp3 —u .ogg, .flac, "
                             ".wav— que reemplace al MIDI de ese tema")
    args = parser.parse_args()
    armar(args.rom, args.game_dir, args.soundfont, args.ganancia,
          args.reemplazos)


if __name__ == "__main__":
    main()
