#!/usr/bin/env python3
"""Verifica que la SNES esté tocando las notas del MIDI, sin escuchar nada.

Con un tono suelto alcanzaba con medirle la frecuencia (wavtone.py). Con un tema
entero no: suenan varias notas a la vez y la autocorrelación no dice cuáles.

Acá se hace al revés. Del MIDI ya sabemos qué notas deberían estar sonando en
cada momento, así que en vez de preguntarle al audio "¿qué frecuencia tenés?" se
le pregunta "¿cuánta energía tenés en esta frecuencia?", que es una cuenta
directa (Goertzel) y no necesita ninguna biblioteca.

La prueba está en la comparación. Para cada nota esperada se mide también un
señuelo un cuarto de tono más arriba: una frecuencia que no es ninguna nota y
que, si el mapeo de alturas estuviera mal, tendría tanta energía como la buena.
Si las notas del MIDI le ganan sistemáticamente a sus señuelos, la cadena entera
—reparto de voces, muestras en BRR, registro de altura del DSP— está bien.

Uso:
    python3 tools/snes_check.py snes/shots/tema.wav --map-id 67
"""

import argparse
import collections
import math
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
import md_music
import midi
import sdsp
import snes_music
from render_map import GAME_DIR, find_resource

WINDOW = 4096           # muestras por ventana de análisis
DECOY = 2 ** (1 / 24.0)  # un cuarto de tono: no cae en ninguna nota


def goertzel(samples, rate, hertz):
    """La energía de una frecuencia dentro de una ventana.

    Es una DFT de un solo punto: en vez de calcular todo el espectro para mirar
    un valor, se calcula ese valor. Son dos multiplicaciones por muestra.
    """
    k = 2.0 * math.cos(2.0 * math.pi * hertz / rate)
    s1 = s2 = 0.0
    for sample in samples:
        s0 = sample + k * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - k * s1 * s2


def read_wav(path):
    with wave.open(path, "rb") as handle:
        rate, channels = handle.getframerate(), handle.getnchannels()
        frames = handle.readframes(handle.getnframes())
    values = struct.unpack("<%dh" % (len(frames) // 2), frames)
    return rate, list(values[::channels])


def expected_notes(map_id, game_dir):
    """Qué notas suenan en cada cuadro, ya pasadas por el reparto de voces.

    Se le pregunta al mismo código que generó la ROM, no al MIDI crudo: las
    notas que se cayeron por falta de voces no tienen por qué estar en el audio,
    y buscarlas sería reprobar a la ROM por algo que decidimos nosotros.
    """
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    music = tree.map_music(map_id)
    path = find_resource([game_dir], "Music", music["name"], (".mid", ".wav"))

    notes, tempos, division, programs = midi.read(path)
    length = md_music.timeline(notes, tempos, division)
    voices = snes_music.assign(notes)

    sounding = collections.defaultdict(set)
    busy = {}
    for note in sorted(notes, key=lambda n: n.start):
        group = voices.get(note.channel)
        if not group or note.channel == midi.DRUM_CHANNEL:
            continue        # la percusión es ruido: no tiene altura que medir
        free = [v for v in group if busy.get(v, 0) <= note.start]
        voice = min(free or group, key=lambda v: busy.get(v, 0))
        busy[voice] = note.end

        # La altura que realmente sale es la del registro del DSP, que puede
        # haber bajado una octava si la nota no entraba en catorce bits.
        step = sdsp.pitch(note.pitch)
        hertz = step * sdsp.SAMPLE_RATE / 4096.0 / sdsp.CYCLE
        for frame in range(note.start, note.end):
            sounding[frame].add(hertz)
    return sounding, length


def score(samples, rate, sounding, offset, windows, length):
    """Cuántas ventanas tienen más energía en la nota que en su señuelo."""
    wins = total = 0
    detail = []
    for index in range(windows):
        # Se mide en el medio de cada nota sostenida, salteando los ataques.
        frame = int((index + 0.5) * length / windows)
        expected = sounding.get(frame)
        if not expected:
            continue

        at = offset + int(frame * rate / md_music.TICKS_PER_SECOND)
        window = samples[at:at + WINDOW]
        if len(window) < WINDOW:
            break

        best = max(expected, key=lambda hz: goertzel(window, rate, hz))
        good = goertzel(window, rate, best)
        bad = goertzel(window, rate, best * DECOY)
        total += 1
        if good > bad:
            wins += 1
        detail.append((frame, best, good, bad))
    return wins, total, detail


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wav")
    parser.add_argument("--map-id", type=int, default=67)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--windows", type=int, default=60)
    args = parser.parse_args()

    rate, samples = read_wav(args.wav)
    peak = max(abs(s) for s in samples) if samples else 0
    print("%s: %.1f s a %d Hz, pico %d de 32767"
          % (args.wav, len(samples) / rate, rate, peak))
    if peak < 200:
        print("SILENCIO: no salió sonido.")
        return 1
    if peak >= 32700:
        print("SATURA: la suma de las voces se pasa de escala.")

    sounding, length = expected_notes(args.map_id, args.game_dir)
    recorded = int(len(samples) / rate * md_music.TICKS_PER_SECOND)
    length = min(length, recorded - 30)

    # La ROM tarda en arrancar: carga el driver y las muestras antes de la
    # primera nota. Se busca el corrimiento que mejor alinea en vez de suponerlo.
    best = (0, 0, 0)
    for offset_frames in range(0, 60, 4):
        offset = int(offset_frames * rate / md_music.TICKS_PER_SECOND)
        wins, total, _ = score(samples, rate, sounding, offset, 20, length)
        if total and wins / total > best[0]:
            best = (wins / total, offset, offset_frames)
    print("corrimiento del arranque: %d cuadros" % best[2])

    wins, total, detail = score(samples, rate, sounding, best[1],
                                args.windows, length)
    if not total:
        print("no hay ventanas con notas para medir")
        return 1

    print("ventanas donde la nota esperada le gana a su señuelo: %d de %d (%.0f%%)"
          % (wins, total, 100 * wins / total))
    for frame, hertz, good, bad in detail[:8]:
        print("  cuadro %5d  %7.1f Hz   nota %.0f dB  señuelo %.0f dB"
              % (frame, hertz, 10 * math.log10(good + 1), 10 * math.log10(bad + 1)))

    if wins / total >= 0.75:
        print("COINCIDE: está tocando el tema.")
        return 0
    print("NO COINCIDE")
    return 1


if __name__ == "__main__":
    sys.exit(main())
