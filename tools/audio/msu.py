#!/usr/bin/env python3
"""The cartridge's MSU-1 tracks, from the game's MIDIs.

MSU-1 is not Super Nintendo hardware: it is an extension supported by the FX
Pak Pro and by emulators, with the music in PCM files next to the ROM. Every
song has a track —the number comes from `pista_msu`, in snes_music.py—, and
with MSU-1 the ROM silences the SPC700 and plays the track; without MSU-1 the
signature is not there and everything sounds as always. See
`workflow/tasks/done/audio-msu-1.md`, and for the battle backgrounds that
travel in the `.msu`, `docs/port/msu-datos.md`.

A track is `<rom>-<number>.pcm`: the "MSU1" signature, the loop point in
samples —four bytes— and the raw audio, signed 16-bit stereo at 44.1 kHz.
And next to it there has to be `<rom>.msu`, which is what turns MSU-1 on.
That one is not written by this but by the converter, with the battle
backgrounds MSU-1 serves to the ROM —see `port/msu_datos.py`—; for the
tracks it can be empty.

The audio comes from rendering the MIDI with fluidsynth and **the same
soundfont the game sounded with on the PC**, which is the one
`snes_samples.py` already uses to get the SPC700 samples: the idea is not to
change the arrangement but to stop synthesizing it with eight voices and
trimmed samples. A song that in the game is a WAV —the SPC700 does not play
it: it comes out silent— gets a track anyway, decoded with ffmpeg like a
replacement.

**The tracks of the cartridge's songs are built, and nothing more**: the
ones listed in the `musica.json` the converter leaves next to the ROM, with
each song's number. The whole game has more than two hundred, and most of
them play in no converted map. A `<rom>-N.pcm` that no longer belongs to any
song is deleted: `just entregar` copies every one it finds to the card.

    rm2k-snes-msu rom/build/release/abl.sfc

There is no need to run it by hand: `just build release` always runs it
—see `pistas` in `cartuchos.py`—, because the ROM that is played carries its
tracks. Their being next to the ROM does not change the tests: the harness
hides the tracks from the core, see `retro.Consola`.

**A track can come from an audio file instead of the MIDI.** If the
replacements directory —`/extras/msu` unless another is given— has a
`<song>.mp3`, `.ogg`, `.flac` or `.wav`, the track is that audio, decoded
with ffmpeg: for example `escape_newyork.mp3`. It is only for MSU-1: without
it the song keeps playing through the SPC700 from the MIDI. The replacements
live in `/extras` and not in the repo for the same reason as the game's art:
the music is not ours to redistribute.

**A track that already exists is not rendered again.** It costs a minute and
a half for the cartridge's and does not depend on it: it depends on the MIDI,
the soundfont, the synthesizer and how it is normalized, and all of that goes
into the key —see `clave_de_la_pista`—. What is stored in
`rom/build/cache/msu/` is the sha256 of the `.pcm`, not the `.pcm`: the
tracks weigh hundreds of megabytes and are already on disk, next to the ROM;
storing them would mean two copies of the same thing. With `SIN_CACHE=1` they
are all redone, which is how one checks that they come out the same.
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

# Run as a script, Python puts this file's folder on `sys.path` and not
# `tools/`, which is where the packages are imported from: see the same
# startup in `port/snes_convert.py`.
# `realpath` and not `abspath`: `just herramientas` installs it on the PATH as
# a symlink, and the folder that works is the real file's.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from audio import snes_music                                # noqa: E402
from audio import snes_samples                              # noqa: E402
from common import environment                                  # noqa: E402
from common import disk_cache                               # noqa: E402
from common import project                                  # noqa: E402
from rpgmaker import resources                               # noqa: E402

# fluidsynth's gain. With 1.0 the songs with many voices saturate, so it is
# rendered low and then normalized: the track's peak ends up at `PICO`, which
# is almost full scale. Without this the track played at a quarter of the
# SPC700 music's volume —measured: peak 4632 against 17012— and switching
# from one song to another gave a jump in volume.
GANANCIA = 0.6
PICO = 0.97

_fluidsynth = None
_ffmpeg = None

# Which extensions the replacements are looked for with, in this order.
# Where is set by `--replacements`: see `common/environment.py`.
EXTENSIONES = (".mp3", ".ogg", ".flac", ".wav")


def huella_de_fluidsynth():
    """Which synthesizer produced the track: the binary on the PATH and its
    version.

    The binary goes in because it is what produces the bytes —the same reason
    `muestras_brr.version()` carries `gunter`'s— and the `--version` text goes
    in because the bulk of the synthesis lives in `libfluidsynth`, which the
    binary does not contain: updating the library without the executable
    changing has to expire the tracks all the same.
    """
    global _fluidsynth
    if _fluidsynth is None:
        ruta = shutil.which("fluidsynth")
        if ruta is None:
            sys.exit("fluidsynth is missing: on Arch, pacman -S fluidsynth")
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(1 << 20), b""):
                h.update(bloque)
        # **Only stdout.** stderr carries the PipeWire and ALSA warnings of a
        # box without a sound card, and inside them goes a pointer address:
        # with ASLR it changes on every run and the key never repeated.
        # Measured: two runs in a row gave two different keys and not a
        # single track was skipped.
        version = subprocess.run(["fluidsynth", "--version"],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True)
        h.update(version.stdout.encode("utf-8"))
        _fluidsynth = h.hexdigest()
    return _fluidsynth


def huella_de_ffmpeg():
    """Which decoder produced a replacement's track: the binary on the PATH
    and its version, for the same reason as `huella_de_fluidsynth`."""
    global _ffmpeg
    if _ffmpeg is None:
        ruta = shutil.which("ffmpeg")
        if ruta is None:
            sys.exit("ffmpeg is missing: on Arch, pacman -S ffmpeg")
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
    """The audio file that replaces this song's MIDI, or None. Without a
    replacements directory, none."""
    if directorio is None:
        return None
    for extension in EXTENSIONES:
        ruta = os.path.join(directorio, nombre + extension)
        if os.path.isfile(ruta):
            return ruta
    return None


def clave_del_reemplazo(audio, pico=PICO):
    """Like `clave_de_la_pista`, for a track that comes from an audio file: a
    replacement, or a song that in the game is a WAV."""
    with open(audio, "rb") as f:
        crudo = f.read()
    return disk_cache.key(disk_cache.version_of("audio/msu.py"),
                          huella_de_ffmpeg(), "%.17g" % pico, crudo)


def decodificar(audio, salida):
    """An audio file to 44.1 kHz 16-bit stereo WAV, with ffmpeg."""
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", audio,
                    "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", salida],
                   check=True)


def clave_de_la_pista(midi, soundfont, ganancia, pico=PICO):
    """Everything that changes the track's bytes, as a key.

    The MIDI, the soundfont and the synthesizer are where the audio comes
    from; the gain and the peak, how it is scaled; and `version_de` is the
    code here, which is what normalizes and builds the file. **The track
    number does not go in**: it does not change a single sample, only the
    file name, and that is why with a single demo renumbering stopped
    redoing anything.
    """
    with open(midi, "rb") as f:
        crudo = f.read()
    return disk_cache.key(disk_cache.version_of("audio/msu.py"),
                          huella_de_fluidsynth(),
                          snes_samples.huella_del_soundfont(soundfont),
                          "%.17g %.17g" % (ganancia, pico),
                          crudo)


def huella_del_archivo(ruta):
    """The sha256 of an already written file, or None if it is not there."""
    h = hashlib.sha256()
    try:
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(1 << 20), b""):
                h.update(bloque)
    except OSError:
        return None
    return h.hexdigest()


def render(midi, salida, soundfont, ganancia=GANANCIA):
    """The MIDI to 44.1 kHz stereo WAV, with fluidsynth."""
    subprocess.run(["fluidsynth", "-ni", "-r", "44100", "-g", str(ganancia),
                    "-F", salida, soundfont, midi],
                   check=True, stdout=subprocess.DEVNULL)


def pista(wav, salida, loop=0, pico=PICO):
    """The WAV as an MSU-1 track, normalized, with its loop point."""
    con = wave.open(wav)
    if (con.getnchannels(), con.getsampwidth(), con.getframerate()) != (2, 2, 44100):
        raise SystemExit("%s is not 16-bit stereo at 44100" % wav)
    # With numpy and not sample by sample: it is the same arithmetic —the
    # product in double precision, truncated towards zero like `int()`, and
    # clipped—, and the tracks come out byte for byte the same. In pure Python
    # it was almost all the time spent redoing a track. The `int32` is because
    # of -32768, whose absolute value does not fit in 16 bits.
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
    """[(name, number)] of the cartridge's songs that have a track, in order
    of number: from the `musica.json` the converter leaves next to the ROM."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(rom)), "musica.json")
    try:
        with open(ruta, encoding="utf-8") as archivo:
            temas = json.load(archivo)["temas"]
    except OSError:
        sys.exit("%s is missing: the tracks are those of the cartridge's "
                 "songs, so it has to be built first" % ruta)
    # By number and not by name: two songs that differ only in case are the
    # same file, and two threads writing the same track clobber each other.
    por_numero = {t["pista"]: t["nombre"] for t in temas if t.get("pista")}
    return [(por_numero[n], n) for n in sorted(por_numero)]


