"""What belongs to the machine and not to the project: where the original
game is, the RTP, the SoundFont, the replacements for the MSU-1 tracks, the
cache and where builds are delivered.

**It arrives by flags, not by environment variables.** Until 2026-09-29 the
tools read `ABL_GAME_DIR` and friends, with this machine's values as
defaults: they knew what the game was called and where it lived. Now each
executable receives what it needs —`--game-dir`, `--rtp-dir`,
`--soundfont`…—, sets it here with `from_arguments`, and the rest of the
tools read it from here. Which variable points to what, and the machine's
values, belong to the caller: the game's `justfile`.

**A value nobody set is an error, not a default**, except the ones that
hang off the project —the cache and the test cartridges, inside its
`build`—: a machine default would be one machine's.

It is a single place that gets configured, and not a parameter in every
function, on purpose: `resources.GAME_DIR` and `resources.RTP_DIR` are
read inside some forty functions of the converter, and passing them as
parameters touched all those signatures. Those names still exist, but they
are resolved here when read
—see each module's `__getattr__`—, so they fail clearly if read without
being set.
"""

import os

from common import project


class MissingEnvironment(SystemExit):
    """A machine value nobody passed. It is a `SystemExit` for the same
    reason as `project.NoProject`: what fixes it is how it was run, not
    the code."""


# What can be set: the name, which is also the flag's `dest`, and the flag
# with its help.
FLAGS = {
    "game_dir": ("--game-dir", "the original RM2k project, where the PNGs, "
                               "the MIDIs and the .lmu files come from"),
    "rtp_dir": ("--rtp-dir", "the RTP the game was built with: what the "
                             "game does not ship is looked up there"),
    "soundfont": ("--soundfont", "the bank the SPC700 samples and the "
                                 "MSU-1 tracks come from"),
    "replacements": ("--replacements", "where to look for a <song>.mp3 "
                                       "—or .ogg, .flac, .wav— that "
                                       "replaces that song's MIDI in the "
                                       "MSU-1 tracks"),
    "cache": ("--cache", "the converter's disk cache. Without this, "
                         "cache/ inside the project's build"),
    "test_cartridges": ("--test-cartridges", "where the test cartridges are "
                                             "built. Without this, tests/ "
                                             "inside the project's build"),
    "shared": ("--shared", "the folder where what gets built is "
                           "delivered"),
}

_values = {}


def configure(**values):
    """Sets the values that are not None. A name that is not in `FLAGS` is a
    programming error, not the caller's."""
    for name, value in values.items():
        if name not in FLAGS:
            raise KeyError(name)
        if value is not None:
            # Absolute: the converter runs from a different directory than
            # the one that called it.
            _values[name] = os.path.abspath(value)


def add_arguments(parser, *names):
    """Adds the flags of `names` to an executable's parser."""
    for name in names:
        flag, help_text = FLAGS[name]
        parser.add_argument(flag, dest=name, metavar="PATH", help=help_text)


def from_arguments(args, *names):
    """Sets what came on the command line."""
    configure(**{name: getattr(args, name) for name in names})


def as_flags(*names):
    """The set values of `names`, as flags: to pass them on to another
    tool that runs in a separate process."""
    flags = []
    for name in names:
        if name in _values:
            flags += [FLAGS[name][0], _values[name]]
    return flags


def _require(name):
    if name not in _values:
        raise MissingEnvironment(
            "missing %s: %s. It belongs to the machine, so it has no default "
            "value; whoever runs this passes it" % (FLAGS[name][0],
                                                   FLAGS[name][1]))
    return _values[name]


def game():
    """The original RM2k project: see `rpgmaker/resources.py`."""
    return _require("game_dir")


def rtp():
    """Don Miguel's RTP: see `rpgmaker/resources.py`."""
    return _require("rtp_dir")


def soundfont():
    """The bank the SPC700 samples and the MSU-1 tracks come from: the
    converter passes it on to `rm2k-snes-audio`, and `audio/msu.py` renders
    with it."""
    return _require("soundfont")


def msu_replacements():
    """Where the MSU-1 track replacements are looked up, or None: without
    replacements, each track comes from its MIDI."""
    return _values.get("replacements")


def cache():
    """The converter's disk cache: see `common/disk_cache.py`."""
    return _values.get("cache") or os.path.join(project.build(), "cache")


def test_cartridges():
    """Where the suite's cartridges are built, except `release`: see
    `cartridges.directory`."""
    return (_values.get("test_cartridges")
            or os.path.join(project.build(), "tests"))


def shared():
    """Where what gets built is delivered: see `assembly/entregar.py`."""
    return _require("shared")
