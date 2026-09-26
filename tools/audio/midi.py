"""Lector mínimo de archivos MIDI: las notas y los controladores que suenan.

Cuándo empieza y cuándo termina cada nota, en qué canal y con qué velocidad,
los cambios de tempo, el primer instrumento de cada canal, y los
controladores que cambian cómo suena una nota que ya sonaba: volumen (CC7),
paneo (CC10), expresión (CC11) y pitch bend, que se devuelven como
`Control`. El pedal (CC64) no se devuelve: alarga las notas, que es lo que
hace un sintetizador con él. Lo demás —reverb, chorus, modulación, los NRPN
del AWE32, el aftertouch— se tira: ver "El paso 3" en
`workflow/tasks/todo/la-calidad-de-la-musica.md` para qué temas lo usan.

Nació para el PSG de la Mega Drive, que no tenía qué hacer con los
controladores; los lee desde el 2026-09-26, para el S-DSP.
"""

import struct

NOTE_OFF = 0x80
NOTE_ON = 0x90
CONTROL = 0xB0
PROGRAM = 0xC0
BEND_STATUS = 0xE0
META = 0xFF
TEMPO = 0x51
DRUM_CHANNEL = 9        # el canal 10 del estándar, contando desde cero

# Los controladores que se devuelven, con el número de General MIDI, y el
# valor que tiene un canal antes de que el MIDI diga nada: los de GM, que son
# los de fluidsynth.
VOLUME, PAN, EXPRESSION = 7, 10, 11
# El pitch bend no es un controlador, pero viaja igual: se lo numera fuera
# del rango de los CC para que no choque con ninguno. Su valor ya viene en
# semitonos, con el rango del canal aplicado.
BEND = 0x100
DEFAULTS = {VOLUME: 100, PAN: 64, EXPRESSION: 127, BEND: 0.0}

SUSTAIN = 64
# Lo que hace falta para el rango del pitch bend: el RPN 0 se elige con
# CC101 y CC100 en cero, y el valor llega por CC6 (semitonos) y CC38
# (centésimos). CC99 y CC98 eligen un NRPN, y desde ahí CC6 ya no es del RPN.
_DATA_MSB, _DATA_LSB = 6, 38
_NRPN_LSB, _NRPN_MSB, _RPN_LSB, _RPN_MSB = 98, 99, 100, 101
_CRUDOS = {VOLUME, PAN, EXPRESSION, SUSTAIN, _DATA_MSB, _DATA_LSB,
           _NRPN_LSB, _NRPN_MSB, _RPN_LSB, _RPN_MSB}
BEND_RANGE = 2          # semitonos, el de GM mientras nadie lo cambie


class Note:
    __slots__ = ("start", "end", "channel", "pitch", "velocity")

    def __init__(self, start, channel, pitch, velocity):
        self.start = start
        self.end = start
        self.channel = channel
        self.pitch = pitch
        self.velocity = velocity


class Control:
    """Un controlador que cambia en un canal: `number` es VOLUME, PAN,
    EXPRESSION o BEND. `end` está sólo para que `musica.timeline` lo pase a
    cuadros igual que a una nota."""

    __slots__ = ("start", "end", "channel", "number", "value")

    def __init__(self, start, channel, number, value):
        self.start = self.end = start
        self.channel = channel
        self.number = number
        self.value = value


def _varlen(data, pos):
    """Los tiempos entre eventos van en 7 bits por byte, el 8 indica "sigue"."""
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def _track(data, pos, end, notes, tempos, programs, raw):
    """Recorre una pista acumulando notas, tempos e instrumentos, en ticks.

    Los controladores van crudos a `raw` y se resuelven después con todas las
    pistas juntas: un canal reparte sus eventos entre varias pistas
    —`escape_newyork` tiene el 4 en cuatro—, así que el rango del bend o el
    pedal que eligió una los usa otra.
    """
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
        elif kind == CONTROL:
            if data[pos] in _CRUDOS:
                raw.append((time, channel, data[pos], data[pos + 1]))
            pos += 2
        elif kind == BEND_STATUS:
            raw.append((time, channel, BEND,
                        (data[pos] | data[pos + 1] << 7) - 8192))
            pos += 2
        else:
            pos += 2                    # el resto son dos bytes

    for note in sounding.values():
        note.end = time


def _controls(raw, notes):
    """Los controladores crudos de todas las pistas, en orden de tiempo, a
    `Control`: el bend a semitonos con el rango de su canal, y el pedal
    aplicado a las notas."""
    controls = []
    param = {}                  # canal -> (es RPN, MSB, LSB) elegido
    semitones = {}              # canal -> rango del bend
    pedal = {}                  # canal -> [(baja, sube)]
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
            # Sin elegir, los dos valen 127: el RPN "nulo". Medido con
            # fluidsynth: un CC101 en 0 sin su CC100 no toca el rango.
            actual = param.get(channel, (rpn, 127, 127))
            if actual[0] != rpn:
                actual = (rpn, 127, 127)
            msb = value if number in (_RPN_MSB, _NRPN_MSB) else actual[1]
            lsb = value if number in (_RPN_LSB, _NRPN_LSB) else actual[2]
            param[channel] = (rpn, msb, lsb)
        elif param.get(channel) == (True, 0, 0):
            # El RPN 0, el rango del bend. **Sin tope**: `3D-Galax` pide 95
            # semitonos y fluidsynth los respeta —medido—; un sintetizador
            # GS lo toparía en 24. Se sigue a fluidsynth, que es contra lo
            # que se compara y de donde sale la pista de MSU-1.
            entero = int(semitones.get(channel, BEND_RANGE))
            fraccion = semitones.get(channel, BEND_RANGE) - entero
            if number == _DATA_MSB:
                semitones[channel] = value + fraccion
            else:
                semitones[channel] = entero + value / 100.0
    if down or pedal:
        # Una nota que se suelta con el pedal abajo sigue sonando hasta que
        # sube, o hasta que se vuelve a tocar la misma tecla. Si no sube
        # nunca, hasta el final del tema.
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
    """Devuelve (notas, tempos, ticks por negra, instrumento de cada canal,
    controladores)."""
    data = open(path, "rb").read()
    if data[:4] != b"MThd":
        raise ValueError("%s no es un MIDI" % path)

    header = struct.unpack(">I", data[4:8])[0]
    _, tracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise ValueError("MIDI con división SMPTE, no soportado")

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
