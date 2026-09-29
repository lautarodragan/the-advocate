#!/usr/bin/env python3
"""The game's cartridges, the ones its project file declares in
`[cartridges]`: `release`, the ROM that is played and that runs almost the
whole suite, and the others, with what does not fit in it.
No test builds anything: they run against what this leaves —see `tanda.rom`—.

    rm2k-snes-cartridges            builds whatever is needed
    rm2k-snes-cartridges release    only that one, with its MSU-1 tracks:
                                    `just build`
    rm2k-snes-cartridges --list     which case goes in which cartridge

A new case is a file in `rom/pruebas/casos/` and nothing else: it goes into
`release` on its own and is run with `tanda.partida("<name>")`. It starts
with a `Teleport` to the map where it has to run: the starting one
—`start_map`— is map 4, the game's router, whose cutscene waits for nobody.

A new cartridge is one more table in `[cartridges]`, and nothing here.
"""

import argparse
import concurrent.futures
import glob
import hashlib
import json
import os
import subprocess
import sys

# `realpath` and not `abspath`: `just install` installs this script on
# the PATH as a symlink, and what matters is where the real file is.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from audio import brr_samples                          # noqa: E402
from common import environment                              # noqa: E402
from common import settings                              # noqa: E402
from common import project                              # noqa: E402
from assembly import assemble                        # noqa: E402
from port import tiles_bin                              # noqa: E402
from port import compress                              # noqa: E402

# `--project` is read before anything else: this module reads the project
# file when imported, and `main`'s `parse_args` comes too late.
if __name__ == "__main__":
    project.from_command_line()

ROOT = project.root()
CASES = project.cases()
RUNTIME = project.runtime()

# **What each cartridge carries belongs to the game, and is in its project
# file** —`project.project_file()`, with the reasons for each value as
# comments—: which maps go in, which are excluded, which cartridges exist and
# which cases each one carries. Until 2026-09-29 it was written here. What
# remains in this file is the mechanism that reads it and builds.
#
# **The maps are values in the file and not converter flags**, on purpose:
# the converter still receives the whole list in `--maps`. This is the only
# one that calls it; `test_horneados` and `test_parches` need the list
# without running it; and since the stamp carries the flags and not
# `rom/data/`, a tree that changes which maps go in makes the cartridge stale
# only if the list travels expanded.
MAPS_BELOW = settings.value("maps", "below", kind=int)
EXCLUDED_MAPS = frozenset(settings.value("maps", "excluded", kind=list))
ADDED_MAPS = tuple(settings.value("maps", "added", kind=list))


def debug_map_id():
    """The debug map's id: the only new map in
    `rom/parches/manual/nuevos/` —see `fork.new_maps`—. It comes from there and
    not from the project file so as not to write the number twice."""
    from rpgmaker import fork
    new_maps = sorted(fork.new_maps())
    if len(new_maps) != 1:
        sys.exit("the debug map is the only new map in %s, and there are %d: %s"
                 % (fork.new_maps_folder(), len(new_maps), new_maps))
    return new_maps[0]


# The debug map, which the game does not have, goes after the added ones.
WITH_DEBUG_MAP = settings.value("debug", "debug_map", kind=bool)
DEBUG_MAP = debug_map_id()
if WITH_DEBUG_MAP:
    ADDED_MAPS += (DEBUG_MAP,)

# The enemies' HP in battle: passes `--enemy-hp` to the converter in
# every cartridge.
WITH_ENEMY_HP = settings.value("debug", "enemy_hp", kind=bool)
_FOR_ALL = ["--enemy-hp"] if WITH_ENEMY_HP else []


def rule_maps(below=MAPS_BELOW, excluded=EXCLUDED_MAPS,
              added=ADDED_MAPS):
    """The game's maps in the order they go to `--maps`: the ones from the
    rule in ascending order, and then the added ones. **The order is that of
    the ROM's table**, so changing it moves the table: see `map_order`
    in snes_convert.py.

    The tree is the one in the `rom/data/` dump, which is what the converter
    reads: that is why the path falls inside `rom/data/` and not inside the
    game —see `lcf.dump_dir`—."""
    from rpgmaker import lcf
    tree = lcf.TreeMap(os.path.join(project.data(), "RPG_RT.lmt"))
    from_rule = [m for m in range(1, below)
                 if tree.map_types.get(m) == 1 and m not in excluded]
    return tuple(from_rule + [m for m in added if m not in from_rule])


GAME_MAPS = rule_maps()

# And the ones that only exist for the suite. `patches.check` reads them
# from here so as not to require a versioned patch for them.
TEST_MAPS = tuple(settings.value("maps", "test", kind=list))

