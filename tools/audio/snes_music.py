"""Converts a map's MIDI to BRR samples and a stream for the S-DSP.

What does not depend on the chip —reading the MIDI and turning times into
frames— is in midi.py and musica.py; the S-DSP part, in sdsp.py. Voices are
allocated note by note, all eight shared by every channel: see `assign`.

Two things come out: the block uploaded to the SPC700's memory (the sample
directory plus the samples in BRR) and each song's stream, per note, which the
65816 expands into DSP writes frame by frame: see "the per-note format". The
caller is the converter, with every song of the cartridge at once: see
`build_varios`.
"""

import collections
import math
import os

from rpgmaker import lcf
from audio import musica
from audio import midi
from audio import muestras_brr
from audio import sdsp
from audio import snes_samples
from audio import spc700
from common import settings
from common import project
from common.parallel import in_parallel
from rpgmaker import resources
from rpgmaker.resources import find_resource

TICKS_PER_SECOND = musica.TICKS_PER_SECOND

# Where each thing lives in the SPC700's 64 KB. The boot ROM keeps the first
# $200 bytes for its variables, so everything starts higher up.
DRIVER_ADDR = 0x0200
SAMPLES_ADDR = 0x0400

BLOQUE = muestras_brr.BLOQUE_MUESTRAS   # 16 samples per BRR block

# The samples go from $0400 to the end of the 64 KB —`ARAM_FIN`, further
# down—, with no reservation: echo is off —FLG with the "do not write the
# buffer" bit— and the SPC700's stack lives at $0100, that is, below. One
# package fits there at a time, and that is what the allocation is done
# against: see `Banco`.
#
# And what is left free for each package when allocating. Each sample's
# length is rounded up to BRR blocks and the allocation asks by budget, so
# this is slack for that; `Banco` checks what they really take against the
# ARAM with no margin. 1 KB is what step 6 was measured with.
ARAM_MARGEN = 1024

# The stream's opcodes **are not declared here**: they come from
# `tools/protocol/music.toml`, which belongs to the stream's writer and its
# reader, and to neither. Until 2026-09-15 they were written by hand on both
# sides, in this file and in main.s, with nothing tying them together.
from audio.music_opcodes import *   # noqa: E402,F401,F403


# Each song's MSU-1 track. The MSU-1 is not console hardware but an extension
# supported by the FX Pak Pro and the emulators: the music comes from a PCM
# file next to the ROM —`<rom>-<track>.pcm`, enabled by a `<rom>.msu`—
# instead of being synthesized on the SPC700. When the song has a track, the
# ROM silences the SPC700 and plays the track; sound effects keep playing on
# the SPC700, so they get the whole ARAM. The tracks are built by
# `tools/audio/msu.py` from the same MIDIs, with the soundfont the original
# game sounded with on the PC.
#
# **Every song has a track**: taro asked for it on 2026-09-26, and until that
# day it was a hand-written list of 22 —the ones that play until leaving
# Lashe City—. A song without a track is one with nothing to come from:
# "(OFF)", or a name that is not in `Music/`. Enforced by
# `test_todo_tema_tiene_su_pista`.
#
# **The number comes from the game, not the cartridge**: it is the song's
# place in the sorted list of `Music/` —case-insensitive, counting from 1—.
# The song's index in the cartridge would have been the obvious choice, but
# that is decided by the order in which the `PlayBGM`s appear when compiling
# (`Temas.indice`), so a new map shifts the numbering of the ones after it,
# and renumbering means hundreds of megabytes to redo and copy to the card
# again. `Music/` belongs to the original game and does not change, so a
# song's number is always the same, in any cartridge and with any list of
# maps: a new song is a new file and nothing else. The numbers come out with
# gaps —the cartridge does not use every song in the game— and the MSU-1
# does not care.
#
# And the size: 16-bit stereo at 44.1 kHz is 10.6 MB per minute, so each
# song's track weighs as much as it lasts. Trimming them by loop does not
# work: of the 21 in Lashe City, the **only** one that repeats exactly at the
# halfway point is `C3classi` —measured by comparing the notes of both
# halves—.
#
# **What giving the battle song a track does NOT fix**, measured on
# 2026-09-14 because it looked like it would: taking it out of the shared bank
# frees 4 samples and 565 B, raises the median rate from 11521 to 12496 Hz and
# **does not bring back a single song** of the nine that were cut. Its weight
# is stream, which lives in the cartridge, not ARAM.
#
# **And after them, the RTP ones named by the LDB's `System`** that the game
# does not ship: in ABL, the Game Over one —`GameOver3`— and the vehicle
# ones. They go after all of `Music/`, sorted, so they do not shift any of
# the game's; and it is only those because the whole RTP does not fit in the
# byte —230 from the game and 111 from the RTP—. A `PlayBGM` that names an
# RTP one —`Farewell2`, in maps 117, 127 and 150— has no track until it is
# added here, and the same test enforces it.
MUSICA_DE_PISTA = (".mid", ".wav")


_numeros_de_pista = {}


def _nombres_de_musica(directorio):
    carpeta = [os.path.join(directorio, e) for e in os.listdir(directorio)
               if e.lower() == "music"] if os.path.isdir(directorio) else []
    nombres = set()
    for archivo in os.listdir(carpeta[0]) if carpeta else []:
        base, ext = os.path.splitext(archivo)
        if ext.lower() in MUSICA_DE_PISTA:
            nombres.add(base.lower())
    return nombres


def numeros_de_pista(game_dir=None):
    """{lowercase song name: track number}, for all of `Music/` and the RTP
    ones named by `System`."""
    game_dir = game_dir or resources.GAME_DIR
    if game_dir not in _numeros_de_pista:
        from rpgmaker.resources import RTP_DIR
        nombres = _nombres_de_musica(game_dir)
        del_rtp = _nombres_de_musica(RTP_DIR)
        ldb = os.path.join(game_dir, "RPG_RT.ldb")
        sistema = sorted(({n.lower() for n in lcf.system_songs(ldb)}
                          - nombres) & del_rtp)
        orden = sorted(nombres) + sistema
        # The number goes in a byte of `tema_msu`, and $FF is "no track".
        if len(orden) > 0xFE:
            raise SystemExit("Music/ has %d songs and the track goes in a byte"
                             % len(orden))
        _numeros_de_pista[game_dir] = {n: i + 1 for i, n in enumerate(orden)}
    return _numeros_de_pista[game_dir]


def ruta_del_tema(nombre, game_dir=None, extensiones=MUSICA_DE_PISTA):
    """The song's file: the game's and, if it is not there, the RTP's, which
    is how RM2k looks for it. `None` if it is in neither."""
    game_dir = game_dir or resources.GAME_DIR
    from rpgmaker.resources import RTP_DIR
    return (find_resource([game_dir, RTP_DIR], "Music", nombre, extensiones)
            if nombre else None)


def pista_msu(nombre, game_dir=None):
    """The song's MSU-1 track number, or None if it has nothing to come
    from: see `numeros_de_pista`."""
    game_dir = game_dir or resources.GAME_DIR
    return numeros_de_pista(game_dir).get(nombre.lower()) if nombre else None


# --- the SPC700 driver ------------------------------------------------------
# It waits for the 65816 to change the token in port 3 —the 65816 increments
# it on every write, and the driver hands it back as an acknowledgement— and
# looks at port 2, which says what to do:
#
#   0  a DSP (register, value) pair in ports 0 and 1: the music
#   1  a byte from port 0 into the ARAM, where the pointer points, which
#      advances
#   2  the ARAM pointer, from ports 0 and 1
#   3  a block: port 0 says how many triplets are coming —up to 85, so that
#      index Y does not go past a byte—, and then one arrives per token, in
#      ports 0, 1 and 2, after the pointer. The pointer does not advance: the
#      65816 sets it again before each block. That is about 56 SPC700 cycles
#      per triplet, about 55 KB per second
#   4  go back to the IPL ROM: see below. It does not answer the
#      acknowledgement, because by the time the 65816 would read it the
#      driver no longer exists
#
# Command 4 is there to **boot the ROM again**. The 65816 cannot reset the
# SPC700 —the console's reset button can, because the line reaches both, but
# a `jml reset` from inside the game cannot—, so after the Game Over the
# SPC700 keeps running this driver and the IPL is no longer there to greet
# with $AA/$BB. `spc_upload` would wait for that greeting **forever**, with
# the screen already on and the map drawn: that is the hang at the Rat
# Tracks' trap chest. Setting bit 7 of $F1 makes the IPL ROM reappear at
# $FFC0, and jumping there boots it from scratch, which is exactly what the
# 65816 sees when the console is switched on.
#
# The three ARAM ones exist because of each map's audio package: the samples
# are uploaded while the music plays, so the driver has to be able to receive
# them without stopping serving the DSP. See `paquete_cargar` in
# tools/runtime/paquete_de_audio.s. The pointer and the count live at $00-$03
# of the zero page, which the boot ROM uses and leaves free.
#
# The music keeps sending 0 commands without touching port 2: whoever
# uploads to the ARAM leaves it at zero before releasing the bus, which is
# why nothing in the stream had to change.

DRIVER = """
    mov x, $F7          ; start with whatever token is there, without firing
espera:
    cmp x, $F7
    beq espera
    mov x, $F7
    mov a, $F6          ; the command
    bne no_dsp
    mov a, $F4          ; DSP register
    mov $F2, a
    mov a, $F5          ; the value that goes in that register
    mov $F3, a
    mov $F7, x          ; acknowledge by handing the token back
    bra espera
no_dsp:
    cmp a, #$01
    bne no_byte
    mov a, $F4
    mov y, #$00
    mov [$00]+y, a
    incw $00
    mov $F7, x
    bra espera
no_byte:
    cmp a, #$02
    bne no_puntero
    mov a, $F4
    mov $00, a
    mov a, $F5
    mov $01, a
    mov $F7, x
    bra espera
no_puntero:
    cmp a, #$04
    bne bloque
    mov a, #$80         ; the IPL ROM, back at $FFC0
    mov $F1, a
    jmp !$FFC0
bloque:
    mov a, $F4
    mov $02, a
    mov $F7, x
    mov y, #$00
terna:
    cmp x, $F7
    beq terna
    mov x, $F7
    mov a, $F4
    mov [$00]+y, a
    inc y
    mov a, $F5
    mov [$00]+y, a
    inc y
    mov a, $F6
    mov [$00]+y, a
    inc y
    mov $F7, x
    dec $02
    bne terna
    bra espera
"""


# --- samples ----------------------------------------------------------------

# --- sound effects ---------------------------------------------------------
#
# The WAVs of `PlaySound` —from the game or the RTP—, in the same ARAM as the
# music bank, with **what the music leaves free** and up to `SE_ARAM`: the
# music comes first. The first attempt reserved 16 KB for them and took it
# from the percussion, which is what gets whatever is left over, and the
# demo's bank dropped from 44 samples to 22. The demo asks for 38 sound
# effects adding up to more than 40 seconds, and that does not fit at any
# reasonable quality, so they are chosen: first the ones the ROM's first maps
# ask for, at `SE_TASA`, trimmed to `SE_MAX_SEGUNDOS`; a longer one repeats
# its last `SE_LOOP_SEGUNDOS` until it lasts as long as it does in RM2k —the
# opening's rain is five seconds of noise, and that way it is heard whole—.
# The ones that do not fit do not play, and the converter says so.
SE_ARAM = 16 * 1024
SE_TASA = 6000
SE_MAX_SEGUNDOS = 0.75           # since the per-map package: see `paquete_cargar`
SE_LOOP_SEGUNDOS = 0.4
SE_VOZ = 7                      # the one stolen from the music
# And the second, so two sound effects can play at once —the opening's rain
# and thunder—, as in RM2k. Both are the ones the music allocation fills
# first with percussion: see `VOCES_DE_EFECTOS`.
SE_VOZ2 = 6
# **Which sound effects go whole, which ones the music pays for, which
# aliases there are per map and which songs go separately are the game's
# decisions by ear**, almost all of them taro's while listening, and they
# live in its project file —`[sound_effects]` and `[music]`— with the reason
# for each. Until 2026-09-29 they were tables here. They are read when used
# and not at import, so the converter can be imported without a game.

def se_enteros():
    """{sound effect: rate in Hz} of the ones that go whole, with no cap or
    loop: they end when the sample ends, which is what they do in RM2k. What
    one takes beyond the usual has to fit in what the music leaves free in
    each package it is in, except for those in `se_enteros_pagados`: see
    `_enteros_entran`. From `[sound_effects.whole]`."""
    return dict(settings.value("sound_effects", "whole", kind=dict))


def se_enteros_pagados():
    """The whole ones that, if they do not fit in the free space, lower the
    music's rate. From `[sound_effects] paid_by_music`."""
    return set(settings.value("sound_effects", "paid_by_music", kind=list))


def se_del_mapa():
    """{(name in RM2k, map id): the sample that plays there}. They are put in
    by `_compilar`, in tools/port/eventos.py. Each one is one more sound
    effect, but not one more directory entry: it shares a place with those
    of the other packages —see `lugares_de_efectos`—. From
    `[sound_effects] per_map`."""
    return {(a["effect"], a["map"]): a["sample"]
            for a in settings.value("sound_effects", "per_map", kind=list)}


def se_de_ruta_sin_paquete():
    """{map id: None for all, or the names} of the sound effects that forced
    move routes ask for —move command 35, see `RUTA_SONIDO` in
    tools/port/eventos.py— and that **do not fit** in their map's audio
    package. From `[sound_effects] route_effects_left_out`."""
    return {m["map"]: None if m["effects"] == "all" else set(m["effects"])
            for m in settings.value("sound_effects", "route_effects_left_out",
                                    kind=list)}


def se_de_tropa_al_paquete():
    """The sound effects of troop pages that **do** go in the battle's audio
    package. From `[sound_effects] troop_effects_in_package`."""
    return set(settings.value("sound_effects", "troop_effects_in_package",
                              kind=list))


def temas_aparte():
    """{map id: names} of the separate songs: they do not go with the other
    songs of their map's package, their `PlayBGM` uploads them alone with the
    package's sound effects —see `extra_aparte` in
    tools/runtime/paquete_de_audio.s—, and they are not inherited by the maps
    you exit to —see `temas_heredados` in snes_convert.py—. From
    `[music] apart_themes`."""
    return {m["map"]: set(m["themes"])
            for m in settings.value("music", "apart_themes", kind=list)}


