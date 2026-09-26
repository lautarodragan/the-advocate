"""El stream de música que arma `snes_music`: a qué voz va cada nota, cuándo
se suelta y con qué envolvente.

No corren ninguna ROM: las notas y el banco se arman a mano, del tamaño justo
para que pase lo que se quiere mirar, y lo que se mira es el stream
empaquetado —lo mismo que la ROM le va a mandar al DSP—, leído de vuelta con
`_leer`. Las de las envolventes leen el SoundFont de verdad, por `gunter` del
PATH: lo que cobran es justamente que los números salgan de ahí.
"""

import math
import os
import struct
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


# --- velocidad y controladores ----------------------------------------------

def _control(cuadro, numero, valor, canal=0):
    return midi.Control(cuadro, canal, numero, valor)


def _armar_con(notas, controles, voces=None):
    voces = voces or {0: [0]}
    drums = set(voces.get(midi.DRUM_CHANNEL, []))
    frames = snes_music.build_events(notas, voces, {0: PIANO}, drums,
                                     _Banco(), controles)
    return snes_music.pack(frames, max(n.end for n in notas) + 10,
                           snes_music.init_writes())


def _escrituras(stream, voz):
    """(cuadro, registro de la voz, valor) de cada escritura, en orden."""
    out, cuadro, i = [], 0, 0
    while stream[i] != snes_music.OP_END:
        if stream[i] == snes_music.OP_WAIT:
            cuadro += stream[i + 1]
            i += 2
            continue
        registro, valor = stream[i + 1], stream[i + 2]
        i += 3
        if registro >> 4 == voz and registro & 0x0F < 8:
            out.append((cuadro, registro & 0x0F, valor))
    return out


def test_la_velocidad_baja_el_volumen_al_cuadrado():
    """fluidsynth atenúa 40·log10(127/v) dB —medido: 64 da -11,9 dB—, o sea
    la amplitud al cuadrado. Hasta el 2026-09-26 la ROM la convertía lineal:
    una nota con velocidad 64 sonaba a la mitad del techo en vez de a un
    cuarto, y los colchones, que van con velocidad baja, tapaban la melodía."""
    nota = midi.Note(0, 0, 60, 64)
    nota.end = 30
    vol = _registros(_armar_con([nota], []), 0)
    esperado = int(round(sdsp.CEILING * (64 / 127.0) ** 2))
    assert vol[sdsp.V_VOL_L] == [esperado], vol[sdsp.V_VOL_L]
    assert vol[sdsp.V_VOL_R] == [esperado], vol[sdsp.V_VOL_R]


def test_el_volumen_del_canal_cambia_a_la_nota_que_ya_sonaba():
    """Un CC7 a mitad de una nota le reescribe el volumen a su voz en ese
    cuadro, a los dos lados: es el fundido del final de `escape_newyork`, que
    hasta el 2026-09-26 no se oía porque el lector tiraba los CC. Y en 50
    —la mitad de los 100 de GM— baja la amplitud a un cuarto, igual que la
    velocidad."""
    nota = midi.Note(0, 0, 60, 127)
    nota.end = 100
    escrito = _escrituras(_armar_con([nota], [_control(40, midi.VOLUME, 50)]),
                          0)
    volumen = [(c, v) for c, r, v in escrito if r == sdsp.V_VOL_L]
    derecha = [(c, v) for c, r, v in escrito if r == sdsp.V_VOL_R]
    cuarto = int(round(sdsp.CEILING / 4.0))
    assert volumen == [(0, sdsp.CEILING), (40, cuarto)], volumen
    assert derecha == [(0, sdsp.CEILING), (40, cuarto)], derecha


def test_la_expresion_y_el_volumen_se_multiplican():
    """CC11 en 64 y CC7 en 127 antes de la nota: 40·log10 cada uno, como
    fluidsynth. El volumen se mide contra 100, así que 127 sube."""
    nota = midi.Note(10, 0, 60, 127)
    nota.end = 50
    stream = _armar_con([nota], [_control(0, midi.EXPRESSION, 64),
                                 _control(0, midi.VOLUME, 127)])
    esperado = int(round(sdsp.CEILING * (127 / 100.0) ** 2 * (64 / 127.0) ** 2))
    assert _registros(stream, 0)[sdsp.V_VOL_L] == [esperado]


def test_el_paneo_reparte_la_nota_entre_los_dos_lados():
    """CC10 en 0 es todo a la izquierda: la derecha en cero y la izquierda
    1,41 veces el techo, porque el centro es el que queda en el techo —el
    seno y coseno de fluidsynth, medido: +3 dB y silencio—. En 32, +2,3 dB
    y -5,3 dB."""
    izquierda = midi.Note(10, 0, 60, 127)
    izquierda.end = 50
    medio = midi.Note(60, 0, 60, 127)
    medio.end = 90
    stream = _armar_con([izquierda, medio], [_control(0, midi.PAN, 0),
                                             _control(55, midi.PAN, 32)])
    vol = _registros(stream, 0)
    l0, l1 = vol[sdsp.V_VOL_L]
    r0, r1 = vol[sdsp.V_VOL_R]
    assert (l0, r0) == (int(round(sdsp.CEILING * 2 ** 0.5)), 0), (l0, r0)
    assert abs(20 * math.log10(l1 / float(sdsp.CEILING)) - 2.3) < 0.3, l1
    assert abs(20 * math.log10(r1 / float(sdsp.CEILING)) + 5.3) < 0.5, r1


