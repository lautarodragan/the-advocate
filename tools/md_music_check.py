#!/usr/bin/env python3
"""Compara lo que la ROM le escribe al PSG contra lo que pidió el conversor.

blastem graba un VGM, que es un log de escrituras a los chips de sonido con el
tiempo entre medio. El conversor de música produce esencialmente lo mismo, así
que se pueden comparar byte a byte: si coinciden, la ROM está reproduciendo
exactamente la música que se generó.

La grabación arranca unos segundos después del arranque y empieza con un
volcado del estado del chip, así que lo que se busca es dónde encaja lo
capturado dentro del stream completo.

Uso:
    python3 tools/md_music_check.py md/shots/musica.vgm --map-id 67
"""

import argparse
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import md_music


def vgm_writes(path):
    """Las escrituras a los chips que hay en un VGM, en orden, y cuánto duró.

    Cada una queda como ("psg", byte) o ("ym", parte, registro, valor), que es
    lo mismo que produce el conversor.
    """
    data = open(path, "rb").read()
    if data[:4] != b"Vgm ":
        sys.exit("%s no es un VGM" % path)

    offset = struct.unpack("<I", data[0x34:0x38])[0]
    pos = 0x34 + offset if offset else 0x40
    writes = []
    samples = 0

    while pos < len(data):
        command = data[pos]
        if command == 0x50:                     # PSG
            writes.append(("psg", data[pos + 1]))
            pos += 2
        elif command in (0x52, 0x53):           # YM2612, parte 1 y parte 2
            writes.append(("ym", 1 if command == 0x52 else 2,
                           data[pos + 1], data[pos + 2]))
            pos += 3
        elif command == 0x61:
            samples += struct.unpack("<H", data[pos + 1:pos + 3])[0]
            pos += 3
        elif command == 0x62:                   # un cuadro de NTSC
            samples += 735
            pos += 1
        elif command == 0x63:                   # un cuadro de PAL
            samples += 882
            pos += 1
        elif 0x70 <= command <= 0x7F:
            samples += (command & 0x0F) + 1
            pos += 1
        elif command == 0x66:
            break
        else:
            pos += 1
    return writes, samples / 44100.0


def stream_writes(stream):
    """Las escrituras del stream del conversor, sin las esperas."""
    writes = []
    pos = 0
    while pos < len(stream):
        op = stream[pos]
        if op == md_music.OP_END:
            break
        if op == md_music.OP_WAIT:
            pos += 2
        elif op == md_music.OP_PSG:
            writes.append(("psg", stream[pos + 1]))
            pos += 2
        else:
            writes.append(("ym", 1 if op == md_music.OP_YM1 else 2,
                           stream[pos + 1], stream[pos + 2]))
            pos += 3
    return writes


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("vgm")
    parser.add_argument("--map-id", type=int, default=67)
    parser.add_argument("--game-dir", default=md_music.GAME_DIR)
    args = parser.parse_args()

    name, stream, _, _ = md_music.build_stream(args.map_id, args.game_dir)
    captured, seconds = vgm_writes(args.vgm)
    expected = stream_writes(stream)

    if len(stream) <= 1:
        print("El mapa %d no tiene música propia: no hay nada que comparar."
              % args.map_id)
        return 0

    kinds = collections.Counter(w[0] for w in captured)
    print("VGM: %d escrituras en %.1f s (%d al PSG, %d al YM2612)"
          % (len(captured), seconds, kinds["psg"], kinds["ym"]))
    kinds = collections.Counter(w[0] for w in expected)
    print("Conversor (%s): %d en total (%d al PSG, %d al YM2612)"
          % (name, len(expected), kinds["psg"], kinds["ym"]))

    # El comienzo de la grabación es el volcado del estado del chip, que no
    # está en el stream. Se busca dónde engancha el resto.
    for skip in range(len(captured)):
        tail = captured[skip:]
        if len(tail) < 32:
            break
        start = _find(expected, tail)
        if start >= 0:
            print("Coinciden: los %d bytes desde el %d de la captura son los "
                  "del conversor desde el %d." % (len(tail), skip, start))
            print("IDÉNTICOS")
            return 0

    print("NO COINCIDEN: lo que la ROM escribe no es lo que generó el conversor.")
    print("  capturado:", captured[:6])
    print("  esperado: ", expected[:6])
    return 1


def _find(haystack, needle):
    """Dónde empieza `needle` dentro de `haystack`, o -1."""
    for start in range(len(haystack) - len(needle) + 1):
        if haystack[start:start + len(needle)] == needle:
            return start
    return -1


if __name__ == "__main__":
    sys.exit(main())
