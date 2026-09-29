"""The music stream `snes_music` builds: which voice each note goes to, when
it is released and with which envelope.

They run no ROM: the notes and the bank are built by hand, just big enough
for what we want to look at to happen, and what is looked at is what the
stream writes to the DSP —the per-note stream packed and decoded, which has
to give `escrituras`: the same the ROM will send it—, with `_salen`. The
envelope ones read the real SoundFont, through `gunter` from the PATH: what
they enforce is precisely that the numbers come from there.

**That SoundFont is passed by whoever runs them, in `SOUNDFONT`**, the same
way Ditto receives its corpus in `DITTO_CORPUS`: the tools do not know where
it is on any machine. Without the variable, those two are skipped with a
message.
"""

import math
import os
import struct

import pytest

from audio import midi, sdsp, snes_music                   # noqa: E402
from comun import ambiente

PIANO, BAJO_SINTETICO, BOMBO, SIN_MUESTRA = 0, 38, 36, 35


class _Muestra:
    def __init__(self, program):
        self.program, self.root, self.rate = program, 60, 16000
        self.frames = self.rate         # one second: how long a hit sounds


class _Banco:
    """What `build_events` asks of the bank: the piano and the kick drum, and
    nothing for key 35."""

    def __init__(self):
        self.voces = [_Muestra(PIANO), _Muestra(BOMBO)]
        self.melodicas = {PIANO: 0}
        self.golpes = {BOMBO: 1}

    def envolvente(self, program, key):
        return 0x8F, 0xE0, sdsp.GAIN_EXP_DECREASE | 12


class _BancoDelSoundFont(_Banco):
    """The same bank, with `Banco`'s envelopes: the SoundFont's."""

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


def _salen(frames, largo):
    """What the song writes to the DSP, (frame, register, value): the per-note
    stream packed and decoded, which has to give `escrituras`."""
    stream, sonidos = snes_music.pack(frames, largo, snes_music.init_writes())
    salen = snes_music.decodificar(stream, sonidos)
    assert salen == snes_music.escrituras(frames, largo,
                                          snes_music.init_writes())
    return salen


def _armar(notas, voces, programas=None, banco=None):
    frames = snes_music.build_events(notas, voces, programas or {0: PIANO},
                                     banco or _Banco())
    return _salen(frames, max(n.end for n in notas) + 10)


def _leer(salen):
    """Per voice, the frames of its KONs and of its releases —ADSR1 at zero,
    which is what hands control to GAIN—, in order. An ADSR1 at zero with the
    `RAMPA` GAIN is not a release but the ramp before a steal, and does not
    count."""
    kon, apagada, gain = {}, [], {}
    for cuadro, registro, valor in salen:
        if registro == sdsp.KON:
            for voz in range(sdsp.VOICES):
                if valor >> voz & 1:
                    kon.setdefault(voz, []).append(cuadro)
        elif registro < 0x80 and registro & 0x0F == sdsp.V_ADSR1 and valor == 0:
            apagada.append((cuadro, registro >> 4))
        elif registro < 0x80 and registro & 0x0F == sdsp.V_GAIN:
            gain[(cuadro, registro >> 4)] = valor
    release = {}
    for cuadro, voz in apagada:
        if gain.get((cuadro, voz)) != snes_music.RAMPA:
            release.setdefault(voz, []).append(cuadro)
    return kon, release


def test_la_nota_robada_no_suelta_a_la_que_le_robo_la_voz():
    """One channel with one voice: the second note steals the voice from the
    first halfway through and lasts longer than it. The first one's release
    —frame 100— landed on the second, which went silent a hundred frames
    before its end: 329 notes of `escape_newyork` until 2026-09-25."""
    salen = _armar([_nota(0, 100), _nota(50, 200)], {0: [0]})
    kon, release = _leer(salen)
    assert kon[0] == [0, 50]
    assert release[0] == [200], (
        "voice 0 is released at %s: the second note ends at 200" % release[0])


