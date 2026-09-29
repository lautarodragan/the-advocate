"""The cartridge's music, as the converter sees it: which songs each map
asks for, which ones can already be playing when a package loads, the job
it hands to `rm2k-snes-audio`, the boot's frame budget, and the `.msu` with
the quality backdrops and sound effects.

The music itself —from MIDI to the SPC700— is `rm2k-snes-audio`'s.
"""

import json
import os
import shutil
import subprocess
import sys

from rpgmaker import lcf
from port import msu_data
from common import settings
from common import project
from common import environment
from port.asm import block


AUDIO = "rm2k-snes-audio"

AUDIO_MISSING = """`rm2k-snes-audio` is missing, the one that compiles the music.

It is a Rust binary that lives in `tools/rm2k-snes/rm2k-snes-audio/` and is installed
as a system tool:

    just -f tools/justfile install rm2k-snes-audio"""


def compile_music(job, directory):
    """Hands the music to `rm2k-snes-audio`, which writes `musicdata.inc`,
    `musica.json` and `audio.json` into `directory`, and prints what each
    song and the bank came out as. Returns `audio.json`.

    Whatever it answers no to —the samples do not fit even at the minimum, a
    song's stream would not write what it has to— stops the conversion with
    its message."""
    binary = shutil.which(AUDIO)
    if binary is None:
        raise SystemExit(AUDIO_MISSING)
    path = os.path.join(directory, "audio-job.json")
    with open(path, "w") as handle:
        json.dump(job, handle, indent=1)
    # What this printed goes before what the binary prints.
    sys.stdout.flush()
    done = subprocess.run(
        [binary, "compile", "--job", path, "--out", directory,
         "--project", project.directory()]
        + environment.as_flags("game_dir", "rtp_dir", "soundfont"))
    if done.returncode:
        raise SystemExit("%s could not compile the music (exit %d): see "
                         "above" % (AUDIO, done.returncode))
    with open(os.path.join(directory, "audio.json")) as handle:
        return json.load(handle)


def separate_songs():
    """{map id: names} of the separate songs: they do not go with the other
    songs of their map's package, their `PlayBGM` uploads them alone with the
    package's sound effects —see `extra_separate` in
    tools/runtime/audio_package.s—, and they are not inherited by the maps
    you exit to —see `inherited_songs`—. From `[music] apart_themes`."""
    return {m["map"]: set(m["themes"])
            for m in settings.value("music", "apart_themes", kind=list)}


def boot_frames(path=None):
    """The ROM's `BOOT_FRAMES`, read from the source: it belongs to the ROM
    and not here."""
    import re
    path = path or os.path.join(project.runtime(), "far_ram.s")
    with open(path) as handle:
        return int(re.search(r"^BOOT_FRAMES\s*=\s*(\d+)", handle.read(),
                             re.M).group(1))


