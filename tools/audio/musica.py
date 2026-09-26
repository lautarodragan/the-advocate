#!/usr/bin/env python3
"""Del MIDI a notas y voces: lo que no depende del chip.

Cuánto dura cada nota y cuántas suenan a la vez. Hasta el 2026-09-26 también
repartía un presupuesto de voces entre canales —`share_voices`—, que se fue
con el reparto fijo: ver `assign` en `snes_music.py`.
"""

import collections

# Un tick por cuadro: es la unidad en la que el port cuenta el tiempo.
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