class Efecto:
    """A sound effect ready for the SPC700: `data` in BRR, at `rate`, which
    goes back to block `loop_block` if it repeats, and lasts `segundos` in
    RM2k."""

    def __init__(self, name, data, rate, loop_block, segundos):
        self.name = name
        self.data = data
        self.rate = rate
        self.loop_block = loop_block or 0
        self.repite = loop_block is not None
        self.segundos = segundos


def leer_wav(nombre, game_dir=None):
    """A mono WAV's samples as signed 16-bit integers, and its rate. None if
    it is missing or is not a WAV that can be understood."""
    game_dir = game_dir or resources.GAME_DIR
    import wave
    from rpgmaker.resources import RTP_DIR
    ruta = find_resource([game_dir, RTP_DIR], "Sound", nombre,
                         (".wav", ".WAV"))
    if not ruta:
        return None
    try:
        w = wave.open(ruta)
    except Exception:
        return None
    ancho, canales, tasa = w.getsampwidth(), w.getnchannels(), w.getframerate()
    datos = w.readframes(w.getnframes())
    if ancho == 1:
        crudo = [(b - 128) << 8 for b in datos]
    elif ancho == 2:
        crudo = [int.from_bytes(datos[i:i + 2], "little", signed=True)
                 for i in range(0, len(datos), 2)]
    else:
        return None
    if canales > 1:
        crudo = [sum(crudo[i:i + canales]) // canales
                 for i in range(0, len(crudo), canales)]
    return crudo, tasa


