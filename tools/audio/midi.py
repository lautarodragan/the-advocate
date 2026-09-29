"""Minimal MIDI file reader: the notes and the controllers that are heard.

When each note starts and ends, on which channel and with which velocity,
the tempo changes, the first instrument of each channel, and the
controllers that change how an already sounding note sounds: volume (CC7),
pan (CC10), expression (CC11) and pitch bend, which are returned as
`Control`. The sustain pedal (CC64) is not returned: it lengthens the notes,
which is what a synthesizer does with it. The rest —reverb, chorus,
modulation, the AWE32's NRPNs, aftertouch— is dropped: see "El paso 3" in
`workflow/tasks/todo/la-calidad-de-la-musica.md` for which songs use it.
"""

import struct

NOTE_OFF = 0x80
NOTE_ON = 0x90
CONTROL = 0xB0
PROGRAM = 0xC0
BEND_STATUS = 0xE0
META = 0xFF
TEMPO = 0x51
DRUM_CHANNEL = 9        # the standard's channel 10, counting from zero

# The controllers that are returned, with their General MIDI number, and the
# value a channel has before the MIDI says anything: GM's, which are
# fluidsynth's.
VOLUME, PAN, EXPRESSION = 7, 10, 11
# Pitch bend is not a controller, but it travels the same way: it is numbered
# outside the CC range so it does not clash with any of them. Its value
# already comes in semitones, with the channel's range applied.
BEND = 0x100
DEFAULTS = {VOLUME: 100, PAN: 64, EXPRESSION: 127, BEND: 0.0}

SUSTAIN = 64
# What the pitch bend range needs: RPN 0 is selected with CC101 and CC100 at
# zero, and the value arrives through CC6 (semitones) and CC38 (cents). CC99
# and CC98 select an NRPN, and from then on CC6 no longer belongs to the RPN.
_DATA_MSB, _DATA_LSB = 6, 38
_NRPN_LSB, _NRPN_MSB, _RPN_LSB, _RPN_MSB = 98, 99, 100, 101
_CRUDOS = {VOLUME, PAN, EXPRESSION, SUSTAIN, _DATA_MSB, _DATA_LSB,
           _NRPN_LSB, _NRPN_MSB, _RPN_LSB, _RPN_MSB}
BEND_RANGE = 2          # semitones, GM's as long as nobody changes it


class Note:
    __slots__ = ("start", "end", "channel", "pitch", "velocity")

    def __init__(self, start, channel, pitch, velocity):
        self.start = start
        self.end = start
        self.channel = channel
        self.pitch = pitch
        self.velocity = velocity


class Control:
    """A controller that changes on a channel: `number` is VOLUME, PAN,
    EXPRESSION or BEND. `end` is there only so that `musica.timeline` converts
    it to frames the same as a note."""

    __slots__ = ("start", "end", "channel", "number", "value")

    def __init__(self, start, channel, number, value):
        self.start = self.end = start
        self.channel = channel
        self.number = number
        self.value = value


def _varlen(data, pos):
    """The times between events go in 7 bits per byte; the 8th means "more follows"."""
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def _track(data, pos, end, notes, tempos, programs, raw):
    """Walks a track collecting notes, tempos and instruments, in ticks.

    The controllers go raw into `raw` and are resolved later with all the
    tracks together: a channel spreads its events over several tracks
    —`escape_newyork` has channel 4 in four of them—, so the bend range or the
    pedal one track chose is used by another.
    """
    time = 0
    status = 0
    sounding = {}

    while pos < end:
        delta, pos = _varlen(data, pos)
        time += delta
        if pos >= end:
            break               # the track ends right after the last delta

        if data[pos] & 0x80:
            status = data[pos]
            pos += 1
        # Otherwise it is "running status": the last one repeats and the byte is already data.

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
            programs.setdefault(channel, data[pos])   # the first one of each channel
            pos += 1
        elif kind == 0xD0:
            pos += 1                    # channel aftertouch
        elif kind == CONTROL:
            if data[pos] in _CRUDOS:
                raw.append((time, channel, data[pos], data[pos + 1]))
            pos += 2
        elif kind == BEND_STATUS:
            raw.append((time, channel, BEND,
                        (data[pos] | data[pos + 1] << 7) - 8192))
            pos += 2
        else:
            pos += 2                    # the rest are two bytes

    for note in sounding.values():
        note.end = time


