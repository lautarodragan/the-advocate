#!/usr/bin/env python3
"""Convierte el MIDI de un mapa a un stream para el PSG de la Mega Drive.

El PSG tiene tres canales de onda cuadrada y uno de ruido, sin envolventes y
sin polifonía por canal. Un MIDI de RM2k trae cuatro o cinco canales con
acordes, así que hay que reducir: cada canal del MIDI va a parar a una voz del
PSG según su altura promedio, y de las notas que suenan a la vez en una misma
voz se toca la última que arrancó, que es lo que hace un sintetizador
monofónico.

Lo que sale es un log de escrituras al PSG con el tiempo entre medio, parecido
a un VGM pero a resolución de cuadro: la ROM sólo tiene que ir escupiendo bytes
al puerto. Toda la música vive en la tabla y el reproductor son veinte líneas.

Uso:
    python3 tools/md_music.py --map-id 67 -o md/src/musicdata
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
import midi
from render_map import GAME_DIR, REPO, find_resource

# El PSG va a 3579545 Hz y divide por 32, así que la frecuencia de un tono es
# reloj / (32 * n) con n de 10 bits.
PSG_CLOCK = 3579545
MAX_DIVIDER = 1023
TONE_VOICES = 3
NOISE_VOICE = 3
SILENT = 15             # atenuación máxima: el canal no suena
TICKS_PER_SECOND = 60   # el stream se genera en cuadros de NTSC


def divider(pitch):
    """El divisor del PSG para una nota MIDI, subiéndola de octava si no entra."""
    while True:
        frequency = 440.0 * 2.0 ** ((pitch - 69) / 12.0)
        value = int(round(PSG_CLOCK / (32.0 * frequency)))
        if value <= MAX_DIVIDER:
            return max(1, value)
        pitch += 12         # demasiado grave para el PSG: una octava arriba


def attenuation(velocity):
    """De la velocidad MIDI a los 16 pasos de atenuación, que son de 2 dB."""
    return max(0, min(SILENT - 1, 2 + (127 - velocity) // 18))


def assign_voices(notes):
    """Reparte los canales del MIDI en las tres voces de tono, por altura.

    El canal de percusión va aparte, al ruido. Los demás se ordenan por altura
    promedio: el más agudo lleva la melodía y el más grave el bajo.
    """
    melodic = {}
    for note in notes:
        if note.channel != midi.DRUM_CHANNEL:
            melodic.setdefault(note.channel, []).append(note.pitch)

    order = sorted(melodic, key=lambda c: -sum(melodic[c]) / len(melodic[c]))
    voices = {}
    for index, channel in enumerate(order):
        # Con más de tres canales, los del medio comparten la voz del medio.
        voices[channel] = 0 if index == 0 else (
            TONE_VOICES - 1 if index == len(order) - 1 else 1)
    voices[midi.DRUM_CHANNEL] = NOISE_VOICE
    return voices


def timeline(notes, tempos, division):
    """Pasa las notas de ticks de MIDI a cuadros, con el tempo aplicado."""
    changes = sorted(tempos)
    marks = [(0, 0, changes[0][1])]     # (tick, segundo, microsegundos por negra)
    for tick, us in changes[1:]:
        last_tick, last_second, last_us = marks[-1]
        marks.append((tick, last_second + (tick - last_tick) / division
                      * last_us / 1e6, us))

    def to_frame(tick):
        base_tick, base_second, us = next(
            m for m in reversed(marks) if m[0] <= tick)
        second = base_second + (tick - base_tick) / division * us / 1e6
        return int(round(second * TICKS_PER_SECOND))

    for note in notes:
        note.start, note.end = to_frame(note.start), to_frame(note.end)
    return max((n.end for n in notes), default=0)


def render_frames(notes, voices, length):
    """El estado de las cuatro voces en cada cuadro: divisor y atenuación."""
    sounding = [[] for _ in range(4)]
    for note in notes:
        sounding[voices[note.channel]].append(note)

    frames = []
    for frame in range(length + 1):
        state = []
        for voice in range(4):
            live = [n for n in sounding[voice]
                    if n.start <= frame < max(n.end, n.start + 1)]
            if not live:
                state.append((None, SILENT))
                continue
            # La última que arrancó, como un sintetizador monofónico.
            note = max(live, key=lambda n: (n.start, n.pitch))
            if voice == NOISE_VOICE:
                # El ruido no tiene altura: sólo un golpe que se apaga solo.
                age = frame - note.start
                state.append((None, min(SILENT, attenuation(note.velocity) + age * 3)))
            else:
                state.append((divider(note.pitch), attenuation(note.velocity)))
        frames.append(state)
    return frames


def psg_stream(frames):
    """Las escrituras al PSG cuadro a cuadro, sólo cuando algo cambia.

    Formato: por cada registro, la cantidad de bytes, los bytes, y cuántos
    cuadros esperar después. El 0xFF como cantidad marca el final y vuelve a
    empezar.
    """
    records = []
    previous = [(None, SILENT)] * 4
    pending = []

    for state in frames:
        writes = []
        for voice in range(4):
            note, volume = state[voice]
            old_note, old_volume = previous[voice]
            if note is not None and note != old_note:
                # Latido de tono: 1 vv 0 dddd con los 4 bits bajos, y después
                # los 6 de arriba.
                writes.append(0x80 | (voice << 5) | (note & 0x0F))
                writes.append((note >> 4) & 0x3F)
            if volume != old_volume:
                writes.append(0x90 | (voice << 5) | (volume & 0x0F))
        previous = list(state)

        if writes:
            records.append((writes, 0))
        elif records:
            records[-1] = (records[-1][0], records[-1][1] + 1)
        else:
            pending.append(0)

    stream = bytearray()
    for writes, delay in records:
        while delay > 254:              # esperas largas, en pedazos
            stream += bytes([len(writes)]) + bytes(writes) + bytes([255])
            writes, delay = [], delay - 255
        stream += bytes([len(writes)]) + bytes(writes) + bytes([delay + 1])
    stream += bytes([0xFF])
    return stream


def build_stream(map_id, game_dir=GAME_DIR):
    """El tema de un mapa como stream para el PSG.

    Devuelve siempre (nombre, stream, segundos, voces). Si el mapa no tiene un
    MIDI propio, el stream es sólo la marca de final y sale mudo.
    """
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    music = tree.map_music(map_id)
    name = music["name"] if music else ""
    path = (find_resource([game_dir], "Music", name, (".mid", ".wav"))
            if name else None)

    if not path or not path.lower().endswith(".mid"):
        return name, bytes([0xFF]), 0.0, {}

    notes, tempos, division = midi.read(path)
    length = timeline(notes, tempos, division)
    voices = assign_voices(notes)
    return (name, psg_stream(render_frames(notes, voices, length)),
            length / TICKS_PER_SECOND, voices)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=67)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("-o", "--output", default=os.path.join(REPO, "md/src/musicdata"))
    args = parser.parse_args()

    name, stream, seconds, voices = build_stream(args.map_id, args.game_dir)

    if len(stream) <= 1:
        print("El mapa %d no tiene un MIDI propio (%s): sale mudo."
              % (args.map_id, name or "sin música"))
    else:
        print("Mapa %d: %s, %.0f s" % (args.map_id, name, seconds))
        print("  canales del MIDI -> voces del PSG: %s"
              % {c: ("ruido" if v == NOISE_VOICE else v)
                 for c, v in sorted(voices.items())})

    with open(args.output + ".h", "w") as handle:
        handle.write("/* Generado por tools/md_music.py. No editar. */\n"
                     "#ifndef MUSICDATA_H\n#define MUSICDATA_H\n\n"
                     "#define MUSIC_NAME  \"%s\"\n"
                     "#define MUSIC_BYTES %d\n\n"
                     "extern const unsigned char md_music[%d];\n\n#endif\n"
                     % (name, len(stream), len(stream)))
    with open(args.output + ".c", "w") as handle:
        handle.write("/* Generado por tools/md_music.py. No editar. */\n"
                     "#include \"musicdata.h\"\n\n"
                     "const unsigned char md_music[%d] = {\n" % len(stream))
        for i in range(0, len(stream), 16):
            handle.write("    " + " ".join("0x%02X," % b for b in stream[i:i + 16])
                         + "\n")
        handle.write("};\n")

    print("  %d bytes -> %s.c / %s.h" % (len(stream), args.output, args.output))


if __name__ == "__main__":
    main()