def write_msu(path, music, backdrops, audio, sounds):
    """Writes the `.msu` to `path` and appends to `music` —the
    `musicdata.inc`— what the ROM needs to read it: the signature, where each
    backdrop is and, per package, where each sound effect is and at which
    pitch each sound plays.

    The backdrops go first —`backdrops` are the `(tiles, colors)` of **all the
    game's**, by number, each in its fixed place: see `msu_data.backdrop_offset`—
    and behind them the quality sound effects of each package, in the order
    of the package table and each package with its own in order of place in
    the directory —their SRCN—: it is the order `upload_placed` uploads them
    in, so the ROM reads them in one go, with a single seek per package. A
    sound effect that is in two packages goes twice even if at the same rate:
    a seek costs Mednafen one or two frames, and the file has no cap.

    Which version of each sound effect goes in each package, and at which
    pitch it plays there, is the music's: `audio` is what
    `rm2k-snes-audio` wrote, see its `msu`. This puts them in the file.
    """
    quality = audio["msu"]
    versions = [bytes.fromhex(v["brr"]) for v in quality["versions"]]
    entries = [part for pair in backdrops for part in pair]
    # Which entry each sound effect of each package is, in SRCN order: two of
    # the same package never share a place.
    first = []
    for package in quality["packages"]:
        first.append(len(entries))
        entries += [versions[v] for v in package["versions"]]
    blob, offset = msu_data.build(entries, backdrops=len(backdrops))
    signature = blob[:msu_data.SIGNATURE_SIZE]
    with open(path + ".nuevo", "wb") as handle:
        handle.write(blob)
    os.replace(path + ".nuevo", path)
    print("  .msu: %d backdrop(s) and %d sound effect(s) in %d B, signature %s -> %s"
          % (len(backdrops), len(entries) - 2 * len(backdrops), len(blob),
             signature.hex(), path))

    # Per package, one row per sound effect of its list —in the order the ROM
    # walks it—: where it is in the `.msu`, how long it is and where it loops
    # back, which is always to the start because they go whole.
    rows, from_rows = bytearray(), bytearray()
    heights, from_heights, already_done = bytearray(), bytearray(), {}
    for package, start in zip(quality["packages"], first):
        from_rows += (len(rows)).to_bytes(2, "little")
        for j in package["rows"]:
            data = versions[package["versions"][j]]
            rows += (offset[start + j].to_bytes(4, "little")
                     + len(data).to_bytes(2, "little") + bytes(2))
        # And the pitch of each sound of `sound_table` with this package's
        # version: with that the ROM does no arithmetic, not even in the
        # interrupt. **Only the sounds whose sound effect is from here**, as
        # (index, pitch) pairs sorted by index and closed with $FFFF, which
        # `msu_pitch` walks: until 2026-09-27 it was one row per package with
        # all the sounds, almost all zeros, and with the whole world chapter
        # it went over a bank. Two packages with the same list share it.
        values = bytearray()
        for k, height in package["pitches"]:
            values += k.to_bytes(2, "little") + height.to_bytes(2, "little")
        values += b"\xFF\xFF"
        values = bytes(values)
        if values not in already_done:
            already_done[values] = len(heights)
            heights += values
        from_heights += already_done[values].to_bytes(2, "little")
    for table in (rows, heights):
        if len(table) > 0x8000:
            raise SystemExit("the .msu sound effect tables go over a "
                             "bank: %d B" % len(table))
    positions = [(offset[2 * k], offset[2 * k + 1]) for k in range(len(backdrops))]
    backdrop_pos = b"".join(a.to_bytes(4, "little") + b.to_bytes(4, "little")
                            for a, b in positions) or bytes(8)
    with open(music, "a") as handle:
        handle.write(
            "\n; The `.msu`: see `escribir_msu` in tools/port/snes_convert.py.\n"
            "; How many entries of the .msu are backdrops —two per backdrop,\n"
            "; the first ones— and how many are sound effects, behind: for\n"
            "; the tests.\n"
            "MSU_BACKDROPS_N = %d\n"
            "MSU_EFFECTS_N = %d\n"
            '.segment "RODATA"\n%s\n'
            % (len(backdrops), len(entries) - 2 * len(backdrops),
               "\n".join(block(label, data or bytes(2)) for label, data
                         in (("msu_data_signature", signature),
                             ("msu_backdrop_pos", backdrop_pos),
                             ("se_msu_pkg", from_rows),
                             ("se_msu_rows", rows),
                             ("se_msu_pitch_pkg", from_heights),
                             ("se_msu_pitch", heights)))))
    # And the same, readable, next to it: which sound each row of
    # `sound_table` is and at which rate each sound effect of each package
    # goes in the `.msu`. The ROM doesn't read it; it is for the tools that
    # touch a sound effect from outside and to look at what the allocation
    # decided.
    rates = quality["rates"]
    with open(os.path.join(os.path.dirname(music), "efectos.json"),
              "w") as handle:
        json.dump({"sonidos": [list(s) for s in sounds],
                   "srcn": {e["name"]: e["srcn"] for e in audio["effects"]},
                   "tasas": rates}, handle, indent=1)
    for package in quality["packages"]:
        theirs = rates.get(package["name"], {})
        if theirs:
            print("  quality sound effects of package %s: %s"
                  % (package["name"], ", ".join(
                      "%d Hz: %d" % (t, sum(1 for v in theirs.values()
                                            if v == t))
                      for t in sorted(set(theirs.values()), reverse=True))))