def _controls(raw, notes):
    """The raw controllers of all the tracks, in time order, to `Control`: the
    bend to semitones with its channel's range, and the pedal applied to the
    notes."""
    controls = []
    param = {}                  # channel -> selected (is RPN, MSB, LSB)
    semitones = {}              # channel -> bend range
    pedal = {}                  # channel -> [(down, up)]
    down = {}
    for time, channel, number, value in sorted(raw, key=lambda e: e[0]):
        if number == BEND:
            controls.append(Control(time, channel, BEND,
                                    value / 8192.0 * semitones.get(
                                        channel, BEND_RANGE)))
        elif number in (VOLUME, PAN, EXPRESSION):
            controls.append(Control(time, channel, number, value))
        elif number == SUSTAIN:
            if value >= 64 and channel not in down:
                down[channel] = time
            elif value < 64 and channel in down:
                pedal.setdefault(channel, []).append((down.pop(channel), time))
        elif number in (_RPN_MSB, _RPN_LSB, _NRPN_MSB, _NRPN_LSB):
            rpn = number in (_RPN_MSB, _RPN_LSB)
            # Unselected, both are 127: the "null" RPN. Measured with
            # fluidsynth: a CC101 at 0 without its CC100 does not touch the range.
            actual = param.get(channel, (rpn, 127, 127))
            if actual[0] != rpn:
                actual = (rpn, 127, 127)
            msb = value if number in (_RPN_MSB, _NRPN_MSB) else actual[1]
            lsb = value if number in (_RPN_LSB, _NRPN_LSB) else actual[2]
            param[channel] = (rpn, msb, lsb)
        elif param.get(channel) == (True, 0, 0):
            # RPN 0, the bend range. **No cap**: `3D-Galax` asks for 95
            # semitones and fluidsynth honors them —measured—; a GS
            # synthesizer would cap it at 24. We follow fluidsynth, which is
            # what we compare against and where the MSU-1 track comes from.
            entero = int(semitones.get(channel, BEND_RANGE))
            fraccion = semitones.get(channel, BEND_RANGE) - entero
            if number == _DATA_MSB:
                semitones[channel] = value + fraccion
            else:
                semitones[channel] = entero + value / 100.0
    if down or pedal:
        # A note released with the pedal down keeps sounding until it goes
        # up, or until the same key is played again. If it never goes up,
        # until the end of the song.
        final = max((n.end for n in notes), default=0)
        for channel, time in down.items():
            pedal.setdefault(channel, []).append((time, final))
        siguiente = {}
        for note in sorted(notes, key=lambda n: -n.start):
            clave = (note.channel, note.pitch)
            for baja, sube in pedal.get(note.channel, ()):
                if baja < note.end < sube:
                    note.end = min(sube, siguiente.get(clave, sube))
                    break
            siguiente[clave] = note.start
    return controls


def read(path):
    """Returns (notes, tempos, ticks per quarter note, instrument of each
    channel, controllers)."""
    data = open(path, "rb").read()
    if data[:4] != b"MThd":
        raise ValueError("%s is not a MIDI file" % path)

    header = struct.unpack(">I", data[4:8])[0]
    _, tracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise ValueError("MIDI with SMPTE division, not supported")

    notes, tempos, programs, raw = [], [], {}, []
    pos = 8 + header
    for _ in range(tracks):
        if data[pos:pos + 4] != b"MTrk":
            break
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        _track(data, pos + 8, pos + 8 + length, notes, tempos, programs, raw)
        pos += 8 + length

    controls = _controls(raw, notes)
    notes.sort(key=lambda n: (n.start, n.pitch))
    return notes, tempos or [(0, 500000)], division, programs, controls
