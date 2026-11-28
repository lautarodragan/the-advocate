# The Advocate

The Advocate is a program that converts RPG Maker 2000 games into SNES
games.

Everything about it —what it is, how it works inside, the decisions, the
divergences from RPG Maker and the research— is in the book:
<https://lautarodragan.github.io/the-advocate-docs/>.

## How it is installed

**It needs `python`, a libretro core and `ca65` + `ld65`**, and the tools
—the Rust projects, which `LAYOUT.md` lists— are installed on the PATH;
compiling them takes a C++ compiler too, for the S-DSP `snes/spc-dsp/`
vendors. A
game consumes them from there, and no script or test of a game calls
`cargo`: the why is in `AGENTS.md`. `ca65` and `ld65` come from cc65,
which is not packaged in every distribution and is compiled from its
sources: see [Sources](https://lautarodragan.github.io/the-advocate-docs/reference/sources.html) in the book.

    just install   # installs the tools on the PATH
    just test      # the repo's Python tests
    just rust-test # those of every Rust project

Or, without compiling: every commit to `main` that passes CI is a release
(`.github/workflows/release.yml`) with the tools built for Linux —glibc 2.35 or
newer, x86_64 and aarch64— and macOS —Apple silicon and Intel—. Unpack one and put
its `the-advocate/bin` on the PATH; cc65 and the rest are still needed.

The runtime travels with the tools: `advocate build` builds it from
`runtime/` of the checkout it was installed from, together with the `.inc`
files the converter writes for each game. What happens between the game
and the ROM is in `internals/pipeline.md` in the book, and the audio in
`internals/audio.md` in the book.

**GitHub Actions checks every push to `main`**
(`.github/workflows/ci.yml`): the Rust workspace is formatted and passes
clippy —`just lint-rust`—, builds without a compiler warning and its tests
pass, `just test` passes, and the test game —made with the tools installed
from that commit, with cc65 and the two libretro cores built from pinned
commits and a free SoundFont— passes its tests in snes9x and in bsnes, and
Goombario finds nothing in its cartridges —`just lint-runtime`—. `just
lint` is both. It runs no ported game, so it
does not replace A Blurred Line's suite, below.

A game is a directory with an `advocate.toml`, which the tools look for
from where they run upwards, the way cargo looks for its `Cargo.toml`; what
belongs to the machine —where the original game is, the RTP, the
SoundFont— reaches them through flags. **There is no `justfile` at the
root**: until 2026-10-02 it was ABL's, which imported its own, and the
tools' one uses `justfile_directory()` to find its things, so imported from
the root it would look for them in the wrong place.

## The ROM tests are mostly in ABL, for now

The tests in `tests/` and those of each Rust project test each stage
alone, with small games made inside the test. The ones that build a
cartridge and run it in an emulator, against goldens, belonged to A Blurred
Line and left with it on 2026-10-02, because they need a game: most of
them test the engine using ABL as a stage.

The test game, `test-game/`, is where they come back to: a game of our
own, made from scratch and with no copyrighted assets, whose tests run its
cartridge here and in CI —phase 2 of the study that planned the split,
`research/2026-10-02-the-test-game.md` in the book, finished on
2026-11-22 with the harness's generic part, `rm2k-snes/harness/`, and ABL's
first ten engine tests—. The rest are still ABL's, so **a change in the
tools is still verified by running ABL's suite with the tools of the
change** as well: how, in "Where this runs" in `AGENTS.md`.

## Licence

The Advocate is free software, under the **GNU General Public License,
version 3 or any later version**: `LICENSE`. taro's, from 2026-11-28.
`snes/spc-dsp/vendor/snes_spc/` is blargg's snes_spc, under the GNU LGPL
2.1 or later, which lets it go into a GPL work: its README says so, and
`snes/spc-dsp/NOTICE` is what the releases carry about it.