def inherited_songs(songs, map_song, initial, title, package_names,
                    in_package=None, separate_ones=None, not_given=()):
    """[(package name, index of a song that can be already playing when it
    loads)], for the job of `rm2k-snes-audio`.

    Almost no map of the game brings its own song: a page starts it, and
    until then the previous map's keeps going, and `package_load_done`
    doesn't move its samples. So the package of a map without its own song
    has to fit next to whatever can be already playing.

    The teleports of the compiled pages are followed —`destinos` of
    `Songs.per_map`— without looking at conditions, with a rule that is what
    makes the count realistic and not "any song to any map" (4 is the game's
    router): **a map with `PlayBGM` leaves with one of its own**, because the
    page that jumps is almost always the one that started the song before. A
    map with its own song silences what plays before loading its own
    —`map_song_mute`—, so it inherits nothing; and the boot map is reached
    with the title's playing. It is what step 6 of
    `workflow/tasks/todo/la-calidad-de-la-musica.md` measured with a separate
    script.

    `in_package` are the songs each map's package uploads on entering
    —without the exit ones, see `Songs.exit_songs`—: a song that arrives
    playing and isn't there has to fit next to it. Without it, the ones its
    pages start. What leaves a map is still any of the ones they start, exit
    ones included: they are precisely the ones that leave with it.

    **Except in a map whose `PlayBGM`s are all exit ones**: there the rule
    above doesn't hold, because each one goes stuck to its jump and the map's
    other jumps carry none. Each jump carries what `Songs.jump` says: the
    exit song that precedes it, or whatever came into the map. It is the
    game's 41 and 40: `Kfmus5` comes into 41 from the page of 37 and goes on
    through 40, 42, 43, 44 and 45, while `golden_axe-turtlevillage2` and
    `tsmedit` play only to leave. From 2026-09-27; until then those maps
    inherited only their exit songs. The boot one keeps the rule above: see
    `carries`.

    `separate_ones` are the separate songs of each package —see
    `separate_songs()`—: they don't leave the map, so they don't
    count in what goes out.

    `not_given` are the jumps of compiled pages that can't happen, as
    [map, destination] pairs: a jump that never happens makes it reserve room
    for a song that never arrives, at the expense of the ones that do. The
    game declares them, in `[music] jumps_that_never_happen` of the project
    file.
    """
    n = len(map_song)
    palettes_needed = [songs.per_map.get(i, {}) for i in range(n)]
    separate_ones = separate_ones or [()] * n
    index = {name: i for i, name in enumerate(package_names[:n])}
    not_given = {(index[str(a)], index[str(b)])
                 for a, b in not_given
                 if str(a) in index and str(b) in index}
    jumps = getattr(songs, "jumps", {})
    fits = [set() for _ in range(n)]
    if title != 0xFF:
        fits[initial].add(title)

    def carries(i, dest):
        if map_song[i] != 0xFF:
            return {map_song[i]}
        theirs = set(palettes_needed[i].get("temas", ())) - set(separate_ones[i])
        # Not the boot one: it is the router, which jumps to mid-game
        # according to variables, and without looking at conditions whatever
        # comes in there would go out anywhere.
        if theirs and theirs <= set(songs.exit_songs(i)) and i != initial:
            # A destination no noted jump names —that of a page that didn't
            # compile whole— carries what came in.
            with_it = jumps.get(i, {}).get(dest, {None})
            return ({t for t in with_it if t is not None}
                    | (fits[i] if None in with_it else set()))
        return theirs or fits[i]

    change = True
    while change:
        change = False
        for i in range(n):
            for dest in palettes_needed[i].get("destinos", ()):
                if (i, dest) in not_given:
                    continue
                leaves = carries(i, dest)
                if (dest != i and map_song[dest] == 0xFF
                        and not leaves <= fits[dest]):
                    fits[dest] |= leaves
                    change = True
    if in_package is None:
        in_package = [palettes_needed[i].get("temas", ()) for i in range(n)]
    return [(package_names[i], t) for i in range(n)
            for t in sorted(fits[i])
            if t not in in_package[i] and t != map_song[i]]


def songs_of_maps(map_ids, game_dir):
    """The name of the song each map gets from the tree, reading it once.

    "" means that entering the map **does not change** what is playing:
    either the map has no song —the root of the tree—, or it is
    `music_type` 1, "an event decides". It is the early `return` of
    `Game_Map::PlayBgm` in easyrpg. An "(OFF)" is a song: it silences, just
    like a `PlayBGM` of "(OFF)".
    """
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    names = []
    for map_id in map_ids:
        music = tree.map_music(map_id)
        names.append(music["name"] if music else "")
    return names


def rom_songs(map_id, songs, game_dir, title=None, map_ids=(),
              game_over=None):
    """Which songs the cartridge asks for, which one plays at boot and which
    one each map starts on entering.

    **All** are asked for: the ones the compiled `PlayBGM`s name, plus that of
    the map where the ROM boots, which is the one that plays without anything
    happening. **And all of them fit**: the index is given by the list and
    costs no ARAM. What the ARAM limits is the samples, and that is allocated
    by `rm2k-snes-audio` per package: at the rate the worst package of
    each one gives, but all of them.

    The indices are those of `Songs` and aren't touched: the bytecode already
    carries them emitted. That is why the map's is added **at the end**,
    which is the only thing that doesn't renumber the others. Going last
    costs nothing: since the per-package budget no song loses samples for its
    place in the list.

    And the own song of each map in `map_ids` —in the order of the map
    table—, which is easyrpg's `Game_Map::PlayBgm`: what plays when entering
    through a teleport. They go behind all, for the same reason, and as each
    one's index or $FF, which is "entering doesn't change the music".
    """
    own = songs_of_maps([map_id], game_dir)[0]
    if own:
        songs.index(own)            # adds it at the end if it wasn't there
    # The title screen's goes after, for the same reason: adding at the end is
    # the only thing that doesn't renumber the ones the bytecode already
    # names. It comes from the LDB —`title_music`, which in ABL is
    # Fantasia_Of_The_Wind— and not from the command line: it is a piece of
    # the game's data, not a choice of ours.
    if title:
        songs.index(title)
    # And the Game Over screen's, for the same reason: `gameover_music`,
    # which in ABL is `GameOver3` and comes from the RTP. See
    # `PACKAGE_GAME_OVER`.
    if game_over:
        songs.index(game_over)
    each_map = []
    for name in songs_of_maps(map_ids, game_dir):
        index = songs.index(name) if name else 0xFF
        # $FF is "doesn't change": a song with that number couldn't be
        # started. A `PlayBGM`, which carries the index in one byte, wouldn't
        # start it either.
        assert index <= 0xFF, "song %r doesn't fit in a byte" % name
        each_map.append(index)
    names = list(songs.names)
    return (names, (names.index(own) if own else 0xFF),
            (names.index(title) if title else 0xFF), each_map,
            (names.index(game_over) if game_over else 0xFF))