MAPS = GAME_MAPS + TEST_MAPS

# The cartridge that is played: the one that carries the ROM with the game's
# name, its MSU-1 tracks, and all the cases. The file has to declare it.
RELEASE = "release"

# What its files are called: `<name>.sfc`, and next to it the `.msu` and the
# `<name>-N.pcm` tracks. The other cartridges' files are called `prueba`.
ROM_NAME = settings.value("rom", "name", kind=str)


def _cartridge(name):
    """(the converter flags, the cases or None if it is all of them) of a
    cartridge in the file. The flags come out in the usual order —the party,
    the starting map, the maps, the graphics, the rest—, because they go into
    the stamp as is."""
    def setting(k, kind):
        return settings.value("cartridges", name, k, kind=kind)
    start_map = setting("start_map", int)
    party = setting("party", list)
    maps = setting("maps", (str, list))
    if isinstance(maps, str):
        if maps != "game":
            sys.exit("%s: maps of %s is a list or \"game\", and it is %r"
                     % (project.project_file(), name, maps))
        maps = MAPS
    cases = setting("cases", (str, list))
    if isinstance(cases, str):
        if cases != "all":
            sys.exit("%s: cases of %s is a list or \"all\", and it is %r"
                     % (project.project_file(), name, cases))
        cases = None
    flags = ((["--party"] + [str(a) for a in party] if party else [])
             + ["--map-id", str(start_map), "--maps"]
             + [str(m) for m in maps if m != start_map]
             + [f for charset, index in setting("test_graphics", list)
                for f in ("--test-graphic", charset, index)]
             + setting("flags", list) + _FOR_ALL)
    return flags, cases


CARTRIDGES = {name: _cartridge(name)
              for name in settings.value("cartridges", kind=dict)}
if RELEASE not in CARTRIDGES or CARTRIDGES[RELEASE][1] is not None:
    sys.exit("%s: missing [cartridges.%s], with cases = \"all\""
             % (project.project_file(), RELEASE))

# The cases `release` does not carry, because there they would change the
# others' images.
EXCLUDED_CASES = set(settings.value("cartridges", RELEASE, "excluded_cases",
                                    kind=list))

# Page 0 is the real game's, except with the debug map, whose entry is what
# goes there: see `[cases]` in the file.
REAL_GAME = settings.value("cases", "real_game", kind=str)
DEBUG_MAP_ENTRY = settings.value("cases", "debug_map_entry",
                                 kind=str)


def first_case(with_debug_map=WITH_DEBUG_MAP):
    """The case on page 0: what "Begin the Story" runs."""
    return (DEBUG_MAP_ENTRY if with_debug_map
            else REAL_GAME)


def excluded_cases(with_debug_map=WITH_DEBUG_MAP):
    """The cases `release` does not carry. Without the map, not its entry
    either: its `Teleport` leads to a map that is not there, and the converter
    balks."""
    return EXCLUDED_CASES | (set() if with_debug_map
                             else {DEBUG_MAP_ENTRY})


FIRST_CASE = first_case()


def fingerprint():
    """What a cartridge depends on, besides its flags and its cases.

    Whatever changes the ROM and is not here leaves it silently stale: that
    is why the binaries and `rom/parches/manual/` go in, since they change it
    without touching any source.
    `rom/data/` does not, since `just datos` regenerates it. The content is
    looked at and not the date, which `git checkout` changes.
    """
    h = hashlib.sha256()
    for path in fingerprint_files():
        with open(path, "rb") as handle:
            h.update(handle.read())
    # And each song's volume ceiling, which changes the streams: by its values
    # and not by the file, because `just techos` rewrites it with what it
    # measured —the peak, the mix fingerprint— after building, and that does
    # not change the ROM.
    from audio import snes_music
    h.update(repr(sorted(snes_music.read_ceilings().items())).encode())
    return h.hexdigest()[:16]


def fingerprint_files(runtime=RUNTIME):
    """The files `fingerprint` reads, in order. `runtime` is a parameter only so
    that a test can pass it a tree built by hand."""
    # All of `tools/runtime/`, and not only what `main.s` includes today: a file
    # that is added and included in the same change has to make the cartridge
    # stale.
    parts = (sorted(r for r in glob.glob(os.path.join(runtime, "**"),
                                         recursive=True) if os.path.isfile(r))
             + assemble.binaries()
             + [tiles_bin.binary(), brr_samples.binary(),
                compress.binary()])
    # Except the tools' tests, which build nothing: with them inside, editing
    # a test made every cartridge stale.
    tests_dir = os.path.join(project.tools(), "tests", "")
    parts += sorted(r for r in glob.glob(os.path.join(project.tools(),
                                                      "*", "*.py"))
                    if not r.startswith(tests_dir))
    parts += sorted(glob.glob(os.path.join(project.manual_patches(), "*",
                                           "*")))
    # And the project file, whole: the converter and the music read it, and
    # not only what reaches the stamp's flags.
    parts.append(project.project_file())
    return parts


