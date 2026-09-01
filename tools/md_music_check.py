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
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import md_music


def vgm_psg_writes(path):
    """Los bytes que el VGM escribe al PSG, en orden, y cuánto duró."""
    data = open(path, "rb").read()
    if data[:4] != b"Vgm ":
        sys.exit("%s no es un VGM" % path)

    offset = struct.unpack("<I", data[0x34:0x38])[0]
    pos = 0x34 + offset if offset else 0x40
    writes = bytearray()
    samples = 0

    while pos < len(data):
        command = data[pos]
        if command == 0x50:                     # escritura al PSG
            writes.append(data[pos + 1])
            pos += 2
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
        elif command in (0x52, 0x53):           # YM2612, que no usamos
            pos += 3
        else:
            pos += 1
    return bytes(writes), samples / 44100.0


def stream_psg_writes(stream):
    """Los bytes del stream del conversor, sin los contadores ni las esperas."""
    writes = bytearray()
    pos = 0
    while pos < len(stream):
        count = stream[pos]
        pos += 1
        if count == 0xFF:
            break
        writes += stream[pos:pos + count]
        pos += count + 1        # los bytes, y después la espera
    return bytes(writes)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("vgm")
    parser.add_argument("--map-id", type=int, default=67)
    parser.add_argument("--game-dir", default=md_music.GAME_DIR)
    args = parser.parse_args()

    name, stream, _, _ = md_music.build_stream(args.map_id, args.game_dir)
    captured, seconds = vgm_psg_writes(args.vgm)
    expected = stream_psg_writes(stream)

    if len(stream) <= 1:
        print("El mapa %d no tiene música propia: no hay nada que comparar."
              % args.map_id)
        return 0

    print("VGM: %d escrituras al PSG en %.1f s" % (len(captured), seconds))
    print("Conversor (%s): %d escrituras en total" % (name, len(expected)))

    # El comienzo de la grabación es el volcado del estado del chip, que no
    # está en el stream. Se busca dónde engancha el resto.
    for skip in range(len(captured)):
        tail = captured[skip:]
        if len(tail) < 32:
            break
        start = expected.find(tail)
        if start >= 0:
            print("Coinciden: los %d bytes desde el %d de la captura son los "
                  "del conversor desde el %d." % (len(tail), skip, start))
            print("IDÉNTICOS")
            return 0

    print("NO COINCIDEN: lo que la ROM escribe no es lo que generó el conversor.")
    print("  capturado:", " ".join("%02X" % b for b in captured[:24]))
    print("  esperado: ", " ".join("%02X" % b for b in expected[:24]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
