# rm2k-snes-mapdata: the data `.inc` of a converted cartridge

    rm2k-snes-mapdata emit --data dump/ --request request.json --out build/ --raw build/crudos/

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
what it takes and what it writes.

A Super Nintendo cartridge converted from an RPG Maker 2000 game is its
runtime —the engine, in 65816 assembly— assembled together with one `.inc`
of data: the constants the runtime is built with and every table it reads.
This writes that `.inc`, from what every other stage of the conversion
answered: each map's record, blocks, pages, objects and poses; the message
window and its font; the title and the full screens; the slots screen, the
pause menu and the text screens; the items, the equipment, the skills; the
battle, its troops, their pages and its scene; and the tables the console
reads from bank 0.

It decides nothing that is not about how the cartridge carries it: which
blocks are shared, how each is cut into LZ2 streams and whether each stream
fits where the console decompresses it, which segment each table goes in
and which ones are declared with `.block` so the packing does not split
them. And it owns the cartridge's **VRAM layouts**, which are the contract
with the runtime: the maps and the screens read them from here.

It is a stage of a converter, with the shape `rm2k-snes/battle/README.md`
describes in "One stage of a converter": it reads the database from a
Ditto dump itself —with `rm2k-snes-battle`'s `Db` and its rules for what an
actor has at its level—, gets in a request what the other stages answered,
and writes pieces and a JSON.

## The subcommands

* `emit`: the whole `.inc`. The request is `Emit` in `src/request.rs`: the
  maps as `wally` and the event compiler left them, the answer of
  `rm2k-snes-screens convert` as it came, the battle model and tables of
  `rm2k-snes-battle`, the troops' pages of the compiler, and what other
  domains decided already as bytes and numbers —the battle animations'
  frames as they end up in VRAM, the scene's backdrops and battlers—. It
  writes `mapdata.inc` and `mapdata.json`, with what it says while it
  writes, what was shared and compressed, and how many frames each map
  takes to decompress; with `--raw`, each map's decompressed blocks, which
  the game's tests compare against what the console loads.
* `maps`: only what goes per map, in three pieces of the `.inc`.
* `pages`: one map's page table, alone, for whoever checks which label it
  names.
* `compress`: the LZ2 streams of some maps' blocks, each part once, for
  whoever round-trips them through another decompressor.
* `vram`: the VRAM layouts, the constants of the cartridge's memory, and
  which layout each of the request's maps gets. The layouts are checked
  against the hardware on every call.

## Where the numbers come from

The engine's numbers —RM2k's, taken from easyrpg-player where they say,
and the console's caps— are in `src/engine.rs` and `src/record.rs`; the
ones measured against A Blurred Line say so. The long templates of
constants keep the text the converter always wrote, and `src/pyfmt.rs`
fills them as Python's `%` did, so that the `.inc` comes out the same
character by character.

## Its tests

They need no game. `tests/python.rs` compares what this writes against the
SHA-256 of what the converter's Python wrote for the same input before it
was deleted: maps made up to go through every path (`tests/maps.json`), and
two whole cartridges over them (`tests/emit-*.json`) with the database of
`rm2k-snes-battle`'s test game.
