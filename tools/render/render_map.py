"""What the converter asks `rm2k-render` to draw, and the game it reads.

**`rm2k-render` draws**, a Rust binary on the PATH, like `lz2`: `draw` is
the call the screens use —the faces, the System's windows and the
`ShowPicture` pictures— and the battle's backdrops and battlers
(`scene.py`); the battle animations have their own shape
(`animation.draw`). `Renderer` holds the game the converter reads —its
database, its map tree, where the pictures are looked up— and reads a map
the way the converter keeps it.

A map's layers and the CharSets its events are drawn with are not asked
from here: since 2026-09-30 `rm2k-snes-maps` draws them, with
`rm2k-render` as a library, as part of converting the map.
"""

import json
import os
import shutil
import subprocess
import tempfile

from PIL import Image

from common import project
from rpgmaker import lcf
from rpgmaker import resources
from rpgmaker.resources import find_resource
from rpgmaker.rm2k import TILE
from render import chipset_recipe

MISSING = """`rm2k-render` is missing, the one that draws the faces, windows and
pictures of the screens, and what the battles are drawn with.

It is a Rust binary that lives in `tools/rm2k/rm2k-render/` and is installed as
a system tool:

    just -f tools/justfile install rm2k-render"""


def binary():
    """The path of the `rm2k-render` on the PATH. Exits with the message if
    it is not there."""
    path = shutil.which("rm2k-render")
    if path is None:
        raise SystemExit(MISSING)
    return path


def draw(command, entries):
    """One call to `rm2k-render <command>` with `entries` as its request, a
    list: the pictures it drew, in RGBA and in the same order. The paths
    in the entries have to be absolute, because the request is written in a
    temporary directory. `face`, `system`, `picture` and `battle` take this
    shape."""
    with tempfile.TemporaryDirectory(prefix="rm2k-render-") as out:
        request_path = os.path.join(out, "request.json")
        with open(request_path, "w", encoding="utf-8") as f:
            json.dump(entries, f)
        drawn = os.path.join(out, "drawn")
        done = subprocess.run(
            [binary(), command, "--request", request_path, "--out", drawn],
            capture_output=True, text=True)
        if done.returncode != 0:
            raise SystemExit("rm2k-render %s could not draw %s:\n%s"
                             % (command, json.dumps(entries),
                                done.stderr.strip()))
        images = []
        for i in range(len(entries)):
            # Read now, before the directory goes away.
            with Image.open(os.path.join(drawn, "%d.png" % i)) as image:
                images.append(image.convert("RGBA"))
        return images


def build_passability(chipset):
    """Table of flags per tile ID, as lmu2png builds it (main.cpp).

    We only use it to decide whether a tile goes before or after the player;
    there is no player here, but it defines the drawing order between the two
    layers.
    """
    flags = bytearray(65536)
    lower, upper = chipset.passable_lower, chipset.passable_upper

    for i in range(3):          # water A/B/C
        flags[1000 * i:1000 * i + 1000] = bytes([lower[i]]) * 1000
    for i in range(3):          # animated tiles
        flags[3000 + i * 50:3050 + i * 50] = bytes([lower[3 + i]]) * 50
    for i in range(12):         # terrain autotiles
        flags[4000 + i * 50:4050 + i * 50] = bytes([lower[6 + i]]) * 50
    for i in range(144):        # common tile pages
        flags[5000 + i] = lower[18 + i]
        flags[10000 + i] = upper[i]
    return flags


class Renderer:
    """Everything shared between maps: the game, the RTP and the caches."""

    def __init__(self, game_dir=None, rtp_dir=None):
        game_dir = game_dir or resources.GAME_DIR
        rtp_dir = rtp_dir or resources.RTP_DIR
        self.database = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
        self.tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
        self.game_dir = game_dir
        self.search_dirs = [project.root(), game_dir, rtp_dir]
        # The images of the ChipSets `rom/parches/manual/` adds are **built**
        # —the game's art is not ours to version, see `chipset_recipe.py`—
        # and go first in the search: they are the ones that win when they
        # exist.
        self.search_dirs.insert(0, chipset_recipe.build_images(
            lambda folder, name: find_resource(self.search_dirs, folder,
                                               name)))

    def load_map(self, path):
        """The map, with its chipset's name set: `collect_npcs` needs it for
        the events that are drawn with a tile."""
        game_map = lcf.Map(path)
        chipset = self.database.chipsets[game_map.chipset_id]
        game_map.chipset_filename = chipset.filename
        # And the passability of its tiles, for the events drawn with one on
        # the lower layer: see `rm2k.event_tile_passability`.
        game_map.passability_table = build_passability(chipset)
        return game_map
