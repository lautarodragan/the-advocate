#!/usr/bin/env python3
"""Convierte el MIDI de un mapa a un stream para los dos chips de sonido.

La Mega Drive tiene el YM2612, con seis voces de síntesis FM, y el PSG, con tres
de onda cuadrada y una de ruido. Un MIDI de RM2k trae cuatro o cinco canales con
acordes y una polifonía mediana de nueve notas, así que igual hay que reducir —
pero con nueve voces en vez de tres se reproduce el 95% del tiempo-nota en lugar
del 56%.

Dos decisiones mandan en el resultado:

  * **Cuántas voces le toca a cada canal del MIDI.** No es una por canal: el
    canal de acordes necesita tres y el de melodía con una alcanza. Se reparten
    de a una, siempre a la que más cobertura gane, que es la misma métrica con
    la que se mide la pérdida.
  * **Qué parche FM le toca a cada instrumento.** Eso no se calcula, se elige de
    oído; el banco está en ym2612.py y es un punto de partida.

Lo que sale es un log de escrituras a los chips con el tiempo entre medio,
parecido a un VGM: la ROM sólo va escupiendo bytes al puerto que corresponda.

Uso:
    python3 tools/md_music.py --map-id 67 -o md/src/musicdata
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
import midi
import ym2612
from render_map import GAME_DIR, REPO, find_resource

PSG_CLOCK = 3579545
MAX_DIVIDER = 1023
PSG_TONES = 3
PSG_NOISE = 3
SILENT = 15
TICKS_PER_SECOND = 60

# Opcodes del stream.
OP_PSG = 0x00
OP_YM1 = 0x01
OP_YM2 = 0x02
OP_WAIT = 0x03
OP_END = 0xFF


# --- reparto de voces -------------------------------------------------------

def note_time(notes):
    """Cuánto tiempo suena cada cantidad de notas a la vez, en cuadros."""
    edges = collections.Counter()
    for note in notes:
        if note.end > note.start:
            edges[note.start] += 1
            edges[note.end] -= 1

    spans = collections.Counter()
    playing, previous = 0, None
    for at in sorted(edges):
        if previous is not None and playing > 0:
            spans[playing] += at - previous
        playing += edges[at]
        previous = at
    return spans


def coverage(spans, voices):
    """Qué fracción del tiempo-nota se reproduce con esa cantidad de voces."""
    total = sum(count * span for count, span in spans.items())
    if not total:
        return 1.0
    return sum(min(count, voices) * span for count, span in spans.items()) / total


def share_voices(channels, budget):
    """Reparte las voces de a una, siempre a la que más cobertura gane.

    Se pondera por cuánto suena cada canal: ganar diez puntos en el que lleva
    la melodía vale más que ganarlos en uno que aparece dos veces.
    """
    if not channels:
        return {}

    given = {channel: 1 for channel in channels}
    weight = {channel: sum(c * s for c, s in spans.items())
              for channel, spans in channels.items()}

    while sum(given.values()) < budget:
        def gain(channel):
            spans = channels[channel]
            return weight[channel] * (coverage(spans, given[channel] + 1)
                                      - coverage(spans, given[channel]))

        best = max(channels, key=gain)
        if gain(best) <= 0:
            break
        given[best] += 1
    return given


def assign(notes, programs):
    """Qué voces del hardware le tocan a cada canal del MIDI.

    La percusión va al ruido del PSG. De los melódicos, los que más suenan se
    llevan las seis voces de FM y el resto cae en los tonos del PSG, que suenan
    peor pero suenan.
    """
    melodic = {}
    for note in notes:
        if note.channel != midi.DRUM_CHANNEL:
            melodic.setdefault(note.channel, []).append(note)

    spans = {channel: note_time(ns) for channel, ns in melodic.items()}
    busiest = sorted(spans, key=lambda c: -sum(a * b for a, b in spans[c].items()))

    fm_channels = busiest[:ym2612.CHANNELS]
    psg_channels = busiest[ym2612.CHANNELS:]

    voices = {}
    next_fm = 0
    for channel, count in share_voices({c: spans[c] for c in fm_channels},
                                       ym2612.CHANNELS).items():
        voices[channel] = [("fm", next_fm + i) for i in range(count)]
        next_fm += count

    for index, channel in enumerate(psg_channels[:PSG_TONES]):
        voices[channel] = [("psg", index)]

    if any(n.channel == midi.DRUM_CHANNEL for n in notes):
        voices[midi.DRUM_CHANNEL] = [("noise", PSG_NOISE)]
    return voices


# --- tiempo -----------------------------------------------------------------

def timeline(notes, tempos, division):
    """Pasa las notas de ticks de MIDI a cuadros, con el tempo aplicado."""
    marks = [(0, 0.0, sorted(tempos)[0][1])]
    for tick, us in sorted(tempos)[1:]:
        last_tick, last_second, last_us = marks[-1]
        marks.append((tick, last_second + (tick - last_tick) / division
                      * last_us / 1e6, us))

    def to_frame(tick):
        base_tick, base_second, us = next(m for m in reversed(marks)
                                          if m[0] <= tick)
        return int(round((base_second + (tick - base_tick) / division * us / 1e6)
                         * TICKS_PER_SECOND))

    for note in notes:
        note.start, note.end = to_frame(note.start), to_frame(note.end)
        note.end = max(note.end, note.start + 1)
    return max((n.end for n in notes), default=0)


# --- PSG --------------------------------------------------------------------

def psg_divider(pitch):
    """El divisor del PSG, subiendo la nota de octava si es muy grave."""
    while True:
        hertz = 440.0 * 2.0 ** ((pitch - 69) / 12.0)
        value = int(round(PSG_CLOCK / (32.0 * hertz)))
        if value <= MAX_DIVIDER:
            return max(1, value)
        pitch += 12


def psg_attenuation(velocity):
    return max(0, min(SILENT - 1, 2 + (127 - velocity) // 18))


# --- generación del stream --------------------------------------------------

def build_events(notes, voices, programs):
    """Las escrituras a los chips, con el cuadro en que van.

    Cada canal del MIDI tiene su grupo de voces; cuando arranca una nota se le
    da la que lleva más tiempo libre, y si no hay ninguna se le saca a la más
    vieja. Es lo que hace un sintetizador cuando se le acaba la polifonía.
    """
    events = collections.defaultdict(list)

    for write in ym2612.init():
        events[0].append(write)

    # El parche de cada voz de FM se carga una sola vez.
    patches = {}
    for channel, group in voices.items():
        patch = ym2612.for_program(programs.get(channel, 0))
        patches[channel] = patch
        for kind, index in group:
            if kind == "fm":
                events[0] += ym2612.load_patch(index, patch)

    busy = {}        # voz -> (cuándo se libera, nota que la tiene)
    for note in sorted(notes, key=lambda n: n.start):
        group = voices.get(note.channel)
        if not group:
            continue

        free = [v for v in group if busy.get(v, (0, None))[0] <= note.start]
        voice = (min(free, key=lambda v: busy.get(v, (0, None))[0]) if free
                 else min(group, key=lambda v: busy[v][0]))
        kind, index = voice

        if not free:                      # se la sacamos a una que sonaba
            if kind == "fm":
                events[note.start] += ym2612.note_off(index)
        busy[voice] = (note.end, note)

        if kind == "fm":
            patch = patches[note.channel]
            events[note.start] += ym2612.note_off(index)
            events[note.start] += ym2612.volume(index, patch, note.velocity)
            events[note.start] += ym2612.note_on(index, note.pitch)
            events[note.end] += ym2612.note_off(index)
        elif kind == "psg":
            divider = psg_divider(note.pitch)
            events[note.start] += [
                ("psg", 0x80 | (index << 5) | (divider & 0x0F)),
                ("psg", (divider >> 4) & 0x3F),
                ("psg", 0x90 | (index << 5) | psg_attenuation(note.velocity)),
            ]
            events[note.end].append(("psg", 0x90 | (index << 5) | SILENT))
        else:
            # El ruido no tiene altura: un golpe que se apaga en unos cuadros.
            level = psg_attenuation(note.velocity)
            events[note.start].append(("psg", 0xE0 | 0x04))     # ruido blanco
            for step in range(6):
                frame = note.start + step * 2
                events[frame].append(
                    ("psg", 0xF0 | min(SILENT, level + step * 3)))
    return events


def pack(events, length):
    """Los eventos como stream de opcodes, con las esperas entre medio."""
    stream = bytearray()
    previous = 0

    for frame in sorted(events):
        if frame > length:
            break
        wait = frame - previous
        while wait > 0:
            step = min(255, wait)
            stream += bytes([OP_WAIT, step])
            wait -= step
        previous = frame

        for write in events[frame]:
            if write[0] == "psg":
                stream += bytes([OP_PSG, write[1] & 0xFF])
            else:
                part, register, value = write
                stream += bytes([OP_YM1 if part == 1 else OP_YM2,
                                 register & 0xFF, value & 0xFF])

    stream.append(OP_END)
    return bytes(stream)


def build_stream(map_id, game_dir=GAME_DIR):
    """El tema de un mapa como stream para los chips.

    Devuelve siempre (nombre, stream, segundos, resumen). Si el mapa no tiene un
    MIDI propio, el stream es sólo la marca de final y sale mudo.
    """
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    music = tree.map_music(map_id)
    name = music["name"] if music else ""
    path = (find_resource([game_dir], "Music", name, (".mid", ".wav"))
            if name else None)

    if not path or not path.lower().endswith(".mid"):
        return name, bytes([OP_END]), 0.0, {}

    notes, tempos, division, programs = midi.read(path)
    length = timeline(notes, tempos, division)
    voices = assign(notes, programs)
    stream = pack(build_events(notes, voices, programs), length)

    spans = {c: note_time([n for n in notes if n.channel == c])
             for c in {n.channel for n in notes}}
    summary = {
        "voices": {c: [("ruido" if k == "noise" else "%s%d" % (k, i))
                       for k, i in g] for c, g in sorted(voices.items())},
        "patches": {c: ym2612.for_program(programs.get(c, 0))["name"]
                    for c, g in sorted(voices.items())
                    if any(k == "fm" for k, _ in g)},
        "coverage": sum(coverage(spans[c], len(voices.get(c, [])))
                        * sum(a * b for a, b in spans[c].items())
                        for c in spans)
        / max(1, sum(sum(a * b for a, b in spans[c].items()) for c in spans)),
    }
    return name, stream, length / TICKS_PER_SECOND, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=67)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("-o", "--output",
                        default=os.path.join(REPO, "md/src/musicdata"))
    args = parser.parse_args()

    name, stream, seconds, summary = build_stream(args.map_id, args.game_dir)

    if len(stream) <= 1:
        print("El mapa %d no tiene un MIDI propio (%s): sale mudo."
              % (args.map_id, name or "sin música"))
    else:
        print("Mapa %d: %s, %.0f s" % (args.map_id, name, seconds))
        print("  voces:   %s" % summary["voices"])
        print("  parches: %s" % summary["patches"])
        print("  se reproduce el %.0f%% del tiempo-nota"
              % (100 * summary["coverage"]))

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
