"""El stream de música que arma `snes_music`: a qué voz va cada nota, cuándo
se suelta y con qué envolvente.

No corren ninguna ROM: las notas y el banco se arman a mano, del tamaño justo
para que pase lo que se quiere mirar, y lo que se mira es el stream
empaquetado —lo mismo que la ROM le va a mandar al DSP—, leído de vuelta con
`_leer`. Las de las envolventes leen el SoundFont de verdad, por `gunter` del
PATH: lo que cobran es justamente que los números salgan de ahí.
"""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

from audio import midi, sdsp, snes_music                   # noqa: E402

PIANO, BAJO_SINTETICO, BOMBO, SIN_MUESTRA = 0, 38, 36, 35


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

    def envolvente(self, program, key):
        return 0x8F, 0xE0, sdsp.GAIN_EXP_DECREASE | 12


class _BancoDelSoundFont(_Banco):
    """El mismo banco, con las envolventes de `Banco`: las del SoundFont."""

    envolvente = snes_music.Banco.envolvente

    def __init__(self):
        super().__init__()
        self.voces.append(_Muestra(BAJO_SINTETICO))
        self.melodicas[BAJO_SINTETICO] = 2
        self._envolventes = {}


def _nota(start, end, channel=0, pitch=60):
    nota = midi.Note(start, channel, pitch, 100)
    nota.end = end
    return nota


def _armar(notas, voces, programas=None, banco=None):
    drums = set(voces.get(midi.DRUM_CHANNEL, []))
    frames = snes_music.build_events(notas, voces, programas or {0: PIANO},
                                     drums, banco or _Banco())
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


def _registros(stream, voz):
    """Lo que cada registro de la voz fue recibiendo, en orden."""
    escrito, i = {}, 0
    while stream[i] != snes_music.OP_END:
        if stream[i] == snes_music.OP_WAIT:
            i += 2
            continue
        registro, valor = stream[i + 1], stream[i + 2]
        i += 3
        if registro >> 4 == voz and registro & 0x0F < 8:
            escrito.setdefault(registro & 0x0F, []).append(valor)
    return escrito


def test_el_bajo_sintetico_se_suelta_en_lo_que_dice_el_soundfont():
    """El bajo sintético (38) del SoundFont se suelta en 30 ms. Con las
    familias de `sdsp` —las de antes del 2026-09-25— arrastraba 2,4 s de cola
    con GAIN exponencial; ahora el release es GAIN lineal, porque la
    exponencial más rápida no llega a cero en menos de 25 ms."""
    stream = _armar([_nota(0, 30, pitch=36)], {0: [0]},
                    {0: BAJO_SINTETICO}, _BancoDelSoundFont())
    gain = _registros(stream, 0)[sdsp.V_GAIN][-1]
    assert gain & 0xE0 == sdsp.GAIN_LINEAR_DECREASE, "GAIN $%02X" % gain
    segundos = 64 * sdsp.PERIODO[gain & 0x1F] / float(sdsp.SAMPLE_RATE)
    assert segundos < 0.1, "el release dura %.3f s" % segundos


def test_el_piano_decae_distinto_en_cada_tecla_y_hasta_callarse():
    """El piano (0) del SoundFont no tiene sostenido —1440 centibels: decae
    hasta el silencio— y su decaimiento se acorta con la tecla. Así que el
    nivel de sostenido del DSP va arriba de todo (SL = 7, la fase de
    decaimiento termina en el acto) y la tasa de sostenido cambia entre un do
    grave y uno agudo. Las familias le daban el mismo ADSR a todas las teclas."""
    stream = _armar([_nota(0, 30, pitch=36), _nota(40, 70, pitch=84)],
                    {0: [0]}, {0: PIANO}, _BancoDelSoundFont())
    adsr2 = _registros(stream, 0)[sdsp.V_ADSR2]
    assert len(adsr2) == 2, "ADSR2 recibió %s" % adsr2
    grave, agudo = adsr2
    assert grave >> 5 == 7 and agudo >> 5 == 7, "ADSR2 %s" % adsr2
    # Tasa más alta es más rápida: la nota aguda se apaga antes.
    assert agudo & 0x1F > grave & 0x1F, "ADSR2 %s" % adsr2


def test_un_release_largo_llega_a_cero_donde_el_soundfont_anda_por_40_db():
    """La caída exponencial del DSP no es exponencial por debajo de 1/8: si
    se la hiciera coincidir en pendiente con la del SoundFont, se apagaría
    mucho antes que él. Un release de un segundo —100 dB en un segundo— va
    hasta cero en ~0,4 s."""
    sf2 = {"env_delay_timecents": -12000, "env_attack_timecents": -12000,
           "env_hold_timecents": -12000, "env_decay_timecents": 0,
           "env_sustain_centibels": 0, "env_release_timecents": 0,
           "env_key_to_hold": 0, "env_key_to_decay": 0}
    _adsr1, _adsr2, gain = sdsp.envelope(sf2, 60)
    assert gain & 0xE0 == sdsp.GAIN_EXP_DECREASE, "GAIN $%02X" % gain
    hasta_cero = (sdsp.PASOS_HASTA_CERO * sdsp.PERIODO[gain & 0x1F]
                  / float(sdsp.SAMPLE_RATE))
    assert 0.3 < hasta_cero < 0.55, "llega a cero en %.3f s" % hasta_cero
