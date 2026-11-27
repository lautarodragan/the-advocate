# harness/

The generic part of the games' test harness: what runs a built cartridge
in a libretro core and asks it questions, for any game's tests, in Python.
It knows no game. The test game's tests, in `test-game/tests/`, use it as
it is; A Blurred Line's harness, in the ports, puts its own on top —its
title screen, its menus, its battles—, and so do the ports' other games.

    rm2k_snes_harness/    the package
      retro.py            drives a libretro core from Python, frame by
                          frame: no X, no clock, no sleeps
      cores.py            which cores, and where the machine has them
      game.py             a game's project and its cartridges, as
                          `build/advocate.json` says them
      session.py          a cartridge running: the tick clock, the cases,
                          the map, the switches, the control, the reset
      golden.py           a capture against its golden, at 15 bits
      rm2k.py             RPG Maker 2000's rules the tests compute what to
                          expect with: passability, terrain, the graphics
                          of a page
      engine.py           the engine's numbers, as the build wrote them
                          into the cartridge's `.sym`: the keys' values,
                          the random seed, the caps
    cores/                what the cores need that their packages lack: the
                          bsnes patches and Mesen2's shim, below

**How a game's tests find it**: `just install` links this directory beside
the tools' `bin/`, as `lib/advocate/harness`, and puts that on Python's
import path with a `.pth` in its `site-packages`; the tests `import
rm2k_snes_harness` and ask no binary where it is. It is a link to the
checkout the tools were installed from, the same that gives the runtime,
so the harness and the runtime whose symbols it reads are always the same
checkout's. A worktree's `install-local` links its own in its
`.local-tools/`, and a game's tests take the one beside the first
`advocate` of their PATH before the one of `site-packages`. A release's
archive carries it at the same place, beside its `bin/`. The test game, which lives here,
names it in its `pytest.ini` instead. Until 2026-11-25 the tests asked
`rm2k-snes-project --harness` where it was.

**A game says once what it is**, before its first test —in its
`conftest.py`—: `rm2k_snes_harness.use(Game(root, goldens,
snapshots))`. From
then on `Session(core, case=...)` is its `release` running with that test
page chosen, and `golden(name, image, core)` compares against its goldens.

`retro.py` left this repo with A Blurred Line's tests on 2026-10-02, and
came back on 2026-11-22 with the rest of their harness that is not that
game's: until then the test game carried a copy of it
and a small harness of its own, `test-game/tests/game.py`, which is where
`game.py`, `session.py` and `golden.py` come from.

## The bsnes patch

`cores/bsnes-wram.patch` is for **bsnes-libretro**, not for this repo. bsnes does
not expose the WRAM —`retro_get_memory_data` returns null for every id— and
the tests' clock asks the ROM which tick of the loop it is on, which lives
in `ticks`, in the WRAM. Without the patch, whatever runs under bsnes falls
back to counting hardware frames, which works as long as the ROM does not
fall behind. And without bsnes there is nothing to answer what running
every test on both cores exists to answer: whether the ROM reads memory
nobody initialised.

The patch exposes only `RETRO_MEMORY_SYSTEM_RAM` and leaves the rest as it
is: bsnes's comment on that function is about the SRAM, which is not touched,
and that is why it is defensible upstream. Its commit message says the rest.

Building it takes `gcc` and `make`, and nothing else:

    git clone https://github.com/libretro/bsnes-libretro
    cd bsnes-libretro
    git am < .../rm2k-snes/harness/cores/bsnes-wram.patch
    make -j$(nproc)
    cp bsnes_libretro.so /usr/lib/libretro/

## The display-access audit

`cores/bsnes-display-audit.patch` goes on top of the other one, and it is
what the test game's `test_terrace.py` runs on, and A Blurred Line's
`tests/rpgmaker/test_display_accesses.py` and `just display-sweep`, in the
ports —see its `harness/display_audit.py`—. bsnes's accurate PPU
—`bsnes_ppu_fast` at `OFF`; the core's default is the fast one— already
does what the console does with the display on: it drops a VRAM write,
gives 0 for a VRAM read and puts a CGRAM write on the entry being drawn.
The patch counts each of those, and the OAM ones, with the line and dot
of the last, and the core exposes them as memory id `0x8000`, six `u32`
that `retro.Console` zeroes before each frame it watches. A frame whose
count is not zero is an access the console would have lost or misplaced,
whether or not the screen shows it. It changes no emulation, and the fast
PPU does not count.