def build_efecto(nombre, game_dir=None, tasa=SE_TASA, enteros=None):
    """`enteros` is `se_enteros()` if not given; with {} the usual one comes
    out, which is what the music budgets for it: see `se_enteros`."""
    game_dir = game_dir or resources.GAME_DIR
    enteros = se_enteros() if enteros is None else enteros
    leido = leer_wav(nombre.split("@")[0], game_dir)
    if not leido or not leido[0]:
        return None
    crudo, fuente = leido
    segundos = len(crudo) / float(fuente)
    guardar = min(len(crudo), int(SE_MAX_SEGUNDOS * fuente))
    if nombre in enteros:
        tasa, guardar = enteros[nombre], len(crudo)
    salen = max(BLOQUE,
                int(round(guardar * tasa / float(fuente)))
                // BLOQUE * BLOQUE)
    audio = snes_samples.normalize(snes_samples.resample(crudo[:guardar],
                                                         salen))
    loop = None
    if guardar < len(crudo):
        largo_loop = int(SE_LOOP_SEGUNDOS * tasa) // BLOQUE
        loop = max(0, salen // BLOQUE - max(1, largo_loop))
    return Efecto(nombre, muestras_brr.codificar(audio, loop_block=loop),
                  tasa, loop,
                  segundos)


def build_efectos(pedidos, game_dir=None, budget=SE_ARAM):
    """The sound effects that fit in `budget`, by priority: `pedidos` is a
    list of names already sorted from most to least requested. Returns
    {name: Efecto} with the ones that fit."""
    game_dir = game_dir or resources.GAME_DIR
    hechos, usado = {}, 0
    # Each sound effect is built on its own —read the WAV, resample it,
    # encode it— and that is pure: all at once, and then the allocation in
    # the requested order.
    unicos = list(dict.fromkeys(pedidos))
    armados = dict(zip(unicos, in_parallel(
        lambda n: build_efecto(n, game_dir), unicos)))
    for nombre in pedidos:
        if nombre in hechos:
            continue
        efecto = armados[nombre]
        if efecto is None:
            continue
        costo = len(efecto.data) + 4          # the sample and its entry
        if usado + costo > budget:
            continue
        hechos[nombre] = efecto
        usado += costo
    return hechos


def altura_de_efecto(efecto, tempo):
    """The DSP pitch register: 4096 is the 32 kHz rate, and RM2k's tempo
    —from 50 to 150— stretches it."""
    return min(0x3FFF, int(round(efecto.rate * 4096 / 32000.0 * tempo / 100.0)))


def cuadros_de_efecto(efecto, tempo):
    """How long it lasts, in 60 Hz frames, with the tempo applied."""
    return max(1, int(round(efecto.segundos * 60 * 100.0 / max(1, tempo))))


def volumen_de_efecto(volumen, balance):
    """DSP left and right, from 0 to 127, from RM2k's volume and pan: pan at
    50 is the center, and toward each side the other one drops."""
    tope = sdsp.MASTER if hasattr(sdsp, "MASTER") else 0x7F
    # The $60 was chosen with the master volume at $60, which is also applied
    # to the sound effects —with MSU-1 or without it—. With `sdsp`'s headroom
    # the master went up, and the sound effect's ceiling goes down by the
    # same amount so it sounds the same.
    v = max(0, min(100, volumen)) * int(round(0x60 * 0x60 / sdsp.MASTER)) // 100
    izquierda = v * min(50, 100 - balance) // 50
    derecha = v * min(50, balance) // 50
    return max(0, min(0x7F, izquierda)), max(0, min(0x7F, derecha))


# --- voice allocation -------------------------------------------------------

def assign(notes):
    """Which DSP voices each MIDI channel may take: all eight, every channel.

    Until 2026-09-26 each melodic channel had its fixed voices —allocated by
    how much note-time each one added— and the drums two at the end. In
    `escape_newyork` that left one voice for the strings' three-note chords,
    one for the polysynth's six-note ones, and none for the clavinet and the
    square wave: 55% of the note-time was lost, against the 23% that is lost
    unavoidably with eight voices. Now allocation is note by note, in
    `build_events`: a note takes a free voice, and if there is none, it steals
    another by priority —see `_victima`—. It is step 5 of
    `workflow/tasks/todo/la-calidad-de-la-musica.md`.

    It still returns one group per channel because `build_events` accepts
    them different, and the tests use it to build small cases.
    """
    return {channel: list(range(sdsp.VOICES))
            for channel in sorted({n.channel for n in notes})}


# The voices that sound effects take from the music: `SE_VOZ` and
# `SE_VOZ2`. While a sound effect plays, what the music writes to its voice
# goes to the shadow and not to the DSP —see `dsp_musica`—, so whatever note
# was there goes silent. That is why percussion hits, which last half a
# second, go there first, and melodic notes only if no other voice is free:
# that is what happened when the drums had those two voices fixed.
VOCES_DE_EFECTOS = (SE_VOZ2, SE_VOZ)


# The GAIN used to bring down a voice that is playing one frame before
# handing it to another note: linear, 64 steps of 6 samples, so it reaches
# zero in 12 ms, before the next frame. What it avoids is the KON click,
# which drops the envelope to zero at once: the prototype for step 5 of
# `workflow/tasks/todo/la-calidad-de-la-musica.md` recorded it (variant 07).
# It is one more `OP_RELEASE_GAIN` in the stream: the driver does not change.
RAMPA = sdsp.GAIN_LINEAR_DECREASE | 26
assert 64 * sdsp.PERIODO[RAMPA & 0x1F] <= sdsp.SAMPLE_RATE // TICKS_PER_SECOND


class _Voz:
    """What the allocation knows about a voice: the note holding it, until
    when it holds it —`fin`— and until when it can be heard —`cola`, with the
    release or however long the hit lasts—, and the volume it started with,
    left plus right."""

    __slots__ = ("nota", "fin", "cola", "nivel")

    def __init__(self, nota, fin, cola, nivel):
        self.nota, self.fin, self.cola, self.nivel = nota, fin, cola, nivel


def _cuadros_del_release(gain):
    """How many frames a voice released with that GAIN takes to go silent,
    from the top: the linear one drops 1/64 per step, and the exponential
    one reaches zero in `PASOS_HASTA_CERO` —see `sdsp`—."""
    periodo = sdsp.PERIODO[gain & 0x1F] or 0
    pasos = (64 if gain & 0xE0 == sdsp.GAIN_LINEAR_DECREASE
             else sdsp.PASOS_HASTA_CERO)
    return int(pasos * periodo * TICKS_PER_SECOND / sdsp.SAMPLE_RATE) + 1


def _libre(voz, t, voces, nota, drums):
    """The order among the free voices —the ones nobody holds at `t`—: the
    lowest wins."""
    s = voces.get(voz)
    # Silent ones first: reusing one that is still sounding in its tail cuts
    # it. Among the sounding ones, the one that dies out first.
    suena = s is not None and s.cola > t
    return (suena, s.cola if suena else 0,
            # Hits go to the sound effect voices; melodic notes, to the rest.
            (voz in VOCES_DE_EFECTOS) != drums,
            # And the one that had a note from the same channel: same
            # instrument and same volume, so the new note costs two bytes.
            s is None or s.nota.channel != nota.channel,
            voz)


def _victima(nota, t, grupo, voces, nivel):
    """Which voice `nota` steals when every voice in its group is held, or
    None if it steals none and does not play.

    It is the prototype's rule —what taro listened to in variant 09 and said
    "is very acceptable"—. Measured on the 32 songs of `release`: always
    stealing the oldest without ever yielding loses the same note-time but
    cuts 2.5 times more notes while they sound, and always stealing the
    weakest loses more; also protecting the lowest and the highest note, or
    stealing within the note's own channel first, tie with it on average and
    gain on some songs what they lose on others, so they did not go in. The
    numbers are in step 5 of
    `workflow/tasks/todo/la-calidad-de-la-musica.md`.

    * The same key of the same channel sounding again steals from itself: it
      is a synthesizer retriggering the note.
    * Never from a note that started in this same frame, which would never
      get to sound; nor from a channel's last voice, which would leave it
      mute.
    * Among the rest, from the weakest —the volume it started with— and, on
      a tie, from the oldest.
    * And the new note yields instead of stealing if its channel is already
      sounding and the victim is another channel's last, or is louder than
      it and its channel has no more voices than the new note's.
    """
    por_canal = collections.Counter(voces[v].nota.channel for v in grupo)
    for v in grupo:
        s = voces[v].nota
        if s.channel == nota.channel and s.pitch == nota.pitch:
            return v

    def ultima(s):
        # Another channel's last voice: stealing it leaves that channel mute.
        # Not the same channel's, which keeps sounding with the new note.
        return s.nota.channel != nota.channel and por_canal[s.nota.channel] <= 1

    def costo(v):
        s = voces[v]
        return (s.nota.start == t, ultima(s), s.nivel, s.nota.start, v)

    v = min(grupo, key=costo)
    s = voces[v]
    if s.nota.start == t:
        return None
    if por_canal[nota.channel] >= 1 and s.nota.channel != nota.channel and (
            ultima(s) or (s.nivel > nivel and por_canal[s.nota.channel]
                          <= por_canal[nota.channel])):
        return None
    return v


# The General MIDI hits that are the same instrument played another way: two
# bass drums, two snares, the hi-hat closed, pedaled and open, two crash
# cymbals, two rides. A MIDI asking for them together is thickening the hit,
# not playing two —the battle song hits 35 and 36 on every beat, and 38 and
# 40 on every snare—. Not the toms: they are different drums and a roll
# brings them together.
FAMILIAS_DE_GOLPES = {35: "bombo", 36: "bombo", 38: "caja", 40: "caja",
                      42: "charles", 44: "charles", 46: "charles",
                      49: "platillo", 57: "platillo", 51: "ride", 59: "ride"}


def _orden_del_cuadro(notas, nivel):
    """In which order the notes that start in the same frame pick a voice:
    when there are not enough for all, the last ones are left out, because
    `_victima` does not steal from a note that started in the frame.

    * **Hits first, one per family** (`FAMILIAS_DE_GOLPES`), from loudest to
      softest: they are short, and they are the rhythm.
    * **Then the melodic notes, by their level divided by their place in
      their channel**: each channel's loudest note goes with its level, the
      second with half, the third with a third. That way the top voice of a
      chord goes before a softer channel, but the second note of that chord
      goes after, unless that channel is little more than a whisper.
    * **Last, a family's repeated hit**, which only plays if there is a
      voice to spare.

    `nivel` is each note's level with the frame's controllers, left plus
    right: `_victima`'s, which is the level the note will sound at.

    Until 2026-09-26 the order was by velocity, and among equals the lowest
    first. In the battle song everything has velocity 127, so the five or
    six hits of each beat —two bass drums, two snares, hi-hat—, the two
    basses and the brass took all eight voices before the melody arrived,
    which is the highest; and a note from the same frame cannot be stolen
    from. Of the 536 notes of its organ's top voice —channel 0, the loudest
    in the mix because of its CC7— 214 did not play, and the main phrase
    (from 15 to 22 s) lost every other note. With the fixed allocation from
    before step 5 this did not happen: the organ had its voice. Measured on
    the 32 songs of `release`, with a throwaway script:

    * the battle melody goes from losing 48% of its time to 0%;
    * on average, the lost note-time drops from 7.38% to 7.05%, and the
      steals from 2,883 to 2,528; the highest note at each instant is lost
      6.9% of the time instead of 10.7%, the lowest 3.7% instead of 3.3%;
      the hits that do not play —counting one family per frame— drop from
      0.39% to 0.12%;
    * the stream shrinks by 3.6 KB, because there are fewer steals and with
      them fewer ramps.

    What was tried and fell short, in the task
    (`workflow/tasks/todo/la-calidad-de-la-musica.md`, step 5b): sorting by
    level alone, without spreading by channel (the melody loses 22%); a
    strict round —every channel its first note before any its second—,
    which saves the melody just the same but gives a voice to
    `escape_newyork`'s velocity-29 strings at the polysynth's expense; and
    what is done in `_victima` —not stealing a note that just started, a cap
    on voices for the drums, hits not stealing—, which changes nothing: the
    melody was not lost to steals but to arriving last in its frame.
    """
    niveles = {id(n): nivel(n) for n in notas}
    lugar = {}
    por_canal = collections.defaultdict(list)
    for n in notas:
        por_canal[n.channel].append(n)
    for canal, ns in por_canal.items():
        if canal == midi.DRUM_CHANNEL:
            vistas = set()
            for n in sorted(ns, key=lambda n: (-niveles[id(n)], n.pitch)):
                familia = FAMILIAS_DE_GOLPES.get(n.pitch, n.pitch)
                lugar[id(n)] = (2 if familia in vistas else 0, -niveles[id(n)])
                vistas.add(familia)
        else:
            por_nivel = sorted(ns, key=lambda n: (-niveles[id(n)], -n.pitch))
            for i, n in enumerate(por_nivel):
                lugar[id(n)] = (1, -niveles[id(n)] / (1.0 + i))
    return sorted(notas, key=lambda n: lugar[id(n)] + (n.pitch,))


# --- the shared bank --------------------------------------------------------

# Samples are requested by key: ("p", program, key) a melodic one, ("g", key)
# a percussion hit. It is one per General MIDI program and one per hit in the
# whole cartridge, so two songs that play piano use the same one. The melodic
# key picks the SoundFont zone: see `zonas_mas_usadas`.
def claves_del_tema(leido, teclas=None):
    """The samples a song read by `leer_tema` asks for, or none. `teclas` are
    the ones from `zonas_mas_usadas`; without it, middle C."""
    if not leido:
        return set()
    teclas = teclas or {}
    return ({("p", p, teclas.get(p, snes_samples.REFERENCE_KEY))
             for p in leido["melodicos"]}
            | {("g", g) for g in leido["golpes"]})


def zonas_mas_usadas(leidos):
    """{program: key}: which key each program's sample is requested with,
    which is what picks the SoundFont zone.

    **The zone where the whole cartridge plays the most note-time of that
    program**, and not middle C's. A sample sounds good near its root: far
    from it, the DSP stretches or squeezes it and you can hear it —an octave
    down the missing highs, an octave up the loop getting shorter—. Measured
    on 2026-09-26 with the 32 songs of `release`: 34% of the melodic
    note-time played twelve semitones or more from the root of the middle C
    sample, on keys for which the SoundFont has another; synth bass 33, in
    twelve songs, plays `MMBAS40`'s zone and not 62's. It is one per program
    just as before, so it costs no ARAM; what it loses is that a program two
    songs play in different registers is right for only one of them. It is
    step 6 of `workflow/tasks/todo/la-calidad-de-la-musica.md`.

    The key is that zone's root if the zone covers it —so two songs that
    play the same zone ask for the same sample—, and if not, the key that
    sounds the most inside the zone.
    """
    tiempo = collections.defaultdict(collections.Counter)
    adentro = collections.defaultdict(collections.Counter)
    # The zones the loop below is going to ask for, requested beforehand all
    # together: see `muestras_brr.precargar`.
    muestras_brr.precargar(
        ("program:%d@%d" % (leido["programas"].get(nota.channel, 0),
                            nota.pitch)
         for leido in leidos if leido for nota in leido["notas"]
         if nota.channel != midi.DRUM_CHANNEL
         and nota.channel in leido["voces"]),
        snes_samples.SOUNDFONT)
    for leido in leidos:
        if not leido:
            continue
        for nota in leido["notas"]:
            if (nota.channel == midi.DRUM_CHANNEL
                    or nota.channel not in leido["voces"]):
                continue
            programa = leido["programas"].get(nota.channel, 0)
            zona = muestras_brr.zona("program:%d@%d" % (programa, nota.pitch),
                                     snes_samples.SOUNDFONT)
            if zona is None:
                continue
            tiempo[programa][zona] += nota.end - nota.start
            adentro[programa, zona][nota.pitch] += nota.end - nota.start
    teclas = {}
    for programa, por_zona in tiempo.items():
        zona = max(por_zona, key=lambda z: (por_zona[z], z))
        raiz = zona[1]
        if muestras_brr.zona("program:%d@%d" % (programa, raiz),
                             snes_samples.SOUNDFONT) == zona:
            teclas[programa] = raiz
        else:
            cuanto = adentro[programa, zona]
            teclas[programa] = max(cuanto, key=lambda k: (cuanto[k], -k))
    return teclas


def _muestra(clave, presupuesto):
    """A key's voice with that budget in BRR bytes, or None if the SoundFont
    does not have it."""
    if clave[0] == "p":
        return snes_samples.build_voice(snes_samples.SOUNDFONT, clave[1],
                                        presupuesto, key=clave[2])
    return snes_samples.build_drum(snes_samples.SOUNDFONT, clave[1],
                                   presupuesto)


# A budget nobody reaches: with it, each sample comes out at the SoundFont's
# rate —capped at `MAX_RATE`—, which is what it would weigh untrimmed.
NATIVA = 1 << 24
# The minimum a sample is given even when its package is full.
PISO = 256


class Restriccion(collections.namedtuple("Restriccion",
                                         "nombre claves libre")):
    """A group of samples that has to fit together in `libre` bytes: those
    of a package's songs, with what its sound effects take already
    subtracted, or those of a package plus those of the song that may be
    playing when it loads."""
    __slots__ = ()


class Grupo(collections.namedtuple("Grupo", "nombre temas ocupan")):
    """Songs —indices— that have to fit together in the ARAM, with `ocupan`
    bytes of sound effects beside them: those of a package, a lone exit song,
    or a package with the song that may be playing when it loads. It is what
    the `Restriccion`s come from: which sample each song plays with is said
    by `copias`."""
    __slots__ = ()


def libre_para(muestras, efectos):
    """What is free for samples with `muestras` of music and `efectos` in
    the directory: the ARAM from behind the directory and the silence up to
    `ARAM_FIN`. Each directory entry is four bytes."""
    return ARAM_FIN - (SAMPLES_ADDR + 4 * (muestras + efectos) + len(SILENCIO))


def restricciones_de(asignacion, grupos, libre):
    """The `Restriccion`s for `repartir` for those groups, with the samples
    each song gets according to `asignacion` —see `copias`—."""
    salida = []
    for g in grupos:
        claves = set().union(*[set(asignacion[t].values()) for t in g.temas])
        if claves:
            salida.append(Restriccion(g.nombre, claves, libre - g.ocupan))
    return salida


# SRCN is one byte and the ROM's sample lists end with $FF, so the directory
# goes up to 255 entries: the music's samples and the sound effect places
# —see `lugares_de_efectos`— together.
DIRECTORIO_MAX = 255
# How many directory places can belong to sound effects: the ROM records
# which sound effect is in each one in `FAR_EFECTO_EN`, which has that size.
SE_LUGARES_MAX = 48
# No copy is made for a sample that already plays at nearly its rate: a
# directory entry is worth more than that.
COPIA_HASTA = 0.9
def se_de_siempre():
    """Up to how many directory entries the first round of `copias` goes:
    the ones the sound effects took when each had its own, and not today's.
    The game measured it: `[music] effect_slots_of_first_copies`."""
    return settings.value("music", "effect_slots_of_first_copies", kind=int)


def copias(claves_de, grupos, efectos, de_siempre, reales=None,
           tope=DIRECTORIO_MAX, hasta=COPIA_HASTA):
    """[{key: sample}], one per song: which sample each song plays each of
    its keys with. Almost always the key itself —one sample per program and
    per hit in the whole cartridge—, except for **the copies**.

    A sample has to fit in every group it is in, so its rate is set by the
    worst one, and the song that never plays there pays for it too: until
    2026-09-26, map 3's 43 KB of sound effects left the drums of **every**
    song at 10 kHz and the oboe at 7. A copy is the same key as another
    sample, only for the songs of one group: they stay the same, and the ones
    outside stop paying for a package they are not in. It is option B of
    step 6 of `workflow/tasks/testing/la-calidad-de-la-musica.md`, bounded:
    full B —one copy per song— would be some 370 directory entries against
    255.

    They are made in two rounds. `efectos` is how many directory entries the
    sound effects take today, and `de_siempre` how many they took when each
    had its own —see `se_de_siempre`—.

    **The usual ones**, one at a time and **the worst first**: the sample
    with the lowest fraction of its native size that has some song outside
    the group limiting it, copied for the ones inside. Then the allocation
    is redone, because the copy changes what each group takes, and it goes
    on until the directory is full as it used to be —with `de_siempre`
    entries for the sound effects— or until none is left below `hasta`.
    These are the ones taro listened to and approved on 2026-09-26, with
    what each one took away from others: what is freed in one package
    competes in the rest.

    **The ones from the entries the sound effects freed up**, from the same
    day: only those that **do not lower the rate of any (song, key) pair**
    compared to how the usual ones left it, and of those, the one that adds
    the most kHz across all. The first round, when it raises a sample, makes
    it compete with the others in its groups, and doing them one at a time,
    worst first, with the free entries lowered 56 pairs for others to raise
    126: see `workflow/tasks/*/el-directorio-de-los-efectos.md`. Here every
    possible copy —each key for the songs of each group it is in— is tried
    against the floor, and it goes on until none adds anything or the
    directory is full. This round allocates with the directory full, even if
    it does not fill up: that way no copy costs anyone its four bytes, and a
    directory that ends up shorter can only leave more room. And it
    allocates with `reales`, the same groups with what their sound effects
    really take: the `se_enteros()` the music does not pay for go in what it
    leaves free, and a copy that goes up to its rate would fill exactly
    that.
    """
    reales = grupos if reales is None else reales
    asignacion = [{k: k for k in ks} for ks in claves_de]
    nativas, tasas = {}, {}

    def nativa(clave):
        if clave not in nativas:
            voz = _muestra(clave, NATIVA)
            nativas[clave], tasas[clave] = len(voz.data), voz.rate / 1000.0
        return nativas[clave]

    def usan(clave):
        return [t for t, a in enumerate(asignacion) if clave in a.values()]

    def copiar(asig, clave, copia, adentro):
        nueva = [dict(a) for a in asig]
        for t in adentro:
            for base, suya in nueva[t].items():
                if suya == clave:
                    nueva[t][base] = copia
        return nueva

    temas_de = {g.nombre: set(g.temas) for g in grupos}
    while True:
        claves = {k for a in asignacion for k in a.values()}
        if len(claves) + de_siempre >= tope:
            break
        rs = restricciones_de(asignacion, grupos,
                              libre_para(len(claves), de_siempre))
        presupuesto, limita = repartir(
            claves, rs, nativas={k: nativa(k) for k in claves})
        peor = None
        for clave, nombre in sorted(limita.items()):
            fraccion = presupuesto[clave] / float(nativa(clave))
            if fraccion >= hasta:
                continue
            suyos = usan(clave)
            adentro = [t for t in suyos if t in temas_de[nombre]]
            afuera = len(suyos) - len(adentro)
            if not adentro or not afuera:
                continue
            candidato = (round(fraccion, 3), -afuera, clave, nombre, adentro)
            if peor is None or candidato < peor:
                peor = candidato
        if peor is None:
            break
        _f, _a, clave, nombre, adentro = peor
        asignacion = copiar(asignacion, clave, clave + ("@" + nombre,),
                            adentro)

    libre = libre_para(tope - efectos, efectos)

    def khz(asig):
        claves = {k for a in asig for k in a.values()}
        presupuesto, _l = repartir(
            claves, restricciones_de(asig, reales, libre),
            nativas={k: nativa(k) for k in claves})
        return claves, presupuesto, [
            {b: presupuesto[s] / float(nativa(s)) * tasas[s]
             for b, s in a.items()} for a in asig]

    claves, presupuesto, piso = khz(asignacion)
    actual = piso
    # Trying all of them on every pass is thousands of allocations: they are
    # tried in the order of what they added the last time they were tried
    # —new ones first—, and the first one that, tried again, adds at least
    # what any of the following ones added is taken. That it lowers no one
    # is always checked on the spot.
    cota = {}
    while len(claves) + efectos < tope:
        candidatas = []
        for clave in sorted(claves):
            if presupuesto[clave] >= hasta * nativa(clave):
                continue
            suyos = usan(clave)
            for g in grupos:
                adentro = tuple(t for t in suyos if t in temas_de[g.nombre])
                copia = clave + ("@" + g.nombre,)
                if (not adentro or len(adentro) == len(suyos)
                        or copia in claves
                        or any(c[0] == clave and c[2] == adentro
                               for c in candidatas)):
                    continue
                candidatas.append((clave, copia, adentro))
        candidatas.sort(key=lambda c: -cota.get(c, float("inf")))
        mejor = None
        for i, candidata in enumerate(candidatas):
            if mejor is not None and mejor[0] >= cota.get(candidata,
                                                          float("inf")):
                break
            clave, copia, adentro = candidata
            nueva = copiar(asignacion, clave, copia, adentro)
            claves_n, presupuesto_n, suben = khz(nueva)
            gana = sum(suben[t][b] - actual[t][b]
                       for t in range(len(suben)) for b in suben[t])
            if any(suben[t][b] < piso[t][b] - 1e-6
                   for t in range(len(suben)) for b in suben[t]):
                gana = 0.0
            cota[candidata] = gana
            if gana > 0.01 and (mejor is None or gana > mejor[0]):
                mejor = (gana, nueva, claves_n, presupuesto_n, suben)
        if mejor is None:
            break
        _g, asignacion, claves, presupuesto, actual = mejor
    return asignacion


def lugares_de_efectos(paquetes, nombres):
    """{sound effect: place}: which of the sound effects' directory entries
    each one goes in. `paquetes` are each package's sound effects and
    `nombres` all of them, in cartridge order.

    Until 2026-09-26 each sound effect had its own entry, and with 92 in the
    cartridge and the music beside them the directory was full: `copias` had
    no room to make more. But the ARAM holds one package at a time, and none
    carries more than a score of sound effects, so two sound effects that
    are never in the same package can share an entry. It is graph coloring
    —two sound effects touch if they share a package—, and with DSATUR as
    many places as the most loaded package has sound effects are enough.

    The ROM cannot tell from the entry which sound effect is there: it
    records it when uploading it (`FAR_EFECTO_EN`, in
    tools/runtime/paquete_de_audio.s).
    """
    toca = {n: set() for n in nombres}
    for suyos in paquetes:
        suyos = [n for n in suyos if n in toca]
        for n in suyos:
            toca[n] |= set(suyos) - {n}
    orden = {n: i for i, n in enumerate(nombres)}
    lugar = {}
    while len(lugar) < len(toca):
        # The most constrained first —the one with the most distinct places
        # already taken around it—, and among those the one with the most
        # neighbors; on a tie, the one earlier in the cartridge, so it always
        # comes out the same.
        n = max((n for n in toca if n not in lugar),
                key=lambda n: (len({lugar[v] for v in toca[n] if v in lugar}),
                               len(toca[n]), -orden[n]))
        tomados = {lugar[v] for v in toca[n] if v in lugar}
        lugar[n] = min(set(range(len(tomados) + 1)) - tomados)
    return lugar


def repartir(claves, restricciones, margen=None, nativas=None):
    """({key: budget}, {key: constraint that limited it}): how much each
    sample gets so that every constraint fits in its space minus `margen`.

    It is progressive filling over the fraction of each sample's native
    size: the fraction of all of them is raised together until some
    constraint fills up, that one's samples are frozen, and it goes on with
    the rest. That way a sample is limited by its **worst** package and not
    by the whole bank, and the one with room to spare does not pay for the
    one without. Whatever is in no constraint that fills up goes whole.
    """
    margen = ARAM_MARGEN if margen is None else margen
    if nativas is None:
        nativas = {k: len(_muestra(k, NATIVA).data) for k in claves}
    fraccion, limita = {}, {}
    libres = set(claves)
    activas = [r for r in restricciones if r.claves & libres]
    # Each constraint's totals are kept up to date as samples freeze,
    # instead of summing them again on every pass: `copias` allocates
    # thousands of times per conversion, and this way each allocation costs
    # a fraction.
    suyas = [set(r.claves) & libres for r in activas]
    suma = [sum(nativas[k] for k in s) for s in suyas]
    fijo = [0.0] * len(activas)
    donde = collections.defaultdict(list)
    for i, s in enumerate(suyas):
        for k in s:
            donde[k].append(i)
    vivas = list(range(len(activas)))
    while libres and vivas:
        peor, cual = None, None
        for i in vivas:
            if not suyas[i]:
                continue
            f = (activas[i].libre - margen - fijo[i]) / suma[i]
            if peor is None or f < peor:
                peor, cual = f, i
        if peor is None or peor >= 1:
            break
        nivel = max(0.0, peor)
        for k in list(suyas[cual]):
            fraccion[k] = nivel
            limita[k] = activas[cual].nombre
            libres.discard(k)
            for j in donde[k]:
                fijo[j] += nivel * nativas[k]
                suma[j] -= nativas[k]
                suyas[j].discard(k)
        vivas.remove(cual)
    return ({k: max(PISO, int(fraccion.get(k, 1.0) * nativas[k]))
             for k in claves}, limita)


class Banco:
    """The samples shared by **every** song in the ROM, one per program and
    one per hit, each with the budget of its worst package.

    There is only one —except for the copies from `copias`—, and not to save
    cartridge space —there is plenty of that— but because of the numbering:
    the SRCN the stream writes is the sample's index in the cartridge, so
    two songs that play piano point to the same one. But **it is not
    uploaded whole**: the ARAM gets packages, one per map —see
    `paquete_cargar` in tools/runtime/paquete_de_audio.s—, so what has to
    fit in the 64 KB is not the bank but each package, with its sound
    effects.

    That is why the budget is per package: step 6 of
    `workflow/tasks/todo/la-calidad-de-la-musica.md`, option A, chosen by
    taro on 2026-09-26. Until that day the whole bank had to fit in the ARAM
    —40 KB for the melodic part and the percussion with whatever was left—,
    and the songs that did not fit stopped contributing programs: nineteen
    of the thirty-two in `release` played with what others had put in, or
    were silent.

    `restricciones` are `repartir`'s; `limita` says which one set each
    sample, for the converter's report.
    """

    def __init__(self, claves, restricciones=(), margen=None):
        claves = {k for k in claves if _muestra(k, NATIVA) is not None}
        presupuesto, self.limita = repartir(claves, restricciones, margen)
        voz = {k: _muestra(k, presupuesto[k]) for k in claves}
        # The budget is a guide: the real length is rounded up to BRR blocks,
        # so what it really takes is checked and, if a constraint goes over
        # its space —without the margin: the margin is for this—, its samples
        # are asked for less and it is built again.
        for _ in range(20):
            pasadas = [r for r in restricciones
                       if self._suma(voz, r.claves) > r.libre]
            if not pasadas:
                break
            for r in pasadas:
                usa = self._suma(voz, r.claves)
                for k in r.claves & set(voz):
                    presupuesto[k] = max(PISO, int(presupuesto[k] * r.libre
                                                   / usa * 0.98))
                    voz[k] = _muestra(k, presupuesto[k])
        else:
            raise SystemExit(
                "the samples of %s do not fit in the ARAM even at the minimum"
                % ", ".join("%s (%d of %d B)" % (r.nombre,
                                                 self._suma(voz, r.claves),
                                                 r.libre) for r in pasadas))
        self.restricciones = list(restricciones)
        self.claves = ([k for k in sorted(claves) if k[0] == "p"]
                       + [k for k in sorted(claves) if k[0] == "g"])
        self.voces = [voz[k] for k in self.claves]
        # From MIDI program to index in the bank, which is what goes in
        # `V_SRCN`; hits go after the melodic ones, so the DSP does not tell
        # percussion from anything else. These are the samples without
        # copies: a song with copies asks for its own with `del_tema`.
        self.melodicas = {k[1]: i for i, k in enumerate(self.claves)
                          if k[0] == "p" and len(k) == 3}
        self.golpes = {k[1]: i for i, k in enumerate(self.claves)
                       if k[0] == "g" and len(k) == 2}
        self._envolventes = {}

    def del_tema(self, asignacion):
        """The bank as a song sees it: its programs and its hits point to the
        samples it was given —see `copias`—, and the rest is everyone's.
        `asignacion` is {key: sample}."""
        vista = _Vista(self)
        indice = {k: i for i, k in enumerate(self.claves)}
        vista.melodicas = {base[1]: indice[k] for base, k in asignacion.items()
                           if base[0] == "p" and k in indice}
        vista.golpes = {base[1]: indice[k] for base, k in asignacion.items()
                        if base[0] == "g" and k in indice}
        return vista

    @staticmethod
    def _suma(voz, claves):
        return sum(len(voz[k].data) for k in claves if k in voz)

    def ocupa(self, claves):
        """How much the samples of those keys take in the ARAM."""
        return sum(len(v.data) for k, v in zip(self.claves, self.voces)
                   if k in claves)

    def envolvente(self, program, key):
        """(ADSR1, ADSR2, release GAIN) of a melodic note: the envelope of
        the SoundFont zone covering the key, translated by `sdsp.envelope`.

        The zone may not be the sample's —each program carries only one, the
        one from `zonas_mas_usadas`—, and that is on purpose: it is the
        envelope the SoundFont would give that key, and on the piano the
        decay changes key by key. If no zone covers the key, middle C's.
        """
        clave = (program, key)
        if clave not in self._envolventes:
            sf2 = (muestras_brr.envolvente("program:%d@%d" % (program, key),
                                           snes_samples.SOUNDFONT)
                   or muestras_brr.envolvente(
                       "program:%d@%d" % (program, snes_samples.REFERENCE_KEY),
                       snes_samples.SOUNDFONT))
            self._envolventes[clave] = sdsp.envelope(sf2, key)
        return self._envolventes[clave]

    @property
    def bytes(self):
        """How much it takes in ARAM: the directory plus the samples."""
        return 4 * len(self.voces) + sum(len(v.data) for v in self.voces)


class _Vista:
    """What `Banco.del_tema` returns: the same bank with one song's indices.
    Whatever it does not override it reads from the bank."""

    def __init__(self, banco):
        self._banco = banco

    def __getattr__(self, nombre):
        return getattr(self._banco, nombre)


# --- events -----------------------------------------------------------------

class Frame:
    """Everything that happens in a frame, split by when it has to be
    written.

    Order matters: first each voice is prepared —volume, pitch, timbre— and
    only at the end are KON and KOF touched, which are what trigger. If it
    were done the other way round, the note would start with the previous
    one's values.
    """

    __slots__ = ("release", "setup", "kon", "kof", "control")

    def __init__(self):
        # The notes released in this frame: (voice, release GAIN), and the
        # voices brought down with `RAMPA` because another note takes them in
        # the next frame.
        self.release = []
        # The ones that start: one `Preparacion` per note, in order.
        self.setup = []
        self.kon = 0
        self.kof = 0
        # What the controllers change on a voice that was already sounding:
        # register -> value, and the frame's last one wins. A dict and not a
        # list because a fade brings several CC7s per frame, and writing the
        # ones in the middle is bytes the DSP never gets to use.
        self.control = {}


# What a note writes to its voice before the KON, and the GAIN it will be
# released with —None for the drums, which are not released—. The seven
# writes come from `Preparacion.escrituras`, in the order they go to the DSP.
class Preparacion(collections.namedtuple(
        "Preparacion", "voz izquierda derecha altura muestra adsr1 adsr2 gain")):
    __slots__ = ()

    def escrituras(self):
        base = self.voz * 0x10
        return [(base + sdsp.V_VOL_L, self.izquierda),
                (base + sdsp.V_VOL_R, self.derecha),
                (base + sdsp.V_PITCH_L, self.altura & 0xFF),
                (base + sdsp.V_PITCH_H, self.altura >> 8),
                (base + sdsp.V_SRCN, self.muestra),
                (base + sdsp.V_ADSR1, self.adsr1),
                (base + sdsp.V_ADSR2, self.adsr2)]


def build_events(notes, voices, programs, banco, controls=(), reparto=None,
                 aire=sdsp.AIRE):
    """The writes to the DSP, frame by frame.

    Each channel has its group of voices —since step 5, all eight for
    everyone: see `assign`—; a note that starts takes a free one, the one
    that cuts least according to `_libre`, and if they are all held it
    steals the one `_victima` says, or it does not play. It is what a
    synthesizer does when it runs out of polyphony.

    The bank comes from outside and is not built here: every song in the ROM
    shares it, so the `V_SRCN` indices this stream writes are that bank's and
    not those of one of its own. See `Banco`.

    `controls` are the song's `midi.Control`s, already in frames: volume,
    expression and pan go into the volume of each side of the note, and bend
    into its pitch. A frame's controls are applied before its notes, so the
    note starts with the state the frame ends with; and a voice that was
    already sounding —or is in its tail— gets its registers rewritten.

    `reparto`, if a list is given, is filled with what each note that has a
    sample got: (note, voice or None if it did not play, frame its voice was
    stolen in or None, until when it holds it —the end of the note, or of
    the sample if it is a hit shorter than the note—). It is where the
    amount of lost note-time comes from.

    `aire` is the ceiling of this song's voices, `sdsp.AIRE`'s or a lower
    one: see `leer_techos`.
    """
    frames = collections.defaultdict(Frame)
    techo = aire / sdsp.AIRE
    bank, index_of, drum_index = banco.voces, banco.melodicas, banco.golpes

    estado = collections.defaultdict(lambda: dict(midi.DEFAULTS))
    pendientes = sorted(controls, key=lambda c: c.start)
    siguiente = 0

    def lados(note, drums):
        c = estado[note.channel]
        return sdsp.volume(note.velocity,
                           techo * (sdsp.CEILING_DRUM if drums
                                    else sdsp.CEILING),
                           c[midi.VOLUME], c[midi.EXPRESSION], c[midi.PAN])

    def altura(note, drums):
        if drums:
            # In General MIDI the note picks the instrument, not the pitch, so
            # each hit has its own sample and is played at its original rate:
            # transposing it would turn a bass drum into something else. That
            # is why the bend does not move it either.
            drum = bank[drum_index[note.pitch]]
            return sdsp.pitch_for(drum.root, drum.root, drum.rate)
        instrument = bank[index_of[programs.get(note.channel, 0)]]
        return sdsp.pitch_for(note.pitch + estado[note.channel][midi.BEND],
                              instrument.root, instrument.rate)

    def controlar(hasta):
        """Applies the controllers up to frame `hasta`, and rewrites what
        changed on the voices whose note is from that channel."""
        nonlocal siguiente
        while (siguiente < len(pendientes)
               and pendientes[siguiente].start <= hasta):
            c = pendientes[siguiente]
            siguiente += 1
            if estado[c.channel][c.number] == c.value:
                continue
            estado[c.channel][c.number] = c.value
            # `owner` still has the note after its end, so this also changes
            # the volume of a tail that is dying out, like fluidsynth.
            # Cutting it at the end of the note saved 1,195 B across the 32
            # songs of `release` (2026-09-26): not worth a special case.
            for voice, note in owner.items():
                if note.channel != c.channel:
                    continue
                base = voice * 0x10
                drums = note.channel == midi.DRUM_CHANNEL
                frame = frames[c.start].control
                if c.number == midi.BEND:
                    if drums:
                        continue
                    step = altura(note, drums)
                    frame[base + sdsp.V_PITCH_L] = step & 0xFF
                    frame[base + sdsp.V_PITCH_H] = step >> 8
                else:
                    izquierda, derecha = lados(note, drums)
                    frame[base + sdsp.V_VOL_L] = izquierda
                    frame[base + sdsp.V_VOL_R] = derecha

    def en_orden():
        """The notes frame by frame, each frame in `_orden_del_cuadro`'s
        order. The frame's controllers are applied before sorting it,
        because the order goes by the level each note starts with; and since
        it is a generator, that only happens once the previous frame has
        allocated its voices, which is when each note used to do it."""
        por_cuadro = collections.defaultdict(list)
        for note in notes:
            por_cuadro[note.start].append(note)
        for cuadro in sorted(por_cuadro):
            controlar(cuadro)
            yield from _orden_del_cuadro(por_cuadro[cuadro], lambda n: sum(
                lados(n, n.channel == midi.DRUM_CHANNEL)))

    # Who owns each voice now: the last note that took it, with until when
    # it holds it and until when it can be heard. A note's release is only
    # scheduled at the end, and only if it reached its end still being the
    # owner: if another note stole the voice first, releasing it would
    # release the thief. Until 2026-09-25 it was scheduled when taking the
    # voice, and 329 notes of `escape_newyork` were cut short, almost all
    # of them the bass.
    voces, owner, robbed, sounded, rampas = {}, {}, {}, [], []
    de_la_voz = {}                  # its owner's `reparto` entry
    for note in en_orden():
        group = voices.get(note.channel)
        if not group:
            continue
        program = programs.get(note.channel, 0)
        drums = note.channel == midi.DRUM_CHANNEL
        # Before picking a voice: a note without a sample does not play, and
        # if it took the voice it would take the place of one that does.
        source = (drum_index.get(note.pitch) if drums
                  else index_of.get(program))
        if source is None:
            continue                    # the bank does not have that hit or program

        step = altura(note, drums)
        izquierda, derecha = lados(note, drums)
        if drums:
            # Instant attack and no decay: the hit already carries its own
            # shape, the envelope only shuts it off at the end so it does not
            # keep reading memory. It has no release, so no GAIN either: it
            # is heard until the sample runs out. But the voice holds it only
            # until the note's end in the MIDI, and what follows is like a
            # release tail: another note can take it. Holding it until the
            # end of the sample made the melodic part lose, across the 32
            # songs, 8.3% of note-time on average instead of 7.9%
            # —Lunar_Pyramid 33% instead of 23%— to save hit tails that in
            # fluidsynth are also released with the note's end.
            adsr1, adsr2, gain = 0x8F, 0xE0, None
            muestra = bank[source]
            cola = note.start + int(math.ceil(
                muestra.frames * TICKS_PER_SECOND / float(muestra.rate)))
            fin = min(cola, note.end)
        else:
            adsr1, adsr2, gain = banco.envolvente(program, note.pitch)
            fin, cola = note.end, note.end + _cuadros_del_release(gain)

        t = note.start
        libres = [v for v in group if v not in voces or voces[v].fin <= t]
        if libres:
            voice = min(libres, key=lambda v: _libre(v, t, voces, note, drums))
        else:
            voice = _victima(note, t, group, voces, izquierda + derecha)
        if voice is None:
            if reparto is not None:
                reparto.append([note, None, None, fin])
            continue
        if voice in owner:
            robbed.setdefault(id(owner[voice]), t)
            if voice in de_la_voz:
                de_la_voz[voice][2] = t
            # If the voice is still sounding, it is brought down to zero in the
            # frame before: KON drops the envelope to zero at once, and that is
            # a click. Not for a note that started in that same frame, which is
            # prepared after the release and undoes it.
            anterior = voces[voice]
            if anterior.cola > t - 1 and anterior.nota.start < t - 1:
                rampas.append((t - 1, voice))
        voces[voice] = _Voz(note, fin, cola, izquierda + derecha)
        owner[voice] = note
        if reparto is not None:
            reparto.append([note, voice, None, fin])
            de_la_voz[voice] = reparto[-1]

        start = frames[note.start]
        base = voice * 0x10
        # What the controllers were rewriting for the previous owner in this
        # frame no longer applies: this note writes its own, with the same
        # state.
        for registro in (sdsp.V_VOL_L, sdsp.V_VOL_R, sdsp.V_PITCH_L,
                         sdsp.V_PITCH_H):
            start.control.pop(base + registro, None)
        start.setup.append(Preparacion(voice, izquierda, derecha, step, source,
                                       adsr1, adsr2, gain))

        start.kon |= 1 << voice
        if not drums:
            sounded.append((note, voice, gain))

    # The ones left after the last note: the fade at the end of
    # `escape_newyork` is CC7 over the notes that were already sounding.
    controlar(float("inf"))

    for note, voice, gain in sounded:
        # Stolen in the same frame it ends in is not released either: the
        # thief writes its ADSR1 after the release and undoes it, so it would
        # be six bytes that do nothing.
        if robbed.get(id(note), note.end + 1) <= note.end:
            continue
        frames[note.end].release.append((voice, gain))
    # Ramps go after their frame's releases, to win over them.
    for cuadro, voice in rampas:
        frames[cuadro].release.append((voice, RAMPA))

    return frames


def init_writes():
    """The DSP's state before the first note.

    It depends neither on the bank nor on which voices are percussion:
    everything here is global to the DSP. It used to take both as parameters
    and never looked at them.
    """
    writes = [
        (sdsp.FLG, sdsp.FLG_BASE),          # no echo, no mute
        (sdsp.MVOL_L, sdsp.MASTER), (sdsp.MVOL_R, sdsp.MASTER),
        (sdsp.EVOL_L, 0x00), (sdsp.EVOL_R, 0x00),
        (sdsp.EON, 0x00),                   # no voice sends to the echo
        (sdsp.PMON, 0x00),                  # no modulation between voices
        (sdsp.NON, 0x00),                   # noise is no longer used: the
                                            # percussion has its own samples
        (sdsp.DIR, SAMPLES_ADDR >> 8),      # where the directory is
        (sdsp.KON, 0x00), (sdsp.KOF, 0x00),
    ]
    return writes


def escrituras(frames, length, init):
    """What the song writes to the DSP: (frame, register, value), in order.

    It is **the stream's specification**, and what until 2026-09-26 was the
    stream itself —a three-byte `OP_DSP register value` per write—. `pack`'s
    per-note format has to expand to exactly this, frame by frame:
    `build_varios` verifies it with every song it builds, and in the ROM
    `rom/pruebas/rpgmaker/test_musica_escrituras.py` does.

    The DSP's registers are plain latches: writing the same value again does
    nothing. So what each one holds is tracked and the writes that change
    nothing are skipped, and there are many: a voice's timbre and sample
    almost never change between two consecutive notes.

    That is safe even with the song looping. A write is skipped only because
    an earlier write in the same stream left that value, and that earlier
    one also runs on the second pass; by induction, the DSP's state at every
    point of the second pass is the same as in the first.

    KON is the exception and is never cached: it is not a latch but a
    trigger. The DSP looks at it every two milliseconds and starts the
    voices whose bit is set, so it has to be cleared by hand or the note
    repeats on its own.
    """
    salen = []
    state = {}
    cuadro = 0

    def write(register, value):
        value &= 0xFF
        if state.get(register) == value:
            return
        state[register] = value
        salen.append((cuadro, register & 0xFF, value))

    for register, value in init:
        write(register, value)

    sounding = 0
    for at in sorted(frames):
        if at > length:
            break
        frame = frames[at]
        if not (frame.release or frame.setup or frame.kon or frame.kof
                or frame.control):
            continue
        cuadro = at

        if sounding:                       # clear the previous frame's trigger
            salen.append((cuadro, sdsp.KON, 0x00))
            sounding = 0
        write(sdsp.KOF, 0x00)
        for voice, gain in frame.release:
            write(voice * 0x10 + sdsp.V_ADSR1, 0x00)    # ADSR off: GAIN rules
            write(voice * 0x10 + sdsp.V_GAIN, gain)
        for preparacion in frame.setup:
            for register, value in preparacion.escrituras():
                write(register, value)
        for register, value in sorted(frame.control.items()):
            write(register, value)
        if frame.kof:
            write(sdsp.KOF, frame.kof)
        if frame.kon:
            salen.append((cuadro, sdsp.KON, frame.kon))
            sounding = frame.kon

    # At the end everything is shut off, otherwise the last note keeps
    # sounding into the loop.
    cuadro = max(cuadro, length)
    salen.append((cuadro, sdsp.KON, 0x00))
    salen.append((cuadro, sdsp.KOF, 0xFF))
    return salen


# --- the per-note format ---------------------------------------------------
#
# Until 2026-09-26 the stream was the writes themselves —`OP_DSP register
# value`, three bytes each— and it weighed more than a fifth of the
# cartridge. Now they are events, and the 65816 expands them (`music_frame`)
# into **the same writes, frame by frame**: the format cannot change how it
# sounds. `build_varios` verifies it with every song it builds, and in the
# ROM `rom/pruebas/rpgmaker/test_musica_escrituras.py` does.
#
# A song is its stream and its table of *sounds*: everything a note writes to
# its voice except the volume —pitch, sample, ADSR— plus the GAIN it will be
# released with. The pitch goes inside, and not separately, because that way
# the instrument and the key are a single byte: the drums change hit on
# almost every note, and the piano changes ADSR2 with the key.
#
# What the format does **not** assume, on purpose, is which channel each
# voice belongs to: the event says the voice and the converter chose it. That
# way step 5's priority allocation from `la-calidad-de-la-musica.md` —any
# voice for any channel— fits in without touching it: a voice changing
# instrument note by note costs the same as not changing it, one sound per
# note. And the ramp before reusing a sounding voice is an `OP_RELEASE_GAIN`
# with the ramp's GAIN, one frame before the note.
#
# The register cache of `escrituras` is kept by the 65816 and not by the
# stream: each event says values and the decoder skips the one the register
# already has. It has a single trap, which is that it cannot say "I don't
# know" —see `decodificar`—. KON does not go in the stream either: the notes
# accumulate it and the wait that closes the frame fires it, which is
# exactly `escrituras`'s rule.

VOCES = sdsp.VOICES
# The voice registers the decoder keeps in its cache: from VOL_L to GAIN.
REGISTROS_DE_VOZ = 8


# The families of eight opcodes, one per voice: the voice goes in the three
# low bits and the family in the upper ones, which is how the decoder finds
# them. See the header of `tools/protocol/music.toml`, which cannot declare
# them.
FAMILIAS = ["NOTE", "NOTE_VOL", "NOTE_PAN", "RELEASE", "RELEASE_GAIN",
            "SET_VOL", "SET_PAN", "SET_PITCH"]
for _k, _familia in enumerate(FAMILIAS):
    for _v in range(VOCES):
        assert globals()["OP_%s_V%d" % (_familia, _v)] == 8 * _k + _v, (
            "music.toml: OP_%s_V%d is not where the family expects it"
            % (_familia, _v))
# The short waits, from OP_WAIT_1 to OP_WAIT_32: one byte closes the frame
# and waits. Almost all of them fit; the rest go with OP_WAIT, sixteen bits.
ESPERA_CORTA = 32
for _n in range(1, ESPERA_CORTA + 1):
    assert globals()["OP_WAIT_%d" % _n] == OP_WAIT_1 + _n - 1, _n
assert OP_WAIT_1 == 8 * len(FAMILIAS)


def _es_de_voz(registro):
    return registro < 0x80 and registro & 0x0F < REGISTROS_DE_VOZ


def escrituras_del_arranque():
    """What `OP_INIT` writes: the `dsp_init_*` table `emit` leaves for the
    ROM —the startup without KON or KOF— followed by KON and KOF at zero."""
    return ([(r, v) for r, v in init_writes() if r not in (sdsp.KON, sdsp.KOF)]
            + [(sdsp.KON, 0x00), (sdsp.KOF, 0x00)])


class _Codificador:
    """Builds a song's per-note stream. It keeps the same state as the
    65816's decoder —the voice register cache, each voice's sound, the
    frame's accumulated KON— and the same cache as `escrituras`, so it
    decides each event knowing exactly which writes it will produce."""

    def __init__(self):
        self.stream = bytearray()
        self.sonidos, self._sonido = [], {}
        self.state = {}             # `escrituras`'s cache
        self.sonido_de = {}         # the sound of each voice's last note

    def sonido(self, p):
        # In the order they are written —PITCH_L, PITCH_H, SRCN, ADSR1,
        # ADSR2—, which is what lets the 65816 walk it with a single index.
        clave = (p.altura & 0xFF, p.altura >> 8, p.muestra, p.adsr1, p.adsr2,
                 0 if p.gain is None else p.gain)
        if clave not in self._sonido:
            self._sonido[clave] = len(self.sonidos)
            self.sonidos.append(clave)
        return self._sonido[clave]

    def cambia(self, registro, valor):
        return self.state.get(registro) != valor & 0xFF

    def escribir(self, registro, valor):
        self.state[registro] = valor & 0xFF

    def op(self, codigo, *datos):
        self.stream.extend((codigo,) + datos)

    def global_(self, registro, valor):
        """A cached write outside the voices: it goes raw if it changes."""
        assert not _es_de_voz(registro), registro
        if self.cambia(registro, valor):
            self.escribir(registro, valor)
            self.op(OP_DSP, registro, valor & 0xFF)

    def nota(self, p):
        v, base = p.voz, p.voz * 0x10
        s = self.sonido(p)
        if (not self.cambia(base + sdsp.V_VOL_L, p.izquierda)
                and not self.cambia(base + sdsp.V_VOL_R, p.derecha)):
            self.op(OP_NOTE_V0 + v, s)
        elif p.izquierda == p.derecha:
            self.op(OP_NOTE_VOL_V0 + v, p.izquierda, s)
        else:
            self.op(OP_NOTE_PAN_V0 + v, p.izquierda, p.derecha, s)
        self.sonido_de[v] = s
        for registro, valor in p.escrituras():
            self.escribir(registro, valor)

    def release(self, v, gain):
        base = v * 0x10
        if (not self.cambia(base + sdsp.V_ADSR1, 0)
                and not self.cambia(base + sdsp.V_GAIN, gain)):
            return                      # it would write nothing
        if self.sonidos[self.sonido_de[v]][5] == gain:
            self.op(OP_RELEASE_V0 + v)
        else:
            self.op(OP_RELEASE_GAIN_V0 + v, gain)
        self.escribir(base + sdsp.V_ADSR1, 0)
        self.escribir(base + sdsp.V_GAIN, gain)

    def controles(self, control):
        por_voz = collections.defaultdict(dict)
        for registro, valor in control.items():
            assert _es_de_voz(registro), (
                "a controller writes $%02X, which is not a voice register" % registro)
            por_voz[registro >> 4][registro & 0x0F] = valor
        for v in sorted(por_voz):
            regs, base = por_voz[v], v * 0x10
            assert set(regs) in ({0, 1}, {2, 3}, {0, 1, 2, 3}), (
                "a controller writes to voice %d the registers %s: the "
                "format only knows the volume pair and the pitch pair"
                % (v, sorted(regs)))
            if 0 in regs and (self.cambia(base, regs[0])
                              or self.cambia(base + 1, regs[1])):
                if regs[0] == regs[1]:
                    self.op(OP_SET_VOL_V0 + v, regs[0])
                else:
                    self.op(OP_SET_PAN_V0 + v, regs[0], regs[1])
                self.escribir(base, regs[0])
                self.escribir(base + 1, regs[1])
            if 2 in regs and (self.cambia(base + 2, regs[2])
                              or self.cambia(base + 3, regs[3])):
                self.op(OP_SET_PITCH_V0 + v, regs[2], regs[3])
                self.escribir(base + 2, regs[2])
                self.escribir(base + 3, regs[3])

    def esperar(self, cuadros):
        if 1 <= cuadros <= ESPERA_CORTA:
            self.op(OP_WAIT_1 + cuadros - 1)
        else:
            self.op(OP_WAIT, cuadros & 0xFF, cuadros >> 8)


def pack(frames, length, init):
    """The song in the per-note format: (stream, sounds).

    `sonidos` are the ones the song plays, in the order of their indices:
    each is (PITCH_L, PITCH_H, SRCN, ADSR1, ADSR2, release GAIN), and the
    stream names them by index. What the stream produces in the DSP is
    **exactly** `escrituras(frames, length, init)`, write by write and frame
    by frame; `build_varios` verifies it with `decodificar`, which is the
    model of the 65816's decoder.
    """
    c = _Codificador()
    init = list(init)
    if [(r, v & 0xFF) for r, v in init] == escrituras_del_arranque():
        c.op(OP_INIT)
        for r, v in init:
            c.escribir(r, v)
    else:
        for r, v in init:
            c.global_(r, v)

    previo, sonando = 0, 0
    for at in sorted(frames):
        if at > length:
            break
        frame = frames[at]
        if not (frame.release or frame.setup or frame.kon or frame.kof
                or frame.control):
            continue
        if at > previo:
            c.esperar(at - previo)
            sonando = 0                 # the decoder clears KON on opening
        previo = at
        c.global_(sdsp.KOF, 0x00)
        for voz, gain in frame.release:
            c.release(voz, gain)
        kon = 0
        for p in frame.setup:
            c.nota(p)
            kon |= 1 << p.voz
        c.controles(frame.control)
        if frame.kof:
            c.global_(sdsp.KOF, frame.kof)
        assert kon == frame.kon, "the frame's KON is not its notes' KON"
        sonando = kon

    # The end: `escrituras` clears KON and shuts everything off in frame
    # `length`.
    if length > previo:
        c.esperar(length - previo)
        if not sonando:
            c.op(OP_DSP, sdsp.KON, 0x00)
    else:
        c.op(OP_WAIT, 0, 0)             # fires the KON without waiting
        c.op(OP_DSP, sdsp.KON, 0x00)
    c.op(OP_DSP, sdsp.KOF, 0xFF)
    c.op(OP_END)
    if len(c.sonidos) > 256:
        raise SystemExit("the song uses %d sounds and the index is one byte"
                         % len(c.sonidos))
    return bytes(c.stream), c.sonidos


def decodificar(stream, sonidos):
    """The model of the 65816's decoder —`music_frame`, in
    tools/runtime/musica.s—, step by step: what the stream writes, (frame,
    register, value), up to its `OP_END`. It has to give the same as
    `escrituras`.

    It also imitates what the 65816 does **not** know. Its cache has no
    "empty": when the song starts it holds whatever was left, and what stands
    in for that is that each voice's first note writes everything without
    looking, and the first release writes its GAIN regardless. If the stream
    ever compared against a register nobody has written yet, on the console
    it would be comparing against garbage: here that stops.
    """
    salen, cache, vistas, con_gain = [], {}, set(), set()
    gain_de = {}
    cuadro, kon, sonando, i = 0, 0, 0, 0

    def w(registro, valor):
        salen.append((cuadro, registro, valor))

    def escribir(registro, valor, forzar=False):
        if not forzar:
            assert registro in cache, (
                "the stream compares register $%02X against the cache before "
                "writing it: in the ROM it would be garbage" % registro)
            if cache[registro] == valor:
                return
        cache[registro] = valor
        w(registro, valor)

    def leer():
        nonlocal i
        i += 1
        return stream[i - 1]

    while True:
        op = leer()
        if op == OP_END:
            return salen
        if op == OP_INIT:
            for r, v in escrituras_del_arranque():
                w(r, v)
            continue
        if op == OP_DSP:
            r, v = leer(), leer()
            assert not _es_de_voz(r)
            w(r, v)
            continue
        if op == OP_WAIT or OP_WAIT_1 <= op < OP_WAIT_1 + ESPERA_CORTA:
            if op == OP_WAIT:
                n = leer()
                n |= leer() << 8
            else:
                n = op - OP_WAIT_1 + 1
            if kon:
                w(sdsp.KON, kon)
                sonando, kon = kon, 0
            if n:
                cuadro += n
                if sonando:
                    w(sdsp.KON, 0)
                    sonando = 0
            continue
        assert op < OP_WAIT_1, "opcode $%02X" % op
        familia, v = FAMILIAS[op >> 3], op & 7
        base = v * 0x10
        if familia.startswith("NOTE"):
            # The voice's first note writes everything: see above.
            forzar = v not in vistas
            vistas.add(v)
            if familia == "NOTE_VOL":
                vol = leer()
                escribir(base + sdsp.V_VOL_L, vol, forzar)
                escribir(base + sdsp.V_VOL_R, vol, forzar)
            elif familia == "NOTE_PAN":
                izq, der = leer(), leer()
                escribir(base + sdsp.V_VOL_L, izq, forzar)
                escribir(base + sdsp.V_VOL_R, der, forzar)
            sonido = sonidos[leer()]
            for k in range(5):          # from PITCH_L to ADSR2, in that order
                escribir(base + sdsp.V_PITCH_L + k, sonido[k], forzar)
            gain_de[v] = sonido[5]
            kon |= 1 << v
        elif familia.startswith("RELEASE"):
            gain = leer() if familia == "RELEASE_GAIN" else gain_de[v]
            escribir(base + sdsp.V_ADSR1, 0)
            escribir(base + sdsp.V_GAIN, gain, v not in con_gain)
            con_gain.add(v)
        elif familia == "SET_VOL":
            vol = leer()
            escribir(base + sdsp.V_VOL_L, vol)
            escribir(base + sdsp.V_VOL_R, vol)
        elif familia == "SET_PAN":
            izq, der = leer(), leer()
            escribir(base + sdsp.V_VOL_L, izq)
            escribir(base + sdsp.V_VOL_R, der)
        elif familia == "SET_PITCH":
            lo, hi = leer(), leer()
            escribir(base + sdsp.V_PITCH_L, lo)
            escribir(base + sdsp.V_PITCH_H, hi)
        else:
            raise AssertionError("opcode $%02X" % op)


def verificar_formato(nombre, stream, sonidos, referencia):
    """That a song's stream, decoded, writes the same as `escrituras`: every
    register, every value, in the same order and the same frame. The
    converter stops at the first difference."""
    salen = decodificar(stream, sonidos)
    if salen == referencia:
        return
    for n, (a, b) in enumerate(zip(salen, referencia)):
        if a != b:
            break
    else:
        n = min(len(salen), len(referencia))
    raise SystemExit(
        "the stream of %s does not write what it has to write: write %d is "
        "%s and it had to be %s (frame, register, value)"
        % (nombre, n, salen[n] if n < len(salen) else "none",
           referencia[n] if n < len(referencia) else "none"))


def tema_del_mapa(map_id, game_dir=None):
    """The name of the song a map gets from the tree, or "" if it has none."""
    game_dir = game_dir or resources.GAME_DIR
    return temas_de_los_mapas([map_id], game_dir)[0]


def temas_de_los_mapas(map_ids, game_dir=None):
    """`tema_del_mapa` for each one, reading the tree only once.

    "" means that entering the map **does not change** what is playing:
    either the map has no song —the root of the tree—, or it is
    `music_type` 1, "an event decides". It is the early `return` of
    `Game_Map::PlayBgm` in easyrpg. An "(OFF)" is a song: it silences, just
    like a `PlayBGM` of "(OFF)".
    """
    game_dir = game_dir or resources.GAME_DIR
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    nombres = []
    for map_id in map_ids:
        music = tree.map_music(map_id)
        nombres.append(music["name"] if music else "")
    return nombres


def leer_tema(name, game_dir=None):
    """What needs to be known about a song **before** having the bank.

    Returns None if the name is missing or is not a MIDI, which is like a map
    without music: the song still goes into the numbering —the bytecode
    already carries its index— but its stream is a lone `OP_END` and the ROM
    stays silent when it is played.
    """
    game_dir = game_dir or resources.GAME_DIR
    path = ruta_del_tema(name, game_dir)
    if not path or not path.lower().endswith(".mid"):
        return None
    notes, tempos, division, programs, controls = midi.read(path)
    voices = assign(notes)
    largo = musica.timeline(notes, tempos, division)
    musica.timeline(controls, tempos, division)
    return {
        "nombre": name,
        "notas": notes,
        "controles": controls,
        "largo": largo,
        "voces": voices,
        "programas": programs,
        # What it contributes to the shared bank: the programs of its melodic
        # channels and the percussion keys it plays.
        "melodicos": {programs.get(c, 0) for c in voices
                      if c != midi.DRUM_CHANNEL},
        "golpes": {n.pitch for n in notes if n.channel == midi.DRUM_CHANNEL},
    }


# --- each song's volume ceiling ---------------------------------------------

# The headroom of each song that would clip with `sdsp.AIRE`'s: option B of
# step 5 of `workflow/tasks/todo/la-calidad-de-la-musica.md`, chosen by taro
# on 2026-09-26. The DSP adds up the eight voices and saturates the sum to
# 16 bits before the master volume, so the only thing that prevents clipping
# is each voice's ceiling; with a single one for all, it is set by the song
# that adds up the most —`rshinld`, because of its CC7 at 127— and the ones
# that do not clip drop almost 4 dB for no reason. With one per song, each
# drops just what it needs.
#
# **It is not written by hand**: `tools/audio/techos.py` (`just techos`)
# measures it by playing each song in the ROM, and what remains is versioned
# data, like the decisions in `rom/parches/auto/`. A song that is not in the
# table goes with `sdsp.AIRE`. Every change to the mix —the samples, the
# envelopes, the allocation— makes it stale, and `test_musica_techos.py`
# enforces that.
def ruta_de_techos():
    """Where the table is: a function and not a constant, because it comes
    from the project, which is found when used and not at import."""
    return os.path.join(project.auto_patches(), "musica", "techos.toml")


def leer_techos(ruta=None):
    """{song: headroom} from the versioned table; empty if it does not exist."""
    import tomllib
    ruta = ruta or ruta_de_techos()
    try:
        with open(ruta, "rb") as archivo:
            tabla = tomllib.load(archivo)
    except FileNotFoundError:
        return {}
    return {nombre: fila["aire"] for nombre, fila in tabla["temas"].items()}


def huella_de_la_mezcla(escrituras_del_tema, banco):
    """What a song's peak depends on, summarized: what it writes to the DSP
    —with its headroom already applied— and the samples it plays, with their
    loop. Whatever changes this can move the peak, and the ceiling table
    stores it so the test knows whether what was measured is still what
    plays. The driver does not count: it mixes nothing, it passes writes
    along."""
    import hashlib
    h = hashlib.sha256(repr(escrituras_del_tema).encode())
    muestras = sorted({valor for _c, registro, valor in escrituras_del_tema
                       if registro < 0x80
                       and registro & 0x0F == sdsp.V_SRCN})
    for i in muestras:
        if i < len(banco.voces):
            v = banco.voces[i]
            h.update(b"%d:%d:" % (i, v.loop_block or 0) + bytes(v.data))
    return h.hexdigest()[:16]


def _enteros_entran(banco, paquetes, herencia, efectos, presupuestado,
                    nombres):
    """That the extra space the `se_enteros()` take fits, in each package,
    in what the music left free: the bank is already allocated without
    counting it, so if it does not fit there is nobody to take it from
    without lowering an instrument's rate, and the converter stops saying
    which one.

    And it says —without stopping— with which song that may be playing a
    package's sound effects used to fit alongside at their usual size and no
    longer fit whole: there they wait for the next `PlayBGM` (see
    `decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md`)."""
    todos, pagados = se_enteros(), se_enteros_pagados()
    claves_de = {}
    for paquete in paquetes:
        nombre, suyos = paquete[0], paquete[1]
        claves_de[nombre] = set().union(
            *[set(banco.asignacion[t].values()) for t in suyos])
    no_entran = []
    banco.enteros_de_mas = {}
    for paquete in paquetes:
        nombre, suyas = paquete[0], set(paquete[2]) & set(efectos)
        enteros = sorted(e for e in suyas
                         if e in todos and e not in pagados)
        if not enteros:
            continue
        ocupan = sum(len(efectos[e].data) for e in suyas)
        banco.enteros_de_mas[str(nombre)] = ocupan - sum(presupuestado[e]
                                                         for e in suyas)
        # The package, and each of its separate songs, which is uploaded with
        # the same sound effects: see `temas_aparte`.
        for suyos in [None] + [[t] for t in (paquete[4] if len(paquete) > 4
                                             else ())]:
            musica = banco.ocupa(claves_de[nombre] if suyos is None
                                 else set(banco.asignacion[suyos[0]].values()))
            if musica + ocupan > banco.libre:
                no_entran.append("%s in package %s%s (%d B over)" % (
                    ", ".join(enteros), nombre,
                    "" if suyos is None else ">" + nombres[suyos[0]],
                    musica + ocupan - banco.libre))
    if no_entran:
        raise SystemExit(
            "the whole sound effects do not fit without lowering an "
            "instrument's rate: %s. Lower their rate in [sound_effects.whole], or remove them"
            % "; ".join(no_entran))
    efectos_de = {p[0]: set(p[2]) & set(efectos) for p in paquetes}
    for nombre, heredado in herencia:
        suyas = efectos_de[nombre]
        if not any(e in todos and e not in pagados
                   for e in suyas):
            continue
        musica = banco.ocupa(claves_de[nombre]
                             | set(banco.asignacion[heredado].values()))
        antes = musica + sum(presupuestado[e] for e in suyas)
        ahora = musica + sum(len(efectos[e].data) for e in suyas)
        if antes <= banco.libre < ahora:
            print("  with %s playing, the whole sound effects of package %s "
                  "do not fit alongside: they wait for the PlayBGM"
                  % (nombres[heredado], nombre))


def build_varios(nombres, game_dir=None, efectos=(), paquetes=None,
                 herencia=(), techos=None, aire_de_medida=None):
    """Every song in the ROM, sharing a single sample bank.

    Returns (driver, the voices —the bank's followed by the sound effects,
    each with its sample number—, songs, bank). There is one dict per song in the
    order they came in: the indices are `Temas`'s, the bytecode already has
    them emitted, so **they cannot be reordered**.

    **Every requested song goes in the cartridge, and all of them with all
    their samples.** An index costs no ARAM: it costs its stream, which
    lives in the cartridge. What competes for the ARAM is the samples, and
    that is allocated per package: see `Banco` and `repartir`.

    `paquetes` are the ROM's, by name: (name, indices of its songs, names of
    its sound effects[, indices of its exit songs[, indices of its separate
    songs]]). Each one has to fit alone in the ARAM, with its sound effects,
    and what its sound effects take is subtracted before allocating; each
    exit song —see `Temas.de_salida` in tools/port/eventos.py— has to fit
    alone, and each separate song —see `temas_aparte`— alone with the
    package's sound effects. If not given, each song is a package without
    sound effects.

    `herencia` are pairs (name of a package, index of a song that may be
    playing when it loads). `paquete_cargar_ya` does not move the samples of
    the song that is playing, so the package's have to fit alongside; **the
    sound effects do not**: if they do not fit, they wait for the next
    `PlayBGM`, which completes the package —see `tema_asegurar`—. It is the
    decision `workflow/decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md`.

    `techos` is each song's headroom, by name —if not given, the versioned
    one: see `leer_techos`—, and `aire_de_medida` overrides it for all: it
    is what `tools/audio/techos.py` builds the ROM it measures peaks in
    with.
    """
    game_dir = game_dir or resources.GAME_DIR
    driver = spc700.assemble(DRIVER, DRIVER_ADDR)
    if techos is None:
        techos = leer_techos()
    # Reading the MIDIs is pure and there is one per song: in parallel, like
    # building them.
    leidos = in_parallel(lambda n: leer_tema(n, game_dir), nombres)
    teclas = zonas_mas_usadas(leidos)
    claves_de = [claves_del_tema(t, teclas) for t in leidos]
    # **All** the sound effects go in: which ones fit is decided by the ROM
    # map by map, when it builds its audio package. They are built before
    # the bank because what each package's take is the first thing
    # subtracted.
    efectos_hechos = build_efectos(list(efectos), game_dir, 1 << 30)
    lista = sorted(efectos_hechos.values(), key=lambda e: list(efectos).index(
        e.name) if e.name in efectos else 0)
    # What the music budgets for each sound effect: the usual one, even if
    # it goes whole. See `se_enteros`.
    presupuestado = {n: len(e.data) for n, e in efectos_hechos.items()}
    todos, pagados = se_enteros(), se_enteros_pagados()
    for n in efectos_hechos:
        if n in todos and n not in pagados:
            presupuestado[n] = len(build_efecto(n, game_dir, enteros={}).data)

    # The keys the SoundFont has; the rest do not play anywhere.
    claves_de = [{k for k in ks if _muestra(k, NATIVA) is not None}
                 for ks in claves_de]
    if paquetes is None:
        paquetes = [(nombre, [i], []) for i, nombre in enumerate(nombres)]
    # What has to fit together: each package with its sound effects; each
    # exit song alone —its `PlayBGM` uploads it, silencing the rest: see
    # `extra_de_salida` in tools/runtime/paquete_de_audio.s—; and each
    # package with the song that may be playing when it loads, without its
    # sound effects.
    # And the same ones with what the sound effects really take, which is
    # what the copies that lower no one allocate with: see `copias`.
    grupos, reales, temas_de = [], [], {}
    for paquete in paquetes:
        nombre, suyos, suyas = paquete[:3]
        salida = paquete[3] if len(paquete) > 3 else ()
        temas_de[nombre] = list(suyos)
        suyas = set(suyas) & set(efectos_hechos)
        ocupan = sum(presupuestado[e] for e in suyas)
        ocupan_real = sum(len(efectos_hechos[e].data) for e in suyas)
        grupos.append(Grupo(str(nombre), tuple(suyos), ocupan))
        reales.append(Grupo(str(nombre), tuple(suyos), ocupan_real))
        for t in salida:
            grupos.append(Grupo("%s>%s" % (nombre, nombres[t]), (t,), 0))
            reales.append(grupos[-1])
        # And each separate song with the package's sound effects, which stay
        # when its `PlayBGM` uploads it: see `temas_aparte`.
        for t in (paquete[4] if len(paquete) > 4 else ()):
            grupos.append(Grupo("%s>%s" % (nombre, nombres[t]), (t,), ocupan))
            reales.append(Grupo(grupos[-1].nombre, (t,), ocupan_real))
    for nombre, heredado in herencia:
        grupos.append(Grupo("%s+%s" % (nombre, nombres[heredado]),
                            tuple(temas_de[nombre]) + (heredado,), 0))
        reales.append(grupos[-1])
    lugar = lugares_de_efectos([set(p[2]) for p in paquetes],
                               [e.name for e in lista])
    lugares = max(lugar.values()) + 1 if lugar else 0
    asignacion = copias(claves_de, grupos, lugares,
                        min(len(lista), se_de_siempre()), reales)
    todas = {k for a in asignacion for k in a.values()}
    libre = libre_para(len(todas), lugares)
    banco = Banco(todas, restricciones_de(asignacion, reales, libre))
    banco.libre = libre
    banco.asignacion = asignacion
    _enteros_entran(banco, paquetes, herencia, efectos_hechos, presupuestado,
                    nombres)

    # Each song is independent once the bank is allocated, and building them
    # was half of this function: they go in parallel, and come back in the
    # usual order.
    contexto = (nombres, leidos, asignacion, banco, techos, aire_de_medida)
    temas = in_parallel(lambda i: _armar_tema(contexto, i),
                        range(len(nombres)))
    # And each one's MSU-1 track: see `pista_msu`.
    for tema in temas:
        tema["pista"] = pista_msu(tema["nombre"], game_dir)
    # The sound effects go after the bank in the same directory, in its
    # `lugares` entries: their `V_SRCN` is the place each one got after the
    # music's samples. And each one also has its sound effect number, which
    # is what the package lists carry, and its `muestra_tabla` row after the
    # music's: see `lugares_de_efectos`.
    banco.lugares = lugares
    banco.efectos = {e.name: (len(banco.voces) + lugar[e.name], e)
                     for e in lista}
    banco.efecto_id = {e.name: i for i, e in enumerate(lista)}
    return (driver, list(banco.voces) + lista, temas, banco)


def _armar_tema(contexto, i):
    """One song of `build_varios`: what it does in parallel."""
    nombres, leidos, asignacion, banco, techos, aire_de_medida = contexto
    nombre, leido, suya = nombres[i], leidos[i], asignacion[i]
    if leido is None:
        return {"nombre": nombre, "stream": bytes([OP_END]),
                "sonidos": [], "escrituras": [],
                "segundos": 0.0, "resumen": {}}
    reparto = []
    aire = aire_de_medida or techos.get(nombre, sdsp.AIRE)
    del_tema = banco.del_tema(suya)
    frames = build_events(leido["notas"], leido["voces"],
                          leido["programas"], del_tema,
                          leido["controles"], reparto, aire)
    referencia = escrituras(frames, leido["largo"], init_writes())
    stream, sonidos = pack(frames, leido["largo"], init_writes())
    verificar_formato(nombre, stream, sonidos, referencia)
    return {"nombre": nombre, "stream": stream, "sonidos": sonidos,
            "escrituras": referencia, "aire": aire,
            "huella": huella_de_la_mezcla(referencia, banco),
            "segundos": leido["largo"] / TICKS_PER_SECOND,
            "resumen": resumen_del_tema(leido, del_tema, reparto)}


def resumen_del_tema(leido, banco, reparto=()):
    """What the recipe prints: voices, timbres and how much gets played."""
    voices, programs = leido["voces"], leido["programas"]
    return {
        "voices": {c: v for c, v in sorted(voices.items())},
        "sounds": {c: programs.get(c, 0)
                   for c in sorted(voices) if c != midi.DRUM_CHANNEL},
        "bank": ["%s (%.0f Hz, %d B)" % (v.name.strip(), v.rate, len(v.data))
                 for v in banco.voces],
        # How much of the note-time is lost for lack of voices, and how much
        # would be lost unavoidably with eight: see `tiempo_perdido`.
        "perdido": tiempo_perdido(reparto),
        # And how many of its notes reach the stream. A note whose program
        # is not in the bank **does not play quieter: it does not exist**
        # —the `continue` in `build_events`—, so this is the voice the
        # player does not hear. It is a different number from `perdido`,
        # which measures polyphony; until 2026-09-26 that one was
        # `coverage`, a count from the fixed per-channel allocation, and they
        # got mixed up on 2026-09-14: for a while it looked like sharing the
        # bank cost nothing, because `coverage` came out the same with the
        # whole bank or the shared one.
        "notas": notas_que_suenan(leido, banco),
    }


def tiempo_perdido(reparto):
    """(what is lost, the floor): what fraction of the note-time of notes
    with a sample does not play for lack of voices, and what fraction could
    not play under any rule —whatever goes beyond eight notes at once—.

    Note-time is how long the note holds its voice: from its start to its
    end in the MIDI, or to the end of the sample if it is a hit that runs
    out sooner. It is lost entirely if the note gets no voice, and from the
    moment of the steal if its voice is stolen before that end. The release
    tail does not count: it is not in the MIDI. It is the prototype's count,
    which in `escape_newyork` gave 55% with the fixed per-channel allocation
    against a floor of 23%.
    """
    total = perdido = 0
    tramos = []
    for nota, voz, robada, fin in reparto:
        largo = fin - nota.start
        total += largo
        tramos.append(_Tramo(nota.start, fin))
        if voz is None:
            perdido += largo
        elif robada is not None:
            perdido += max(0, fin - robada)
    spans = musica.note_time(tramos)
    piso = sum(max(0, n - sdsp.VOICES) * cuadros for n, cuadros in spans.items())
    return perdido / float(max(1, total)), piso / float(max(1, total))


_Tramo = collections.namedtuple("_Tramo", "start end")


def notas_que_suenan(leido, banco):
    """What fraction of the MIDI's notes has its sample in the bank."""
    total = suenan = 0
    for nota in leido["notas"]:
        if nota.channel not in leido["voces"]:
            continue
        total += 1
        if nota.channel == midi.DRUM_CHANNEL:
            suenan += banco.golpes.get(nota.pitch) is not None
        else:
            programa = leido["programas"].get(nota.channel, 0)
            suenan += banco.melodicas.get(programa) is not None
    return suenan / max(1, total)


def tabla_de_sonidos(sonidos, banco):
    """One row per entry of `Temas.sonidos`: the sample —$FF if it did not
    fit—, the pitch, the volume of each side, how many frames it lasts and
    the sound effect number, which is what says which of the ones sharing
    the sample it is: see `lugares_de_efectos`."""
    filas = []
    efectos = getattr(banco, "efectos", {}) if banco is not None else {}
    for nombre, volumen, tempo, balance in sonidos:
        hecho = efectos.get(nombre)
        if hecho is None:
            filas.append((0xFF, 0, 0, 0, 0, 0xFF))
            continue
        srcn, efecto = hecho
        izquierda, derecha = volumen_de_efecto(volumen, balance)
        filas.append((srcn, altura_de_efecto(efecto, tempo), izquierda,
                      derecha, cuadros_de_efecto(efecto, tempo),
                      banco.efecto_id[nombre]))
    return filas


# The silence: a BRR block with the end and loop bits, and eight zero bytes.
# It is where every sample that is not in the ARAM points in the directory.
SILENCIO = bytes([0x03]) + bytes(8)
# And how far uploads go: the last 64 bytes of the ARAM are the ones the boot
# ROM covers when it is enabled, and that way the limit fits in sixteen bits.
ARAM_FIN = 0x10000 - 64


def muestras_del_tema(tema):
    """Which samples a song uses: the values its stream writes to the
    voices' SRCN registers. It is what the ROM has to have in the ARAM to
    play it, taken from what the song does —its stream, decoded— and not
    from how it was built."""
    return sorted({valor for _cuadro, registro, valor
                   in decodificar(tema["stream"], tema["sonidos"])
                   if _es_de_voz(registro)
                   and registro & 0x0F == sdsp.V_SRCN})


# What uploading to the SPC700 costs, in frames, for the boot count. A
# package's samples go in triplets through the driver's command 3 —see
# `subir_muestra` in tools/runtime/paquete_de_audio.s—: measured in the ROM
# on 2026-09-26, from 1.33 to 1.42 frames per KB across eighteen packages,
# and a bit more goes here. The driver and the directory go byte by byte
# through the IPL, which measured 1.4. And loading the map, without audio
# and without decompressing, is about 8 frames (measured with map 6 of
# `test-special`, which has no package); 10 go here. What decompressing
# costs depends on the map and goes separately.
CUADROS_POR_KB_PAQUETE = 1.45
CUADROS_POR_KB_IPL = 1.5
CUADROS_DEL_MAPA = 10
# Where `BOOT_CUADROS` lives, which belongs to the ROM and not here.
RAM_LEJANA = os.path.join(project.runtime(), "ram_lejana.s")


def cuadros_del_arranque(driver, voces, temas, paquete, descomprimir=0.0,
                         directorio=None):
    """How long boot takes, erring high: the map, the driver and the
    directory through the IPL, and the samples of the boot map's package
    —(song indices, sound effect sample indices, exit songs), `emit`'s—.
    The exit ones count: they are uploaded if there is room, and with an
    empty ARAM there is. `descomprimir` is the frames that decompressing the
    boot map's LZ2 blocks takes, which `CUADROS_DEL_MAPA` does not count:
    see `cuadros_de_descomprimir` in snes_convert.py. `directorio` is (music
    samples, sound effect places), `emit`'s: the sound effects go by number,
    with their row after the music's.
    Returns (frames, package bytes)."""
    suyos, efectos = paquete[:2]
    salida = paquete[2] if len(paquete) > 2 else ()
    musica_n, lugares = directorio or (len(voces), 0)
    indices = {musica_n + e for e in efectos}
    for t in list(suyos) + list(salida):
        if temas[t]["sonidos"]:
            indices |= set(muestras_del_tema(temas[t]))
    del_paquete = sum(len(voces[i].data) for i in indices)
    ipl = len(driver) + 4 * max(1, musica_n + lugares) + len(SILENCIO)
    return (CUADROS_DEL_MAPA + descomprimir
            + ipl * CUADROS_POR_KB_IPL / 1024.0
            + del_paquete * CUADROS_POR_KB_PAQUETE / 1024.0, del_paquete)


def boot_cuadros(ruta=RAM_LEJANA):
    """The ROM's `BOOT_CUADROS`, read from the source."""
    import re
    with open(ruta) as archivo:
        return int(re.search(r"^BOOT_CUADROS\s*=\s*(\d+)", archivo.read(),
                             re.M).group(1))


def emit(path, temas, driver, voces, arranque=0xFF, titulo=0xFF,
         sonidos=(), paquetes=(), tema_de_mapa=(), directorio=None,
         efecto_lugar=(), game_over=(0xFF, 0xFFFF)):
    """The .inc the assembler builds along with main.s.

    `temas` are `build_varios`'s, in `Temas` order: the bytecode already has
    those indices emitted. `arranque` is which one plays from the first
    frame, or $FF if the ROM boots silent and a `PlayBGM` turns it on.

    `voces` are all the cartridge's samples, numbered: the music's followed
    by the sound effects. None is uploaded at boot: they go to the SPC700 in
    **packages**, one per map —`paquetes`, in map table order, each with its
    songs, its sound effects' samples and its exit songs—, and the directory
    starts with all of them pointing to the silence. See `paquete_cargar` in
    tools/runtime/paquete_de_audio.s.

    `tema_de_mapa` is the song each map turns on when entered, in the same
    order, or $FF if entering does not change what is playing. See
    `mapa_tema_callar`.

    `directorio` is (music samples, sound effect places): the directory's
    entries are those and not one per voice, because sound effects share
    places —see `lugares_de_efectos`—; `voces` carries every sound effect
    after the music, one per number, and `efecto_lugar` is each one's
    `V_SRCN`. The sound effect lists in `paquetes` go by number.
    """
    def block(label, data, bloque=False):
        # No `.bloque` except on the samples, and `.cruza` instead: the
        # driver goes byte by byte through the ports —`spc_block` does the
        # bank jump by hand— and the stream is walked by `advance`, which
        # does the same jump, so they can end up split. The samples do carry
        # it: `subir_a_aram` walks them with a 24-bit pointer that does not
        # jump banks, in exchange for being shorter. See `resolver` in
        # tools/ensamblado/bancos.py, which does not let one through with
        # neither of the two.
        out = ([".bloque %d" % len(data)] if bloque else [".cruza"]) \
            + ["%s:" % label]
        for i in range(0, len(data), 16):
            out.append("    .byte " + ",".join("$%02X" % b for b in data[i:i + 16]))
        return "\n".join(out)

    etiquetas = ["tema_stream_%d" % i for i in range(len(temas))] or \
        ["tema_stream_0"]
    streams = [t["stream"] for t in temas] or [bytes([OP_END])]
    tabla = "\n".join(
        "%s:\n    .byte %s" % (nombre, ", ".join(prefijo + e for e in etiquetas))
        for nombre, prefijo in (("tema_lo", "<"), ("tema_hi", ">"),
                                ("tema_bk", "^")))
    # The DSP prologue, for the MSU-1 path. With a track the stream never
    # runs, and it is the start of the stream that takes the DSP out of the
    # mute the SPC700 boots with, sets its master volume and tells it where
    # the sample directory is. Without this, sound effects fire against a
    # mute DSP and are not heard.
    #
    # KON and KOF are left out on purpose: with a track, the ROM leaves KOF
    # at $FF so the music's voices do not play, and `se_despues` clears it
    # only when a sound effect starts. Writing KOF as zero here would turn
    # back on the voices of a song that is not playing.
    #
    # They go in two parallel tables and not in one of pairs because the
    # 65816 walks them with an index: `lda dsp_init_reg, y`.
    init = [(r, v) for r, v in init_writes()
            if r not in (sdsp.KON, sdsp.KOF)]
    tabla += "\ndsp_init_reg:\n    .byte " + ", ".join(
        "$%02X" % r for r, _ in init) + ", $FF"
    tabla += "\ndsp_init_val:\n    .byte " + ", ".join(
        "$%02X" % v for _, v in init) + ", $00"
    # And which MSU-1 track each one gets, or $FF: see `pista_msu`.
    tabla += "\ntema_msu:\n    .byte " + ", ".join(
        "$%02X" % (t.get("pista") or 0xFF)
        for t in (temas or [{"nombre": ""}]))
    # And each map's own song. Outside bank 0: it is read once per teleport,
    # with `lda f:mapa_tema, x`.
    del_mapa = list(tema_de_mapa) or [0xFF]
    tabla_mapa_tema = ".bloque %d\nmapa_tema:\n    .byte " % len(del_mapa) \
        + ", ".join("$%02X" % t for t in del_mapa)
    # And the music's sounds —`pack`'s: six bytes, the pitch, SRCN, ADSR1,
    # ADSR2 and the release GAIN—, those of every song in one table and
    # where each one's start. In a single bank, because `music_frame`
    # reaches them with `lda f:musica_sonidos, x` and a sixteen-bit X does
    # not cross banks.
    cuerpo, bases = bytearray(), []
    for t in temas:
        bases.append(len(cuerpo))
        for sonido in t["sonidos"]:
            cuerpo += bytes(sonido)
    if len(cuerpo) > 0x8000:
        raise SystemExit("the music's sounds go over one bank: %d B"
                         % len(cuerpo))
    tabla_mapa_tema += ("\n.bloque %d\ntema_sonidos:\n    .word "
                        % (2 * len(bases or [0]))
                        + ", ".join("%d" % b for b in bases or [0]) + "\n"
                        + block("musica_sonidos", bytes(cuerpo) or bytes(6),
                                bloque=True))
    # And the sound effects: seven bytes per entry of `Temas.sonidos`.
    # Outside bank 0: `op_sound` reads them with `lda f:sonido_tabla, x`.
    filas = list(sonidos) or [(0xFF, 0, 0, 0, 0, 0xFF)]
    tabla_se = ".bloque %d\nsonido_tabla:\n" % (7 * len(filas)) + "\n".join(
        "    .byte $%02X, <%d, >%d, %d, %d, <%d, >%d" % (
            srcn, altura, altura, izquierda, derecha, cuadros, cuadros)
        for srcn, altura, izquierda, derecha, cuadros, _e in filas)
    # And which sound effect each row is, separately so as not to touch the
    # seven columns `sonido_tocar` and efectos_con_msu.s walk: the row's
    # sample is a place several sound effects share, and `sonido_tocar` asks
    # with this whether the one in the ARAM is its own. And each sound
    # effect's place, which is what the package uses to upload it.
    tabla_se += "\n.bloque %d\nsonido_efecto:\n    .byte " % len(filas) \
        + ", ".join("$%02X" % fila[5] for fila in filas)
    lugares_se = list(efecto_lugar) or [0xFF]
    tabla_se += "\n.bloque %d\nefecto_lugar:\n    .byte " % len(lugares_se) \
        + ", ".join("$%02X" % l for l in lugares_se)

    # The SPC700 directory, with all of them on the silence, and the silence
    # after it. It is the only thing `spc_upload` uploads besides the driver.
    musica_n, lugares = directorio or (len(voces), 0)
    n = max(1, musica_n + lugares)
    if n > DIRECTORIO_MAX:
        raise SystemExit("the directory has %d entries and SRCN is one "
                         "byte" % n)
    if len(voces) - musica_n > 0xFF:
        raise SystemExit("there are %d sound effects and their number is one byte"
                         % (len(voces) - musica_n))
    if lugares > SE_LUGARES_MAX:
        raise SystemExit("the sound effects ask for %d directory places and the ROM "
                         "records %d: see FAR_EFECTO_EN" % (lugares,
                                                            SE_LUGARES_MAX))
    silencio = SAMPLES_ADDR + 4 * n
    datos = silencio + len(SILENCIO)
    samples = (silencio.to_bytes(2, "little") * 2) * n + SILENCIO
    # Each sample, on its own, and its row: the pointer, its length and
    # where it loops back to.
    muestras = [block("muestra_%d" % i, v.data, bloque=True)
                for i, v in enumerate(voces)] or [block("muestra_0", SILENCIO)]
    filas_m = []
    for i, v in enumerate(voces or [None]):
        largo = len(v.data) if v is not None else len(SILENCIO)
        loop = v.loop_block * muestras_brr.BLOQUE_BYTES if v is not None else 0
        filas_m.append("    .byte <(muestra_%d), >(muestra_%d), ^(muestra_%d), "
                       "<%d, >%d, <%d, >%d" % (i, i, i, largo, largo, loop, loop))
    # Which samples each song uses, and each map's package. Two blocks with
    # an index of offsets in front, and each list terminated with $FF.
    def listas(label, grupos):
        cuerpo, ofs = bytearray(), []
        for grupo in grupos:
            ofs.append(2 * len(grupos) + len(cuerpo))
            for parte in grupo:
                cuerpo += bytes(parte) + b"\xFF"
        datos_ = b"".join(o.to_bytes(2, "little") for o in ofs) + bytes(cuerpo)
        return block(label, datos_ or b"\xFF", bloque=True)
    # Decoding the streams to find out is pure and costly: in parallel.
    tema_muestras = listas("tema_muestras", [
        [m] for m in in_parallel(lambda i: muestras_del_tema(temas[i]),
                                 range(len(temas)))] or [[[]]])
    # Each package, four lists: its songs, its sound effects' samples, its
    # exit songs and its separate songs —see `extra_de_salida` and
    # `extra_aparte` in tools/runtime/paquete_de_audio.s—.
    paquetes = [tuple(p) + ((),) * (4 - len(p)) for p in paquetes] or \
        [([], [], [], [])]
    bloque_paquetes = listas("paquetes", [[list(t), list(m), list(s),
                                            list(a)]
                                           for t, m, s, a in paquetes])

    with open(path, "w") as handle:
        handle.write(
            "; Generated by tools/audio/snes_music.py. Do not edit.\n"
            # The next line and the "sin música" below stay in Spanish on
            # purpose: they are data. `tools/audio/techos.py` reads them with
            # a regex, and `rom/pruebas/arnes/consola.py`, `test_msu.py` and
            # `test_msu_efectos.py` look for "; Temas: ".
            "; Temas: %s\n\n"
            "; How many songs the cartridge carries and which one plays from boot.\n"
            "; The indices are those of `Temas` in eventos.py, that is, the ones\n"
            "; the PlayBGM bytecode already has emitted.\n"
            "; $FF in TEMA_ARRANQUE means 'the ROM boots silent': the song of the\n"
            "; map it boots in does not exist, so an event has to turn it on.\n"
            "TEMA_TOTAL       = %d\n"
            "TEMA_ARRANQUE    = $%02X\n"
            "; And the title screen's, which comes from the LDB's `title_music`.\n"
            "; $FF means this ROM has no title screen.\n"
            "TEMA_TITULO      = $%02X\n"
            # `rom/src/` and not `tools/runtime/`, here and six lines further
            # down, on purpose: it is text that goes into the `.inc`, and the
            # paths in what is emitted are not changed yet
            # (workflow/decisiones/las-herramientas-se-separan-de-abl.md).
            "; And the Game Over screen's —`gameover_music`— with its package,\n"
            "; which goes after all the others: the song alone. $FF and $FFFF\n"
            "; if this ROM has no such screen. See rom/src/game_over.s.\n"
            "TEMA_GAME_OVER   = $%02X\n"
            "PAQUETE_GAME_OVER = $%04X\n"
            "; The master volume the song plays at and the two DSP registers it\n"
            "; goes in. `sdsp.py` emits them, since that is where they come\n"
            "; from: the stream already writes them at start, and a `FadeOutBGM`\n"
            "; writes them again lowering them. Writing them in rom/src/ too\n"
            "; would be two sides that can be wrong in the same way.\n"
            "TEMA_VOLUMEN     = $%02X\n"
            "DSP_MVOL_L       = $%02X\n"
            "DSP_MVOL_R       = $%02X\n"
            "SPC_DRIVER_ADDR  = $%04X\n"
            "SPC_DRIVER_SIZE  = %d\n"
            "SPC_SAMPLES_ADDR = $%04X\n"
            "SPC_SAMPLES_SIZE = %d\n"
            "; Samples go to the SPC700 in packages: see `paquete_cargar`.\n"
            "; The directory is at SPC_SAMPLES_ADDR, the silence after it, and\n"
            "; the samples are placed between ARAM_DATOS and ARAM_FIN.\n"
            "; MUESTRAS_N is the directory's entries: the music's, and from\n"
            "; SE_PRIMERA on the SE_LUGARES the sound effects share.\n"
            "; Each sound effect has its number —EFECTOS_N in total, which is\n"
            "; what the package lists carry— and its `muestra_tabla` row at\n"
            "; SE_PRIMERA plus that number. See `lugares_de_efectos`.\n"
            "MUESTRAS_N       = %d\n"
            "SE_PRIMERA       = %d\n"
            "SE_LUGARES       = %d\n"
            "EFECTOS_N        = %d\n"
            "ARAM_SILENCIO    = $%04X\n"
            "ARAM_DATOS       = $%04X\n"
            "ARAM_FIN         = $%04X\n"
            "PAQUETES_N       = %d\n"
            "; The sound effects: which voice they play on and how many entries\n"
            "; `sonido_tabla` has. See `build_efectos`.\n"
            "SE_VOZ           = %d\n"
            "SE_BIT           = $%02X\n"
            "SE_REG           = $%02X\n"
            "SE2_BIT          = $%02X\n"
            "SE2_REG          = $%02X\n"
            "SONIDOS_N        = %d\n\n"
            "; Where each song's stream starts, split into three tables\n"
            "; because they are read with an index: they go in bank 0 like\n"
            "; everything the CPU walks with `lda tabla, x`.\n"
            '.segment "TABLAS"\n%s\n\n'
            '.segment "RODATA"\n%s\n%s\n%s\n%s\n'
            '.bloque %d\nmuestra_tabla:\n%s\n%s\n%s\n%s\n%s\n'
            % (", ".join(t["nombre"] or "sin música" for t in temas)
               or "ninguno",
               len(temas), arranque, titulo, game_over[0], game_over[1],
               sdsp.MASTER, sdsp.MVOL_L, sdsp.MVOL_R,
               DRIVER_ADDR, len(driver),
               SAMPLES_ADDR, len(samples),
               n, musica_n, lugares, len(voces) - musica_n,
               silencio, datos, ARAM_FIN, len(paquetes),
               SE_VOZ, 1 << SE_VOZ, SE_VOZ * 16, 1 << SE_VOZ2, SE_VOZ2 * 16,
               len(list(sonidos)),
               tabla, tabla_se, tabla_mapa_tema,
               block("spc_driver", driver),
               block("spc_samples", samples),
               7 * len(filas_m), "\n".join(filas_m),
               tema_muestras, bloque_paquetes,
               "\n".join(muestras),
               "\n".join(block(e, st) for e, st in zip(etiquetas, streams))))
