# rm2k-render: an RPG Maker 2000 game's graphics, as pictures

    let chipset = picture::read_rm2k(&find_resource(&dirs, "ChipSet", "Town").unwrap())?;
    let layers = map.render(&Atlas::new(&chipset))?;
    let sheet = charset::tile_sheet(&chipset, 12);
    let window = system::window(&system, 256, 80, background);
    let (bounds, frames) = battle_animation::frames(&animation, &sheet);

A library, and `cargo test` tests it. It is not a command: the stages that
start from what RM2k would have drawn —the maps, the screens, the pictures,
the text— and the converter call it in their own process.

It draws what RM2k draws, the way RM2k draws it, and nothing about what
anyone does with the pictures afterwards. Today that is a map's tile layers,
what its events are drawn with, what its battles are drawn with —the
cells of a battle animation, backdrops and enemies—, and what the screens
are drawn with: faces, windows and `ShowPicture` pictures. Where the line is
drawn, piece by piece, is whether a viewer of the game on a PC would draw it
the same way.

A map is two layers of tile ids and a ChipSet. `Map::render` draws them the
way RM2k stacks them around the hero, and nothing else: no panorama, no
events, no hero. Where the game and the RTP are is the caller's business:
nothing here has a default path, and nothing here knows which game a map is
from.

## What comes out

`Map::render` gives `Layers`:

* `lower`: what is drawn **behind** the hero, on opaque black;
* `upper`: what is drawn **in front** of it, on transparency;
* `variants`: for each animated family the map uses, its other drawings
  behind the hero: two more for the three drawings of the water, three more
  for the four of the animated tiles. Drawing 0 is `lower`. A family the
  map does not use is not there.

`Map::render_over_panorama` is the same with `lower` transparent where
nothing is drawn, where the map's panorama shows through. All of them are
RGBA at eight bits.

Which side of the hero a tile goes on is not the layer it sits on but the
ChipSet's passability: a lower-layer tile with either of the `0x30` bits, or
an upper-layer one with the star, `0x10`, goes in front. Both layers are
drawn cell by cell, lower tile first. That rule, the passability table it
reads and where each piece of the ChipSet is are RM2k's, and they are
`rm2k-rules`' (`rm2k/rules/`): what stays here is the drawing.

`Atlas::new` expands the ChipSet: 32 tiles by 45, every combination of
every autotile, in the order the tile ids index them. It is what every
drawing above is copied from.

## The map

A `Map` is its size, its two layers and its ChipSet's two passability
tables, with Ditto's field names; the caller builds it from Ditto's dump,
after changing whatever it changes —a patch, something baked into a
layer—. A broken one is an answer and not a panic: a layer without `width *
height` tiles, a tile id outside 0 to 65535, passability shorter than 162
and 144 entries.

## Where the ChipSet comes from

`source::find_resource` looks a picture up by name, in `<game>/ChipSet/` and
then `<rtp>/ChipSet/` —whichever folder and directories the caller gives—,
**without regard to case**: RM2k stores names without extension, and the
games were made on Windows. A caller that also keys a cache on the ChipSet's
bytes reads the file it hashed, so that the file hashed and the file drawn
cannot be two different ones.

`picture::read_rm2k` reads it the way RM2k does: in an **indexed** picture,
index 0 is the colour key, whatever the file's own transparency chunk says.
Grey, RGB and RGBA at eight bits are read too, with the transparency they
declare, and so is a BMP, which RM2k takes in every folder.

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

That is not a style choice: what a map looks like is A Blurred Line's
goldens', pixel for pixel, and they hold these roundings. `tests/every_id.rs` draws a
map of every id over an indexed ChipSet and a half-transparent one, which
no game brings, and checks it is drawn whole.

## What an event is drawn with

`charset` draws **CharSet sheets**: the picture a character's 24x32 poses
are cut from, 4 characters by 2 of 12 poses each, in RM2k's layout. Cutting
a pose is the caller's, and so is whatever a pose becomes afterwards.

* **A CharSet** is read with its colour key, as the ChipSets are: the poses
  are already where RM2k looks for them.
* **`tile_sheet`** is an event drawn with no CharSet: RM2k draws a tile —0
  to 143— of the ChipSet's upper layer where the event stands, whichever way
  it faces or steps. The sheet has that tile in the twelve poses of
  character 0, standing on its cell the way a pose stands on it —4 pixels
  in, 16 down—, so it can be cut like any other.
* **`translucent`** is a page with RM2k's "translucent" set, which it draws
  at 160 of 255 over whatever is behind: an RGBA picture of that —for
  example `lower` from `Map::render`— and the cell the event stands on.
  Every pose is blended over the piece of it the pose would cover there,
  and comes out **opaque** where it has pixels. Past the edges of what is
  behind there is nothing, which RM2k shows as black. What to put behind is
  the caller's to choose.