def test_la_nota_robada_en_el_cuadro_en_que_termina_no_escribe_su_release():
    """It ends at 100 and another starts at 100 on the same voice: the
    stealing note re-arms the ADSR after the release, so the release does
    nothing and is left out."""
    kon, release = _leer(_armar([_nota(0, 100), _nota(100, 150)], {0: [0]}))
    assert kon[0] == [0, 100]
    assert release[0] == [150]


def test_una_nota_sin_muestra_no_ocupa_una_voz():
    """The drums with two voices: a kick drum on 6, a key the bank does not
    have, and another kick drum overlapping the first. If the key without a
    sample takes 7, the second kick steals 6 from the first, which is still
    sounding, while 7 is silent."""
    notas = [_nota(0, 30, midi.DRUM_CHANNEL, BOMBO),
             _nota(5, 100, midi.DRUM_CHANNEL, SIN_MUESTRA),
             _nota(10, 40, midi.DRUM_CHANNEL, BOMBO)]
    kon, _release = _leer(_armar(notas, {midi.DRUM_CHANNEL: [6, 7]}))
    assert kon.get(6) == [0] and kon.get(7) == [10], kon


def _registros(salen, voz):
    """What each of the voice's registers received, in order."""
    escrito = {}
    for _cuadro, registro, valor in salen:
        if registro >> 4 == voz and registro & 0x0F < 8:
            escrito.setdefault(registro & 0x0F, []).append(valor)
    return escrito


@pytest.fixture
def soundfont():
    """The SoundFont from `SOUNDFONT`, set for `snes_music`; without it, the
    test is skipped."""
    ruta = os.environ.get("SOUNDFONT")
    if not ruta:
        pytest.skip("a real SoundFont is needed: SOUNDFONT=<the .sf2>")
    ambiente.fijar(soundfont=ruta)


@pytest.mark.usefixtures("soundfont")
def test_el_bajo_sintetico_se_suelta_en_lo_que_dice_el_soundfont():
    """The SoundFont's synth bass (38) is released in 30 ms. With `sdsp`'s
    families —the ones from before 2026-09-25— it dragged a 2.4 s tail with
    exponential GAIN; now the release is linear GAIN, because the fastest
    exponential does not reach zero in less than 25 ms."""
    salen = _armar([_nota(0, 30, pitch=36)], {0: [0]},
                    {0: BAJO_SINTETICO}, _BancoDelSoundFont())
    gain = _registros(salen, 0)[sdsp.V_GAIN][-1]
    assert gain & 0xE0 == sdsp.GAIN_LINEAR_DECREASE, "GAIN $%02X" % gain
    segundos = 64 * sdsp.PERIODO[gain & 0x1F] / float(sdsp.SAMPLE_RATE)
    assert segundos < 0.1, "the release lasts %.3f s" % segundos


@pytest.mark.usefixtures("soundfont")
def test_el_piano_decae_distinto_en_cada_tecla_y_hasta_callarse():
    """The SoundFont's piano (0) has no sustain —1440 centibels: it decays to
    silence— and its decay gets shorter with the key. So the DSP's sustain
    level goes at the very top (SL = 7, the decay phase ends immediately) and
    the sustain rate changes between a low C and a high one. The families
    gave the same ADSR to every key."""
    salen = _armar([_nota(0, 30, pitch=36), _nota(40, 70, pitch=84)],
                    {0: [0]}, {0: PIANO}, _BancoDelSoundFont())
    adsr2 = _registros(salen, 0)[sdsp.V_ADSR2]
    assert len(adsr2) == 2, "ADSR2 received %s" % adsr2
    grave, agudo = adsr2
    assert grave >> 5 == 7 and agudo >> 5 == 7, "ADSR2 %s" % adsr2
    # A higher rate is faster: the high note fades out sooner.
    assert agudo & 0x1F > grave & 0x1F, "ADSR2 %s" % adsr2


