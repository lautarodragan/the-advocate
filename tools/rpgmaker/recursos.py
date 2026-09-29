"""Where the game and the RTP are, and how a resource is found inside them.

It is not about drawing: it is the game's configuration and RM2k's resource
lookup, used alike by the render, the audio and the converter.
"""

import os

from common import environment

# `GAME_DIR` is the original RM2k project, and `RTP_DIR` the RTP it was built
# with. The executable sets them from `--game-dir` and `--rtp-dir` —see
# `common/environment.py`— and they are read when used: reading them unset
# fails saying which flag is missing.
#
# For ABL, the RTP is Don Miguel's (June 2000), extracted from RTPE.EXE. It is
# not the "official" RTP: the RPG Maker 2000 used outside Japan was his
# translation, and along the way he added files of his own (Future1-3, among
# others) that ABL uses. EasyRPG's free RTP does not work here: it is a
# replacement with different art. Neither the game nor the RTP live in the
# repo: they are not ours to redistribute. The RTP used to be `RTP/` inside
# the repo, excluded by .gitignore, which is the worst combination —it took up
# space, was not versioned, and looked like part of the project—.
_DEL_AMBIENTE = {"GAME_DIR": environment.game, "RTP_DIR": environment.rtp}


def __getattr__(nombre):
    if nombre in _DEL_AMBIENTE:
        return _DEL_AMBIENTE[nombre]()
    raise AttributeError("module %r has no attribute %r" % (__name__, nombre))


def find_resource(dirs, folder, name, extensions=(".png", ".bmp")):
    """Looks for <dir>/<folder>/<name>.<ext>, case-insensitively.

    RM2k stores names without extension and the original game ran on
    Windows, so the .lmu files say nothing about the file's real case.
    """
    for directory in dirs:
        for entry in os.listdir(directory) if os.path.isdir(directory) else []:
            if entry.lower() != folder.lower():
                continue
            subdir = os.path.join(directory, entry)
            for filename in os.listdir(subdir):
                base, ext = os.path.splitext(filename)
                if base.lower() == name.lower() and ext.lower() in extensions:
                    return os.path.join(subdir, filename)
    return None
