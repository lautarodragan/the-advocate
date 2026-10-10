# rm2k-snes-cartridge

What turns a converted RPG Maker 2000 game into Super NES cartridges, and says
how much room they have left. Three executables share one library:

    rm2k-snes-cartridges    which cartridges the project declares; builds the stale ones
    rm2k-snes-assemble      bank packing, ca65 + ld65, header checksum, symbols
    rm2k-snes-space         how much is left in each bank and each RAM area

They read the game's `rm2k-snes.toml` through `rm2k-project` (see
`../project/`), and run the rest of the suite **from the PATH**: the converter
(`rm2k-snes-convert`), the MSU-1 tracks (`rm2k-snes-msu`) and `ca65`/`ld65`,
from the cc65 project.

## `rm2k-snes-cartridges`

    rm2k-snes-cartridges                 builds whatever is not up to date
    rm2k-snes-cartridges release         only that one, with its MSU-1 tracks
    rm2k-snes-cartridges --list          which case goes in which cartridge
    rm2k-snes-cartridges --list --json   everything a test suite needs to know
    rm2k-snes-cartridges release --convert-into DIR -- --converter-flag
                                         a copy somewhere else, with more flags

**What each cartridge carries belongs to the game**, in `[cartridges]`: the
starting map, the party, the maps —a list, or `"game"` for the rule in
`[maps]`—, the test graphics, extra converter flags and the cases —a list, or
`"all"`—. `release` is required and carries all the cases: it is the ROM that
is played, and its MSU-1 tracks are made with it.

**A cartridge is rebuilt when its stamp does not match.** The stamp,
`sello.txt` next to the ROM, carries three things:

    inputs <16 hex digits>        the fingerprint, below
    flags ["--map-id", …]         the converter flags, the maps expanded
    case <name> <sha256>          one line per case, in page order

The fingerprint hashes everything that changes a ROM without changing its
flags: the whole runtime, `ca65`, `ld65`, the binaries the converter runs,
`rm2k-snes-assemble` —the bank packing lives there—, the converter's Python
sources, the hand-made patches, the project file and each song's volume
headroom. Contents, never dates.

`--list --json` is what a game's test suite reads instead of importing any of
this: where each cartridge and its ROM are, its flags, its cases and whether
each starts with a `Teleport`, whether it is stale and why, which cartridge a
case runs in, the maps, and the files in the fingerprint.

## `rm2k-snes-assemble`

    rm2k-snes-assemble runtime/main.s -I build/game -o build/game/game.sfc \
        --symbols build/game/game.sfc.sym
    rm2k-snes-assemble --sources runtime/main.s
    rm2k-snes-assemble --memory-map

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
found in the `-I` directory. One that is also next to the file including it
is refused, because `ca65` would read that one first and the ROM would come
out with another build's data.

Then it writes the memory map, `memoria.cfg`, next to the generated files
—8 MB ExHiROM, one area per data bank, the code's first two banks linked as
LoROM's banks 0 and 1, and the third at `$C0:0000`—, runs `ca65` and `ld65` standing in the directory
above the tools so the debug file names sources by relative paths, copies the
two LoROM code banks to the second 4 MB, where the console reaches them through
banks `$00` and `$01`, writes the header checksum and, with `--symbols`, a
table of `name value` lines. Why the map is the way it is, in the docs of
`src/banks.rs`.

`--sources` prints the `.s` files a main file includes, in the order `ca65`
reads them; `--memory-map`, the map's numbers as JSON.

## `rm2k-snes-space`

    rm2k-snes-space                 every cartridge
    rm2k-snes-space release         only that one
    rm2k-snes-space DIR/game.sfc    a ROM built separately
    rm2k-snes-space --json …        the same, as JSON

It reads what the build left —the debug file and the memory map— and relinks
nothing: data banks used and free —whole banks of 64 KB, fast and slow, and
halves—, the gaps inside the used ones, what is left in the three code banks —0, 1 and `$C0`—,
in the BSS and the zero page, and in the text block. **The number that
matters is how many whole banks are free**, not a percentage. A stale cartridge is refused.

## Tests

    cargo test

The packing, the memory map, the checksum, the symbols and what the
cartridges read from a project are tested on files and games made inside the
test. That the ROMs come out right is enforced by whatever runs them.