def test_un_release_largo_llega_a_cero_donde_el_soundfont_anda_por_40_db():
    """The DSP's exponential decrease is not exponential below 1/8: if its
    slope were matched to the SoundFont's, it would fade out much sooner than
    the SoundFont. A one-second release —100 dB in one second— goes to zero
    in ~0.4 s."""
    sf2 = {"env_delay_timecents": -12000, "env_attack_timecents": -12000,
           "env_hold_timecents": -12000, "env_decay_timecents": 0,
           "env_sustain_centibels": 0, "env_release_timecents": 0,
           "env_key_to_hold": 0, "env_key_to_decay": 0}
    _adsr1, _adsr2, gain = sdsp.envelope(sf2, 60)
    assert gain & 0xE0 == sdsp.GAIN_EXP_DECREASE, "GAIN $%02X" % gain
    hasta_cero = (sdsp.PASOS_HASTA_CERO * sdsp.PERIODO[gain & 0x1F]
                  / float(sdsp.SAMPLE_RATE))
    assert 0.3 < hasta_cero < 0.55, "reaches zero in %.3f s" % hasta_cero


# --- voice allocation ------------------------------------------------------

def _repartir(notas, programas=None):
    """The notes with the voices from `assign` —all eight for everyone—: what
    came out and which voice each one went to."""
    reparto = []
    programas = programas or {c: PIANO for c in range(16)
                              if c != midi.DRUM_CHANNEL}
    frames = snes_music.build_events(notas, snes_music.assign(notas),
                                     programas, _Banco(), (), reparto)
    return _salen(frames, max(n.end for n in notas) + 10), reparto


def test_un_acorde_suena_entero_aunque_haya_mas_canales_que_voces():
    """Seven melodic channels and the drums, taking turns, and channel 0
    plays a four-note chord. With the fixed per-channel allocation —until
    2026-09-26— the drums took two voices, the six busiest channels one each,
    the seventh none, and only one note of the chord sounded: in
    `escape_newyork` those were the string and polysynth chords, and the
    clavinet and the square wave, which never sounded."""
    notas = [_nota(100 * c, 100 * c + 50, c) for c in range(7)]
    notas += [_nota(700, 750, midi.DRUM_CHANNEL, BOMBO)]
    notas += [_nota(800, 900, 0, 60 + k) for k in (0, 4, 7, 12)]
    salen, reparto = _repartir(notas)
    sin_voz = [(n.channel, n.pitch) for n, v, _r, _f in reparto if v is None]
    assert not sin_voz, "notes without a voice while voices were free: %s" % sin_voz
    kon, _release = _leer(salen)
    en_el_acorde = [v for v, cuadros in kon.items() if 800 in cuadros]
    assert len(en_el_acorde) == 4, (
        "of the four-note chord %d voices sound: %s" % (len(en_el_acorde),
                                                       sorted(en_el_acorde)))


def test_ninguna_nota_se_queda_sin_voz_si_hay_una_libre():
    """A random song, with more polyphony than voices at times: a note that
    gets no voice can only be one that arrives with all eight held."""
    import random
    azar = random.Random(5)
    notas = []
    for _ in range(400):
        inicio = azar.randrange(0, 2000)
        canal = azar.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, midi.DRUM_CHANNEL])
        tecla = BOMBO if canal == midi.DRUM_CHANNEL else azar.randrange(40, 90)
        nota = midi.Note(inicio, canal, tecla, azar.randrange(20, 128))
        nota.end = inicio + azar.randrange(1, 120)
        notas.append(nota)
    _salen_, reparto = _repartir(notas)
    assert any(v is None for _n, v, _r, _f in reparto), (
        "the case never goes past eight voices: it tests nothing")

    def sostenida(n, v, robada, fin, t):
        # Who holds a voice at `t`: it started before, has not ended and was
        # not stolen from. A hit releases it at the end of the note or of the
        # sample, whichever comes first: that is the fourth field of `reparto`.
        return (v is not None and n.start <= t < fin
                and (robada is None or robada > t))
    for nota, voz, _r, _f in reparto:
        if voz is not None:
            continue
        t = nota.start
        ocupadas = {v for n, v, r, f in reparto if sostenida(n, v, r, f, t)}
        assert len(ocupadas) == sdsp.VOICES, (
            "the note at %d on channel %d did not sound with %d voices held"
            % (t, nota.channel, len(ocupadas)))


