# rm2k-snes-maps: an RPG Maker 2000 game's maps, as a cartridge carries them

    rm2k-snes-maps map --data dump/ --search-dir pictures/ --request request.json --out build/map/

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
what it takes and what it writes.

A map on the console is two background layers in mode 3 —the one behind the
hero at 8 bits a pixel, the one in front at 4—, the events drawn as 32x32
objects in eight palettes of fifteen colours, and a table of 16x16 blocks
the console redraws its tilemap window from. This makes all of it, a map
per call:

* **the layers**: drawn as RM2k draws them, cut to 15 bits, with the lower
  half of colour memory split between the two, what is lost when it does
  not fit, and each converted to tiles, with the runs of the ChipSet's
  animation;
* **the events baked into them**: an opaque event drawn with a ChipSet tile
  that never moves goes into the upper layer instead of being a sprite,
  unless that moves anybody else's colours;
* **the objects**: which events are drawn, which poses each graphic can
  show, how the eight palettes are split —the leader candidates first and
  alone, the rest while they fit and with someone else's colours when they
  do not—, the VRAM bank with one pose per slot, the cartridge's bank of
  the twelve poses of whoever changes pose, and the timer's digits, the
  raindrops, a picture and the battle animation's box at the end;
* **the blocks and where the hero starts**.

It is a stage of a converter, with the shape `rm2k-snes/battle/README.md`
describes in "One stage of a converter": it reads the game from a Ditto
dump itself, gets in a request what the cartridge decided and what other
domains answered, and writes pieces and a JSON.

## Three crates

The work is two libraries that do not know each other, and this one, which
joins them:

* `rm2k-snes-map-background`: the lower half of colour memory and the two
  background layers, and the blocks;
* `rm2k-snes-map-sprites`: the upper half and the objects;
* `rm2k-snes-maps`: reading the map and its events, drawing the sheets,
  baking —which takes a sprite into a layer, so it needs both halves— and
  the whole map.

Cargo keeps the two halves apart: the day the objects want to look at a
layer, it is a dependency somebody has to write.

## The request

    {"map": 7,
     "map_files": {"11": "…/Map0011.json"}, "chipset_files": {"53": "…/0053.json"},
     "names": [[3, 1, "Ghost~horneado:7:4:5"]], "test_event": false,
     "leaders": [10, 1],
     "pages": [{"event": 2, "page": 0, "trigger": 0, "code": "0603…",
                "route_targets": [2], "own_route": null, "turns": true}],
     "route_graphics": [["People1", 3]], "also_walk": [],
     "timer": null, "rain": false, "picture": null,
     "battle_animation": false, "singles": [["People1", 3]],
     "palette_weight": {"savept": 1}, "dither": "five_of_eight"}

What the project put over the dump: `map_files` and `chipset_files`, its
own maps and the ChipSets it adds; `names`, the names the caller gives some
graphics —a translucent one baked against its cell, one drawn apart from
the hero—, by event and page id; and `test_event`, an empty event first in
the map where a test starts.

What the cartridge decided: `leaders`, the actors that can lead, the first
leading; `timer`, the System picture if the cartridge carries the timer in
this map; `rain`; `picture`, a `ShowPicture` picture this map owns, already
cut into tiles; `singles`, the graphics no other map of the cartridge has;
`palette_weight`, which CharSets are served first; and `dither`.

**What other domains answered, as data**: `pages` and `route_graphics` are
the event compiler's scan of the map, as it answered them —who walks is
what the compiled bytecode sends walking, and the compiler walks it: each
page record says whether it compiled, whom its code sends a route to,
whether it walks a route of its own and whether it turns—; from them and
the events that are drawn this stage decides who gets the twelve poses,
which still ones animate and who turns toward the hero (`moves.rs`), and
says so in its answer. `also_walk` are the events someone other than the
map's pages sends walking, like a test page. `battle_animation`, whether
some page draws a battle animation, is the animations'.

## What comes out

Into `--out`: what `layers` writes —the tiles of both layers, their
colour-memory words and tilemaps, the runs, the block table, the pictures
of what Adeleine decided, and `layers.json`—, `sprites.bin` and
`poses-<k>.bin`, and `map.json`, with the events baked, the events drawn,
the palettes and slots, the leader candidates' rows, the extras, the table
of command 34, where the hero starts, who walks, animates still and turns,
and **what the conversion says, in
order**, each note marked if it stops the conversion. The caller prints
them: an event that changes graphic and does not fit is a door the player
cannot open, and a build that does not stop there is worse than one that
does.

`bakeable` and `split` answer two questions a whole map does not show,
for whoever checks them against a real game: which events are baked and
what the table says of their cells, and how the palettes are split with a
given number of them.

## Where the numbers come from

The rules of RPG Maker —passability, which page shows, the poses of a
CharSet— are `rm2k-rules`'; the drawing, `rm2k-render`'s; which colours are
lost, Adeleine's; cutting tiles, Voodoo's. What is left here is the
console's: 15-bit colour, mode 3, 32x32 objects, eight palettes, a tile
name grid sixteen wide.
