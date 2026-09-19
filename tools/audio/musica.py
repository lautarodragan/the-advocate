#!/usr/bin/env python3
"""Del MIDI a notas y voces: lo que las dos consolas hacen igual.

Cuánto dura cada nota, cuántas voces pide un canal, cómo repartir un
presupuesto de voces entre canales y cuánto de lo que suena llegamos a tocar.
Nada de esto depende del chip: el YM2612 pide construir el timbre con cuatro
operadores y el S-DSP pide una forma de onda, pero antes de eso el problema es
el mismo.

Salió de `md_music.py`, que era del port a Mega Drive y sin embargo el port a
SNES le importaba seis cosas. Mismo caso que `asignador.py` —que se llamó
`pixeles.py`— y `rm2k.py`.
"""

import collections

# Un tick por cuadro: es la unidad en la que los dos ports cuentan el tiempo.
TICKS_PER_SECOND = 60

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