def all_cases():
    return sorted(os.path.splitext(os.path.basename(r))[0]
                  for r in glob.glob(os.path.join(CASES, "*.json")))


def cases_of(name, with_debug_map=WITH_DEBUG_MAP):
    """The cartridge's cases, in the order of its pages. `with_debug_map`
    is a parameter only so that a test can look at the clean delivery without
    building it."""
    cases = CARTRIDGES[name][1]
    if cases is None:
        first = first_case(with_debug_map)
        return [first] + [n for n in all_cases()
                          if n not in excluded_cases(with_debug_map) and n != first]
    return list(cases)


def without_title(name):
    """Whether the cartridge starts without a title screen, straight on the
    map."""
    return "--no-title" in CARTRIDGES[name][0]


def where_is(case):
    """The cartridges that carry the case: first the one that carries all of
    them, then the rest by name.

    **It does not come from the order of `CARTRIDGES`**, on purpose: a case
    that is in two —`parado-tapado`— runs in the first, and with the
    dictionary in another order it ran in the small one and moved its golden
    without anyone touching the case.
    """
    return sorted((n for n in CARTRIDGES if case in cases_of(n)),
                  key=lambda n: (CARTRIDGES[n][1] is not None, n))


def _contents(cases):
    contents = []
    for case in cases:
        with open(os.path.join(CASES, case + ".json"), encoding="utf-8") as a:
            contents.append((case, a.read()))
    return contents


def stamp(name, inputs=None):
    """What the cartridge's stamp has to say for it to be up to date."""
    flags, _cases = CARTRIDGES[name]
    return "%s\n%r" % (inputs or fingerprint(),
                       (flags, _contents(cases_of(name))))


def directory(name):
    """What the tests write does not go here but to `rom/pruebas/snapshots/`."""
    if name == RELEASE:
        return os.path.join(project.build(), RELEASE)
    return os.path.join(environment.test_cartridges(),
                        name.replace("test-", "", 1))


def rom_of(name):
    # The MSU-1 looks for its tracks by the `.sfc`'s name.
    return os.path.join(directory(name),
                        ROM_NAME + ".sfc" if name == RELEASE
                        else "prueba.sfc")


def msu_of(name):
    """The cartridge's `.msu`: the converter writes it, with the battle
    backgrounds the MSU-1 serves to the ROM —see tools/port/msu_data.py—,
    and it is also what turns on the MSU-1 for the tracks. Next to the `.sfc`
    and with its name, which is where the emulator and the FX Pak look for
    it."""
    return os.path.splitext(rom_of(name))[0] + ".msu"


def _file(name, what):
    return os.path.join(directory(name), what)


def stale(name, inputs=None):
    """Why the cartridge is no good, or None if it is up to date."""
    if name not in CARTRIDGES:
        return "does not exist"
    try:
        with open(_file(name, "sello.txt")) as handle:
            stamped = handle.read()
    except OSError:
        return "is not built"
    if stamped != stamp(name, inputs):
        return "was built with other sources, other flags or other cases"
    # The converter writes it along with the ROM and it does not go into the
    # stamp: without it the cartridge would work, but the MSU-1 test would
    # have nothing to read.
    if not os.path.isfile(msu_of(name)):
        return "does not have its .msu"
    return None


def manifest(name):
    """(the cases, whether each one starts with a `Teleport`), per page."""
    cases = cases_of(name)
    return cases, [_teleports(text) for _n, text in _contents(cases)]


def _teleports(text):
    """Whether the case starts with a `Teleport`: the harness waits for the
    arrival, and looking at whether the ROM is fading is not enough, because
    there are maps that fade on their own when entered."""
    commands = json.loads(text).get("event_commands") or [{}]
    return commands[0].get("code") == "Teleport"


def build(name, inputs):
    """Converts and assembles the cartridge, if it is not up to date. Says
    whether it built it."""
    if not stale(name, inputs):
        return False
    convert(name, directory(name), rom_of(name))
    with open(_file(name, "sello.txt"), "w") as handle:
        handle.write(stamp(name, inputs))
    return True