def armar(rom, game_dir=None, soundfont=None, ganancia=GANANCIA,
          reemplazos=None, charlar=True):
    """Leaves next to `rom` the `.msu` and one track per song of the
    cartridge, and deletes the ones that no longer belong to any song.

    Returns how many tracks it redid and how many were already there.
    `charlar` false silences the ones already there: `cartuchos.py` calls it
    on every `just pruebas`.
    """
    game_dir = game_dir or resources.GAME_DIR
    soundfont = soundfont or snes_samples.SOUNDFONT
    reemplazos = reemplazos or environment.msu_replacements()
    base = os.path.splitext(rom)[0]
    # The file that turns MSU-1 on. The converter writes it with its data, so
    # here it is created only if missing —a loose ROM, built by hand—, and
    # empty: without the signature it expects, the ROM reads the backgrounds
    # from itself. Mode "ab" does not truncate it if it is already there.
    abierto = open(base + ".msu", "ab")
    abierto.close()
    pistas = pistas_del_cartucho(rom)
    numeros = {numero for _nombre, numero in pistas}
    for vieja in glob.glob(glob.escape(base) + "-*.pcm"):
        numero = vieja[len(base) + 1:-len(".pcm")]
        if numero.isdigit() and int(numero) not in numeros:
            os.remove(vieja)
            print("track %s: no longer belongs to any song, deleted" % numero)
    # The tracks at once, in threads: each one writes its own file, the heavy
    # part runs in fluidsynth or ffmpeg and in numpy, and one by one they were
    # what took longest in a cold build. What is printed stays in order.
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
                    print("track %d: %-22s already there -> %s-%d.pcm"
                          % (numero, nombre, base, numero))
            else:
                hechas += 1
                print(linea)
    return hechas, estaban


