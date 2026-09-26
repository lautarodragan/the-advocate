"""El stream de música que arma `snes_music`: a qué voz va cada nota y cuándo
se suelta.

No corren ninguna ROM ni leen el SoundFont: las notas y el banco se arman a
mano, del tamaño justo para que pase lo que se quiere mirar, y lo que se mira
es el stream empaquetado —lo mismo que la ROM le va a mandar al DSP—, leído
de vuelta con `_leer`.
"""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

from audio import midi, sdsp, snes_music                   # noqa: E402

PIANO, BOMBO, SIN_MUESTRA = 0, 36, 35


class _Muestra:
    def __init__(self, program):
        self.program, self.root, self.rate = program, 60, 16000


class _Banco:
    """Lo que `build_events` le pide al banco: el piano y el bombo, y nada
    para la tecla 35."""

    def __init__(self):
        self.voces = [_Muestra(PIANO), _Muestra(BOMBO)]
        self.melodicas = {PIANO: 0}
        self.golpes = {BOMBO: 1}


def _nota(start, end, channel=0, pitch=60):
    nota = midi.Note(start, channel, pitch, 100)
    nota.end = end
    return nota


def _armar(notas, voces):
    drums = set(voces.get(midi.DRUM_CHANNEL, []))
    frames = snes_music.build_events(notas, voces, {0: PIANO}, drums, _Banco())
    return snes_music.pack(frames, max(n.end for n in notas) + 10,
                           snes_music.init_writes())


def _leer(stream):
    """Por voz, los cuadros de sus KON y los de sus releases —ADSR1 en cero,
    que es lo que le pasa el mando a GAIN—, en orden."""
    kon, release = {}, {}
    cuadro, i = 0, 0
    while stream[i] != snes_music.OP_END:
        if stream[i] == snes_music.OP_WAIT:
            cuadro += stream[i + 1]
            i += 2
            continue
        registro, valor = stream[i + 1], stream[i + 2]
        i += 3
        if registro == sdsp.KON:
            for voz in range(sdsp.VOICES):
                if valor >> voz & 1:
                    kon.setdefault(voz, []).append(cuadro)
        elif registro & 0x0F == sdsp.V_ADSR1 and registro < 0x80 and valor == 0:
            release.setdefault(registro >> 4, []).append(cuadro)
    return kon, release


def test_la_nota_robada_no_suelta_a_la_que_le_robo_la_voz():
    """Un canal con una voz: la segunda nota le roba la voz a la primera a
    mitad de camino y dura más que ella. El release de la primera —cuadro
    100— caía sobre la segunda, que se apagaba cien cuadros antes de su fin:
    329 notas de `escape_newyork` hasta el 2026-09-25."""
    stream = _armar([_nota(0, 100), _nota(50, 200)], {0: [0]})
    kon, release = _leer(stream)
    assert kon[0] == [0, 50]
    assert release[0] == [200], (
        "la voz 0 se suelta en %s: la segunda nota termina en 200" % release[0])


def test_la_nota_robada_en_el_cuadro_en_que_termina_no_escribe_su_release():
    """Termina en 100 y otra arranca en 100 en la misma voz: la ladrona
    rearma el ADSR detrás del release, así que el release no hace nada y no
    va."""
    kon, release = _leer(_armar([_nota(0, 100), _nota(100, 150)], {0: [0]}))
    assert kon[0] == [0, 100]
    assert release[0] == [150]


def test_una_nota_sin_muestra_no_ocupa_una_voz():
    """La batería con dos voces: un bombo en la 6, una tecla que el banco no
    trae y otro bombo que se superpone al primero. Si la tecla sin muestra
    ocupa la 7, el segundo bombo le roba la 6 al primero, que sigue sonando,
    mientras la 7 está callada."""
    notas = [_nota(0, 30, midi.DRUM_CHANNEL, BOMBO),
             _nota(5, 100, midi.DRUM_CHANNEL, SIN_MUESTRA),
             _nota(10, 40, midi.DRUM_CHANNEL, BOMBO)]
    kon, _release = _leer(_armar(notas, {midi.DRUM_CHANNEL: [6, 7]}))
    assert kon.get(6) == [0] and kon.get(7) == [10], kon
