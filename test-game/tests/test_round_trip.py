"""That the test game comes back from Ditto byte for byte: the RM2k files
`just game` packed into `build/game/`, unpacked with `ditto unpack` and
packed again from the exact dump, each `.lmu`, `.ldb` and `.lmt` the same
as before.

It proves Ditto reads what Ditto writes, and it runs in CI, where no game
of anyone else's can go: `src/` is written by hand, so the binary in
`build/game/` is the only one in this repository, and a field `pack`
writes and `unpack` loses —or reads back in another shape— shows here.
That Ditto reads what RPG Maker wrote is asked by the ports' boot suite,
over each game's original; Ditto's own tests ask it of whatever game
`DITTO_CORPUS` names.

With the `ditto` of the PATH, the one that made `build/game/`. Until
2026-11-23 the round trip was a recipe in each port, and the test game had
none.
"""

import os
import subprocess

GAME = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "build", "game")

# What RPG Maker writes and Ditto reads; the rest of `build/game/` is the
# assets, copied.
FORMATS = (".lmu", ".ldb", ".lmt")


def _files(directory):
    return {name: os.path.join(directory, name)
            for name in os.listdir(directory) if name.lower().endswith(FORMATS)}


def test_the_game_comes_back_from_ditto_byte_for_byte(tmp_path):
    assert os.path.isdir(GAME), (
        "no %s: run the tests with `just test` in test-game/, which makes "
        "the game first" % GAME)
    for command in (["ditto", "unpack", GAME, tmp_path / "exact",
                     tmp_path / "resolved"],
                    ["ditto", "pack", tmp_path / "exact", tmp_path / "game"]):
        done = subprocess.run(command, capture_output=True, text=True)
        assert not done.returncode, "%s: %s" % (" ".join(map(str, command)),
                                                done.stderr)
    before = _files(GAME)
    after = _files(tmp_path / "game")
    assert before, "%s has no RPG Maker files" % GAME
    different = []
    for name in sorted(set(before) & set(after)):
        with open(before[name], "rb") as a, open(after[name], "rb") as b:
            if a.read() != b.read():
                different.append(name)
    assert sorted(before) == sorted(after) and not different, (
        "the test game does not come back from Ditto byte for byte, of %d "
        "files: different %s, missing %s, extra %s"
        % (len(before), different, sorted(set(before) - set(after)),
           sorted(set(after) - set(before))))