def _una_pista(base, nombre, numero, game_dir, soundfont, ganancia,
               reemplazos):
    """One track of `armar`. Returns the line that reports it, or None if it
    was already there."""
    salida = "%s-%d.pcm" % (base, numero)
    audio = reemplazo(reemplazos, nombre)
    midi = None
    if not audio:
        fuente = snes_music.ruta_del_tema(nombre, game_dir)
        if not fuente:
            sys.exit("cannot find the music for %s" % nombre)
        if fuente.lower().endswith(".mid"):
            midi = fuente
        else:
            audio = fuente
    if audio:
        clave = clave_del_reemplazo(audio)
    else:
        clave = clave_de_la_pista(midi, soundfont, ganancia)
    # The track that is already there, if this same code wrote it with these
    # same sources. What is stored is the sha256 of the `.pcm`, so a run cut
    # off halfway —the `.pcm` is written in one go, and weighs tens of
    # megabytes— is not taken as good: it does not match and is redone.
    guardado = disk_cache.read("msu", clave)
    # The `is not None` is not redundant: without a cache `leer` gives
    # `None`, and a missing `.pcm` gives `None` too, so comparing them
    # plainly would say "already there" exactly when there is nothing.
    if guardado is not None and guardado == huella_del_archivo(salida):
        return None
    temporal = salida + ".wav"
    if audio:
        decodificar(audio, temporal)
    else:
        render(midi, temporal, soundfont, ganancia)
    # It is written alongside and replaced, instead of overwriting the `.pcm`
    # in place: truncating it would change the content for whoever has it
    # open —an emulator playing it— or linked under another name.
    muestras, escala = pista(temporal, salida + ".nuevo")
    os.replace(salida + ".nuevo", salida)
    os.remove(temporal)
    disk_cache.write("msu", clave, huella_del_archivo(salida))
    return ("track %d: %-22s %6.1f s, %d MB, normalized x%.2f -> %s%s"
            % (numero, nombre, muestras / 44100.0,
               os.path.getsize(salida) // (1 << 20), escala, salida,
               "  (from %s)" % audio if audio else ""))


# What it uses from the machine: the RTP, because a song can come from there;
# and the cache, where it remembers which tracks are already there.
DEL_AMBIENTE = ("game_dir", "rtp_dir", "soundfont", "replacements", "cache")


def main():
    project.from_command_line()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rom", help="the ROM: the tracks go next to it, with "
                                    "its name and the track number")
    project.add_argument(parser)
    environment.add_arguments(parser, *DEL_AMBIENTE)
    parser.add_argument("--ganancia", type=float, default=GANANCIA)
    args = parser.parse_args()
    environment.from_arguments(args, *DEL_AMBIENTE)
    armar(args.rom, ganancia=args.ganancia)


if __name__ == "__main__":
    main()
