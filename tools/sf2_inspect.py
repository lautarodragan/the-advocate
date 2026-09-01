#!/usr/bin/env python3
"""Muestra qué trae el SoundFont para los instrumentos que usa el juego.

Sirve para dos cosas: verificar que el lector de sf2.py entiende el archivo, y
decidir el presupuesto de ARAM antes de convertir nada. Lo que importa de cada
muestra es cuántos cuadros tiene y si trae loop: sin loop, una nota sostenida se
corta, y con loop podemos guardar sólo el ataque más un ciclo.

Uso:
    python3 tools/sf2_inspect.py --map-id 67
    python3 tools/sf2_inspect.py --programs 0 48 33
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
import midi
import sf2
from render_map import GAME_DIR, find_resource

SOUNDFONT = "/usr/share/soundfonts/FluidR3_GM.sf2"
REFERENCE_KEY = 60      # do central: la nota con la que se elige la zona
DRUM_BANK = 128         # donde General MIDI guarda los kits de percusión
DRUM_PROGRAM = 0        # el kit estándar

LOOP_NAMES = {sf2.LOOP_NONE: "sin loop",
              sf2.LOOP_CONTINUOUS: "loop",
              sf2.LOOP_UNTIL_RELEASE: "loop hasta soltar"}


def drums_of_map(map_id, game_dir):
    """Qué notas de percusión usa el MIDI, y cuántas veces cada una."""
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    music = tree.map_music(map_id)
    path = find_resource([game_dir], "Music", music["name"], (".mid", ".wav"))
    if not path or not path.lower().endswith(".mid"):
        return {}

    notes, _tempos, _division, _programs = midi.read(path)
    hits = collections.Counter(n.pitch for n in notes
                               if n.channel == midi.DRUM_CHANNEL)
    return dict(hits.most_common())


def programs_of_map(map_id, game_dir):
    """Los instrumentos que pide el MIDI de un mapa, por canal."""
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    music = tree.map_music(map_id)
    path = find_resource([game_dir], "Music", music["name"], (".mid", ".wav"))
    if not path or not path.lower().endswith(".mid"):
        return {}, music["name"]

    notes, _tempos, _division, programs = midi.read(path)
    used = {}
    for note in notes:
        if note.channel != midi.DRUM_CHANNEL:
            used.setdefault(note.channel, programs.get(note.channel, 0))
    return used, music["name"]


def report_drum(font, note, hits):
    """La percusión vive en el banco 128, y ahí cada nota es un instrumento.

    Un kit no está multi-muestreado por altura como un piano: cada tecla trae su
    propia grabación —el bombo, el charles, el plato— y por eso hay que pedir
    una zona por cada nota que el MIDI use, no una por preset.
    """
    zone, sample = font.zone_for(DRUM_PROGRAM, note, bank=DRUM_BANK)
    if sample is None:
        print("  nota %3d (%4d golpes)  SIN MUESTRA" % (note, hits))
        return None

    modes = zone.get(sf2.GEN_SAMPLE_MODES, sf2.LOOP_NONE)
    print("  nota %3d (%4d golpes)  %-26s %6d cuadros a %5d Hz, %s"
          % (note, hits, sample.name[:26], sample.frames, sample.rate,
             LOOP_NAMES.get(modes, "?")))
    return sample


def report(font, program, label=""):
    zone, sample = font.zone_for(program, REFERENCE_KEY)
    if sample is None:
        print("  programa %3d %-14s SIN PRESET" % (program, label))
        return None

    modes = zone.get(sf2.GEN_SAMPLE_MODES, sf2.LOOP_NONE)
    loop = sample.loop_end - sample.loop_start
    root = zone.get(sf2.GEN_ROOT_KEY) or sample.root_key

    print("  programa %3d %-14s %-22s %6d cuadros a %5d Hz, nota %3d, %s"
          % (program, label, sample.name[:22], sample.frames, sample.rate,
             root, LOOP_NAMES.get(modes, "?")))
    if modes != sf2.LOOP_NONE:
        print("               loop de %d cuadros (%.0f ms)"
              % (loop, 1000.0 * loop / sample.rate))
    return sample


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=67)
    parser.add_argument("--programs", type=int, nargs="*")
    parser.add_argument("--drums", action="store_true",
                        help="la percusión del mapa en vez de los melódicos")
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--soundfont", default=SOUNDFONT)
    args = parser.parse_args()

    font = sf2.SoundFont(args.soundfont)
    print("%s: %d presets, %d instrumentos, %d muestras, %.0f MB de PCM"
          % (os.path.basename(args.soundfont), len(font.presets) - 1,
             len(font.instruments) - 1, len(font.samples) - 1,
             font.pcm_size / 1e6))
    print()

    if args.programs:
        print("Programas pedidos:")
        for program in args.programs:
            report(font, program)
        return

    if args.drums:
        hits = drums_of_map(args.map_id, args.game_dir)
        print("Percusión del mapa %d, banco %d preset %d (%s):"
              % (args.map_id, DRUM_BANK, DRUM_PROGRAM,
                 font.preset_name(font.find_preset(DRUM_PROGRAM, DRUM_BANK))
                 if font.find_preset(DRUM_PROGRAM, DRUM_BANK) is not None
                 else "no está"))
        total = 0
        for note, count in hits.items():
            sample = report_drum(font, note, count)
            if sample:
                total += sample.frames
        print("  %d cuadros en total antes de remuestrear" % total)
        return

    used, name = programs_of_map(args.map_id, args.game_dir)
    if not used:
        print("El mapa %d no tiene un MIDI propio." % args.map_id)
        return

    print("Mapa %d (%s), instrumentos por canal:" % (args.map_id, name))
    seen = collections.OrderedDict()
    for channel, program in sorted(used.items()):
        seen.setdefault(program, []).append(channel)
    for program, channels in seen.items():
        report(font, program, "canal %s" % ",".join(map(str, channels)))


if __name__ == "__main__":
    main()