def test_se_le_roba_a_la_mas_debil_y_no_a_la_ultima_de_un_canal():
    """All eight held: channel 0 with seven notes, one of them soft, and
    channel 1 with just one, the softest of all. The new note on channel 2
    steals the voice from channel 0's soft one: stealing from channel 1 would
    leave it mute. It is the prototype's rule, the one from the variant taro
    listened to."""
    notas = [_nota(0, 500, 0, 60 + k) for k in range(6)]
    suave = midi.Note(0, 0, 70, 40)
    suave.end = 500
    solita = midi.Note(0, 1, 50, 30)
    solita.end = 500
    nueva = _nota(100, 200, 2, 80)
    _salen_, reparto = _repartir(notas + [suave, solita, nueva])
    voz = {id(n): (v, r) for n, v, r, _f in reparto}
    assert voz[id(nueva)][0] == voz[id(suave)][0], (
        "the new note took voice %s and channel 0's soft one was %s"
        % (voz[id(nueva)][0], voz[id(suave)][0]))
    assert voz[id(suave)][1] == 100 and voz[id(solita)][1] is None


def test_la_voz_de_arriba_del_acorde_no_llega_ultima_a_su_cuadro():
    """Eleven notes in the same frame, all with the same velocity: five hits
    —two kick drums, two snares and the hi-hat—, three one-note channels and
    channel 0's three-note chord. The hits go first, one per family; then the
    melodic part, each channel's loudest note before anyone's second; the
    repeated hits last. Left out are the second kick, the second snare and
    the bottom note of the chord.

    Until 2026-09-26 the order was velocity and, on a tie, lowest first: the
    top voice of the chord —the melody— arrived last and got no voice,
    because a note that started in the same frame is not stolen from. In the
    battle song it was 214 of the 536 notes of its melody."""
    class _BancoConBateria(_Banco):
        def __init__(self):
            super().__init__()
            for tecla in (35, 38, 40, 42):
                self.golpes[tecla] = len(self.voces)
                self.voces.append(_Muestra(tecla))

    notas = [_nota(0, 30, midi.DRUM_CHANNEL, tecla)
             for tecla in (35, 36, 38, 40, 42)]
    notas += [_nota(0, 100, canal, tecla)
              for canal, tecla in ((1, 40), (2, 45), (3, 50))]
    notas += [_nota(0, 100, 0, tecla) for tecla in (64, 67, 72)]
    reparto = []
    snes_music.build_events(notas, snes_music.assign(notas),
                            {c: PIANO for c in range(4)}, _BancoConBateria(),
                            (), reparto)
    sin_voz = sorted((n.channel, n.pitch) for n, v, _r, _f in reparto
                     if v is None)
    assert sin_voz == [(0, 64), (midi.DRUM_CHANNEL, 36),
                       (midi.DRUM_CHANNEL, 40)], sin_voz


