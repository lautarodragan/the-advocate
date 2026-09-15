#!/usr/bin/env python3
"""Muestra qué trae el SoundFont para los instrumentos que usa el juego.

Leer el banco lo hace `brr sf2`, y `brr sf2 --list-samples` ya lista todo lo
que un banco tiene. Lo que esto agrega es lo único que el binario no puede
saber, porque no sabe nada de este juego: **qué programas y qué golpes pide el
MIDI de un mapa**. Con eso se decide el presupuesto de ARAM antes de convertir
nada, que es para lo que existe.

De cada muestra importa cuántos cuadros tiene y si trae loop: sin loop, una
nota sostenida se corta, y con loop podemos guardar sólo el ataque más un
ciclo.

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
import muestras_brr
from render_map import GAME_DIR, find_resource

SOUNDFONT = "/usr/share/soundfonts/FluidR3_GM.sf2"
REFERENCE_KEY = 60      # do central: la nota con la que se elige la zona
DRUM_BANK = 128         # donde General MIDI guarda los kits de percusión
DRUM_PROGRAM = 0        # el kit estándar


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


def report_drum(soundfont, note, hits):
    """La percusión vive en el banco 128, y ahí cada nota es un instrumento.

    Un kit no está multi-muestreado por altura como un piano: cada tecla trae su
    propia grabación —el bombo, el charles, el plato— y por eso hay que pedir
    una zona por cada nota que el MIDI use, no una por preset.
    """
    sample = muestras_brr.extraer("drum:%d" % note, soundfont)
    if sample is None:
        print("  nota %3d (%4d golpes)  SIN MUESTRA" % (note, hits))
        return None

    print("  nota %3d (%4d golpes)  %-26s %6d cuadros a %5d Hz, %s"
          % (note, hits, sample.nombre[:26], sample.cuadros, sample.tasa,
             "loop" if sample.loop else "sin loop"))
    return sample


def report(soundfont, program, label=""):
    sample = muestras_brr.extraer("program:%d@%d" % (program, REFERENCE_KEY),
                                  soundfont)
    if sample is None:
        print("  programa %3d %-14s SIN PRESET" % (program, label))
        return None

    print("  programa %3d %-14s %-22s %6d cuadros a %5d Hz, nota %3d, %s"
          % (program, label, sample.nombre[:22], sample.cuadros, sample.tasa,
             sample.nota, "loop" if sample.loop else "sin loop"))
    if sample.loop:
        loop = sample.loop_end - sample.loop_start
        print("               loop de %d cuadros (%.0f ms)"
              % (loop, 1000.0 * loop / sample.tasa))
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

    presets = muestras_brr.presets(args.soundfont)
    print("%s: %d presets" % (os.path.basename(args.soundfont), len(presets)))
    print()

    if args.programs:
        print("Programas pedidos:")
        for program in args.programs:
            report(args.soundfont, program)
        return

    if args.drums:
        hits = drums_of_map(args.map_id, args.game_dir)
        kit = [n for b, p, n in presets
               if b == DRUM_BANK and p == DRUM_PROGRAM]
        print("Percusión del mapa %d, banco %d preset %d (%s):"
              % (args.map_id, DRUM_BANK, DRUM_PROGRAM,
                 kit[0] if kit else "no está"))
        total = 0
        for note, count in hits.items():
            sample = report_drum(args.soundfont, note, count)
            if sample:
                total += sample.cuadros
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
        report(args.soundfont, program, "canal %s" % ",".join(map(str, channels)))


if __name__ == "__main__":
    main()
