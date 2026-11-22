# The test game

A game of our own, written as text and with free assets, for the engine's
ROM tests to live in. Until it exists they live in A Blurred Line, whose
suite tests what RPG Maker 2000 does using that game as a stage; this is
where they come back to, one by one. Why, and the plan, are in the book:
the research "The test game" and the page on the test game under "Project
progress".

Today it is a skeleton: the meadow —the Exterior ChipSet, the hero, an
elder with People1's CharSet, and a signpost and a board that lead to
everything else, see "Playing it"—, a test that boots the cartridge, walks up
to the elder and reads what he says, the first engine test brought back
from A Blurred Line —switches past 1023— and the first born here: a chain
of nested calls that returns. And two more maps with the same ChipSet,
the garden and the showcase, where the console loses colours: a little,
and too much. They are the book's examples of the lossy optimizations,
next to RM2k's drawing of the same. And a fourth, the clearing, with no
events at all, and two big ones: the plain, 200x200, and the vast, too big
for the console, which leaves it out. And the ring, which loops on both
axes, with two walkers that go round it. And the terrace, a slab of grass
in a night sky that scrolls on its own, where three walkers go round
under a transparent box in the middle of the screen, and then in the
rain, which an event starts when talked to. And the lookout, whose
night sky a parallel page swaps for a dawn, and whose dispatcher sends the
hero on when its switch is on. And the doors, two rooms of one map crossed
by teleports to itself, with a door that opens, a hatch to stand on and
an awning that, opened, goes above the hero;
and the patchwork, 60x60 of stripes no two neighbouring rows draw alike,
for the camera. And the erasure, a bare field where a statue and a
pacer erase themselves, and a loop leads back to the same map. The showcase's ChipSet gives its first four tiles a
terrain each. And the crossing, four cells
with two events standing on each, where every one whose trigger matches
fires. And a common event that shows a box with escapes the console
cannot show, which it drops and the build lists, one that changes the
map's ChipSet, which it drops too, and one with letters outside ASCII,
which it draws or shows plain. And a case that puts six small pictures
up on the meadow at once and slides two of them, and one that types boxes
in the System's colours and at three speeds. The database has three
actors —the Hero, Alda and Bram, who is in no party— and one item, the
Sword, for the cases that read an actor's stats; and Zoë Peña, the Poción
Ácida and the Avispón, an actor, an item and the one enemy of the one
troop, whose names carry letters outside ASCII for the text screens.

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
    ChipSet/, CharSet/, FaceSet/, System/
                        the pictures, from EasyRPG's RTP
    Picture/, Panorama/ the pictures that are ours, drawn by scripts
    AUTHORS.md          whose each picture is, its license and its link;
                        `tests/test_test_game_assets.py`, at the root,
                        fails if a picture has no line there
    LICENSE-CC-BY-4.0.txt
                        the license most of them are under
    advocate.toml       its cartridges, like a port's: `release`, and
                        `test-vblank` with the vblank's probe
    hub.toml            the meadow's hub: the guide's maps and the
                        tester's menus, which `just hub` writes into
                        `src/maps/Map0001.json`
    tester/             the cases the tester runs, one JSON each, in a
                        case's format: the commands of a page
    cases/              the test pages the harness still injects, like a
                        port's: `nothing`, the game as it boots, and the
                        probe cartridge's `terrace`
    justfile            making it, building it, testing it, delivering it
    tests/              its tests, in pytest, and their goldens
    build/              what is made: not versioned

## Playing it

Everything the tests reach is reached by playing, from the meadow, where
the game starts:

* **the guide**, the signpost to the left of the hero: a teleport to each
  map —the lookout twice, once with its dispatcher on—, landing where its
  tests land;
* **the tester**, the board right below the hero, who faces it on boot: the
  cases, grouped —boxes, variables, events, maps, hero and keys,
  letters— four options a menu, the last one "More" when there are more.
  A case runs there, with the hero on the start cell, as the harness ran
  it at boot: the board calls its page on the shelf, an event with no
  graphic in the top left corner's bush;
  `branch-switched` is `branch` with its switch on;
* **the Way Home**, an item both hand out, which brings the hero back to
  the meadow from anywhere: the pause menu, then the items;
* on the erasure, **the keeper** in the corner wakes the statue's other
  page or starts the pacer.

A case leaves behind what it changes —a picture, a tint, the party—, as a
page of a game does: a reset starts clean.

A new case is a file in `tester/` and its name in a group of `hub.toml`,
and then `just hub`; a new map, its line in `hub.toml`'s guide.
`tests/test_hub.py` is red until the meadow says what those two say.

