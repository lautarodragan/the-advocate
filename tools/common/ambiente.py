"""What belongs to the machine and not to the project: where the original
game is, the RTP, the SoundFont, the replacements for the MSU-1 tracks, the
cache and where builds are delivered.

**It arrives by flags, not by environment variables.** Until 2026-09-29 the
tools read `ABL_GAME_DIR` and friends, with this machine's values as
defaults: they knew what the game was called and where it lived. Now each
executable receives what it needs —`--game-dir`, `--rtp-dir`,
`--soundfont`…—, sets it here with `desde_argumentos`, and the rest of the
tools read it from here. Which variable points to what, and the machine's
values, belong to the caller: the game's `justfile`.

**A value nobody set is an error, not a default**, except the ones that
hang off the project —the cache and the test cartridges, inside its
`build`—: a machine default would be one machine's.

It is a single place that gets configured, and not a parameter in every
function, on purpose: `recursos.GAME_DIR`, `recursos.RTP_DIR` and
`snes_samples.SOUNDFONT` are read inside some forty functions of the
converter and the music, and passing them as parameters touched all those
signatures. Those names still exist, but they are resolved here when read
—see each module's `__getattr__`—, so they fail clearly if read without
being set.
"""

import os

from common import proyecto


class FaltaElAmbiente(SystemExit):
    """A machine value nobody passed. It is a `SystemExit` for the same
    reason as `proyecto.NoHayProyecto`: what fixes it is how it was run, not
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
    "reemplazos": ("--reemplazos", "where to look for a <song>.mp3 —or "
                                   ".ogg, .flac, .wav— that replaces that "
                                   "song's MIDI in the MSU-1 tracks"),
    "cache": ("--cache", "the converter's disk cache. Without this, "
                         "cache/ inside the project's build"),
    "test_cartridges": ("--test-cartridges", "where the test cartridges are "
                                             "built. Without this, tests/ "
                                             "inside the project's build"),
    "compartido": ("--compartido", "the folder where what gets built is "
                                   "delivered"),
}

_fijados = {}


def fijar(**valores):
    """Sets the values that are not None. A name that is not in `FLAGS` is a
    programming error, not the caller's."""
    for nombre, valor in valores.items():
        if nombre not in FLAGS:
            raise KeyError(nombre)
        if valor is not None:
            # Absolute: the converter runs from a different directory than
            # the one that called it.
            _fijados[nombre] = os.path.abspath(valor)


def argumentos(parser, *nombres):
    """Adds the flags of `nombres` to an executable's parser."""
    for nombre in nombres:
        flag, ayuda = FLAGS[nombre]
        parser.add_argument(flag, dest=nombre, metavar="PATH", help=ayuda)


def desde_argumentos(args, *nombres):
    """Sets what came on the command line."""
    fijar(**{nombre: getattr(args, nombre) for nombre in nombres})


def como_flags(*nombres):
    """The set values of `nombres`, as flags: to pass them on to another
    tool that runs in a separate process."""
    flags = []
    for nombre in nombres:
        if nombre in _fijados:
            flags += [FLAGS[nombre][0], _fijados[nombre]]
    return flags


def _pedir(nombre):
    if nombre not in _fijados:
        raise FaltaElAmbiente(
            "missing %s: %s. It belongs to the machine, so it has no default "
            "value; whoever runs this passes it" % (FLAGS[nombre][0],
                                                   FLAGS[nombre][1]))
    return _fijados[nombre]


def juego():
    """The original RM2k project: see `rpgmaker/recursos.py`."""
    return _pedir("game_dir")


def rtp():
    """Don Miguel's RTP: see `rpgmaker/recursos.py`."""
    return _pedir("rtp_dir")


def soundfont():
    """The bank the samples come from: see `audio/snes_samples.py`."""
    return _pedir("soundfont")


def reemplazos_msu():
    """Where the MSU-1 track replacements are looked up, or None: without
    replacements, each track comes from its MIDI."""
    return _fijados.get("reemplazos")


def cache():
    """The converter's disk cache: see `common/cache_disco.py`."""
    return _fijados.get("cache") or os.path.join(proyecto.build(), "cache")


def cartuchos_de_prueba():
    """Where the suite's cartridges are built, except `release`: see
    `cartuchos.directorio`."""
    return (_fijados.get("test_cartridges")
            or os.path.join(proyecto.build(), "tests"))


def compartido():
    """Where what gets built is delivered: see `ensamblado/entregar.py`."""
    return _pedir("compartido")
