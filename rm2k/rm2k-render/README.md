# rm2k-render: an RPG Maker 2000 game's graphics, as pictures

    rm2k-render layers --map 7 --data dump/ --game-dir game/ --rtp-dir rtp/ --out map7/
    rm2k-render layers --request map.json --chipset-file ChipSet/Town.png --out map7/
    rm2k-render atlas --chipset Town --game-dir game/ --rtp-dir rtp/ -o town-atlas.png
    rm2k-render charset --request charsets.json --out sheets/
    rm2k-render face --request faces.json --out faces/
    rm2k-render system --request windows.json --out windows/
    rm2k-render picture --request pictures.json --out pictures/
    rm2k-render battle-animation --request animations.json --out cells/
    rm2k-render battle --request battle.json --out pictures/

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
what it writes.

It draws what RM2k draws, the way RM2k draws it, and nothing about what
anyone does with the pictures afterwards. Today that is a map's tile layers,
what its events are drawn with, what its battles are drawn with —the
cells of a battle animation, backdrops and enemies—, and what the screens
are drawn with: faces, windows and `ShowPicture` pictures. Where the line is drawn, piece by
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
`rm2k-rules`' (`rm2k/rules/`): what stays here is the drawing.

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

## What the screens are drawn with

`face`, `system` and `picture` take a request like `charset`'s —a JSON
list, paths relative to it— and write picture `i` as `<i>.png`, RGBA. Each
entry names its own file, and a file several entries share is read once.
Every entry is checked and drawn before anything is written: a request with
a bad entry leaves the directory as it was.

    [{"faceset_file": "FaceSet/Actors.png", "index": 5}]

`face` cuts face `index` —0 to 15, four across— from a FaceSet, 48x48,
with its colour key: in a FaceSet too, index 0 is transparent.

    [{"system_file": "System/Blue.png", "draw": "window",
      "width": 256, "height": 80, "message_stretch": 0},
     {"system_file": "System/Blue.png", "draw": "cursor",
      "width": 120, "height": 16},
     {"system_file": "System/Blue.png", "draw": "text_color", "color": 0},
     {"system_file": "System/Blue.png", "draw": "shadow"},
     {"system_file": "System/Blue.png", "draw": "timer"}]

`system` draws from the System, the 160x80 picture every window is made
of:

* **`window`**: an empty window of that size, as easyrpg's `Window` makes
  it. The 32x32 background fills it **stretched** or **tiled**, as the
  database's `message_stretch` says —0 or 1, the number as the database
  has it; EasyRPG's own third value is refused—, and the frame goes on top:
  the 8x8 corners, and the edges repeated between them.
* **`cursor`**: the cursor of a list, laid out like the frame over
  transparency, with its middle repeated inside. `drawing` 1 is the second
  of the two it blinks between.
* **`text_color`** `color`, 0 to 19, and **`shadow`**: the 16x16 blocks a
  letter takes its pixels from, which is why RM2k's text has a gradient.
  Drawing letters with them is the caller's, with whatever font it has.
* **`timer`**: the timer's eleven 8x16 glyphs in a row, the digits and the
  colon.

Where each piece is in the System is `rm2k-rules`' (`system`). Two things
are the drawing this replaces' and not easyrpg's, and they are said here
because they only show with some Systems: the stretch picks the nearest
pixel the way Pillow's `NEAREST` does, and the edges repeat from where they
start —next to the corner—, where easyrpg repeats them from the window's
corner, half an edge off. With an edge that repeats every 8 pixels the two
are the same.

    [{"picture_file": "Picture/Sign.png",
      "use_transparent_color": true, "top_trans": 30}]

`picture` is the picture of a `ShowPicture` as RM2k puts it on the screen:
index 0 transparent **only** if the command asks for its transparent
colour, and every pixel at the opacity of `top_trans`, the transparency
from 0 to 100 —`255 * (100 - top_trans) / 100`, rounded down, which is
`rm2k-rules`' (`picture`)—. Where it goes, at what size and in which tone
is the caller's.