`just deliver "<what to look at>"`, with `SHARED`, leaves the build where
taro plays it; see the recipe.

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
The harness is the tools' generic one, `rm2k-snes/harness/` at the
repository's root, and what is the test game's —where it is, the flags it
is built with, where its goldens are— is said once, in `tests/conftest.py`.
bsnes needs a patch to expose its WRAM, `rm2k-snes/harness/cores/bsnes-wram.patch`;
the CI workflow builds both cores, and its steps are how to build them by
hand.

They play it: each boots the game and reaches what it tests through the
hub, as a player does —`play.py`—, and only pokes the RAM where playing it
cannot be done or would take absurdly long, which it says on that line.

    hub.py, play.py     the hub written from `hub.toml`, and playing it:
                        the guide, the tester's menus, the Way Home
    test_hub.py         the meadow says what `hub.toml` says, every case
                        and every map is offered, and each map is reached
                        and left with the Way Home
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
    test_faces.py       `ChangeFaceGraphic`: a box with Actor1's face on
                        the left, one on the right and mirrored, one that
                        keeps it, one with another face, and one after it
                        is cleared
    test_empty_map.py   the clearing, a map with no events, reached by a
                        Teleport: it arrives and draws
    test_key_long_form.py
                        `KeyInputProc` with RM2k 1.50's ten parameters,
                        the four directions one by one: the action key,
                        cancel and down read into a variable
    test_actor_stats.py `ControlVars` from an actor: the Hero's level,
                        experience, attack and defense with the Sword and
                        his weapon and shield; Bram's level, who never
                        fights; and the experience saturating at the word
    test_big_maps.py    the plain, 200x200, whose grid goes one byte a
                        cell and past the first 32 KB: two walks across
                        where it changes bank; and the vast, 330x200,
                        which fits no way and is left out, so its Teleport
                        is the box
    test_terrace.py     a transparent box in the middle over the terrace's
                        scrolling panorama, with walkers under its lines:
                        on which vblank line each line goes up, on the
                        `test-vblank` cartridge's probe; that nothing
                        reaches the screen while it is drawn, on bsnes's
                        accurate PPU with the display-access audit
                        (`AUDIT_CORE`); and what it looks like
    test_panorama_swap.py
                        the lookout's `ChangePBG` from its night sky to a
                        dawn while a page carried from another map waits:
                        the picture before and after, and that the carried
                        bytecode comes through the swap byte for byte
    test_linter.py      Goombario over the cartridge: the runtime falls in
                        none of the traps it knows, but for the lines
                        annotated as right
    test_screen_letters.py
                        Latin-1 on the text screens: Zoë's name in a box,
                        `\N[0]`, and on the menu; the Poción Ácida on the
                        items screen, in a shop and in the battle's item
                        list, against the Avispón

And the first ten that came from A Blurred Line's `tests/rpgmaker/` on
2026-11-22, with their cases rewritten on these maps —phase 2 of the
research—. They ask the ROM's RAM, not the screen, so they have no goldens:

    test_variables.py   `ControlVars`: the operations, the random numbers
                        against the xorshift, the branch by variable both
                        ways, a character's place on RM2k's screen, the
                        word's ceiling, an item's count, and the
                        variables through a save and a reset
    test_conditional.py `ConditionalBranch`: the branch that runs with its
                        switch turned on before the page, and the ones
                        skipped, after which the page goes on
    test_labels.py      `Label` and `JumpToLabel`: backwards, forwards, to
                        one that is not there and inside an `else`
    test_key.py         `KeyInputProc`: the number of each key, the edge
                        and not the button held, and cancel winning
    test_speed.py       the pad walks at the speed a route left, to the
                        pixel, and the speed travels in the save
    test_jumps.py       the budget of chained teleports comes back with
                        control; the lookout's dispatcher sends the hero on
    test_terrain.py     `StoreTerrainID` on the showcase's first four
                        tiles, which its ChipSet gives four terrains
    test_same_door.py   the doors' door to the same map keeps what moved
                        when it opened, there and back
    test_own_action.py  the action key looks at the hero's own cell for an
                        event above them, and not at the one in front
    test_camera.py      the patchwork's window in the VRAM against the
                        camera, two rows or columns a tick

And on the same day, for what no test of A Blurred Line looked at:

    test_erase_event.py `EraseEvent` on the erasure: a statue on the
                        hero's layer that erases itself is not drawn and
                        lets the hero through its cell, its foreground
                        page goes on, it stays erased over a jump to the
                        same map and comes back when the map is loaded
                        again; and a parallel page that erases its walking
                        event stops there, does not start again and leaves
                        it still and not drawn

A capture with no golden is left in `tests/snapshots/golden/` and the test
fails: it is looked at and, if it is right, copied to `tests/golden/` in a
commit of its own that says why.
