"""Converts a map's MIDI to BRR samples and a stream for the S-DSP.

What does not depend on the chip —reading the MIDI and turning times into
frames— is in midi.py and music.py; the S-DSP part, in sdsp.py. Voices are
allocated note by note, all eight shared by every channel: see `assign`.

Two things come out: the block uploaded to the SPC700's memory (the sample
directory plus the samples in BRR) and each song's stream, per note, which the
65816 expands into DSP writes frame by frame: see "the per-note format". The
caller is the converter, with every song of the cartridge at once: see
`build_all`.
"""

import collections
import math
import os

from rpgmaker import lcf
from audio import music
from audio import midi
from audio import brr_samples
from audio import sdsp
from audio import snes_samples
from audio import spc700
from common import settings
from common import project
from common.parallel import in_parallel
from rpgmaker import resources
from rpgmaker.resources import find_resource

TICKS_PER_SECOND = music.TICKS_PER_SECOND

# Where each thing lives in the SPC700's 64 KB. The boot ROM keeps the first
# $200 bytes for its variables, so everything starts higher up.
DRIVER_ADDR = 0x0200
SAMPLES_ADDR = 0x0400

BLOCK = brr_samples.BLOCK_SAMPLES   # 16 samples per BRR block

# The samples go from $0400 to the end of the 64 KB —`ARAM_END`, further
# down—, with no reservation: echo is off —FLG with the "do not write the
# buffer" bit— and the SPC700's stack lives at $0100, that is, below. One
# package fits there at a time, and that is what the allocation is done
# against: see `Bank`.
#
# And what is left free for each package when allocating. Each sample's
# length is rounded up to BRR blocks and the allocation asks by budget, so
# this is slack for that; `Bank` checks what they really take against the
# ARAM with no margin. 1 KB is what step 6 was measured with.
ARAM_MARGIN = 1024

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
# (`Songs.index`), so a new map shifts the numbering of the ones after it,
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
TRACK_EXTENSIONS = (".mid", ".wav")


_track_numbers = {}


def _music_names(directory):
    folder = [os.path.join(directory, e) for e in os.listdir(directory)
              if e.lower() == "music"] if os.path.isdir(directory) else []
    names = set()
    for handle in os.listdir(folder[0]) if folder else []:
        base, ext = os.path.splitext(handle)
        if ext.lower() in TRACK_EXTENSIONS:
            names.add(base.lower())
    return names


def track_numbers(game_dir=None):
    """{lowercase song name: track number}, for all of `Music/` and the RTP
    ones named by `System`."""
    game_dir = game_dir or resources.GAME_DIR
    if game_dir not in _track_numbers:
        from rpgmaker.resources import RTP_DIR
        names = _music_names(game_dir)
        from_rtp = _music_names(RTP_DIR)
        ldb = os.path.join(game_dir, "RPG_RT.ldb")
        system_songs = sorted(({n.lower() for n in lcf.system_songs(ldb)}
                               - names) & from_rtp)
        order = sorted(names) + system_songs
        # The number goes in a byte of `song_msu`, and $FF is "no track".
        if len(order) > 0xFE:
            raise SystemExit("Music/ has %d songs and the track goes in a byte"
                             % len(order))
        _track_numbers[game_dir] = {n: i + 1 for i, n in enumerate(order)}
    return _track_numbers[game_dir]


def song_path(name, game_dir=None, extensions=TRACK_EXTENSIONS):
    """The song's file: the game's and, if it is not there, the RTP's, which
    is how RM2k looks for it. `None` if it is in neither."""
    game_dir = game_dir or resources.GAME_DIR
    from rpgmaker.resources import RTP_DIR
    return (find_resource([game_dir, RTP_DIR], "Music", name, extensions)
            if name else None)


def msu_track(name, game_dir=None):
    """The song's MSU-1 track number, or None if it has nothing to come
    from: see `track_numbers`."""
    game_dir = game_dir or resources.GAME_DIR
    return track_numbers(game_dir).get(name.lower()) if name else None


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
# them without stopping serving the DSP. See `package_load` in
# tools/runtime/audio_package.s. The pointer and the count live at $00-$03
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
# ask for, at `SE_RATE`, trimmed to `SE_MAX_SECONDS`; a longer one repeats
# its last `SE_LOOP_SECONDS` until it lasts as long as it does in RM2k —the
# opening's rain is five seconds of noise, and that way it is heard whole—.
# The ones that do not fit do not play, and the converter says so.
SE_ARAM = 16 * 1024
SE_RATE = 6000
SE_MAX_SECONDS = 0.75           # since the per-map package: see `package_load`
SE_LOOP_SECONDS = 0.4
SE_VOICE = 7                      # the one stolen from the music
# And the second, so two sound effects can play at once —the opening's rain
# and thunder—, as in RM2k. Both are the ones the music allocation fills
# first with percussion: see `EFFECT_VOICES`.
SE_VOICE2 = 6
# **Which sound effects go whole, which ones the music pays for, which
# aliases there are per map and which songs go separately are the game's
# decisions by ear**, almost all of them taro's while listening, and they
# live in its project file —`[sound_effects]` and `[music]`— with the reason
# for each. Until 2026-09-29 they were tables here. They are read when used
# and not at import, so the converter can be imported without a game.

def se_whole():
    """{sound effect: rate in Hz} of the ones that go whole, with no cap or
    loop: they end when the sample ends, which is what they do in RM2k. What
    one takes beyond the usual has to fit in what the music leaves free in
    each package it is in, except for those in `se_paid_by_music`: see
    `_whole_effects_fit`. From `[sound_effects.whole]`."""
    return dict(settings.value("sound_effects", "whole", kind=dict))


def se_paid_by_music():
    """The whole ones that, if they do not fit in the free space, lower the
    music's rate. From `[sound_effects] paid_by_music`."""
    return set(settings.value("sound_effects", "paid_by_music", kind=list))


def se_per_map():
    """{(name in RM2k, map id): the sample that plays there}. They are put in
    by `_compile`, in tools/port/events.py. Each one is one more sound
    effect, but not one more directory entry: it shares a place with those
    of the other packages —see `effect_places`—. From
    `[sound_effects] per_map`."""
    return {(a["effect"], a["map"]): a["sample"]
            for a in settings.value("sound_effects", "per_map", kind=list)}


def se_route_left_out():
    """{map id: None for all, or the names} of the sound effects that forced
    move routes ask for —move command 35, see `ROUTE_SOUND` in
    tools/port/events.py— and that **do not fit** in their map's audio
    package. From `[sound_effects] route_effects_left_out`."""
    return {m["map"]: None if m["effects"] == "all" else set(m["effects"])
            for m in settings.value("sound_effects", "route_effects_left_out",
                                    kind=list)}


def se_troop_in_package():
    """The sound effects of troop pages that **do** go in the battle's audio
    package. From `[sound_effects] troop_effects_in_package`."""
    return set(settings.value("sound_effects", "troop_effects_in_package",
                              kind=list))


def separate_songs():
    """{map id: names} of the separate songs: they do not go with the other
    songs of their map's package, their `PlayBGM` uploads them alone with the
    package's sound effects —see `extra_separate` in
    tools/runtime/audio_package.s—, and they are not inherited by the maps
    you exit to —see `inherited_songs` in snes_convert.py—. From
    `[music] apart_themes`."""
    return {m["map"]: set(m["themes"])
            for m in settings.value("music", "apart_themes", kind=list)}


class SoundEffect:
    """A sound effect ready for the SPC700: `data` in BRR, at `rate`, which
    goes back to block `loop_block` if it repeats, and lasts `seconds` in
    RM2k."""

    def __init__(self, name, data, rate, loop_block, seconds):
        self.name = name
        self.data = data
        self.rate = rate
        self.loop_block = loop_block or 0
        self.repeats = loop_block is not None
        self.seconds = seconds


def read_wav(name, game_dir=None):
    """A mono WAV's samples as signed 16-bit integers, and its rate. None if
    it is missing or is not a WAV that can be understood."""
    game_dir = game_dir or resources.GAME_DIR
    import wave
    from rpgmaker.resources import RTP_DIR
    path = find_resource([game_dir, RTP_DIR], "Sound", name,
                         (".wav", ".WAV"))
    if not path:
        return None
    try:
        w = wave.open(path)
    except Exception:
        return None
    width, channels, rate = w.getsampwidth(), w.getnchannels(), w.getframerate()
    data = w.readframes(w.getnframes())
    if width == 1:
        raw = [(b - 128) << 8 for b in data]
    elif width == 2:
        raw = [int.from_bytes(data[i:i + 2], "little", signed=True)
               for i in range(0, len(data), 2)]
    else:
        return None
    if channels > 1:
        raw = [sum(raw[i:i + channels]) // channels
               for i in range(0, len(raw), channels)]
    return raw, rate


