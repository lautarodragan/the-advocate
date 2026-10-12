# From RPG Maker 2000 to the Super Nintendo

The tools that port a game made in RPG Maker 2000 to the Super Nintendo,
and the runtime —the engine in assembly— that runs it on the console: how
an RM2k game is read, how it is converted, and the architectural whys that
have no line of code to live in. The idea is an "RPG Maker 2000 PLUS":
compatible with RM2k, and with whatever is added available to any game
(`decisions/rm2k-plus.md` in the book).

It was born porting *A Blurred Line*, and **ABL lives in its own repo**
since 2026-10-02: its data, its patches, its tests and its goldens. The
history of what was its own stayed here, in `git log`.

What is **not** here: where we left off, which is the `the-advocate-work`
repo; how each part of the port works today, which is `internals/` in the
book and the comments in the code; and the story of how we got here, which
is in `git log`. What is in each folder is said by the map at the top of
`AGENTS.md`, and `LAYOUT.md` gives the one of this repo's folders.

**`AGENTS.md` —how work is done— is not here either**: there is a single
one for all the repos, with the roster of sub-agents, in
`the-advocate-work`, since 2026-10-10. A "see AGENTS.md" in a comment of
this repo is that one.

## Contents

* [How it is installed](#how-it-is-installed)
* [The ROM tests are in ABL, for now](#the-rom-tests-are-in-abl-for-now)
* [The architecture](#the-architecture)
    * [The background goes in mode 3, always](#the-background-goes-in-mode-3-always)
    * [The cartridge is ExHiROM, of 8 MB](#the-cartridge-is-exhirom-of-8-mb)
    * [The tables go in bank 0](#the-tables-go-in-bank-0)
* [What is missing](#what-is-missing)
* [References](#references)

## How it is installed

**It needs `python`, a libretro core and `ca65` + `ld65`**, and the tools
—the Rust projects, which `LAYOUT.md` lists— are installed on the PATH. A
game consumes them from there, and no script or test of a game calls
`cargo`: the why is in `AGENTS.md`. `ca65` and `ld65` come from cc65,
which is not packaged in every distribution and is compiled from its
sources: see "References".

    just install   # installs the tools on the PATH
    just test      # the repo's Python tests
    just rust-test # those of every Rust project

The runtime travels with the tools: `rm2k-snes-cartridges` builds it from
`runtime/` of the checkout it was installed from, together with the `.inc`
files the converter writes for each game. What happens between the game
and the ROM is in `internals/pipeline.md` in the book, and the audio in
`internals/audio.md` in the book.

A game is a directory with an `rm2k-snes.toml`, which the tools look for
from where they run upwards, the way cargo looks for its `Cargo.toml`; what
belongs to the machine —where the original game is, the RTP, the
SoundFont— reaches them through flags. **There is no `justfile` at the
root**: until 2026-10-02 it was ABL's, which imported its own, and the
tools' one uses `justfile_directory()` to find its things, so imported from
the root it would look for them in the wrong place.

## The ROM tests are in ABL, for now

**Today this repo has no tests that run a ROM.** The ones it has —those in
`tests/` and those of each Rust project— test each stage alone, with small
games made inside the test. The ones that build a cartridge and run it in
an emulator, against goldens, belong to A Blurred Line and left with it,
because they need a game: most of them test the engine using ABL as a
stage.

So **a change in the tools is verified by running ABL's suite with the
tools of the change**: how, in "Where this runs" in `AGENTS.md`. It is the
risk pointed out by the study that planned the split
(`research/2026-10-02-el-juego-de-pruebas.md` in the book), and its phase
2 cuts it: a test game of our own, made from scratch and with no
copyrighted assets, where the engine's tests move to.

## The architecture

### The background goes in mode 3, always

The map goes in **mode 3, with 8 bits per pixel**, on every map. There each
background pixel is a direct index into CGRAM and there is no palette per
tile, so the problem of splitting the colours into groups such that no
tile needs two does not exist. It could not be avoided any other way: there
are maps with tiles of 16, 17 and 19 colours, and those do not fit in a
palette of 15 however many palettes there are. It costs twice the VRAM per
tile, 64 bytes instead of 32.

The price is that mode 3 has **two background layers and nothing more**:
BG1 is the map and BG2 the upper layer together with the message window.
What in RM2k would ask for a third one —the panorama, the rain as a layer—
has nowhere to go, and the sprites stay at 4 bits: 15 colours and the
transparent one, which Adeleine picks (`snes/adeleine/`). How VRAM and
CGRAM are split map by map, in `internals/vram.md` in the book and
`internals/cgram.md` in the book.

**The exception, since 2026-10-05, is the panorama.** Wally chooses for
each map, with what the map and its panorama say and nothing else, how it
is shown: if it is never seen, nothing; if it does not move against the
map, baked into the background; if the map draws nothing above the hero,
in BG2 in mode 3; if it draws little, in BG2 too, with what is above in the
background and BG1's priority; and if it draws more, the map goes in mode
1, at 4 bits, and the panorama in BG3. See `Way` in
`rm2k-snes/wally/src/background/panorama.rs`, `runtime/pano.s` and, for
what was measured, `research/2026-10-05-los-panoramas.md` in the book.

### The cartridge is ExHiROM, of 8 MB

Since 2026-10-01, because the whole game does not fit in 4 MB with any
cut: see `decisions/el-cartucho-pasa-a-8-mb.md` in the book. Until that day
it was **LoROM**, and the code was written for LoROM; what changed and what
did not has a reason that is in no line:

* **The data goes in banks of 64 KB, from `$0000`**, and the next bank
  follows the previous one: what is walked by hand across banks —the music
  stream, the samples uploaded to the SPC700, the text block— only adds one
  to the bank. In LoROM each bank was the 32 KB from `$8000` to `$FFFF`,
  and the next one continued from its `$8000`.
* **The code still sees banks 0 and 1 as in LoROM**: 32 KB from `$8000`, at
  `$00` and at its fast mirror, `$80`. In ExHiROM those are not the same
  ROM —`$80` is from the first 4 MB and `$00` from the second—, so the
  build puts the two code banks twice in the file. It costs 64 KB, and in
  exchange the runtime did not notice: the vectors still land in `$00`, the
  `jml` to `+ FAST` still leads to the fast mirror, and Mednafen —which
  with `snes_faust` reads `$80-$BF` from the second 4 MB, unlike the
  cartridge— sees the same as the console.
* **The third code bank is not LoROM's**: `FAR2`, since 2026-10-02, is the
  low half of `$C0`, fast and without a copy, because what lives there is
  only entered with a `jsl` to its address. Which code goes in which of the
  three is said by the header of `runtime/main.s`.
* **Only the first 4 MB are fast**: FastROM does not reach banks
  `$40-$7D`. The packing fills the fast ones first.
* **There is ROM that is not used**: the low halves of `$70-$7D`, where
  Mesen2 and mesen-s put the SRAM even if the cartridge has ROM, and those
  of `$7E` and `$7F`, which are the WRAM.
* **The SRAM is at `$20:6000`**, 8 KB, and LoROM saves do not load.

All of that came out of a test ROM run on five emulators before moving the
game, which is ABL's `exhirom` recipe; the detail, in the documentation of
`banks.rs`, in `rm2k-snes/cartridge/src/`.

### The tables go in bank 0

Bank 0 is the code's, and the CPU sees its 32 KB from `$8000` to `$FFFF`:
see above.

`lda table, x` addresses **the data bank register**, not the bank where the
table is. That register is 0 and we never touch it —except in the battle,
which sets it to `$7E` and says so—, so a table in another bank is read
from the wrong place, with no error at all, with bytes that happen to be
there. And it is easy to half-fix, because what keeps working are the
direct writes and the DMA clears, which carry the bank explicitly: enough
for the screen corruption to go away and the underlying bug to stay.

So there is a `TABLES` segment that the linker puts in bank 0, and
everything the CPU walks with an index has to be there. **And bank 0 is 32
KB, so the table that grows with the content moves out**: it is read with
`lda f:table, x`, which carries the bank in the instruction; it costs one
byte per instruction and **forces the index to be X**, because absolute
long addressing indexed with Y does not exist.

What does not fit in a bank cannot be walked with an index: the cell grid
of a large map does not fit, and it is read with a 24-bit pointer. It lives
decompressed in the upper half of the two WRAM banks —see
`decisions/la-grilla-vive-en-la-wram.md` in the book and
`internals/maps.md` in the book—, which has the same shape as a LoROM
bank: going past `$FFFF` does not lead to the next bank's `$0000` but to
its `$8000`. `ptr_more` and `ptr_minus` are the only routines that know
that; everything else uses them and forgets about it.

And a moved table, or one that is walked with `[ptr], y`, **has to be
declared with `.block`** so as not to end up split between two banks: see
`block` in `asm.rs` of `rm2k-snes/mapdata/`. The packing refuses to build
with an undeclared RODATA label, and what crosses on purpose —the music
stream, what is uploaded to the SPC700— carries `.crossbank`, and crosses
only between two banks that follow each other: the split is done by
`rm2k-snes-assemble` before `ca65`, see `resolve` in
`rm2k-snes/cartridge/src/banks.rs`.

## What is missing

It is not written here, because here it aged without anyone noticing:

* what was decided and not started is in the `todo` tasks of
  `the-advocate-work`, and what we would like and nobody is doing in the
  `wishlist` ones —`nu tasks/tasks.nu ls -s todo`, standing there—;
* where the ROM does not do what RM2k does, in `divergences/` in the book;
* which event commands are accepted without being done is said by
  `ACCEPTED_UNDONE`, in the event compiler (`rm2k-snes/events/`), which is
  an executable list and cannot go out of sync;
* and what no test looks at, in ABL's `pruebas/UNTESTED.md`.

## References

**The numbers and the semantics come from here, not from memory**: it
already happened once that three RM2k command codes were put in from
memory and were wrong.

RPG Maker 2000:

* [liblcf](https://github.com/EasyRPG/liblcf) — the LCF format, the chunk
  ids and the command codes; Ditto's schema comes from there
* [EasyRPG Player](https://github.com/EasyRPG/Player) — the reference
  interpreter: what each command and each move command does
* [Game-Decompilations](https://github.com/SamidyFR/Game-Decompilations) —
  a list of decompilations, for what EasyRPG does not explain

The console:

* [fullsnes](https://problemkaputt.de/fullsnes.htm), by nocash — the
  reference for the whole hardware
* anomie's documents —registers, timings, the SPC700—, which most of the
  other references cite
* the [superfamicom.org wiki](https://wiki.superfamicom.org/)
* "SNES translucency FAQ", by Bregalad (2009, revised in 2015) — colour
  math explained; it is a third party's and does not come with the repo:
  it is found by its title
* [sd2snes](https://github.com/mrehkopf/sd2snes) — the FX Pak Pro's
  firmware: how it really implements the MSU-1
* [the Final Fantasy VI disassembly](https://github.com/everything8215/ff6)
  — text as one byte per letter that the 65816 composes, which is what the
  message window does

The emulators, which besides running the ROM are the code that is read
when the documentation is not enough —which ones are used for testing by
hand and what each one implements, in `reference/snes/emulators.md` in the
book—:

* [bsnes](https://github.com/bsnes-emu/bsnes),
  [snes9x](https://github.com/snes9xgit/snes9x),
  [Mesen2](https://github.com/SourMesen/Mesen2),
  [Mesen-S](https://github.com/SourMesen/Mesen-S),
  [ares](https://github.com/ares-emulator/ares) and
  [Mednafen](https://mednafen.github.io/)

And [cc65](https://github.com/cc65/cc65), where `ca65` and `ld65` come from.
