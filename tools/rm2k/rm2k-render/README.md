# rm2k-render: an RPG Maker 2000 game's graphics, as pictures

    rm2k-render layers --map 7 --data dump/ --game-dir game/ --rtp-dir rtp/ --out map7/
    rm2k-render layers --request map.json --chipset-file ChipSet/Town.png --out map7/
    rm2k-render atlas --chipset Town --game-dir game/ --rtp-dir rtp/ -o town-atlas.png
    rm2k-render charset --request charsets.json --out sheets/

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
what it writes.

It draws what RM2k draws, the way RM2k draws it, and nothing about what
anyone does with the pictures afterwards. Today that is a map's tile layers
and what its events are drawn with; where the line is drawn, piece by
piece, is whether a viewer of the game on a PC would draw it the same way.

A map is two layers of tile ids and a ChipSet. `layers` draws them the way
RM2k stacks them around the hero, and nothing else: no panorama, no events,
no hero. Where the files go is the caller's business, and so is where the
game and the RTP are: nothing here has a default path, and nothing here
knows which game a map is from.

## What comes out

`layers` writes, into the `--out` directory:

* `lower.png`: what is drawn **behind** the hero, on opaque black;
* `upper.png`: what is drawn **in front** of it, on transparency;
* for each animated family the map uses, its other drawings behind the hero:
  `water-1.png` and `water-2.png` for the three drawings of the water,
  `animated-1.png` to `animated-3.png` for the four of the animated tiles.
  Drawing 0 is `lower.png`.

A family the map does not use gets no files, and files of one left there by
an earlier call are removed: which families a map animates is read from
which files exist. All of them are RGBA PNGs at eight bits.

Which side of the hero a tile goes on is not the layer it sits on but the
ChipSet's passability: a lower-layer tile with either of the `0x30` bits, or
an upper-layer one with the star, `0x10`, goes in front. Both layers are
drawn cell by cell, lower tile first. That rule, the passability table it
reads and where each piece of the ChipSet is are RM2k's, and they are
`rm2k-rules`' (`tools/rm2k/rules/`): what stays here is the drawing.

`atlas` writes the ChipSet expanded: 32 tiles by 45, every combination of
every autotile, in the order the tile ids index them. It is what every
drawing above is copied from.

## Where the map comes from

**`--map N`** reads map `N` from the Ditto dump in **`--data`**, with
Ditto's own library: the map with its layers, and its ChipSet's entry from
the database's `chipsets`. Either of Ditto's views will do, and it has to
be a dump —its `ditto.json` says which view and which version—. Like the
game and the RTP, where the dump is is the caller's to say: this does not
look for it.

That is the dump **as Ditto wrote it**. A caller that changes the map before
drawing it —patches it, puts something into a layer— sends it as a
**`--request`**: a JSON file that is a piece of the dump, a `Map` and its
`Chipset`, read with Ditto's types. A field it leaves out holds the
format's default, as in Ditto's exact dump.

    {"width": 3, "height": 2,
     "lower_layer": [0, 3000, 4000, 5000, 5001, 5002],
     "upper_layer": [10000, 10001, 10000, 10000, 10000, 10000],
     "chipset": {"chipset_name": "Town",
                 "passable_data_lower": [15, ...],
                 "passable_data_upper": [15, ...]}}

## Where the ChipSet comes from

By name, in `<game>/ChipSet/` and then `<rtp>/ChipSet/`, **without regard
to case** —RM2k stores names without extension, and the games were made on
Windows—; or `--chipset-file`, which skips the lookup. A caller that also
keys a cache on the ChipSet's bytes wants the second: then the file it
hashed and the file drawn cannot be two different ones.

In an **indexed** ChipSet, index 0 is the colour key, whatever the file's
own transparency chunk says: that is how RM2k draws them. Grey, RGB and
RGBA at eight bits are read too, with the transparency they declare. BMP
is refused: RM2k takes them, but no ChipSet this has been checked against is
one.

## The autotiles

The left half of a ChipSet is not tiles but pieces: the three waters, their
depth edges, three animated tiles and twelve terrains, which the editor
combines according to the neighbours and stores in the map as an id per
combination. The offsets that assemble each combination are EasyRPG Tools'
`lmu2png`, whose author wrote that it was easier to write them down than to
work out the rule behind them. They are here as they were there.

## Exactly those pixels

Every copy is **through the source's alpha**, blended as integers with the
division by 255 rounded as `((v + 128) >> 8 + v + 128) >> 8`. With an
indexed ChipSet the alpha is only 0 or 255 and the blend is a plain copy;
with half transparencies the rounding shows, and a tile reaches a map
through two copies —ChipSet to atlas, atlas to map—, each one rounding.

That is not a style choice. Until this crate existed the same layers were
drawn by a Python port of the same code, and what this draws was checked
equal to it, pixel for pixel, on every map of a whole game. `tests/python.rs`
keeps the SHA-256 of what that Python drew for a ChipSet and a map generated
inside the test —an indexed one and a half-transparent one—, so the check
does not need the Python, nor the game.

## What an event is drawn with

`charset` draws **CharSet sheets**: the picture a character's 24x32 poses
are cut from, 4 characters by 2 of 12 poses each, in RM2k's layout. Cutting
a pose is the caller's, and so is whatever a pose becomes afterwards. It
takes a JSON request, a list with an entry per sheet, and writes sheet `i`
as `<i>.png` in `--out`, an RGBA PNG at eight bits:

    [{"charset_file": "CharSet/Hero.png"},
     {"chipset_file": "ChipSet/Town.png", "tile": 12},
     {"charset_file": "CharSet/Ghost.png",
      "translucent": {"behind": "lower.png", "x": 7, "y": 4}}]

* **`charset_file`** is a CharSet with its colour key, as the ChipSets are
  read: the poses are already where RM2k looks for them.
* **`chipset_file` and `tile`** are an event drawn with no CharSet: RM2k
  draws tile `tile` —0 to 143— of the ChipSet's upper layer where the event
  stands, whichever way it faces or steps. The sheet has that tile in the
  twelve poses of character 0, standing on its cell the way a pose stands
  on it —4 pixels in, 16 down—, so it can be cut like any other.
* **`translucent`** is a page with RM2k's "translucent" set, which it draws
  at 160 of 255 over whatever is behind. `behind` is an RGBA picture of
  that —for example `lower.png` from `layers`— and `x`, `y` the cell the
  event stands on: every pose is blended over the piece of it the pose would
  cover there, and comes out **opaque** where it has pixels. Past the edges
  of `behind` there is nothing, which RM2k shows as black. What to put
  behind is the caller's to choose.

Paths are relative to the request. A request is one process for as many
sheets as it lists, and a picture several entries share is read once: a
caller that needs many sheets is better off asking for them together.

The blend is `(over * 160 + under * 95) / 255` rounded **down**, and the
sheet's own alpha does not weigh in: any pixel that is not fully
transparent is mixed whole. The tile of a tile event is copied through its
alpha twice, like a tile of the layers. Both are what the Python that drew
these before gave, and `tests/charsets.rs` keeps its hashes for CharSets,
ChipSets and a background generated inside the test.

## Exit codes

`1` when the answer is no: the ChipSet is not there, a layer does not have
`width * height` tiles, a tile id is outside 0 to 65535, the passability is
shorter than 162 and 144 entries, a `charset` entry is neither of the two
kinds or asks for a tile past 143. `2` when the call is wrong: a missing
flag, a file that cannot be read.