def build_sound_effect(name, game_dir=None, rate=SE_RATE, whole=None):
    """`whole` is `se_whole()` if not given; with {} the usual one comes
    out, which is what the music budgets for it: see `se_whole`."""
    game_dir = game_dir or resources.GAME_DIR
    whole = se_whole() if whole is None else whole
    parsed = read_wav(name.split("@")[0], game_dir)
    if not parsed or not parsed[0]:
        return None
    raw, source = parsed
    seconds = len(raw) / float(source)
    keep = min(len(raw), int(SE_MAX_SECONDS * source))
    if name in whole:
        rate, keep = whole[name], len(raw)
    out = max(BLOCK,
              int(round(keep * rate / float(source)))
              // BLOCK * BLOCK)
    audio = snes_samples.normalize(snes_samples.resample(raw[:keep],
                                                         out))
    loop = None
    if keep < len(raw):
        loop_length = int(SE_LOOP_SECONDS * rate) // BLOCK
        loop = max(0, out // BLOCK - max(1, loop_length))
    return SoundEffect(name, brr_samples.encode(audio, loop_block=loop),
                       rate, loop,
                       seconds)


def build_sound_effects(requested, game_dir=None, budget=SE_ARAM):
    """The sound effects that fit in `budget`, by priority: `requested` is a
    list of names already sorted from most to least requested. Returns
    {name: SoundEffect} with the ones that fit."""
    game_dir = game_dir or resources.GAME_DIR
    done, used = {}, 0
    # Each sound effect is built on its own —read the WAV, resample it,
    # encode it— and that is pure: all at once, and then the allocation in
    # the requested order.
    unique = list(dict.fromkeys(requested))
    built = dict(zip(unique, in_parallel(
        lambda n: build_sound_effect(n, game_dir), unique)))
    for name in requested:
        if name in done:
            continue
        effect = built[name]
        if effect is None:
            continue
        cost = len(effect.data) + 4          # the sample and its entry
        if used + cost > budget:
            continue
        done[name] = effect
        used += cost
    return done


def effect_pitch(effect, tempo):
    """The DSP pitch register: 4096 is the 32 kHz rate, and RM2k's tempo
    —from 50 to 150— stretches it."""
    return min(0x3FFF, int(round(effect.rate * 4096 / 32000.0 * tempo / 100.0)))


def effect_frames(effect, tempo):
    """How long it lasts, in 60 Hz frames, with the tempo applied."""
    return max(1, int(round(effect.seconds * 60 * 100.0 / max(1, tempo))))


def effect_volume(volume, balance):
    """DSP left and right, from 0 to 127, from RM2k's volume and pan: pan at
    50 is the center, and toward each side the other one drops."""
    cap = sdsp.MASTER if hasattr(sdsp, "MASTER") else 0x7F
    # The $60 was chosen with the master volume at $60, which is also applied
    # to the sound effects —with MSU-1 or without it—. With `sdsp`'s headroom
    # the master went up, and the sound effect's ceiling goes down by the
    # same amount so it sounds the same.
    v = max(0, min(100, volume)) * int(round(0x60 * 0x60 / sdsp.MASTER)) // 100
    left = v * min(50, 100 - balance) // 50
    right = v * min(50, balance) // 50
    return max(0, min(0x7F, left)), max(0, min(0x7F, right))


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
    another by priority —see `_victim`—. It is step 5 of
    `workflow/tasks/todo/la-calidad-de-la-musica.md`.

    It still returns one group per channel because `build_events` accepts
    them different, and the tests use it to build small cases.
    """
    return {channel: list(range(sdsp.VOICES))
            for channel in sorted({n.channel for n in notes})}


# The voices that sound effects take from the music: `SE_VOICE` and
# `SE_VOICE2`. While a sound effect plays, what the music writes to its voice
# goes to the shadow and not to the DSP —see `dsp_music`—, so whatever note
# was there goes silent. That is why percussion hits, which last half a
# second, go there first, and melodic notes only if no other voice is free:
# that is what happened when the drums had those two voices fixed.
EFFECT_VOICES = (SE_VOICE2, SE_VOICE)


# The GAIN used to bring down a voice that is playing one frame before
# handing it to another note: linear, 64 steps of 6 samples, so it reaches
# zero in 12 ms, before the next frame. What it avoids is the KON click,
# which drops the envelope to zero at once: the prototype for step 5 of
# `workflow/tasks/todo/la-calidad-de-la-musica.md` recorded it (variant 07).
# It is one more `OP_RELEASE_GAIN` in the stream: the driver does not change.
RAMP = sdsp.GAIN_LINEAR_DECREASE | 26
assert 64 * sdsp.PERIOD[RAMP & 0x1F] <= sdsp.SAMPLE_RATE // TICKS_PER_SECOND


class _Voice:
    """What the allocation knows about a voice: the note holding it, until
    when it holds it —`end`— and until when it can be heard —`cola`, with the
    release or however long the hit lasts—, and the volume it started with,
    left plus right."""

    __slots__ = ("note", "end", "tail", "level")

    def __init__(self, note, end, tail, level):
        self.note, self.end, self.tail, self.level = note, end, tail, level


def _release_frames(gain):
    """How many frames a voice released with that GAIN takes to go silent,
    from the top: the linear one drops 1/64 per step, and the exponential
    one reaches zero in `STEPS_TO_ZERO` —see `sdsp`—."""
    period = sdsp.PERIOD[gain & 0x1F] or 0
    steps = (64 if gain & 0xE0 == sdsp.GAIN_LINEAR_DECREASE
             else sdsp.STEPS_TO_ZERO)
    return int(steps * period * TICKS_PER_SECOND / sdsp.SAMPLE_RATE) + 1


def _free_order(voice, t, voices, note, drums):
    """The order among the free voices —the ones nobody holds at `t`—: the
    lowest wins."""
    s = voices.get(voice)
    # Silent ones first: reusing one that is still sounding in its tail cuts
    # it. Among the sounding ones, the one that dies out first.
    is_sounding = s is not None and s.tail > t
    return (is_sounding, s.tail if is_sounding else 0,
            # Hits go to the sound effect voices; melodic notes, to the rest.
            (voice in EFFECT_VOICES) != drums,
            # And the one that had a note from the same channel: same
            # instrument and same volume, so the new note costs two bytes.
            s is None or s.note.channel != note.channel,
            voice)


def _victim(note, t, group, voices, level):
    """Which voice `note` steals when every voice in its group is held, or
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
    by_channel = collections.Counter(voices[v].note.channel for v in group)
    for v in group:
        s = voices[v].note
        if s.channel == note.channel and s.pitch == note.pitch:
            return v

    def is_last(s):
        # Another channel's last voice: stealing it leaves that channel mute.
        # Not the same channel's, which keeps sounding with the new note.
        return s.note.channel != note.channel and by_channel[s.note.channel] <= 1

    def cost(v):
        s = voices[v]
        return (s.note.start == t, is_last(s), s.level, s.note.start, v)

    v = min(group, key=cost)
    s = voices[v]
    if s.note.start == t:
        return None
    if by_channel[note.channel] >= 1 and s.note.channel != note.channel and (
            is_last(s) or (s.level > level and by_channel[s.note.channel]
                           <= by_channel[note.channel])):
        return None
    return v


# The General MIDI hits that are the same instrument played another way: two
# bass drums, two snares, the hi-hat closed, pedaled and open, two crash
# cymbals, two rides. A MIDI asking for them together is thickening the hit,
# not playing two —the battle song hits 35 and 36 on every beat, and 38 and
# 40 on every snare—. Not the toms: they are different drums and a roll
# brings them together.
HIT_FAMILIES = {35: "bombo", 36: "bombo", 38: "caja", 40: "caja",
                42: "charles", 44: "charles", 46: "charles",
                49: "platillo", 57: "platillo", 51: "ride", 59: "ride"}


def _frame_order(notes, level):
    """In which order the notes that start in the same frame pick a voice:
    when there are not enough for all, the last ones are left out, because
    `_victim` does not steal from a note that started in the frame.

    * **Hits first, one per family** (`HIT_FAMILIES`), from loudest to
      softest: they are short, and they are the rhythm.
    * **Then the melodic notes, by their level divided by their place in
      their channel**: each channel's loudest note goes with its level, the
      second with half, the third with a third. That way the top voice of a
      chord goes before a softer channel, but the second note of that chord
      goes after, unless that channel is little more than a whisper.
    * **Last, a family's repeated hit**, which only plays if there is a
      voice to spare.

    `level` is each note's level with the frame's controllers, left plus
    right: `_victim`'s, which is the level the note will sound at.

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
    what is done in `_victim` —not stealing a note that just started, a cap
    on voices for the drums, hits not stealing—, which changes nothing: the
    melody was not lost to steals but to arriving last in its frame.
    """
    levels = {id(n): level(n) for n in notes}
    place = {}
    by_channel = collections.defaultdict(list)
    for n in notes:
        by_channel[n.channel].append(n)
    for channel, ns in by_channel.items():
        if channel == midi.DRUM_CHANNEL:
            seen = set()
            for n in sorted(ns, key=lambda n: (-levels[id(n)], n.pitch)):
                family = HIT_FAMILIES.get(n.pitch, n.pitch)
                place[id(n)] = (2 if family in seen else 0, -levels[id(n)])
                seen.add(family)
        else:
            by_level = sorted(ns, key=lambda n: (-levels[id(n)], -n.pitch))
            for i, n in enumerate(by_level):
                place[id(n)] = (1, -levels[id(n)] / (1.0 + i))
    return sorted(notes, key=lambda n: place[id(n)] + (n.pitch,))


# --- the shared bank --------------------------------------------------------

# Samples are requested by key: ("p", program, key) a melodic one, ("g", key)
# a percussion hit. It is one per General MIDI program and one per hit in the
# whole cartridge, so two songs that play piano use the same one. The melodic
# key picks the SoundFont zone: see `most_used_zones`.
def song_keys(parsed, root_keys=None):
    """The samples a song read by `read_song` asks for, or none. `root_keys` are
    the ones from `most_used_zones`; without it, middle C."""
    if not parsed:
        return set()
    root_keys = root_keys or {}
    return ({("p", p, root_keys.get(p, snes_samples.REFERENCE_KEY))
             for p in parsed["melodicos"]}
            | {("g", g) for g in parsed["golpes"]})


def most_used_zones(parsed_songs):
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
    time_by_zone = collections.defaultdict(collections.Counter)
    inside = collections.defaultdict(collections.Counter)
    # The zones the loop below is going to ask for, requested beforehand all
    # together: see `brr_samples.preload`.
    brr_samples.preload(
        ("program:%d@%d" % (parsed["programas"].get(note.channel, 0),
                            note.pitch)
         for parsed in parsed_songs if parsed for note in parsed["notas"]
         if note.channel != midi.DRUM_CHANNEL
         and note.channel in parsed["voces"]),
        snes_samples.SOUNDFONT)
    for parsed in parsed_songs:
        if not parsed:
            continue
        for note in parsed["notas"]:
            if (note.channel == midi.DRUM_CHANNEL
                    or note.channel not in parsed["voces"]):
                continue
            program = parsed["programas"].get(note.channel, 0)
            zone = brr_samples.zone("program:%d@%d" % (program, note.pitch),
                                    snes_samples.SOUNDFONT)
            if zone is None:
                continue
            time_by_zone[program][zone] += note.end - note.start
            inside[program, zone][note.pitch] += note.end - note.start
    root_keys = {}
    for program, by_zone in time_by_zone.items():
        zone = max(by_zone, key=lambda z: (by_zone[z], z))
        root = zone[1]
        if brr_samples.zone("program:%d@%d" % (program, root),
                            snes_samples.SOUNDFONT) == zone:
            root_keys[program] = root
        else:
            amount = inside[program, zone]
            root_keys[program] = max(amount, key=lambda k: (amount[k], -k))
    return root_keys


def _sample(key, budget):
    """A key's voice with that budget in BRR bytes, or None if the SoundFont
    does not have it."""
    if key[0] == "p":
        return snes_samples.build_voice(snes_samples.SOUNDFONT, key[1],
                                        budget, key=key[2])
    return snes_samples.build_drum(snes_samples.SOUNDFONT, key[1],
                                   budget)


# A budget nobody reaches: with it, each sample comes out at the SoundFont's
# rate —capped at `MAX_RATE`—, which is what it would weigh untrimmed.
NATIVE = 1 << 24
# The minimum a sample is given even when its package is full.
FLOOR = 256


class Constraint(collections.namedtuple("Constraint",
                                        "name keys free")):
    """A group of samples that has to fit together in `free` bytes: those
    of a package's songs, with what its sound effects take already
    subtracted, or those of a package plus those of the song that may be
    playing when it loads."""
    __slots__ = ()


class Group(collections.namedtuple("Group", "name songs effect_bytes")):
    """Songs —indices— that have to fit together in the ARAM, with `effect_bytes`
    bytes of sound effects beside them: those of a package, a lone exit song,
    or a package with the song that may be playing when it loads. It is what
    the `Constraint`s come from: which sample each song plays with is said
    by `copies`."""
    __slots__ = ()


def free_for(samples, effects):
    """What is free for samples with `samples` of music and `effects` in
    the directory: the ARAM from behind the directory and the silence up to
    `ARAM_END`. Each directory entry is four bytes."""
    return ARAM_END - (SAMPLES_ADDR + 4 * (samples + effects) + len(SILENCE))


def constraints_for(assignment, groups, free):
    """The `Constraint`s for `allocate` for those groups, with the samples
    each song gets according to `assignment` —see `copies`—."""
    exits = []
    for g in groups:
        keys = set().union(*[set(assignment[t].values()) for t in g.songs])
        if keys:
            exits.append(Constraint(g.name, keys, free - g.effect_bytes))
    return exits


# SRCN is one byte and the ROM's sample lists end with $FF, so the directory
# goes up to 255 entries: the music's samples and the sound effect places
# —see `effect_places`— together.
DIRECTORY_MAX = 255
# How many directory places can belong to sound effects: the ROM records
# which sound effect is in each one in `FAR_EFFECT_IN`, which has that size.
SE_PLACES_MAX = 48
# No copy is made for a sample that already plays at nearly its rate: a
# directory entry is worth more than that.
COPY_UNTIL = 0.9
def se_usual():
    """Up to how many directory entries the first round of `copies` goes:
    the ones the sound effects took when each had its own, and not today's.
    The game measured it: `[music] effect_slots_of_first_copies`."""
    return settings.value("music", "effect_slots_of_first_copies", kind=int)


def copies(keys_of, groups, effects, usual, real=None,
           cap=DIRECTORY_MAX, until=COPY_UNTIL):
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

    They are made in two rounds. `effects` is how many directory entries the
    sound effects take today, and `usual` how many they took when each
    had its own —see `se_usual`—.

    **The usual ones**, one at a time and **the worst first**: the sample
    with the lowest fraction of its native size that has some song outside
    the group limiting it, copied for the ones inside. Then the allocation
    is redone, because the copy changes what each group takes, and it goes
    on until the directory is full as it used to be —with `usual`
    entries for the sound effects— or until none is left below `until`.
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
    allocates with `real`, the same groups with what their sound effects
    really take: the `se_whole()` the music does not pay for go in what it
    leaves free, and a copy that goes up to its rate would fill exactly
    that.
    """
    real = groups if real is None else real
    assignment = [{k: k for k in ks} for ks in keys_of]
    natives, rates = {}, {}

    def native(key):
        if key not in natives:
            voice = _sample(key, NATIVE)
            natives[key], rates[key] = len(voice.data), voice.rate / 1000.0
        return natives[key]

    def users(key):
        return [t for t, a in enumerate(assignment) if key in a.values()]

    def with_copy(asg, key, copy, inside):
        new_asg = [dict(a) for a in asg]
        for t in inside:
            for base, own_map in new_asg[t].items():
                if own_map == key:
                    new_asg[t][base] = copy
        return new_asg

    songs_of = {g.name: set(g.songs) for g in groups}
    while True:
        keys = {k for a in assignment for k in a.values()}
        if len(keys) + usual >= cap:
            break
        rs = constraints_for(assignment, groups,
                             free_for(len(keys), usual))
        budget, limited_by = allocate(
            keys, rs, natives={k: native(k) for k in keys})
        worst = None
        for key, name in sorted(limited_by.items()):
            fraction = budget[key] / float(native(key))
            if fraction >= until:
                continue
            own = users(key)
            inside = [t for t in own if t in songs_of[name]]
            outside = len(own) - len(inside)
            if not inside or not outside:
                continue
            option = (round(fraction, 3), -outside, key, name, inside)
            if worst is None or option < worst:
                worst = option
        if worst is None:
            break
        _f, _a, key, name, inside = worst
        assignment = with_copy(assignment, key, key + ("@" + name,),
                               inside)

    free = free_for(cap - effects, effects)

    def khz(asg):
        keys = {k for a in asg for k in a.values()}
        budget, _l = allocate(
            keys, constraints_for(asg, real, free),
            natives={k: native(k) for k in keys})
        return keys, budget, [
            {b: budget[s] / float(native(s)) * rates[s]
             for b, s in a.items()} for a in asg]

    keys, budget, floor = khz(assignment)
    current = floor
    # Trying all of them on every pass is thousands of allocations: they are
    # tried in the order of what they added the last time they were tried
    # —new ones first—, and the first one that, tried again, adds at least
    # what any of the following ones added is taken. That it lowers no one
    # is always checked on the spot.
    bound = {}
    while len(keys) + effects < cap:
        candidates = []
        for key in sorted(keys):
            if budget[key] >= until * native(key):
                continue
            own = users(key)
            for g in groups:
                inside = tuple(t for t in own if t in songs_of[g.name])
                copy = key + ("@" + g.name,)
                if (not inside or len(inside) == len(own)
                        or copy in keys
                        or any(c[0] == key and c[2] == inside
                               for c in candidates)):
                    continue
                candidates.append((key, copy, inside))
        candidates.sort(key=lambda c: -bound.get(c, float("inf")))
        best = None
        for i, candidate in enumerate(candidates):
            if best is not None and best[0] >= bound.get(candidate,
                                                         float("inf")):
                break
            key, copy, inside = candidate
            new_asg = with_copy(assignment, key, copy, inside)
            keys_n, budget_n, raised = khz(new_asg)
            gained = sum(raised[t][b] - current[t][b]
                         for t in range(len(raised)) for b in raised[t])
            if any(raised[t][b] < floor[t][b] - 1e-6
                   for t in range(len(raised)) for b in raised[t]):
                gained = 0.0
            bound[candidate] = gained
            if gained > 0.01 and (best is None or gained > best[0]):
                best = (gained, new_asg, keys_n, budget_n, raised)
        if best is None:
            break
        _g, assignment, keys, budget, current = best
    return assignment


def effect_places(packages, names):
    """{sound effect: place}: which of the sound effects' directory entries
    each one goes in. `packages` are each package's sound effects and
    `names` all of them, in cartridge order.

    Until 2026-09-26 each sound effect had its own entry, and with 92 in the
    cartridge and the music beside them the directory was full: `copies` had
    no room to make more. But the ARAM holds one package at a time, and none
    carries more than a score of sound effects, so two sound effects that
    are never in the same package can share an entry. It is graph coloring
    —two sound effects touch if they share a package—, and with DSATUR as
    many places as the most loaded package has sound effects are enough.

    The ROM cannot tell from the entry which sound effect is there: it
    records it when uploading it (`FAR_EFFECT_IN`, in
    tools/runtime/audio_package.s).
    """
    touches = {n: set() for n in names}
    for own in packages:
        own = [n for n in own if n in touches]
        for n in own:
            touches[n] |= set(own) - {n}
    order = {n: i for i, n in enumerate(names)}
    place = {}
    while len(place) < len(touches):
        # The most constrained first —the one with the most distinct places
        # already taken around it—, and among those the one with the most
        # neighbors; on a tie, the one earlier in the cartridge, so it always
        # comes out the same.
        n = max((n for n in touches if n not in place),
                key=lambda n: (len({place[v] for v in touches[n] if v in place}),
                               len(touches[n]), -order[n]))
        taken = {place[v] for v in touches[n] if v in place}
        place[n] = min(set(range(len(taken) + 1)) - taken)
    return place


def allocate(keys, constraints, margin=None, natives=None):
    """({key: budget}, {key: constraint that limited it}): how much each
    sample gets so that every constraint fits in its space minus `margin`.

    It is progressive filling over the fraction of each sample's native
    size: the fraction of all of them is raised together until some
    constraint fills up, that one's samples are frozen, and it goes on with
    the rest. That way a sample is limited by its **worst** package and not
    by the whole bank, and the one with room to spare does not pay for the
    one without. Whatever is in no constraint that fills up goes whole.
    """
    margin = ARAM_MARGIN if margin is None else margin
    if natives is None:
        natives = {k: len(_sample(k, NATIVE).data) for k in keys}
    fraction, limited_by = {}, {}
    free_voices = set(keys)
    active = [r for r in constraints if r.keys & free_voices]
    # Each constraint's totals are kept up to date as samples freeze,
    # instead of summing them again on every pass: `copies` allocates
    # thousands of times per conversion, and this way each allocation costs
    # a fraction.
    own_fx = [set(r.keys) & free_voices for r in active]
    sums = [sum(natives[k] for k in s) for s in own_fx]
    fixed = [0.0] * len(active)
    where = collections.defaultdict(list)
    for i, s in enumerate(own_fx):
        for k in s:
            where[k].append(i)
    alive = list(range(len(active)))
    while free_voices and alive:
        worst, which = None, None
        for i in alive:
            if not own_fx[i]:
                continue
            f = (active[i].free - margin - fixed[i]) / sums[i]
            if worst is None or f < worst:
                worst, which = f, i
        if worst is None or worst >= 1:
            break
        level = max(0.0, worst)
        for k in list(own_fx[which]):
            fraction[k] = level
            limited_by[k] = active[which].name
            free_voices.discard(k)
            for j in where[k]:
                fixed[j] += level * natives[k]
                sums[j] -= natives[k]
                own_fx[j].discard(k)
        alive.remove(which)
    return ({k: max(FLOOR, int(fraction.get(k, 1.0) * natives[k]))
             for k in keys}, limited_by)


class Bank:
    """The samples shared by **every** song in the ROM, one per program and
    one per hit, each with the budget of its worst package.

    There is only one —except for the copies from `copies`—, and not to save
    cartridge space —there is plenty of that— but because of the numbering:
    the SRCN the stream writes is the sample's index in the cartridge, so
    two songs that play piano point to the same one. But **it is not
    uploaded whole**: the ARAM gets packages, one per map —see
    `package_load` in tools/runtime/audio_package.s—, so what has to
    fit in the 64 KB is not the bank but each package, with its sound
    effects.

    That is why the budget is per package: step 6 of
    `workflow/tasks/todo/la-calidad-de-la-musica.md`, option A, chosen by
    taro on 2026-09-26. Until that day the whole bank had to fit in the ARAM
    —40 KB for the melodic part and the percussion with whatever was left—,
    and the songs that did not fit stopped contributing programs: nineteen
    of the thirty-two in `release` played with what others had put in, or
    were silent.

    `constraints` are `allocate`'s; `limited_by` says which one set each
    sample, for the converter's report.
    """

    def __init__(self, keys, constraints=(), margin=None):
        keys = {k for k in keys if _sample(k, NATIVE) is not None}
        budget, self.limited_by = allocate(keys, constraints, margin)
        voice = {k: _sample(k, budget[k]) for k in keys}
        # The budget is a guide: the real length is rounded up to BRR blocks,
        # so what it really takes is checked and, if a constraint goes over
        # its space —without the margin: the margin is for this—, its samples
        # are asked for less and it is built again.
        for _ in range(20):
            over = [r for r in constraints
                    if self._sum(voice, r.keys) > r.free]
            if not over:
                break
            for r in over:
                used = self._sum(voice, r.keys)
                for k in r.keys & set(voice):
                    budget[k] = max(FLOOR, int(budget[k] * r.free
                                               / used * 0.98))
                    voice[k] = _sample(k, budget[k])
        else:
            raise SystemExit(
                "the samples of %s do not fit in the ARAM even at the minimum"
                % ", ".join("%s (%d of %d B)" % (r.name,
                                                 self._sum(voice, r.keys),
                                                 r.free) for r in over))
        self.constraints = list(constraints)
        self.keys = ([k for k in sorted(keys) if k[0] == "p"]
                       + [k for k in sorted(keys) if k[0] == "g"])
        self.voices = [voice[k] for k in self.keys]
        # From MIDI program to index in the bank, which is what goes in
        # `V_SRCN`; hits go after the melodic ones, so the DSP does not tell
        # percussion from anything else. These are the samples without
        # copies: a song with copies asks for its own with `for_song`.
        self.melodic = {k[1]: i for i, k in enumerate(self.keys)
                        if k[0] == "p" and len(k) == 3}
        self.hits = {k[1]: i for i, k in enumerate(self.keys)
                     if k[0] == "g" and len(k) == 2}
        self._envelopes = {}

    def for_song(self, assignment):
        """The bank as a song sees it: its programs and its hits point to the
        samples it was given —see `copies`—, and the rest is everyone's.
        `assignment` is {key: sample}."""
        view = _View(self)
        index = {k: i for i, k in enumerate(self.keys)}
        view.melodic = {base[1]: index[k] for base, k in assignment.items()
                        if base[0] == "p" and k in index}
        view.hits = {base[1]: index[k] for base, k in assignment.items()
                     if base[0] == "g" and k in index}
        return view

    @staticmethod
    def _sum(voice, keys):
        return sum(len(voice[k].data) for k in keys if k in voice)

    def takes(self, keys):
        """How much the samples of those keys take in the ARAM."""
        return sum(len(v.data) for k, v in zip(self.keys, self.voices)
                   if k in keys)

    def envelope(self, program, key):
        """(ADSR1, ADSR2, release GAIN) of a melodic note: the envelope of
        the SoundFont zone covering the key, translated by `sdsp.envelope`.

        The zone may not be the sample's —each program carries only one, the
        one from `most_used_zones`—, and that is on purpose: it is the
        envelope the SoundFont would give that key, and on the piano the
        decay changes key by key. If no zone covers the key, middle C's.
        """
        cache_key = (program, key)
        if cache_key not in self._envelopes:
            sf2 = (brr_samples.envelope("program:%d@%d" % (program, key),
                                        snes_samples.SOUNDFONT)
                   or brr_samples.envelope(
                       "program:%d@%d" % (program, snes_samples.REFERENCE_KEY),
                       snes_samples.SOUNDFONT))
            self._envelopes[cache_key] = sdsp.envelope(sf2, key)
        return self._envelopes[cache_key]

    @property
    def bytes(self):
        """How much it takes in ARAM: the directory plus the samples."""
        return 4 * len(self.voices) + sum(len(v.data) for v in self.voices)


class _View:
    """What `Bank.for_song` returns: the same bank with one song's indices.
    Whatever it does not override it reads from the bank."""

    def __init__(self, bank):
        self._bank = bank

    def __getattr__(self, name):
        return getattr(self._bank, name)


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
        # voices brought down with `RAMP` because another note takes them in
        # the next frame.
        self.release = []
        # The ones that start: one `NoteSetup` per note, in order.
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
# writes come from `NoteSetup.writes`, in the order they go to the DSP.
class NoteSetup(collections.namedtuple(
        "NoteSetup", "voice left right pitch sample adsr1 adsr2 gain")):
    __slots__ = ()

    def writes(self):
        base = self.voice * 0x10
        return [(base + sdsp.V_VOL_L, self.left),
                (base + sdsp.V_VOL_R, self.right),
                (base + sdsp.V_PITCH_L, self.pitch & 0xFF),
                (base + sdsp.V_PITCH_H, self.pitch >> 8),
                (base + sdsp.V_SRCN, self.sample),
                (base + sdsp.V_ADSR1, self.adsr1),
                (base + sdsp.V_ADSR2, self.adsr2)]


def build_events(notes, voices, programs, bank, controls=(), allocation=None,
                 headroom=sdsp.HEADROOM):
    """The writes to the DSP, frame by frame.

    Each channel has its group of voices —since step 5, all eight for
    everyone: see `assign`—; a note that starts takes a free one, the one
    that cuts least according to `_free_order`, and if they are all held it
    steals the one `_victim` says, or it does not play. It is what a
    synthesizer does when it runs out of polyphony.

    The bank comes from outside and is not built here: every song in the ROM
    shares it, so the `V_SRCN` indices this stream writes are that bank's and
    not those of one of its own. See `Bank`.

    `controls` are the song's `midi.Control`s, already in frames: volume,
    expression and pan go into the volume of each side of the note, and bend
    into its pitch. A frame's controls are applied before its notes, so the
    note starts with the state the frame ends with; and a voice that was
    already sounding —or is in its tail— gets its registers rewritten.

    `allocation`, if a list is given, is filled with what each note that has a
    sample got: (note, voice or None if it did not play, frame its voice was
    stolen in or None, until when it holds it —the end of the note, or of
    the sample if it is a hit shorter than the note—). It is where the
    amount of lost note-time comes from.

    `headroom` is the ceiling of this song's voices, `sdsp.HEADROOM`'s or a lower
    one: see `read_ceilings`.
    """
    frames = collections.defaultdict(Frame)
    ceiling = headroom / sdsp.HEADROOM
    bank_voices, index_of, drum_index = bank.voices, bank.melodic, bank.hits

    state = collections.defaultdict(lambda: dict(midi.DEFAULTS))
    pending = sorted(controls, key=lambda c: c.start)
    next_control = 0

    def sides(note, drums):
        c = state[note.channel]
        return sdsp.volume(note.velocity,
                           ceiling * (sdsp.CEILING_DRUM if drums
                                      else sdsp.CEILING),
                           c[midi.VOLUME], c[midi.EXPRESSION], c[midi.PAN])

    def pitch(note, drums):
        if drums:
            # In General MIDI the note picks the instrument, not the pitch, so
            # each hit has its own sample and is played at its original rate:
            # transposing it would turn a bass drum into something else. That
            # is why the bend does not move it either.
            drum = bank_voices[drum_index[note.pitch]]
            return sdsp.pitch_for(drum.root, drum.root, drum.rate)
        instrument = bank_voices[index_of[programs.get(note.channel, 0)]]
        return sdsp.pitch_for(note.pitch + state[note.channel][midi.BEND],
                              instrument.root, instrument.rate)

    def apply_controls(until):
        """Applies the controllers up to frame `until`, and rewrites what
        changed on the voices whose note is from that channel."""
        nonlocal next_control
        while (next_control < len(pending)
               and pending[next_control].start <= until):
            c = pending[next_control]
            next_control += 1
            if state[c.channel][c.number] == c.value:
                continue
            state[c.channel][c.number] = c.value
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
                    step = pitch(note, drums)
                    frame[base + sdsp.V_PITCH_L] = step & 0xFF
                    frame[base + sdsp.V_PITCH_H] = step >> 8
                else:
                    left, right = sides(note, drums)
                    frame[base + sdsp.V_VOL_L] = left
                    frame[base + sdsp.V_VOL_R] = right

    def in_order():
        """The notes frame by frame, each frame in `_frame_order`'s
        order. The frame's controllers are applied before sorting it,
        because the order goes by the level each note starts with; and since
        it is a generator, that only happens once the previous frame has
        allocated its voices, which is when each note used to do it."""
        by_frame = collections.defaultdict(list)
        for note in notes:
            by_frame[note.start].append(note)
        for frame_no in sorted(by_frame):
            apply_controls(frame_no)
            yield from _frame_order(by_frame[frame_no], lambda n: sum(
                sides(n, n.channel == midi.DRUM_CHANNEL)))

    # Who owns each voice now: the last note that took it, with until when
    # it holds it and until when it can be heard. A note's release is only
    # scheduled at the end, and only if it reached its end still being the
    # owner: if another note stole the voice first, releasing it would
    # release the thief. Until 2026-09-25 it was scheduled when taking the
    # voice, and 329 notes of `escape_newyork` were cut short, almost all
    # of them the bass.
    holders, owner, robbed, sounded, ramps = {}, {}, {}, [], []
    owner_entry = {}                  # its owner's `allocation` entry
    for note in in_order():
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

        step = pitch(note, drums)
        left, right = sides(note, drums)
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
            sample = bank_voices[source]
            tail = note.start + int(math.ceil(
                sample.frames * TICKS_PER_SECOND / float(sample.rate)))
            end = min(tail, note.end)
        else:
            adsr1, adsr2, gain = bank.envelope(program, note.pitch)
            end, tail = note.end, note.end + _release_frames(gain)

        t = note.start
        free_voices = [v for v in group if v not in holders or holders[v].end <= t]
        if free_voices:
            voice = min(free_voices, key=lambda v: _free_order(v, t, holders, note, drums))
        else:
            voice = _victim(note, t, group, holders, left + right)
        if voice is None:
            if allocation is not None:
                allocation.append([note, None, None, end])
            continue
        if voice in owner:
            robbed.setdefault(id(owner[voice]), t)
            if voice in owner_entry:
                owner_entry[voice][2] = t
            # If the voice is still sounding, it is brought down to zero in the
            # frame before: KON drops the envelope to zero at once, and that is
            # a click. Not for a note that started in that same frame, which is
            # prepared after the release and undoes it.
            previous = holders[voice]
            if previous.tail > t - 1 and previous.note.start < t - 1:
                ramps.append((t - 1, voice))
        holders[voice] = _Voice(note, end, tail, left + right)
        owner[voice] = note
        if allocation is not None:
            allocation.append([note, voice, None, end])
            owner_entry[voice] = allocation[-1]

        start = frames[note.start]
        base = voice * 0x10
        # What the controllers were rewriting for the previous owner in this
        # frame no longer applies: this note writes its own, with the same
        # state.
        for register in (sdsp.V_VOL_L, sdsp.V_VOL_R, sdsp.V_PITCH_L,
                         sdsp.V_PITCH_H):
            start.control.pop(base + register, None)
        start.setup.append(NoteSetup(voice, left, right, step, source,
                                     adsr1, adsr2, gain))

        start.kon |= 1 << voice
        if not drums:
            sounded.append((note, voice, gain))

    # The ones left after the last note: the fade at the end of
    # `escape_newyork` is CC7 over the notes that were already sounding.
    apply_controls(float("inf"))

    for note, voice, gain in sounded:
        # Stolen in the same frame it ends in is not released either: the
        # thief writes its ADSR1 after the release and undoes it, so it would
        # be six bytes that do nothing.
        if robbed.get(id(note), note.end + 1) <= note.end:
            continue
        frames[note.end].release.append((voice, gain))
    # Ramps go after their frame's releases, to win over them.
    for frame_no, voice in ramps:
        frames[frame_no].release.append((voice, RAMP))

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


def writes(frames, length, init):
    """What the song writes to the DSP: (frame, register, value), in order.

    It is **the stream's specification**, and what until 2026-09-26 was the
    stream itself —a three-byte `OP_DSP register value` per write—. `pack`'s
    per-note format has to expand to exactly this, frame by frame:
    `build_all` verifies it with every song it builds, and in the ROM
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
    out = []
    state = {}
    frame_no = 0

    def write(register, value):
        value &= 0xFF
        if state.get(register) == value:
            return
        state[register] = value
        out.append((frame_no, register & 0xFF, value))

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
        frame_no = at

        if sounding:                       # clear the previous frame's trigger
            out.append((frame_no, sdsp.KON, 0x00))
            sounding = 0
        write(sdsp.KOF, 0x00)
        for voice, gain in frame.release:
            write(voice * 0x10 + sdsp.V_ADSR1, 0x00)    # ADSR off: GAIN rules
            write(voice * 0x10 + sdsp.V_GAIN, gain)
        for setup in frame.setup:
            for register, value in setup.writes():
                write(register, value)
        for register, value in sorted(frame.control.items()):
            write(register, value)
        if frame.kof:
            write(sdsp.KOF, frame.kof)
        if frame.kon:
            out.append((frame_no, sdsp.KON, frame.kon))
            sounding = frame.kon

    # At the end everything is shut off, otherwise the last note keeps
    # sounding into the loop.
    frame_no = max(frame_no, length)
    out.append((frame_no, sdsp.KON, 0x00))
    out.append((frame_no, sdsp.KOF, 0xFF))
    return out


# --- the per-note format ---------------------------------------------------
#
# Until 2026-09-26 the stream was the writes themselves —`OP_DSP register
# value`, three bytes each— and it weighed more than a fifth of the
# cartridge. Now they are events, and the 65816 expands them (`music_frame`)
# into **the same writes, frame by frame**: the format cannot change how it
# sounds. `build_all` verifies it with every song it builds, and in the
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
# The register cache of `writes` is kept by the 65816 and not by the
# stream: each event says values and the decoder skips the one the register
# already has. It has a single trap, which is that it cannot say "I don't
# know" —see `decode`—. KON does not go in the stream either: the notes
# accumulate it and the wait that closes the frame fires it, which is
# exactly `writes`'s rule.

VOICES = sdsp.VOICES
# The voice registers the decoder keeps in its cache: from VOL_L to GAIN.
VOICE_REGISTERS = 8


# The families of eight opcodes, one per voice: the voice goes in the three
# low bits and the family in the upper ones, which is how the decoder finds
# them. See the header of `tools/protocol/music.toml`, which cannot declare
# them.
FAMILIES = ["NOTE", "NOTE_VOL", "NOTE_PAN", "RELEASE", "RELEASE_GAIN",
            "SET_VOL", "SET_PAN", "SET_PITCH"]
for _k, _family in enumerate(FAMILIES):
    for _v in range(VOICES):
        assert globals()["OP_%s_V%d" % (_family, _v)] == 8 * _k + _v, (
            "music.toml: OP_%s_V%d is not where the family expects it"
            % (_family, _v))
# The short waits, from OP_WAIT_1 to OP_WAIT_32: one byte closes the frame
# and waits. Almost all of them fit; the rest go with OP_WAIT, sixteen bits.
SHORT_WAIT = 32
for _n in range(1, SHORT_WAIT + 1):
    assert globals()["OP_WAIT_%d" % _n] == OP_WAIT_1 + _n - 1, _n
assert OP_WAIT_1 == 8 * len(FAMILIES)


def _is_voice_register(register):
    return register < 0x80 and register & 0x0F < VOICE_REGISTERS


def boot_writes():
    """What `OP_INIT` writes: the `dsp_init_*` table `emit` leaves for the
    ROM —the startup without KON or KOF— followed by KON and KOF at zero."""
    return ([(r, v) for r, v in init_writes() if r not in (sdsp.KON, sdsp.KOF)]
            + [(sdsp.KON, 0x00), (sdsp.KOF, 0x00)])


class _Encoder:
    """Builds a song's per-note stream. It keeps the same state as the
    65816's decoder —the voice register cache, each voice's sound, the
    frame's accumulated KON— and the same cache as `writes`, so it
    decides each event knowing exactly which writes it will produce."""

    def __init__(self):
        self.stream = bytearray()
        self.sounds, self._sound_index = [], {}
        self.state = {}             # `writes`'s cache
        self.sound_of = {}         # the sound of each voice's last note

    def sound(self, p):
        # In the order they are written —PITCH_L, PITCH_H, SRCN, ADSR1,
        # ADSR2—, which is what lets the 65816 walk it with a single index.
        key = (p.pitch & 0xFF, p.pitch >> 8, p.sample, p.adsr1, p.adsr2,
               0 if p.gain is None else p.gain)
        if key not in self._sound_index:
            self._sound_index[key] = len(self.sounds)
            self.sounds.append(key)
        return self._sound_index[key]

    def changes(self, register, value):
        return self.state.get(register) != value & 0xFF

    def write(self, register, value):
        self.state[register] = value & 0xFF

    def op(self, code, *data):
        self.stream.extend((code,) + data)

    def global_(self, register, value):
        """A cached write outside the voices: it goes raw if it changes."""
        assert not _is_voice_register(register), register
        if self.changes(register, value):
            self.write(register, value)
            self.op(OP_DSP, register, value & 0xFF)

    def note(self, p):
        v, base = p.voice, p.voice * 0x10
        s = self.sound(p)
        if (not self.changes(base + sdsp.V_VOL_L, p.left)
                and not self.changes(base + sdsp.V_VOL_R, p.right)):
            self.op(OP_NOTE_V0 + v, s)
        elif p.left == p.right:
            self.op(OP_NOTE_VOL_V0 + v, p.left, s)
        else:
            self.op(OP_NOTE_PAN_V0 + v, p.left, p.right, s)
        self.sound_of[v] = s
        for register, value in p.writes():
            self.write(register, value)

    def release(self, v, gain):
        base = v * 0x10
        if (not self.changes(base + sdsp.V_ADSR1, 0)
                and not self.changes(base + sdsp.V_GAIN, gain)):
            return                      # it would write nothing
        if self.sounds[self.sound_of[v]][5] == gain:
            self.op(OP_RELEASE_V0 + v)
        else:
            self.op(OP_RELEASE_GAIN_V0 + v, gain)
        self.write(base + sdsp.V_ADSR1, 0)
        self.write(base + sdsp.V_GAIN, gain)

    def controls(self, control):
        by_voice = collections.defaultdict(dict)
        for register, value in control.items():
            assert _is_voice_register(register), (
                "a controller writes $%02X, which is not a voice register" % register)
            by_voice[register >> 4][register & 0x0F] = value
        for v in sorted(by_voice):
            regs, base = by_voice[v], v * 0x10
            assert set(regs) in ({0, 1}, {2, 3}, {0, 1, 2, 3}), (
                "a controller writes to voice %d the registers %s: the "
                "format only knows the volume pair and the pitch pair"
                % (v, sorted(regs)))
            if 0 in regs and (self.changes(base, regs[0])
                              or self.changes(base + 1, regs[1])):
                if regs[0] == regs[1]:
                    self.op(OP_SET_VOL_V0 + v, regs[0])
                else:
                    self.op(OP_SET_PAN_V0 + v, regs[0], regs[1])
                self.write(base, regs[0])
                self.write(base + 1, regs[1])
            if 2 in regs and (self.changes(base + 2, regs[2])
                              or self.changes(base + 3, regs[3])):
                self.op(OP_SET_PITCH_V0 + v, regs[2], regs[3])
                self.write(base + 2, regs[2])
                self.write(base + 3, regs[3])

    def wait(self, n_frames):
        if 1 <= n_frames <= SHORT_WAIT:
            self.op(OP_WAIT_1 + n_frames - 1)
        else:
            self.op(OP_WAIT, n_frames & 0xFF, n_frames >> 8)


def pack(frames, length, init):
    """The song in the per-note format: (stream, sounds).

    `sounds` are the ones the song plays, in the order of their indices:
    each is (PITCH_L, PITCH_H, SRCN, ADSR1, ADSR2, release GAIN), and the
    stream names them by index. What the stream produces in the DSP is
    **exactly** `writes(frames, length, init)`, write by write and frame
    by frame; `build_all` verifies it with `decode`, which is the
    model of the 65816's decoder.
    """
    c = _Encoder()
    init = list(init)
    if [(r, v & 0xFF) for r, v in init] == boot_writes():
        c.op(OP_INIT)
        for r, v in init:
            c.write(r, v)
    else:
        for r, v in init:
            c.global_(r, v)

    previous, sounding = 0, 0
    for at in sorted(frames):
        if at > length:
            break
        frame = frames[at]
        if not (frame.release or frame.setup or frame.kon or frame.kof
                or frame.control):
            continue
        if at > previous:
            c.wait(at - previous)
            sounding = 0                 # the decoder clears KON on opening
        previous = at
        c.global_(sdsp.KOF, 0x00)
        for voice, gain in frame.release:
            c.release(voice, gain)
        kon = 0
        for p in frame.setup:
            c.note(p)
            kon |= 1 << p.voice
        c.controls(frame.control)
        if frame.kof:
            c.global_(sdsp.KOF, frame.kof)
        assert kon == frame.kon, "the frame's KON is not its notes' KON"
        sounding = kon

    # The end: `writes` clears KON and shuts everything off in frame
    # `length`.
    if length > previous:
        c.wait(length - previous)
        if not sounding:
            c.op(OP_DSP, sdsp.KON, 0x00)
    else:
        c.op(OP_WAIT, 0, 0)             # fires the KON without waiting
        c.op(OP_DSP, sdsp.KON, 0x00)
    c.op(OP_DSP, sdsp.KOF, 0xFF)
    c.op(OP_END)
    if len(c.sounds) > 256:
        raise SystemExit("the song uses %d sounds and the index is one byte"
                         % len(c.sounds))
    return bytes(c.stream), c.sounds


def decode(stream, sounds):
    """The model of the 65816's decoder —`music_frame`, in
    tools/runtime/music.s—, step by step: what the stream writes, (frame,
    register, value), up to its `OP_END`. It has to give the same as
    `writes`.

    It also imitates what the 65816 does **not** know. Its cache has no
    "empty": when the song starts it holds whatever was left, and what stands
    in for that is that each voice's first note writes everything without
    looking, and the first release writes its GAIN regardless. If the stream
    ever compared against a register nobody has written yet, on the console
    it would be comparing against garbage: here that stops.
    """
    out, cache, seen, with_gain = [], {}, set(), set()
    gain_of = {}
    frame_no, kon, sounding, i = 0, 0, 0, 0

    def w(register, value):
        out.append((frame_no, register, value))

    def write(register, value, force=False):
        if not force:
            assert register in cache, (
                "the stream compares register $%02X against the cache before "
                "writing it: in the ROM it would be garbage" % register)
            if cache[register] == value:
                return
        cache[register] = value
        w(register, value)

    def read():
        nonlocal i
        i += 1
        return stream[i - 1]

    while True:
        op = read()
        if op == OP_END:
            return out
        if op == OP_INIT:
            for r, v in boot_writes():
                w(r, v)
            continue
        if op == OP_DSP:
            r, v = read(), read()
            assert not _is_voice_register(r)
            w(r, v)
            continue
        if op == OP_WAIT or OP_WAIT_1 <= op < OP_WAIT_1 + SHORT_WAIT:
            if op == OP_WAIT:
                n = read()
                n |= read() << 8
            else:
                n = op - OP_WAIT_1 + 1
            if kon:
                w(sdsp.KON, kon)
                sounding, kon = kon, 0
            if n:
                frame_no += n
                if sounding:
                    w(sdsp.KON, 0)
                    sounding = 0
            continue
        assert op < OP_WAIT_1, "opcode $%02X" % op
        family, v = FAMILIES[op >> 3], op & 7
        base = v * 0x10
        if family.startswith("NOTE"):
            # The voice's first note writes everything: see above.
            force = v not in seen
            seen.add(v)
            if family == "NOTE_VOL":
                vol = read()
                write(base + sdsp.V_VOL_L, vol, force)
                write(base + sdsp.V_VOL_R, vol, force)
            elif family == "NOTE_PAN":
                left, right = read(), read()
                write(base + sdsp.V_VOL_L, left, force)
                write(base + sdsp.V_VOL_R, right, force)
            sound = sounds[read()]
            for k in range(5):          # from PITCH_L to ADSR2, in that order
                write(base + sdsp.V_PITCH_L + k, sound[k], force)
            gain_of[v] = sound[5]
            kon |= 1 << v
        elif family.startswith("RELEASE"):
            gain = read() if family == "RELEASE_GAIN" else gain_of[v]
            write(base + sdsp.V_ADSR1, 0)
            write(base + sdsp.V_GAIN, gain, v not in with_gain)
            with_gain.add(v)
        elif family == "SET_VOL":
            vol = read()
            write(base + sdsp.V_VOL_L, vol)
            write(base + sdsp.V_VOL_R, vol)
        elif family == "SET_PAN":
            left, right = read(), read()
            write(base + sdsp.V_VOL_L, left)
            write(base + sdsp.V_VOL_R, right)
        elif family == "SET_PITCH":
            lo, hi = read(), read()
            write(base + sdsp.V_PITCH_L, lo)
            write(base + sdsp.V_PITCH_H, hi)
        else:
            raise AssertionError("opcode $%02X" % op)


def check_format(name, stream, sounds, reference):
    """That a song's stream, decoded, writes the same as `writes`: every
    register, every value, in the same order and the same frame. The
    converter stops at the first difference."""
    out = decode(stream, sounds)
    if out == reference:
        return
    for n, (a, b) in enumerate(zip(out, reference)):
        if a != b:
            break
    else:
        n = min(len(out), len(reference))
    raise SystemExit(
        "the stream of %s does not write what it has to write: write %d is "
        "%s and it had to be %s (frame, register, value)"
        % (name, n, out[n] if n < len(out) else "none",
           reference[n] if n < len(reference) else "none"))


def song_of_map(map_id, game_dir=None):
    """The name of the song a map gets from the tree, or "" if it has none."""
    game_dir = game_dir or resources.GAME_DIR
    return songs_of_maps([map_id], game_dir)[0]


def songs_of_maps(map_ids, game_dir=None):
    """`song_of_map` for each one, reading the tree only once.

    "" means that entering the map **does not change** what is playing:
    either the map has no song —the root of the tree—, or it is
    `music_type` 1, "an event decides". It is the early `return` of
    `Game_Map::PlayBgm` in easyrpg. An "(OFF)" is a song: it silences, just
    like a `PlayBGM` of "(OFF)".
    """
    game_dir = game_dir or resources.GAME_DIR
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    names = []
    for map_id in map_ids:
        music = tree.map_music(map_id)
        names.append(music["name"] if music else "")
    return names


def read_song(name, game_dir=None):
    """What needs to be known about a song **before** having the bank.

    Returns None if the name is missing or is not a MIDI, which is like a map
    without music: the song still goes into the numbering —the bytecode
    already carries its index— but its stream is a lone `OP_END` and the ROM
    stays silent when it is played.
    """
    game_dir = game_dir or resources.GAME_DIR
    path = song_path(name, game_dir)
    if not path or not path.lower().endswith(".mid"):
        return None
    notes, tempos, division, programs, controls = midi.read(path)
    voices = assign(notes)
    length = music.timeline(notes, tempos, division)
    music.timeline(controls, tempos, division)
    return {
        "nombre": name,
        "notas": notes,
        "controles": controls,
        "largo": length,
        "voces": voices,
        "programas": programs,
        # What it contributes to the shared bank: the programs of its melodic
        # channels and the percussion keys it plays.
        "melodicos": {programs.get(c, 0) for c in voices
                      if c != midi.DRUM_CHANNEL},
        "golpes": {n.pitch for n in notes if n.channel == midi.DRUM_CHANNEL},
    }


# --- each song's volume ceiling ---------------------------------------------

# The headroom of each song that would clip with `sdsp.HEADROOM`'s: option B of
# step 5 of `workflow/tasks/todo/la-calidad-de-la-musica.md`, chosen by taro
# on 2026-09-26. The DSP adds up the eight voices and saturates the sum to
# 16 bits before the master volume, so the only thing that prevents clipping
# is each voice's ceiling; with a single one for all, it is set by the song
# that adds up the most —`rshinld`, because of its CC7 at 127— and the ones
# that do not clip drop almost 4 dB for no reason. With one per song, each
# drops just what it needs.
#
# **It is not written by hand**: `tools/audio/ceilings.py` (`just techos`)
# measures it by playing each song in the ROM, and what remains is versioned
# data, like the decisions in `rom/parches/auto/`. A song that is not in the
# table goes with `sdsp.HEADROOM`. Every change to the mix —the samples, the
# envelopes, the allocation— makes it stale, and `test_musica_techos.py`
# enforces that.
def ceilings_path():
    """Where the table is: a function and not a constant, because it comes
    from the project, which is found when used and not at import."""
    return os.path.join(project.auto_patches(), "musica", "techos.toml")


def read_ceilings(path=None):
    """{song: headroom} from the versioned table; empty if it does not exist."""
    import tomllib
    path = path or ceilings_path()
    try:
        with open(path, "rb") as handle:
            table = tomllib.load(handle)
    except FileNotFoundError:
        return {}
    return {name: row["aire"] for name, row in table["temas"].items()}


def mix_fingerprint(song_writes, bank):
    """What a song's peak depends on, summarized: what it writes to the DSP
    —with its headroom already applied— and the samples it plays, with their
    loop. Whatever changes this can move the peak, and the ceiling table
    stores it so the test knows whether what was measured is still what
    plays. The driver does not count: it mixes nothing, it passes writes
    along."""
    import hashlib
    h = hashlib.sha256(repr(song_writes).encode())
    samples = sorted({value for _c, register, value in song_writes
                      if register < 0x80
                      and register & 0x0F == sdsp.V_SRCN})
    for i in samples:
        if i < len(bank.voices):
            v = bank.voices[i]
            h.update(b"%d:%d:" % (i, v.loop_block or 0) + bytes(v.data))
    return h.hexdigest()[:16]


def _whole_effects_fit(bank, packages, inheritance, effects, budgeted,
                       names):
    """That the extra space the `se_whole()` take fits, in each package,
    in what the music left free: the bank is already allocated without
    counting it, so if it does not fit there is nobody to take it from
    without lowering an instrument's rate, and the converter stops saying
    which one.

    And it says —without stopping— with which song that may be playing a
    package's sound effects used to fit alongside at their usual size and no
    longer fit whole: there they wait for the next `PlayBGM` (see
    `decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md`)."""
    whole_fx, paid = se_whole(), se_paid_by_music()
    keys_of = {}
    for package in packages:
        name, own = package[0], package[1]
        keys_of[name] = set().union(
            *[set(bank.assignment[t].values()) for t in own])
    not_fitting = []
    bank.whole_extra = {}
    for package in packages:
        name, own_fx = package[0], set(package[2]) & set(effects)
        whole = sorted(e for e in own_fx
                       if e in whole_fx and e not in paid)
        if not whole:
            continue
        effect_bytes = sum(len(effects[e].data) for e in own_fx)
        bank.whole_extra[str(name)] = effect_bytes - sum(budgeted[e]
                                                         for e in own_fx)
        # The package, and each of its separate songs, which is uploaded with
        # the same sound effects: see `separate_songs`.
        for own in [None] + [[t] for t in (package[4] if len(package) > 4
                                           else ())]:
            music_bytes = bank.takes(keys_of[name] if own is None
                                     else set(bank.assignment[own[0]].values()))
            if music_bytes + effect_bytes > bank.free:
                not_fitting.append("%s in package %s%s (%d B over)" % (
                    ", ".join(whole), name,
                    "" if own is None else ">" + names[own[0]],
                    music_bytes + effect_bytes - bank.free))
    if not_fitting:
        raise SystemExit(
            "the whole sound effects do not fit without lowering an "
            "instrument's rate: %s. Lower their rate in [sound_effects.whole], or remove them"
            % "; ".join(not_fitting))
    effects_of = {p[0]: set(p[2]) & set(effects) for p in packages}
    for name, inherited in inheritance:
        own_fx = effects_of[name]
        if not any(e in whole_fx and e not in paid
                   for e in own_fx):
            continue
        music_bytes = bank.takes(keys_of[name]
                                 | set(bank.assignment[inherited].values()))
        before = music_bytes + sum(budgeted[e] for e in own_fx)
        now = music_bytes + sum(len(effects[e].data) for e in own_fx)
        if before <= bank.free < now:
            print("  with %s playing, the whole sound effects of package %s "
                  "do not fit alongside: they wait for the PlayBGM"
                  % (names[inherited], name))


def build_all(names, game_dir=None, effects=(), packages=None,
              inheritance=(), ceilings=None, measuring_headroom=None):
    """Every song in the ROM, sharing a single sample bank.

    Returns (driver, the voices —the bank's followed by the sound effects,
    each with its sample number—, songs, bank). There is one dict per song in the
    order they came in: the indices are `Songs`'s, the bytecode already has
    them emitted, so **they cannot be reordered**.

    **Every requested song goes in the cartridge, and all of them with all
    their samples.** An index costs no ARAM: it costs its stream, which
    lives in the cartridge. What competes for the ARAM is the samples, and
    that is allocated per package: see `Bank` and `allocate`.

    `packages` are the ROM's, by name: (name, indices of its songs, names of
    its sound effects[, indices of its exit songs[, indices of its separate
    songs]]). Each one has to fit alone in the ARAM, with its sound effects,
    and what its sound effects take is subtracted before allocating; each
    exit song —see `Songs.exit_songs` in tools/port/events.py— has to fit
    alone, and each separate song —see `separate_songs`— alone with the
    package's sound effects. If not given, each song is a package without
    sound effects.

    `inheritance` are pairs (name of a package, index of a song that may be
    playing when it loads). `package_load_done` does not move the samples of
    the song that is playing, so the package's have to fit alongside; **the
    sound effects do not**: if they do not fit, they wait for the next
    `PlayBGM`, which completes the package —see `song_ensure`—. It is the
    decision `workflow/decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md`.

    `ceilings` is each song's headroom, by name —if not given, the versioned
    one: see `read_ceilings`—, and `measuring_headroom` overrides it for all: it
    is what `tools/audio/ceilings.py` builds the ROM it measures peaks in
    with.
    """
    game_dir = game_dir or resources.GAME_DIR
    driver = spc700.assemble(DRIVER, DRIVER_ADDR)
    if ceilings is None:
        ceilings = read_ceilings()
    # Reading the MIDIs is pure and there is one per song: in parallel, like
    # building them.
    parsed_songs = in_parallel(lambda n: read_song(n, game_dir), names)
    root_keys = most_used_zones(parsed_songs)
    keys_of = [song_keys(t, root_keys) for t in parsed_songs]
    # **All** the sound effects go in: which ones fit is decided by the ROM
    # map by map, when it builds its audio package. They are built before
    # the bank because what each package's take is the first thing
    # subtracted.
    built_effects = build_sound_effects(list(effects), game_dir, 1 << 30)
    effect_list = sorted(built_effects.values(), key=lambda e: list(effects).index(
        e.name) if e.name in effects else 0)
    # What the music budgets for each sound effect: the usual one, even if
    # it goes whole. See `se_whole`.
    budgeted = {n: len(e.data) for n, e in built_effects.items()}
    whole_fx, paid = se_whole(), se_paid_by_music()
    for n in built_effects:
        if n in whole_fx and n not in paid:
            budgeted[n] = len(build_sound_effect(n, game_dir, whole={}).data)

    # The keys the SoundFont has; the rest do not play anywhere.
    keys_of = [{k for k in ks if _sample(k, NATIVE) is not None}
               for ks in keys_of]
    if packages is None:
        packages = [(name, [i], []) for i, name in enumerate(names)]
    # What has to fit together: each package with its sound effects; each
    # exit song alone —its `PlayBGM` uploads it, silencing the rest: see
    # `exit_extra` in tools/runtime/audio_package.s—; and each
    # package with the song that may be playing when it loads, without its
    # sound effects.
    # And the same ones with what the sound effects really take, which is
    # what the copies that lower no one allocate with: see `copies`.
    groups, real, songs_of = [], [], {}
    for package in packages:
        name, own, own_fx = package[:3]
        exits = package[3] if len(package) > 3 else ()
        songs_of[name] = list(own)
        own_fx = set(own_fx) & set(built_effects)
        effect_bytes = sum(budgeted[e] for e in own_fx)
        real_effect_bytes = sum(len(built_effects[e].data) for e in own_fx)
        groups.append(Group(str(name), tuple(own), effect_bytes))
        real.append(Group(str(name), tuple(own), real_effect_bytes))
        for t in exits:
            groups.append(Group("%s>%s" % (name, names[t]), (t,), 0))
            real.append(groups[-1])
        # And each separate song with the package's sound effects, which stay
        # when its `PlayBGM` uploads it: see `separate_songs`.
        for t in (package[4] if len(package) > 4 else ()):
            groups.append(Group("%s>%s" % (name, names[t]), (t,), effect_bytes))
            real.append(Group(groups[-1].name, (t,), real_effect_bytes))
    for name, inherited in inheritance:
        groups.append(Group("%s+%s" % (name, names[inherited]),
                            tuple(songs_of[name]) + (inherited,), 0))
        real.append(groups[-1])
    place = effect_places([set(p[2]) for p in packages],
                          [e.name for e in effect_list])
    places = max(place.values()) + 1 if place else 0
    assignment = copies(keys_of, groups, places,
                        min(len(effect_list), se_usual()), real)
    all_keys = {k for a in assignment for k in a.values()}
    free = free_for(len(all_keys), places)
    bank = Bank(all_keys, constraints_for(assignment, real, free))
    bank.free = free
    bank.assignment = assignment
    _whole_effects_fit(bank, packages, inheritance, built_effects, budgeted,
                       names)

    # Each song is independent once the bank is allocated, and building them
    # was half of this function: they go in parallel, and come back in the
    # usual order.
    context = (names, parsed_songs, assignment, bank, ceilings, measuring_headroom)
    songs = in_parallel(lambda i: _build_song(context, i),
                        range(len(names)))
    # And each one's MSU-1 track: see `msu_track`.
    for song in songs:
        song["pista"] = msu_track(song["nombre"], game_dir)
    # The sound effects go after the bank in the same directory, in its
    # `places` entries: their `V_SRCN` is the place each one got after the
    # music's samples. And each one also has its sound effect number, which
    # is what the package lists carry, and its `sample_table` row after the
    # music's: see `effect_places`.
    bank.places = places
    bank.effects = {e.name: (len(bank.voices) + place[e.name], e)
                    for e in effect_list}
    bank.effect_id = {e.name: i for i, e in enumerate(effect_list)}
    return (driver, list(bank.voices) + effect_list, songs, bank)


def _build_song(context, i):
    """One song of `build_all`: what it does in parallel."""
    names, parsed_songs, assignment, bank, ceilings, measuring_headroom = context
    name, parsed, own_map = names[i], parsed_songs[i], assignment[i]
    if parsed is None:
        return {"nombre": name, "stream": bytes([OP_END]),
                "sonidos": [], "escrituras": [],
                "segundos": 0.0, "resumen": {}}
    allocation = []
    headroom = measuring_headroom or ceilings.get(name, sdsp.HEADROOM)
    for_song = bank.for_song(own_map)
    frames = build_events(parsed["notas"], parsed["voces"],
                          parsed["programas"], for_song,
                          parsed["controles"], allocation, headroom)
    reference = writes(frames, parsed["largo"], init_writes())
    stream, sounds = pack(frames, parsed["largo"], init_writes())
    check_format(name, stream, sounds, reference)
    return {"nombre": name, "stream": stream, "sonidos": sounds,
            "escrituras": reference, "aire": headroom,
            "huella": mix_fingerprint(reference, bank),
            "segundos": parsed["largo"] / TICKS_PER_SECOND,
            "resumen": song_summary(parsed, for_song, allocation)}


def song_summary(parsed, bank, allocation=()):
    """What the recipe prints: voices, timbres and how much gets played."""
    voices, programs = parsed["voces"], parsed["programas"]
    return {
        "voices": {c: v for c, v in sorted(voices.items())},
        "sounds": {c: programs.get(c, 0)
                   for c in sorted(voices) if c != midi.DRUM_CHANNEL},
        "bank": ["%s (%.0f Hz, %d B)" % (v.name.strip(), v.rate, len(v.data))
                 for v in bank.voices],
        # How much of the note-time is lost for lack of voices, and how much
        # would be lost unavoidably with eight: see `lost_time`.
        "perdido": lost_time(allocation),
        # And how many of its notes reach the stream. A note whose program
        # is not in the bank **does not play quieter: it does not exist**
        # —the `continue` in `build_events`—, so this is the voice the
        # player does not hear. It is a different number from `lost`,
        # which measures polyphony; until 2026-09-26 that one was
        # `coverage`, a count from the fixed per-channel allocation, and they
        # got mixed up on 2026-09-14: for a while it looked like sharing the
        # bank cost nothing, because `coverage` came out the same with the
        # whole bank or the shared one.
        "notas": notes_that_sound(parsed, bank),
    }


def lost_time(allocation):
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
    total = lost = 0
    intervals = []
    for note, voice, stolen_at, end in allocation:
        length = end - note.start
        total += length
        intervals.append(_Span(note.start, end))
        if voice is None:
            lost += length
        elif stolen_at is not None:
            lost += max(0, end - stolen_at)
    spans = music.note_time(intervals)
    floor = sum(max(0, n - sdsp.VOICES) * n_frames for n, n_frames in spans.items())
    return lost / float(max(1, total)), floor / float(max(1, total))


_Span = collections.namedtuple("_Span", "start end")


def notes_that_sound(parsed, bank):
    """What fraction of the MIDI's notes has its sample in the bank."""
    total = sounding_n = 0
    for note in parsed["notas"]:
        if note.channel not in parsed["voces"]:
            continue
        total += 1
        if note.channel == midi.DRUM_CHANNEL:
            sounding_n += bank.hits.get(note.pitch) is not None
        else:
            program = parsed["programas"].get(note.channel, 0)
            sounding_n += bank.melodic.get(program) is not None
    return sounding_n / max(1, total)


def sound_table(sounds, bank):
    """One row per entry of `Songs.sounds`: the sample —$FF if it did not
    fit—, the pitch, the volume of each side, how many frames it lasts and
    the sound effect number, which is what says which of the ones sharing
    the sample it is: see `effect_places`."""
    rows = []
    effects = getattr(bank, "effects", {}) if bank is not None else {}
    for name, volume, tempo, balance in sounds:
        entry = effects.get(name)
        if entry is None:
            rows.append((0xFF, 0, 0, 0, 0, 0xFF))
            continue
        srcn, effect = entry
        left, right = effect_volume(volume, balance)
        rows.append((srcn, effect_pitch(effect, tempo), left,
                     right, effect_frames(effect, tempo),
                     bank.effect_id[name]))
    return rows


# The silence: a BRR block with the end and loop bits, and eight zero bytes.
# It is where every sample that is not in the ARAM points in the directory.
SILENCE = bytes([0x03]) + bytes(8)
# And how far uploads go: the last 64 bytes of the ARAM are the ones the boot
# ROM covers when it is enabled, and that way the limit fits in sixteen bits.
ARAM_END = 0x10000 - 64


def song_samples(song):
    """Which samples a song uses: the values its stream writes to the
    voices' SRCN registers. It is what the ROM has to have in the ARAM to
    play it, taken from what the song does —its stream, decoded— and not
    from how it was built."""
    return sorted({value for _frame_no, register, value
                   in decode(song["stream"], song["sonidos"])
                   if _is_voice_register(register)
                   and register & 0x0F == sdsp.V_SRCN})


# What uploading to the SPC700 costs, in frames, for the boot count. A
# package's samples go in triplets through the driver's command 3 —see
# `upload_sample` in tools/runtime/audio_package.s—: measured in the ROM
# on 2026-09-26, from 1.33 to 1.42 frames per KB across eighteen packages,
# and a bit more goes here. The driver and the directory go byte by byte
# through the IPL, which measured 1.4. And loading the map, without audio
# and without decompressing, is about 8 frames (measured with map 6 of
# `test-special`, which has no package); 10 go here. What decompressing
# costs depends on the map and goes separately.
FRAMES_PER_KB_PACKAGE = 1.45
FRAMES_PER_KB_IPL = 1.5
MAP_FRAMES = 10
# Where `BOOT_FRAMES` lives, which belongs to the ROM and not here.
FAR_RAM = os.path.join(project.runtime(), "far_ram.s")


def boot_frames_estimate(driver, voices, songs, package, decompress=0.0,
                         directory=None):
    """How long boot takes, erring high: the map, the driver and the
    directory through the IPL, and the samples of the boot map's package
    —(song indices, sound effect sample indices, exit songs), `emit`'s—.
    The exit ones count: they are uploaded if there is room, and with an
    empty ARAM there is. `decompress` is the frames that decompressing the
    boot map's LZ2 blocks takes, which `MAP_FRAMES` does not count:
    see `decompress_frames` in snes_convert.py. `directory` is (music
    samples, sound effect places), `emit`'s: the sound effects go by number,
    with their row after the music's.
    Returns (frames, package bytes)."""
    own, effects = package[:2]
    exits = package[2] if len(package) > 2 else ()
    music_n, places = directory or (len(voices), 0)
    indices = {music_n + e for e in effects}
    for t in list(own) + list(exits):
        if songs[t]["sonidos"]:
            indices |= set(song_samples(songs[t]))
    package_bytes = sum(len(voices[i].data) for i in indices)
    ipl = len(driver) + 4 * max(1, music_n + places) + len(SILENCE)
    return (MAP_FRAMES + decompress
            + ipl * FRAMES_PER_KB_IPL / 1024.0
            + package_bytes * FRAMES_PER_KB_PACKAGE / 1024.0, package_bytes)


def boot_frames(path=FAR_RAM):
    """The ROM's `BOOT_FRAMES`, read from the source."""
    import re
    with open(path) as handle:
        return int(re.search(r"^BOOT_FRAMES\s*=\s*(\d+)", handle.read(),
                             re.M).group(1))


def emit(path, songs, driver, voices, boot=0xFF, title=0xFF,
         sounds=(), packages=(), map_song=(), directory=None,
         effect_place=(), game_over=(0xFF, 0xFFFF)):
    """The .inc the assembler builds along with main.s.

    `songs` are `build_all`'s, in `Songs` order: the bytecode already has
    those indices emitted. `boot` is which one plays from the first
    frame, or $FF if the ROM boots silent and a `PlayBGM` turns it on.

    `voices` are all the cartridge's samples, numbered: the music's followed
    by the sound effects. None is uploaded at boot: they go to the SPC700 in
    **packages**, one per map —`packages`, in map table order, each with its
    songs, its sound effects' samples and its exit songs—, and the directory
    starts with all of them pointing to the silence. See `package_load` in
    tools/runtime/audio_package.s.

    `map_song` is the song each map turns on when entered, in the same
    order, or $FF if entering does not change what is playing. See
    `map_song_mute`.

    `directory` is (music samples, sound effect places): the directory's
    entries are those and not one per voice, because sound effects share
    places —see `effect_places`—; `voices` carries every sound effect
    after the music, one per number, and `effect_place` is each one's
    `V_SRCN`. The sound effect lists in `packages` go by number.
    """
    def block(label, data, as_block=False):
        # No `.block` except on the samples, and `.crossbank` instead: the
        # driver goes byte by byte through the ports —`spc_block` does the
        # bank jump by hand— and the stream is walked by `advance`, which
        # does the same jump, so they can end up split. The samples do carry
        # it: `subir_a_aram` walks them with a 24-bit pointer that does not
        # jump banks, in exchange for being shorter. See `resolve` in
        # tools/assembly/banks.py, which does not let one through with
        # neither of the two.
        out = ([".block %d" % len(data)] if as_block else [".crossbank"]) \
            + ["%s:" % label]
        for i in range(0, len(data), 16):
            out.append("    .byte " + ",".join("$%02X" % b for b in data[i:i + 16]))
        return "\n".join(out)

    labels = ["song_stream_%d" % i for i in range(len(songs))] or \
        ["song_stream_0"]
    streams = [t["stream"] for t in songs] or [bytes([OP_END])]
    table = "\n".join(
        "%s:\n    .byte %s" % (name, ", ".join(prefix + e for e in labels))
        for name, prefix in (("song_lo", "<"), ("song_hi", ">"),
                             ("song_bk", "^")))
    # The DSP prologue, for the MSU-1 path. With a track the stream never
    # runs, and it is the start of the stream that takes the DSP out of the
    # mute the SPC700 boots with, sets its master volume and tells it where
    # the sample directory is. Without this, sound effects fire against a
    # mute DSP and are not heard.
    #
    # KON and KOF are left out on purpose: with a track, the ROM leaves KOF
    # at $FF so the music's voices do not play, and `se_after` clears it
    # only when a sound effect starts. Writing KOF as zero here would turn
    # back on the voices of a song that is not playing.
    #
    # They go in two parallel tables and not in one of pairs because the
    # 65816 walks them with an index: `lda dsp_init_reg, y`.
    init = [(r, v) for r, v in init_writes()
            if r not in (sdsp.KON, sdsp.KOF)]
    table += "\ndsp_init_reg:\n    .byte " + ", ".join(
        "$%02X" % r for r, _ in init) + ", $FF"
    table += "\ndsp_init_val:\n    .byte " + ", ".join(
        "$%02X" % v for _, v in init) + ", $00"
    # And which MSU-1 track each one gets, or $FF: see `msu_track`.
    table += "\nsong_msu:\n    .byte " + ", ".join(
        "$%02X" % (t.get("pista") or 0xFF)
        for t in (songs or [{"nombre": ""}]))
    # And each map's own song. Outside bank 0: it is read once per teleport,
    # with `lda f:map_song, x`.
    per_map = list(map_song) or [0xFF]
    map_song_table = ".block %d\nmap_song:\n      .byte " % len(per_map) \
        + ", ".join("$%02X" % t for t in per_map)
    # And the music's sounds —`pack`'s: six bytes, the pitch, SRCN, ADSR1,
    # ADSR2 and the release GAIN—, those of every song in one table and
    # where each one's start. In a single bank, because `music_frame`
    # reaches them with `lda f:music_sounds, x` and a sixteen-bit X does
    # not cross banks.
    body, bases = bytearray(), []
    for t in songs:
        bases.append(len(body))
        for sound in t["sonidos"]:
            body += bytes(sound)
    if len(body) > 0x8000:
        raise SystemExit("the music's sounds go over one bank: %d B"
                         % len(body))
    map_song_table += ("\n.block %d\nsong_sounds:\n      .word "
                       % (2 * len(bases or [0]))
                       + ", ".join("%d" % b for b in bases or [0]) + "\n"
                       + block("music_sounds", bytes(body) or bytes(6),
                               as_block=True))
    # And the sound effects: seven bytes per entry of `Songs.sounds`.
    # Outside bank 0: `op_sound` reads them with `lda f:sound_table, x`.
    rows = list(sounds) or [(0xFF, 0, 0, 0, 0, 0xFF)]
    se_table = ".block %d\nsound_table:\n" % (7 * len(rows)) + "\n".join(
        "    .byte $%02X, <%d, >%d, %d, %d, <%d, >%d" % (
            srcn, pitch, pitch, left, right, n_frames, n_frames)
        for srcn, pitch, left, right, n_frames, _e in rows)
    # And which sound effect each row is, separately so as not to touch the
    # seven columns `sound_play` and msu_effects.s walk: the row's
    # sample is a place several sound effects share, and `sound_play` asks
    # with this whether the one in the ARAM is its own. And each sound
    # effect's place, which is what the package uses to upload it.
    se_table += "\n.block %d\nsound_effect:\n      .byte " % len(rows) \
        + ", ".join("$%02X" % row[5] for row in rows)
    se_places = list(effect_place) or [0xFF]
    se_table += "\n.block %d\neffect_place:\n     .byte " % len(se_places) \
        + ", ".join("$%02X" % l for l in se_places)

    # The SPC700 directory, with all of them on the silence, and the silence
    # after it. It is the only thing `spc_upload` uploads besides the driver.
    music_n, places = directory or (len(voices), 0)
    n = max(1, music_n + places)
    if n > DIRECTORY_MAX:
        raise SystemExit("the directory has %d entries and SRCN is one "
                         "byte" % n)
    if len(voices) - music_n > 0xFF:
        raise SystemExit("there are %d sound effects and their number is one byte"
                         % (len(voices) - music_n))
    if places > SE_PLACES_MAX:
        raise SystemExit("the sound effects ask for %d directory places and the ROM "
                         "records %d: see FAR_EFFECT_IN" % (places,
                                                            SE_PLACES_MAX))
    silence = SAMPLES_ADDR + 4 * n
    data = silence + len(SILENCE)
    directory_bytes = (silence.to_bytes(2, "little") * 2) * n + SILENCE
    # Each sample, on its own, and its row: the pointer, its length and
    # where it loops back to.
    samples = [block("sample_%d" % i, v.data, as_block=True)
               for i, v in enumerate(voices)] or [block("sample_0", SILENCE)]
    sample_rows = []
    for i, v in enumerate(voices or [None]):
        length = len(v.data) if v is not None else len(SILENCE)
        loop = v.loop_block * brr_samples.BLOCK_BYTES if v is not None else 0
        sample_rows.append("    .byte <(sample_%d), >(sample_%d), ^(sample_%d), "
                           "<%d, >%d, <%d, >%d" % (i, i, i, length, length, loop, loop))
    # Which samples each song uses, and each map's package. Two blocks with
    # an index of offsets in front, and each list terminated with $FF.
    def lists(label, groups):
        body, ofs = bytearray(), []
        for group in groups:
            ofs.append(2 * len(groups) + len(body))
            for part in group:
                body += bytes(part) + b"\xFF"
        data_ = b"".join(o.to_bytes(2, "little") for o in ofs) + bytes(body)
        return block(label, data_ or b"\xFF", as_block=True)
    # Decoding the streams to find out is pure and costly: in parallel.
    song_samples_block = lists("song_samples", [
        [m] for m in in_parallel(lambda i: song_samples(songs[i]),
                                 range(len(songs)))] or [[[]]])
    # Each package, four lists: its songs, its sound effects' samples, its
    # exit songs and its separate songs —see `exit_extra` and
    # `extra_separate` in tools/runtime/audio_package.s—.
    packages = [tuple(p) + ((),) * (4 - len(p)) for p in packages] or \
        [([], [], [], [])]
    packages_block = lists("packages", [[list(t), list(m), list(s),
                                            list(a)]
                                           for t, m, s, a in packages])

    with open(path, "w") as handle:
        handle.write(
            "; Generated by tools/audio/snes_music.py. Do not edit.\n"
            # The next line, with the "no music" below, is data:
            # `tools/audio/ceilings.py` reads it with a regex, and
            # `rom/pruebas/arnes/consola.py`, `test_msu.py` and
            # `test_msu_efectos.py` look for "; Songs: ".
            "; Songs: %s\n\n"
            "; How many songs the cartridge carries and which one plays from boot.\n"
            "; The indices are those of `Songs` in events.py, that is, the ones\n"
            "; the PlayBGM bytecode already has emitted.\n"
            "; $FF in SONG_BOOT means 'the ROM boots silent': the song of the\n"
            "; map it boots in does not exist, so an event has to turn it on.\n"
            "SONG_TOTAL       = %d\n"
            "SONG_BOOT        = $%02X\n"
            "; And the title screen's, which comes from the LDB's `title_music`.\n"
            "; $FF means this ROM has no title screen.\n"
            "SONG_TITLE       = $%02X\n"
            # `rom/src/` and not `tools/runtime/`, here and six lines further
            # down, on purpose: it is text that goes into the `.inc`, and the
            # paths in what is emitted are not changed yet
            # (workflow/decisiones/las-herramientas-se-separan-de-abl.md).
            "; And the Game Over screen's —`gameover_music`— with its package,\n"
            "; which goes after all the others: the song alone. $FF and $FFFF\n"
            "; if this ROM has no such screen. See rom/src/game_over.s.\n"
            "SONG_GAME_OVER   = $%02X\n"
            "PACKAGE_GAME_OVER = $%04X\n"
            "; The master volume the song plays at and the two DSP registers it\n"
            "; goes in. `sdsp.py` emits them, since that is where they come\n"
            "; from: the stream already writes them at start, and a `FadeOutBGM`\n"
            "; writes them again lowering them. Writing them in rom/src/ too\n"
            "; would be two sides that can be wrong in the same way.\n"
            "SONG_VOLUME      = $%02X\n"
            "DSP_MVOL_L       = $%02X\n"
            "DSP_MVOL_R       = $%02X\n"
            "SPC_DRIVER_ADDR  = $%04X\n"
            "SPC_DRIVER_SIZE  = %d\n"
            "SPC_SAMPLES_ADDR = $%04X\n"
            "SPC_SAMPLES_SIZE = %d\n"
            "; Samples go to the SPC700 in packages: see `package_load`.\n"
            "; The directory is at SPC_SAMPLES_ADDR, the silence after it, and\n"
            "; the samples are placed between ARAM_DATA and ARAM_END.\n"
            "; SAMPLES_N is the directory's entries: the music's, and from\n"
            "; SE_FIRST on the SE_PLACES the sound effects share.\n"
            "; Each sound effect has its number —EFFECTS_N in total, which is\n"
            "; what the package lists carry— and its `sample_table` row at\n"
            "; SE_FIRST plus that number. See `lugares_de_efectos`.\n"
            "SAMPLES_N        = %d\n"
            "SE_FIRST         = %d\n"
            "SE_PLACES        = %d\n"
            "EFFECTS_N        = %d\n"
            "ARAM_SILENCE     = $%04X\n"
            "ARAM_DATA        = $%04X\n"
            "ARAM_END         = $%04X\n"
            "PACKAGES_N       = %d\n"
            "; The sound effects: which voice they play on and how many entries\n"
            "; `sound_table` has. See `build_efectos`.\n"
            "SE_VOICE         = %d\n"
            "SE_BIT           = $%02X\n"
            "SE_REG           = $%02X\n"
            "SE2_BIT          = $%02X\n"
            "SE2_REG          = $%02X\n"
            "SOUNDS_N         = %d\n\n"
            "; Where each song's stream starts, split into three tables\n"
            "; because they are read with an index: they go in bank 0 like\n"
            "; everything the CPU walks with `lda tabla, x`.\n"
            '.segment "TABLES"\n%s\n\n'
            '.segment "RODATA"\n%s\n%s\n%s\n%s\n'
            '.block %d\nsample_table:\n%s\n%s\n%s\n%s\n%s\n'
            % (", ".join(t["nombre"] or "no music" for t in songs)
               or "none",
               len(songs), boot, title, game_over[0], game_over[1],
               sdsp.MASTER, sdsp.MVOL_L, sdsp.MVOL_R,
               DRIVER_ADDR, len(driver),
               SAMPLES_ADDR, len(directory_bytes),
               n, music_n, places, len(voices) - music_n,
               silence, data, ARAM_END, len(packages),
               SE_VOICE, 1 << SE_VOICE, SE_VOICE * 16, 1 << SE_VOICE2, SE_VOICE2 * 16,
               len(list(sounds)),
               table, se_table, map_song_table,
               block("spc_driver", driver),
               block("spc_samples", directory_bytes),
               7 * len(sample_rows), "\n".join(sample_rows),
               song_samples_block, packages_block,
               "\n".join(samples),
               "\n".join(block(e, st) for e, st in zip(labels, streams))))
