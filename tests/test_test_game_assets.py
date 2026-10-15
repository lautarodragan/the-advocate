"""That every picture of the test game says whose it is.

The test game, in `test-game/`, is public and carries assets made by other
people, under licenses that ask for attribution: author, license, link and
whether it was changed. `test-game/AUTHORS.md` gives that per file, in a
table whose first column is the file. A picture added without its line
there is one the repository has no right to show, and nothing else would
notice; a line left after its file is gone credits what is not there.

It reads only the repository: the files git tracks under `test-game/` and
that table.
"""

import os
import re
import subprocess

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = "test-game"

# What is an asset: what a game carries beside its data, by extension —the
# pictures, the music and the sounds RM2k reads—.
ASSETS = (".png", ".bmp", ".xyz", ".mid", ".midi", ".wav", ".ogg", ".mp3")

# What is not someone else's even if it has an asset's extension: the
# goldens are what our cartridge drew.
OURS = (GAME + "/tests/",)


def _tracked():
    out = subprocess.run(["git", "ls-files", GAME], cwd=TOOLS, check=True,
                         capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def _credited():
    """The files `AUTHORS.md` gives a line to: the first cell of each row of
    its table, in backquotes."""
    with open(os.path.join(TOOLS, GAME, "AUTHORS.md")) as file:
        return {GAME + "/" + m for m in re.findall(r"^\| `([^`]+)` \|", file.read(),
                                                     re.MULTILINE)}


def test_every_asset_has_its_line_in_authors():
    assets = {path for path in _tracked()
              if path.lower().endswith(ASSETS) and not path.startswith(OURS)}
    missing = sorted(assets - _credited())
    assert not missing, ("these files of the test game have no line in "
                         "test-game/AUTHORS.md: %s" % ", ".join(missing))


def test_every_line_in_authors_is_a_file_there():
    gone = sorted(_credited() - set(_tracked()))
    assert not gone, ("test-game/AUTHORS.md credits files that are not "
                      "there: %s" % ", ".join(gone))
