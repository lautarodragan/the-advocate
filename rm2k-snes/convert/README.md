# rm2k-snes-convert: an RPG Maker 2000 game into a cartridge's data

    rm2k-snes-convert --project game/ --game-dir original/ --rtp-dir rtp/ \
        --soundfont bank.sf2 -o build/mapdata.inc --msu build/game.msu \
        --map-id 4 --maps 1 2 3

`cargo build --release`, or `cargo test`. `--help` prints every flag.

A Super Nintendo cartridge converted from an RPG Maker 2000 game is the
suite's runtime assembled together with the data the conversion writes:
`mapdata.inc` and `musicdata.inc`, the `.msu`, and what the conversion
decided to lose. Every domain of that conversion is a **stage** of its own,
a program on the PATH with the shape `rm2k-snes/battle/README.md` describes
in "One stage of a converter": it reads the game from the Ditto dump
itself, gets in a request what the cartridge decided and the dump does not
say, and writes what it made. This is the program that asks them, in order:

1. the text boxes reflowed for the console's window (`rm2k-snes-screens
   boxes`), and the event compiler's first call (`rm2k-snes-events scan`):
   the whole game's indices and which pages of each map compile;
2. each map (`wally map`), in parallel;
3. the battle's tables (`rm2k-snes-battle tables`): experience and each
   map's random encounters, with the troops they name;
4. every page of the cartridge (`rm2k-snes-events compile`);
5. the screens (`rm2k-snes-screens convert`), the title and the Game Over
   (`rm2k-snes-images fullscreen`), the battle animations, backdrops and
   battlers (`rm2k-snes-images`) and the battle's model (`rm2k-snes-battle
   model`);
6. the emission (`rm2k-snes-mapdata emit`), which writes the `.inc`;
7. the patches (`rm2k-snes-patches`) and the music (`rm2k-snes-audio
   cartridge`), which write next to it.

What it decides itself is what joins them, and none of it is a rule of
RPG Maker nor a format of the console —those are the stages', and
`rm2k-rules`'—:

* **which maps and which test pages** the cartridge carries: the maps in
  table order, which is the order a compiled teleport counts in, and each
  test page —`--test-commands`, one per `--case`— in the map its first
  `Teleport` goes to;
* **who can lead the party** in each map, by simulating the
  `ChangePartyMembers` of the pages that compile, batch by batch: the
  hero's poses have to be in VRAM before the leader changes;
* **which items and actors** the cartridge needs a name and a face for,
  **where the timer can run** —its digits cost a sprite palette—, and
  whether it rains;
* **which pictures, animations, backdrops and battlers** go in, and where
  each lands: what the map has room for, what the bytecode shows, what
  each battle can ask for;
* **the checks of the compiled pages** against the runtime's caps, which
  the console cannot warn about: events with a parallel page, events a map
  sends walking, blocks a map substitutes, a hero that flashes with an NPC.

And it builds the images of the ChipSets the project adds, from their
recipe (`src/chipsets.rs`): the art is not the project's to version, so the
project keeps which block is copied where, and the image is built into the
project's build, where `wally` finds it first.

## What the project says

The project file —`advocate.toml`, found from the current directory or
with `--project`— says where the dump, the build and the manual patches
are, and what the game decided: the opaque translucent graphics, the
palette weights, the maps the timer never runs in, the pictures cropped to
the console's screen instead of scaled, the counters, the sound
effects, the fallback backdrop, the ROM's title and save signature. A key it
does not declare is an error, never a default. The manual patches —a map
redone, a map the game lacks, a ChipSet added— are validated whole on every
run (`src/fork.rs`), and apply only to the project's own dump.

Where the machine keeps the original game, the RTP and the SoundFont comes
by flags, `--game-dir`, `--rtp-dir` and `--soundfont`, with no default.
`TRANSLUCENT_MODE=dither` and `DITHER_PATTERN` choose how a translucent page
is drawn, to compare the ways on the same tree.

## Tests

`cargo test` needs no game: the scans run over small maps made inside the
test, the bytes of the scene and the pictures over drawings made there too,
and the manual patches over a folder of its own. That every stage gets the
request it always got is what the game's cartridges say, built byte by byte
the same as before this was Rust.
