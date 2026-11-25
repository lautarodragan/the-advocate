# rm2k-snes-cartridge

What turns a converted RPG Maker 2000 game into Super NES cartridges, and says
how much room they have left. A library: `advocate build` (`../advocate/`)
is the command over it.

* **The cartridges** (`cartridges.rs`): which ones the project declares,
  whether each is up to date, and building them —the converter, the
  assembling and the MSU-1 tracks for each—.
* **The assembling** (`assemble.rs`, `banks.rs`): the bank packing, `ca65` +
  `ld65`, the header checksum and the symbols.
* **The space** (`space.rs`): how much is left in each bank and each RAM
  area.

It reads the game's `advocate.toml` through `rm2k-project` (see
`../project/`), and calls the rest of the suite as libraries: the converter
(`rm2k-snes-convert`) and the MSU-1 tracks (`rm2k-snes-audio`'s `tracks`).
What it runs is not ours: `ca65` and `ld65`, from the cc65 project, and the
tracks' synthesizer and encoder. Until 2026-11-25 it had a binary,
`rm2k-snes-cartridges`, with `assemble` and `space` subcommands, which ran
the converter and `rm2k-snes-audio msu` as processes; until 2026-11-23
those subcommands were executables of their own, `rm2k-snes-assemble` and
`rm2k-snes-space`.

## The cartridges

**What each cartridge carries belongs to the game**, in `[cartridges]`: the
starting map, the party, the maps —a list, or `"game"` for the rule in
`[maps]`—, the test graphics, extra converter flags and the cases —a list, or
`"all"`—. `release` is required and carries all the cases: it is the ROM that
is played, and its MSU-1 tracks are made with it.

**A cartridge is rebuilt when its stamp does not match.** The stamp,
`stamp.txt` next to the ROM, carries three things:

    inputs <16 hex digits>        the fingerprint, below
    flags ["--map-id", …]         the converter flags, the maps expanded
    case <name> <sha256>          one line per case, in page order

The fingerprint hashes everything that changes a ROM without changing its
flags: the whole runtime, `ca65`, `ld65`, the running builder —with the
converter, its stages and the bank packing, which are libraries compiled
into it; not whichever is first on the PATH—, the game's dump, the
hand-made patches, the project file and each song's volume headroom, and
the original game's resources —every `.png`, `.bmp`, `.xyz`, `.mid` and
`.wav` below `--game-dir`, with its name—. Contents, never dates. The RTP
and the SoundFont go in **by their path**: after changing one in place,
`--force` builds even what is up to date. Without `--game-dir` the
fingerprint is an error.

`describe` is what a game's test suite reads instead of importing any of
this, inside the `build/advocate.json` that `advocate build` leaves: where
each cartridge and its ROM are, its flags, its cases and whether each starts
with a `Teleport`, whether it is stale and why **when the build ended**,
which cartridge a case runs in, the maps, and the files in the fingerprint.

## The assembling

**The bank packing.** A DMA that crosses a bank wraps around inside it, and
does not read the next bank, so everything the ROM uploads by DMA has to fit whole in one bank. `ld65`
cannot pack variable-size blocks, so the generated data sends everything to
`RODATA` with a directive in front of each piece —`.block N` for one that
must not be split, `.crossbank` for one walked by code that jumps banks by
hand—, and this packs the pieces first-fit decreasing into `BANKnn` segments,
**rewriting the generated files in place**, before `ca65` runs. The fast
banks fill first, and what crosses banks by hand only crosses between two
that continue each other. Every label
of more than one byte has to be covered by one of the two directives, and
that is enforced on every build, not on the day the cut lands on one.

Which files are "generated" is not a list of names: they are the `.include`s
found in the cartridge's directory. One that is also next to the file
including it is refused, because `ca65` would read that one first and the ROM
would come out with another build's data.

Then it writes the memory map, `memory.cfg`, next to the generated files
—8 MB ExHiROM, one area per data bank, the code's first two banks linked as
LoROM's banks 0 and 1, and the third at `$C0:0000`—, runs `ca65` and `ld65` standing in the directory
above the tools so the debug file names sources by relative paths, copies the
two LoROM code banks to the second 4 MB, where the console reaches them through
banks `$00` and `$01`, writes the header checksum and a table of `name value`
lines, the symbols. Why the map is the way it is, in the docs of
`src/banks.rs`.

`sources` gives the `.s` files a main file includes, in the order `ca65`
reads them, and `memory_map` the map's numbers: both go into
`build/advocate.json`.

## The space

It reads what the build left —the debug file and the memory map— and relinks
nothing: data banks used and free —whole banks of 64 KB, fast and slow, and
halves—, the gaps inside the used ones, what is left in the code banks —0, 1, `$C0`, `$C1` and `$FF`—,
in the BSS and the zero page, and in the text block. **The number that
matters is how many whole banks are free**, not a percentage. It is measured
when a cartridge is built, into `space.json` beside its ROM.

## Tests

    cargo test

The packing, the memory map, the checksum, the symbols and what the
cartridges read from a project are tested on files and games made inside the
test. That the ROMs come out right is enforced by whatever runs them.