def test_el_bend_mueve_la_altura_antes_y_durante_la_nota():
    """Un bend antes de la nota la toca desafinada desde el principio —así
    arrancan las de `dcbest`— y uno durante le reescribe la altura a la voz."""
    nota = midi.Note(10, 0, 60, 127)
    nota.end = 100
    stream = _armar_con([nota], [_control(0, midi.BEND, 1.0),
                                 _control(50, midi.BEND, -2.0)])
    escrito = _escrituras(stream, 0)
    altura = {}
    for cuadro, registro, valor in escrito:
        if registro == sdsp.V_PITCH_L:
            altura.setdefault(cuadro, [0, 0])[0] = valor
        elif registro == sdsp.V_PITCH_H:
            altura.setdefault(cuadro, [0, 0])[1] = valor
    pasos = {c: l | h << 8 for c, (l, h) in altura.items()}
    assert pasos[10] == sdsp.pitch_for(61, 60, 16000), pasos
    assert pasos[50] == sdsp.pitch_for(58, 60, 16000), pasos


def test_un_control_no_toca_la_voz_de_otro_canal_ni_la_de_la_bateria():
    """El CC7 del canal 0 no cambia la voz del canal 1, y el bend de la
    batería no mueve el golpe: en General MIDI la nota elige el instrumento."""
    melodia = midi.Note(0, 0, 60, 127)
    melodia.end = 100
    otra = midi.Note(0, 1, 60, 127)
    otra.end = 100
    bombo = midi.Note(0, midi.DRUM_CHANNEL, BOMBO, 127)
    bombo.end = 100
    voces = {0: [0], 1: [1], midi.DRUM_CHANNEL: [6]}
    drums = {6}
    frames = snes_music.build_events(
        [melodia, otra, bombo], voces, {0: PIANO, 1: PIANO}, drums, _Banco(),
        [_control(40, midi.VOLUME, 50, 0),
         _control(40, midi.BEND, 2.0, midi.DRUM_CHANNEL)])
    stream = snes_music.pack(frames, 110, snes_music.init_writes())
    assert [c for c, r, v in _escrituras(stream, 0) if r == sdsp.V_VOL_L] == [0, 40]
    assert [c for c, r, v in _escrituras(stream, 1) if r == sdsp.V_VOL_L] == [0]
    assert [c for c, r, v in _escrituras(stream, 6)
            if r == sdsp.V_PITCH_L] == [0]


# --- el lector ---------------------------------------------------------------

def _midi(tmp_path, eventos):
    """Un MIDI de una pista, formato 0, 96 ticks por negra, con `eventos`
    (delta, bytes)."""

    def varlen(n):
        b = [n & 0x7F]
        n >>= 7
        while n:
            b.insert(0, (n & 0x7F) | 0x80)
            n >>= 7
        return bytes(b)
    pista = b"".join(varlen(d) + e for d, e in eventos) + b"\x00\xff\x2f\x00"
    datos = (b"MThd" + struct.pack(">IHHH", 6, 0, 1, 96) + b"MTrk"
             + struct.pack(">I", len(pista)) + pista)
    ruta = tmp_path / "t.mid"
    ruta.write_bytes(datos)
    return str(ruta)


def _bend(fraccion_del_rango, canal=0):
    valor = int(fraccion_del_rango * 8192) + 8192
    return bytes([0xE0 | canal, valor & 0x7F, valor >> 7])


def test_el_lector_aplica_el_rango_del_bend_sólo_con_el_rpn_0_entero(tmp_path):
    """El rango se elige con CC101 y CC100 en cero y llega por CC6. Un CC101
    solo no alcanza —medido con fluidsynth: `dcbest` manda CC101 y CC6 en 64
    sin CC100, y su bend sigue en 2 semitonos—."""
    ruta = _midi(tmp_path, [
        (0, bytes([0xB0, 101, 0])), (0, bytes([0xB0, 6, 64])),
        (0, _bend(0.5)),
        (0, bytes([0xB1, 101, 0])), (0, bytes([0xB1, 100, 0])),
        (0, bytes([0xB1, 6, 12])), (0, _bend(0.5, 1)),
        (0, bytes([0x90, 60, 100])), (96, bytes([0x80, 60, 0]))])
    _n, _t, _d, _p, controles = midi.read(ruta)
    bends = {c.channel: c.value for c in controles if c.number == midi.BEND}
    assert bends == {0: 1.0, 1: 6.0}, bends


def test_el_lector_alarga_las_notas_que_suelta_con_el_pedal_abajo(tmp_path):
    """CC64: la nota que se suelta con el pedal abajo sigue hasta que el pedal
    sube. Es el piano del título, `Fantasia_Of_The_Wind`."""
    ruta = _midi(tmp_path, [
        (0, bytes([0xB0, 64, 127])),
        (0, bytes([0x90, 60, 100])), (96, bytes([0x80, 60, 0])),
        (96, bytes([0xB0, 64, 0])),
        (0, bytes([0x90, 62, 100])), (96, bytes([0x80, 62, 0]))])
    notas, _t, _d, _p, _c = midi.read(ruta)
    fines = [(n.pitch, n.start, n.end) for n in notas]
    assert fines == [(60, 0, 192), (62, 192, 288)], fines