`tests/screens.rs` keeps the SHA-256 of what the Python that drew these
before gave for Systems —an indexed one and a half-transparent one—,
FaceSets and a picture generated inside the test; what that Python never
drew —the tiled background, the second cursor, a transparency— is checked
there against RM2k's rules.

## What a battle is drawn with

`battle-animation` draws **the cells of a battle animation**. A frame of
one is a list of cells, each a square of the animation's sheet —five
across, of 96, or of 128 if the animation is `large`— drawn centred on its
`(x, y)` from the anchor, zoomed by `zoom` percent, faded by
`transparency` percent, and toned. It takes a JSON request, a list with an
entry per animation, the animation named as in a Ditto dump:

    [{"sheet_file": "Battle/Hit.png",
      "animation": {"large": false, "frames": [{"cells": [
        {"cell_id": 3, "x": 0, "y": -8, "zoom": 75, "transparency": 20,
         "tone_red": 150, "tone_green": 100, "tone_blue": 100,
         "tone_gray": 100}]}]}}]

and for animation `i` it writes, in `--out`:

* `<i>.json`: `{"box": [x, y, width, height], "frames": [[{"x": x, "y": y,
  "tone": [red, green, blue, gray]}, ...], ...]}`. The **box** is the
  smallest rectangle that holds every valid cell of every frame, relative
  to the anchor, and is `null` if there are none: every frame is in its
  coordinates, and the anchor is at minus its corner. Each frame lists the
  cells RM2k draws of it, in the order they are stacked, with their corner
  in the box.
* `<i>-<f>-<k>.png`: cell `k` of frame `f`, cut from the sheet, zoomed and
  faded, an RGBA PNG.

**What comes out is the cells, not the frames**, and that is because of
the tone. RM2k tones each cell before stacking it, and a tone depends on
the depth the pictures are shown at —eight bits a channel on a PC, fewer
elsewhere—, which is the caller's to know. So each cell goes out with its
tone unapplied, and toning and stacking them is the caller's. A cell
marked not `valid` —the hole the editor leaves when one in the middle is
deleted— is not drawn and does not count for the box; one the sheet does
not have is not drawn either, but the box still makes room for it.

The zoom is **bilinear**, the `image` crate's, with the colour
premultiplied by the alpha so a transparent pixel does not bleed into its
neighbours: `Picture::resized`, which the pictures that are scaled for the
console use too. Until 2026-10-02 it was Pillow's arithmetic copied to the
bit, and a zoomed cell is no longer checked against what the Python drew:
the tests check where it lands and its size, and the zoom itself by its
properties.
The zoomed side is the sheet's times `zoom` percent, rounded down and at
least a pixel; the fade multiplies the alpha by `100 - transparency`
percent, rounded down, with the transparency clamped to 0..100.

`battle` draws **a battle's backdrops and its enemies' pictures**, one per
entry, as `<i>.png`:

    [{"backdrop_file": "Backdrop/Forest.png"},
     {"monster_file": "Monster/Slime.png", "hue": 120}]

* A **backdrop** comes out opaque: RM2k gives it no colour key, so index 0
  is a colour like any other.
* A **battler** has its colour key, and is turned `hue` degrees around the
  colour wheel —the enemy's `battler_hue`, which is what makes one picture
  two enemies—, with easyrpg's integer HSL. A transparent pixel keeps
  whatever colour it had.

Where each enemy stands, which one covers which, and what size any of this
is shown at are the caller's. Paths are relative to the request.
`tests/battle.rs` keeps the hashes of what the Python drew before, for
cells, battlers and backdrops of pictures generated inside the test.

## Exit codes

`1` when the answer is no: the ChipSet is not there, a layer does not have
`width * height` tiles, a tile id is outside 0 to 65535, the passability is
shorter than 162 and 144 entries, a `charset` entry is neither of the two
kinds or asks for a tile past 143, an entry of `face`, `system` or
`picture` lacks a field or has one out of its range. `2` when the call is
wrong: a missing flag, a file that cannot be read.