def test_la_voz_que_suena_se_baja_un_cuadro_antes_de_robarla():
    """One voice, two notes: the second steals the voice from the first while
    it sounds. In the frame before, the voice has to come down with the ramp
    —ADSR1 at zero and GAIN `RAMPA`, 12 ms linear—, because KON drops it to
    zero at once and that is a click. The third note arrives with the voice
    silent for a while: that one needs no ramp."""
    salen = _armar([_nota(0, 100), _nota(50, 120), _nota(400, 450)], {0: [0]})
    escrito = _escrituras(salen, 0)
    gain = [(c, v) for c, r, v in escrito if r == sdsp.V_GAIN]
    assert (49, snes_music.RAMPA) in gain, (
        "voice 0 does not come down with the ramp before the steal at frame 50: %s" % gain)
    assert (49, sdsp.V_ADSR1, 0) in escrito, (
        "without ADSR1 at zero the ramp's GAIN is not in control")
    assert not [c for c, v in gain if v == snes_music.RAMPA and c > 49], (
        "the third note arrives with the voice silent and needs no ramp: %s"
        % gain)


def test_la_cola_de_un_release_tambien_se_baja_antes_de_reusar_la_voz():
    """The first note has already been released, but its tail is still
    sounding when the second takes the voice —`_Banco`'s GAIN is exponential
    and slow—: the ramp goes in anyway."""
    salen = _armar([_nota(0, 40), _nota(60, 100)], {0: [0]})
    gain = [(c, v) for c, r, v in _escrituras(salen, 0) if r == sdsp.V_GAIN]
    assert gain[:2] == [(40, sdsp.GAIN_EXP_DECREASE | 12),
                        (59, snes_music.RAMPA)], gain


# --- velocity and controllers ----------------------------------------------

def _control(cuadro, numero, valor, canal=0):
    return midi.Control(cuadro, canal, numero, valor)


def _armar_con(notas, controles, voces=None):
    voces = voces or {0: [0]}
    frames = snes_music.build_events(notas, voces, {0: PIANO}, _Banco(),
                                     controles)
    return _salen(frames, max(n.end for n in notas) + 10)


def _escrituras(salen, voz):
    """(frame, voice register, value) of each write, in order."""
    out = []
    for cuadro, registro, valor in salen:
        if registro >> 4 == voz and registro & 0x0F < 8:
            out.append((cuadro, registro & 0x0F, valor))
    return out


def test_la_velocidad_baja_el_volumen_al_cuadrado():
    """fluidsynth attenuates by 40·log10(127/v) dB —measured: 64 gives
    -11.9 dB—, that is, the amplitude squared. Until 2026-09-26 the ROM
    converted it linearly: a note with velocity 64 played at half the volume
    ceiling instead of a quarter, and the pads, which go at low velocity,
    drowned out the melody."""
    nota = midi.Note(0, 0, 60, 64)
    nota.end = 30
    vol = _registros(_armar_con([nota], []), 0)
    esperado = int(round(sdsp.CEILING * (64 / 127.0) ** 2))
    assert vol[sdsp.V_VOL_L] == [esperado], vol[sdsp.V_VOL_L]
    assert vol[sdsp.V_VOL_R] == [esperado], vol[sdsp.V_VOL_R]


def test_el_volumen_del_canal_cambia_a_la_nota_que_ya_sonaba():
    """A CC7 in the middle of a note rewrites its voice's volume in that
    frame, on both sides: it is the fade at the end of `escape_newyork`,
    which until 2026-09-26 could not be heard because the reader dropped the
    CCs. And at 50 —half of GM's 100— it lowers the amplitude to a quarter,
    the same as velocity."""
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
    """CC11 at 64 and CC7 at 127 before the note: 40·log10 each, like
    fluidsynth. The volume is measured against 100, so 127 raises it."""
    nota = midi.Note(10, 0, 60, 127)
    nota.end = 50
    salen = _armar_con([nota], [_control(0, midi.EXPRESSION, 64),
                                 _control(0, midi.VOLUME, 127)])
    esperado = int(round(sdsp.CEILING * (127 / 100.0) ** 2 * (64 / 127.0) ** 2))
    assert _registros(salen, 0)[sdsp.V_VOL_L] == [esperado]


