#!/usr/bin/env python3
"""From MIDI to notes and voices: what does not depend on the chip.

How long each note lasts and how many play at once. Until 2026-09-26 it also
split a voice budget among channels —`share_voices`—, which went away with
the fixed assignment: see `assign` in `snes_music.py`.
"""

import collections

# One tick per frame: it is the unit in which the port counts time.
TICKS_PER_SECOND = 60

def note_time(notes):
    """How long each number of simultaneous notes plays, in frames."""
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
    """Converts the notes from MIDI ticks to frames, with the tempo applied."""
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