The blend is `(over * 160 + under * 95) / 255` rounded **down**, and the
sheet's own alpha does not weigh in: any pixel that is not fully
transparent is mixed whole. The tile of a tile event is copied through its
alpha twice, like a tile of the layers. `tests/charsets.rs` checks the tile in each pose and
the blend's bounds over CharSets, ChipSets and a background generated
inside the test.

## What the screens are drawn with

`face::face` cuts face `index` —0 to 15, four across— from a FaceSet read
with its colour key, 48x48: in a FaceSet too, index 0 is transparent.

`system` draws from the System, the 160x80 picture every window is made
of:

* **`window`**: an empty window of that size, as easyrpg's `Window` makes
  it. The 32x32 background fills it **stretched** or **tiled**, as the
  database's `message_stretch` says —`rm2k-rules`' `system::background`
  turns the number into one of the two, and has nothing for EasyRPG's own
  third value—, and the frame goes on top: the 8x8 corners, and the edges
  repeated between them.
* **`cursor`**: the cursor of a list, laid out like the frame over
  transparency, with its middle repeated inside. Drawing 1 is the second
  of the two it blinks between.
* **`text_color`**, 0 to 19, and **`shadow`**: the 16x16 blocks a letter
  takes its pixels from, which is why RM2k's text has a gradient. Drawing
  letters with them is the caller's, with whatever font it has.
* **`timer`**: the timer's eleven 8x16 glyphs in a row, the digits and the
  colon.

Where each piece is in the System is `rm2k-rules`' (`system`). Two things
are the drawing this replaces' and not easyrpg's, and they are said here
because they only show with some Systems: the stretch picks the nearest
pixel the way Pillow's `NEAREST` does, and the edges repeat from where they
start —next to the corner—, where easyrpg repeats them from the window's
corner, half an edge off. With an edge that repeats every 8 pixels the two
are the same.

`show_picture::picture` is the picture of a `ShowPicture` as RM2k puts it
on the screen: index 0 transparent **only** if the command asks for its
transparent colour, and every pixel at the opacity of `top_trans`, the
transparency from 0 to 100 —`255 * (100 - top_trans) / 100`, rounded down,
which is `rm2k-rules`' (`picture`)—. It takes the file read both ways, with
`read_unkeyed` and with `read_rm2k`. Where it goes, at what size and in
which tone is the caller's.

`tests/screens.rs` draws Systems —an indexed one and a half-transparent
one—, FaceSets and a picture generated inside the test at sizes a game's
screens do not use, and checks the tiled background, the second cursor, a
face past its FaceSet and a transparency against RM2k's rules.

## What a battle is drawn with

`battle_animation::frames` draws **the cells of a battle animation**. A
frame of one is a list of cells, each a square of the animation's sheet
—five across, of 96, or of 128 if the animation is `large`— drawn centred on
its `(x, y)` from the anchor, zoomed by `zoom` percent, faded by
`transparency` percent, and toned. It takes the animation as Ditto reads it
and gives:

* the **box**, the smallest rectangle that holds every valid cell of every
  frame, relative to the anchor, or none if there are none: every frame is
  in its coordinates, and the anchor is at minus its corner;
* for each frame, the cells RM2k draws of it, in the order they are
  stacked: each cut from the sheet, zoomed and faded, with its corner in
  the box and its tone.

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
bit: the tests check where a cell lands and its size, and the zoom itself
by its properties.
The zoomed side is the sheet's times `zoom` percent, rounded down and at
least a pixel; the fade multiplies the alpha by `100 - transparency`
percent, rounded down, with the transparency clamped to 0..100.

`battle` draws **a battle's backdrops and its enemies' pictures**:

* A **backdrop** comes out opaque: RM2k gives it no colour key, so index 0
  is a colour like any other.
* A **battler** has its colour key, and is turned some degrees around the
  colour wheel —the enemy's `battler_hue`, which is what makes one picture
  two enemies—, with easyrpg's integer HSL. A transparent pixel keeps
  whatever colour it had.

Where each enemy stands, which one covers which, and what size any of this
is shown at are the caller's. `tests/battle.rs` checks, over pictures
generated inside the test, where each cell lands and how big, its tone,
the animation's box, a battler's hue going round and a backdrop opaque.

## Two kinds of no

`Bad::Answer` when the answer is no: a map that is broken as above, a
picture that cannot be drawn the way RM2k would. `Bad::Usage` when the call
is wrong: a file that cannot be read.