def test_el_paneo_reparte_la_nota_entre_los_dos_lados():
    """CC10 at 0 is fully left: the right at zero and the left 1.41 times the
    volume ceiling, because the center is what sits at the ceiling
    —fluidsynth's sine and cosine, measured: +3 dB and silence—. At 32,
    +2.3 dB and -5.3 dB."""
    izquierda = midi.Note(10, 0, 60, 127)
    izquierda.end = 50
    medio = midi.Note(60, 0, 60, 127)
    medio.end = 90
    salen = _armar_con([izquierda, medio], [_control(0, midi.PAN, 0),
                                             _control(55, midi.PAN, 32)])
    vol = _registros(salen, 0)
    l0, l1 = vol[sdsp.V_VOL_L]
    r0, r1 = vol[sdsp.V_VOL_R]
    assert (l0, r0) == (int(round(sdsp.CEILING * 2 ** 0.5)), 0), (l0, r0)
    assert abs(20 * math.log10(l1 / float(sdsp.CEILING)) - 2.3) < 0.3, l1
    assert abs(20 * math.log10(r1 / float(sdsp.CEILING)) + 5.3) < 0.5, r1


def test_el_bend_mueve_la_altura_antes_y_durante_la_nota():
    """A bend before the note plays it detuned from the start —that is how
    `dcbest`'s begin— and one during it rewrites the voice's pitch."""
    nota = midi.Note(10, 0, 60, 127)
    nota.end = 100
    salen = _armar_con([nota], [_control(0, midi.BEND, 1.0),
                                 _control(50, midi.BEND, -2.0)])
    escrito = _escrituras(salen, 0)
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
    """Channel 0's CC7 does not change channel 1's voice, and the drums' bend
    does not move the hit: in General MIDI the note picks the instrument."""
    melodia = midi.Note(0, 0, 60, 127)
    melodia.end = 100
    otra = midi.Note(0, 1, 60, 127)
    otra.end = 100
    bombo = midi.Note(0, midi.DRUM_CHANNEL, BOMBO, 127)
    bombo.end = 100
    voces = {0: [0], 1: [1], midi.DRUM_CHANNEL: [6]}
    frames = snes_music.build_events(
        [melodia, otra, bombo], voces, {0: PIANO, 1: PIANO}, _Banco(),
        [_control(40, midi.VOLUME, 50, 0),
         _control(40, midi.BEND, 2.0, midi.DRUM_CHANNEL)])
    salen = _salen(frames, 110)
    assert [c for c, r, v in _escrituras(salen, 0) if r == sdsp.V_VOL_L] == [0, 40]
    assert [c for c, r, v in _escrituras(salen, 1) if r == sdsp.V_VOL_L] == [0]
    assert [c for c, r, v in _escrituras(salen, 6)
            if r == sdsp.V_PITCH_L] == [0]


# --- the reader --------------------------------------------------------------

def _midi(tmp_path, eventos):
    """A one-track MIDI, format 0, 96 ticks per quarter note, with `eventos`
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
    """The range is selected with CC101 and CC100 at zero and arrives through
    CC6. A CC101 alone is not enough —measured with fluidsynth: `dcbest`
    sends CC101 and CC6 at 64 without CC100, and its bend stays at 2
    semitones—."""
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
    """CC64: the note released with the pedal down goes on until the pedal
    comes up. It is the title screen's piano, `Fantasia_Of_The_Wind`."""
    ruta = _midi(tmp_path, [
        (0, bytes([0xB0, 64, 127])),
        (0, bytes([0x90, 60, 100])), (96, bytes([0x80, 60, 0])),
        (96, bytes([0xB0, 64, 0])),
        (0, bytes([0x90, 62, 100])), (96, bytes([0x80, 62, 0]))])
    notas, _t, _d, _p, _c = midi.read(ruta)
    fines = [(n.pitch, n.start, n.end) for n in notas]
    assert fines == [(60, 0, 192), (62, 192, 288)], fines
