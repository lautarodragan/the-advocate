# The test game

A game of our own, written as text and with free assets, for the engine's
ROM tests to live in. Until it exists they live in A Blurred Line, whose
suite tests what RPG Maker 2000 does using that game as a stage; this is
where they come back to, one by one. Why, and the plan, are in the book:
the research "The test game" and the page on the test game under "Project
progress".

Today it is a skeleton: the meadow —the Exterior ChipSet, the hero and an
elder with People1's CharSet—, a test that boots the cartridge, walks up
to the elder and reads what he says, the first engine test brought back
from A Blurred Line —switches past 1023— and the first born here: a chain
of nested calls that returns. And two more maps with the same ChipSet,
the garden and the showcase, where the console loses colours: a little,
and too much. They are the book's examples of the lossy optimizations,
next to RM2k's drawing of the same. And a fourth, the clearing, with no
events at all. And a common event that shows a box with escapes the console
cannot show, which it drops and the build lists.

    src/                the game, as text: what to edit
      ditto.json, maps.json, db/, maps/MapNNNN.json
                        a Ditto exact dump, written by hand: liblcf's
                        names, enums by name, and every field that holds its
                        default left out. `rm2k/ditto/README.md` says the
                        format
      maps/MapNNNN.toml each map's tile layers, sketched: a grid of
                        characters and a legend of the tiles each one stands
                        for, which `rm2k-sketch` makes into the dump's
                        `.tiles`. See `rm2k/sketch/`
      RPG_RT.ini        the game's title, for RPG Maker and EasyRPG
    ChipSet/, CharSet/, System/
                        the pictures, from EasyRPG's RTP
    AUTHORS.md          whose each picture is, its license and its link;
                        `tests/test_test_game_assets.py`, at the root,
                        fails if a picture has no line there
    LICENSE-CC-BY-4.0.txt
                        the license most of them are under
    rm2k-snes.toml      its cartridge, like a port's
    cases/              the test pages the cartridge carries, one JSON
                        each, like a port's; a test chooses one with
                        `Session(core, case=...)`
    justfile            making it, building it, testing it
    tests/              its tests, in pytest, and their goldens
    build/              what is made: not versioned

## Making it, building it

    SOUNDFONT=<a .sf2> just test     # makes it, builds it and tests it
    just game                        # only makes it: build/game/, build/data/

From the repository's root, `just test-game` is the same `test`. The tools
come from the PATH, like for any game, and a worktree's `.local-tools/`
first.

`just game` makes the RM2k files out of `src/` into `build/game/` —with the
pictures beside them: that folder opens in RPG Maker 2000 or in EasyRPG
Player— and dumps them back into `build/data/`, which is what the converter
reads, the same path as a port's dump. The editor can be used to draw: what
it saves, `ditto unpack` turns back into an exact dump, which is copied into
`src/` by hand —and a map drawn there loses its sketch, since the editor
writes ids—.

**The SoundFont** belongs to the machine and comes in `SOUNDFONT`, with no
default. The game has no music yet, but the converter asks for one; once it
has, the samples go into the cartridge, so for the cartridge to be ours to
give away the SoundFont has to be a free one.

**No RTP**: the cartridge is built with an empty `--rtp-dir`. Everything the
game uses is in this folder, so a missing picture is an error and not one
quietly found in somebody's RTP.

## Its tests

They boot the cartridge in a libretro core —snes9x, and bsnes, which starts
with garbage in WRAM— and compare what it draws against goldens, at 15 bits.
The harness is `tests/game.py`, small on purpose, and the core driver
`tests/emulator/retro.py`, a copy of A Blurred Line's: phase 2 of the
research brings the generic part of that game's harness here, and then both
go.

    test_meadow.py      the meadow as it is reached, and the elder's message
    test_switches_past_1023.py
                        a switch past 1023 set, branched on and asked for
                        by a page —the meadow's invisible event at (1,1)—
    test_leader_name.py `\N[0]` before and after the party is reordered, a
                        renamed actor's `\N[n]` and the menu with its new
                        name, and the rename through a save and a reset
    test_nested_calls.py
                        a chain of six CallEvents —the invisible events at
                        column 18, and common event 1— that returns to each
                        caller and goes on, with a parallel page running
    test_lossy_colours.py
                        the garden and the showcase as they are reached:
                        what the console draws where it merges colours a
                        little and where it merges too much
    test_empty_map.py   the clearing, a map with no events, reached by a
                        Teleport: it arrives and draws

A capture with no golden is left in `tests/snapshots/golden/` and the test
fails: it is looked at and, if it is right, copied to `tests/golden/` in a
commit of its own that says why.
