"""Lector mínimo de archivos MIDI: lo justo para sacar las notas.

No interpreta controladores, pitch bend ni instrumentos — sólo cuándo empieza y
cuándo termina cada nota, en qué canal y con qué velocidad, más los cambios de
tempo. Es todo lo que se puede aprovechar en el PSG de la Mega Drive, que tiene
tres canales de onda cuadrada y uno de ruido.
"""

import struct

NOTE_OFF = 0x80
NOTE_ON = 0x90
PROGRAM = 0xC0
META = 0xFF
TEMPO = 0x51
DRUM_CHANNEL = 9        # el canal 10 del estándar, contando desde cero


class Note:
    __slots__ = ("start", "end", "channel", "pitch", "velocity")

    def __init__(self, start, channel, pitch, velocity):
        self.start = start
        self.end = start
        self.channel = channel
        self.pitch = pitch
        self.velocity = velocity


def _varlen(data, pos):
    """Los tiempos entre eventos van en 7 bits por byte, el 8 indica "sigue"."""
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def _track(data, pos, end, notes, tempos, programs):
    """Recorre una pista acumulando notas, tempos e instrumentos, en ticks."""
    time = 0
    status = 0
    sounding = {}

    while pos < end:
        delta, pos = _varlen(data, pos)
        time += delta
        if pos >= end:
            break               # la pista termina justo después del último delta

        if data[pos] & 0x80:
            status = data[pos]
            pos += 1
        # Si no, es "running status": se repite el último y el byte ya es dato.

        kind, channel = status & 0xF0, status & 0x0F

        if status == META:
            meta = data[pos]
            length, pos = _varlen(data, pos + 1)
            if meta == TEMPO:
                tempos.append((time, int.from_bytes(data[pos:pos + 3], "big")))
            pos += length
        elif status in (0xF0, 0xF7):
            length, pos = _varlen(data, pos)
            pos += length
        elif kind in (NOTE_ON, NOTE_OFF):
            pitch, velocity = data[pos], data[pos + 1]
            pos += 2
            key = (channel, pitch)
            if kind == NOTE_ON and velocity:
                if key in sounding:
                    sounding[key].end = time
                note = Note(time, channel, pitch, velocity)
                sounding[key] = note
                notes.append(note)
            elif key in sounding:
                sounding.pop(key).end = time
        elif kind == PROGRAM:
            programs.setdefault(channel, data[pos])   # el primero de cada canal
            pos += 1
        elif kind == 0xD0:
            pos += 1                    # aftertouch de canal
        else:
            pos += 2                    # el resto son dos bytes

    for note in sounding.values():
        note.end = time


def read(path):
    """Devuelve (notas, tempos, ticks por negra, instrumento de cada canal)."""
    data = open(path, "rb").read()
    if data[:4] != b"MThd":
        raise ValueError("%s no es un MIDI" % path)

    header = struct.unpack(">I", data[4:8])[0]
    _, tracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise ValueError("MIDI con división SMPTE, no soportado")

    notes, tempos, programs = [], [], {}
    pos = 8 + header
    for _ in range(tracks):
        if data[pos:pos + 4] != b"MTrk":
            break
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        _track(data, pos + 8, pos + 8 + length, notes, tempos, programs)
        pos += 8 + length

    notes.sort(key=lambda n: (n.start, n.pitch))
    tempos.sort()
    return notes, tempos or [(0, 500000)], division, programs