**It is a core of its own, not the one above.** `just audit-core`, in
A Blurred Line's `abl/` in the ports, fetches bsnes-libretro at the commit its `bsnes_pin` names,
applies both patches, builds it and installs it in `AUDIT_CORE`, which
`machine.just` sets: the plain `bsnes_libretro.so` stays as it is, because
every suite running loads it. Run it again when a patch or the pin
changes, or on a new machine; without the core, the test skips saying
so. The CI workflow, `.github/workflows/ci.yml`, builds it the same way
for the test game.

A patch that no longer applies after moving the pin is redone on the new
commit and committed here with it.

## The MSU-1 log

`cores/bsnes-msu-log.patch` goes on top of the other two, in the same core. It
logs every write to `$2000-$2007` and every read of `$2000`, in order, with
the status `$2000` gave just before and where the track was playing, and
each run of reads of the data port, `$2001`, as one entry; the core
exposes the log as memory id `0x8001`, and `retro.Console.msu_accesses`
reads it and starts it over. It is what the save tests of A Blurred
Line's `tests/abl/test_msu.py` look at: the order a save speaks to the MSU-1 in,
and a seek nobody reads from, which no emulator's sound or state shows
—they answer a seek at once—. It changes no emulation either. A new patch
is a new `just audit-core`.

## Mesen2's core

taro plays on Mesen2, and sends what goes wrong as a Mesen2 save state, a
`.mss`. `cores/mesen2_shim.cpp` is Mesen2's core behind the libretro calls
`retro.py` makes —load, a frame, the pad, the picture, the WRAM, the
SRAM, the VRAM—, plus what only Mesen2 has: its `.mss` states, its lag
counter as memory id `0x8100` —the number its HUD shows: a frame in which
nothing read the pad—, and a line profiler that does not touch the ROM.
Mesen2 has no libretro core of its own; `mesen-s`, the third core
installed, is Mesen-S, its predecessor, and does not load its states.

**No test of the suite uses it**: it is a tool for bug reports. Building
it takes Mesen2's sources and minutes, and what it answers —what taro's
emulator saw, from taro's game— is not a regression's question. Its
picture agrees with snes9x's at 15 bits —0 pixels of 57,344 on the title
screen, measured on 2026-11-17—.

**Building it**, once per machine or when the shim or the pin changes,
from A Blurred Line's `abl/`, in the ports, whose recipes these are:

    just mesen2-core

It fetches Mesen2 at the commit `mesen2_pin` names —the version taro plays
with— into a clone of its own, compiles it with the shim and installs the
core in `MESEN2_CORE`; both places are `machine.just`'s.

**Playing a state**: the ROM it was saved from, the `.mss`, and what to
press, counted in hardware frames from the state, each held `--hold`
frames —2—:

    just mesen2 <rom> <state>.mss --frames 300
    just mesen2 <rom> <state>.mss --press a:0 up:8 --frames 120
    just mesen2 <rom> <state>.mss --press a:0 up:8 --frames 60 --watch

It prints the lag frames Mesen2 counted and the ticks the ROM counted over
those frames. `--watch` adds one line per tick of the main loop: the lines
it was busy —more than 262 is a frame lost— and how many each of the
loop's calls took, or each of the routines named after it. `--poke
tint_s=100` writes a byte after loading, to see which part of the state
makes the difference; `--shot` keeps the last frame and `--save` a new
`.mss`. From a script, that game's `harness/mesen2.py`'s `Mesen2` does the same over
any console on that core, and its `session` starts a `suite.session` on
it.

**A `.mss` only replays on the ROM it was saved from.** It is the whole
console, not the game's save: on another build the saved program counter
falls in the middle of other code, and Mesen2 loads it anyway without a
word. So the ROM is rebuilt from the delivery's two commits —its
`README.txt` names them—: the ports checked out at the first, and
the-advocate at the second with its `cartridge` installed locally, as
"Where this runs" in the work repo's `AGENTS.md` says —the runtime goes
with the checkout `cartridge` was compiled from—, and `just cartridges
release` in the ports' with that `bin/` first in the PATH. It comes out byte for byte the delivered `abl.sfc`
—compare their sha256—, with its `.sym` next to it, which names the
routines. A delivered `abl.sfc` with its `.dbg` works too.

And **a `.mss` only loads on the Mesen2 version that saved it**: taro's
are from Community Edition 2.2.1. When taro moves to another, the pin
moves with it, in its own commit, and the shim is checked again: it
reaches into Mesen2's private members to run one frame on the caller's
thread, and a new version can move them.