def convert(name, dest, sfc, extra=()):
    """Converts and assembles the cartridge in `dest`, without a stamp and
    even if it is up to date. `extra` are extra flags for the converter:
    that is how `tools/audio/ceilings.py` builds a copy of `release` with
    another volume, without touching the real one."""
    flags, _cases = CARTRIDGES[name]
    os.makedirs(dest, exist_ok=True)
    log = os.path.join(dest, "conversor.log")
    # The cases go at the end: after a `--case`, any cartridge flag would
    # belong to that case, and the converter rejects it.
    case_flags = []
    for k, case in enumerate(cases_of(name)):
        case_flags += (["--case"] if k else []) + [
            "--test-commands",
            os.path.relpath(os.path.join(CASES, case + ".json"), ROOT)]
    # With `--project`, because it runs standing in the repo root —see
    # `assemble.ROOT`— and from there it would not find the file by
    # searching.
    command = ([sys.executable, os.path.join(project.tools(), "port",
                                             "snes_convert.py"),
                "--project", project.directory(),
                *environment.as_flags(*TO_CONVERTER),
                "-o", os.path.join(dest, "mapdata.inc"),
                "--msu", os.path.splitext(sfc)[0] + ".msu"]
               + flags + list(extra) + case_flags)
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    with open(log, "w") as handle:
        handle.write(result.stdout + result.stderr)
    if result.returncode:
        sys.stderr.write(result.stdout[-3000:] + result.stderr)
        sys.exit("%s: the converter failed; everything is in %s" % (name, log))
    assemble.assemble(os.path.join(RUNTIME, "main.s"),
                      dest, sfc, sfc + ".sym")


# What the converter needs from the machine, since it runs in another
# process and receives it by flags; and what this one adds: where the test
# cartridges go, and the replacements for the MSU-1 tracks.
TO_CONVERTER = ("game_dir", "rtp_dir", "soundfont", "cache")
FROM_ENVIRONMENT = TO_CONVERTER + ("test_cartridges", "replacements")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    project.add_argument(parser)
    environment.add_arguments(parser, *FROM_ENVIRONMENT)
    parser.add_argument("--list", action="store_true",
                        help="which case goes in which cartridge, without building anything")
    parser.add_argument("names", nargs="*", metavar="CARTRIDGE",
                        help="only these; without names, all of them. It is what "
                             "`just build release` uses")
    args = parser.parse_args()
    environment.from_arguments(args, *FROM_ENVIRONMENT)
    for name in args.names:
        if name not in CARTRIDGES:
            sys.exit("there is no cartridge %r: the ones there are %s"
                     % (name, ", ".join(CARTRIDGES)))
    if args.list:
        for name in CARTRIDGES:
            cases = cases_of(name)
            print("%s (%d): %s" % (name, len(cases), " ".join(cases)))
        return
    inputs = fingerprint()
    names = args.names or list(CARTRIDGES)
    # The cartridges and the tracks are built at the same time, in threads:
    # each one writes in its own directory, and the heavy work runs in
    # subprocesses —the converter, `ca65`, fluidsynth—. What they share is the
    # disk cache, which writes aside and renames. What is printed stays in the
    # usual order.
    #
    # The tracks, **after `release`** and not alongside it: they are its
    # songs', which the converter leaves in its `musica.json`. Meanwhile the
    # other cartridges get built.
    with concurrent.futures.ThreadPoolExecutor(len(names) + 1) as pool:
        built = {name: pool.submit(build, name, inputs)
                 for name in names}
        made = (pool.submit(msu_tracks, built[RELEASE])
                if RELEASE in names else None)
        for name in names:
            print("%s: %s" % (name, "built" if built[name].result()
                              else "up to date"))
            if name == RELEASE:
                print(made.result())


def msu_tracks(built=None):
    """The MSU-1 tracks next to the ROM that is played: `release` always
    carries them, so there is no other way to have the ROM with tracks.

    They go outside the stamp and are checked even if the ROM is up to date:
    which ones they are is said by the cartridge —its `musica.json`—, but how
    each one sounds depends on the MIDI, the soundfont and the synthesizer,
    and `msu.build` already knows which ones are there —see
    `track_key`—. Having them next to it does not change the suite:
    the harness hides the tracks from the core, see `retro.Console`.
    Returns the line that reports it, which `main` prints in its place.
    """
    if built is not None:
        built.result()         # the `musica.json` that says which ones
    from audio import msu       # fluidsynth and ffmpeg, only for `release`
    made, already = msu.build(rom_of(RELEASE), verbose=False)
    return ("%s: MSU-1 tracks, %d made and %d that were already there"
            % (RELEASE, made, already))


if __name__ == "__main__":
    main()
