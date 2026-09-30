# Adeleine: which colours a picture loses

Adeleine decides **which colours a picture loses and how the ones left are
grouped into palettes**. It is the half of a graphics pipeline that changes
what is seen. The other half, cutting tiles and writing colour memory, is
Voodoo's, and Voodoo never touches a pixel. To tell which side something
belongs to, ask whether it changes a pixel.

    adeleine merge  --request counts.json --out answer/
    adeleine pack   --request tiles.json  --out answer/
    adeleine reduce --request both.json   --out answer/

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints
the shape of its request and its answer.

Nothing here knows what the pictures are of. A colour is three channels. A
tile is the set of colours it draws with. A palette has sixteen entries, and
the first one is transparent, so a tile gets fifteen unless the request says
otherwise.

## The three questions

* **`merge`**: bring these colours down to N. It is for a sprite, a face or a
  backdrop, where every pixel can use every colour.
* **`pack`**: split these tiles' colours into at most N palettes, so that
  each tile draws with one. Nothing is merged. The answer is `null` if they
  do not fit.
* **`reduce`**: merge until the tiles fit in N palettes. This is `pack` for a
  picture that does not fit as it is. The real limit is how the colours are
  spread, not how many there are: a tile with 14 colours forces those 14
  into one palette.

## How it merges

It merges the pair that **shows the least**, one pair at a time. Sending
colour `a` to colour `b` costs `pixels(a) × distance(a, b)`, which is the
error the change adds to the picture. The distance is luma-weighted, 30 / 59
/ 11. The cheapest merge goes first, the pixels of the colour that went are
added to the one that stayed, and the loop starts again.

Counting only pixels would kill a colour that covers few pixels but defines
the drawing, like a highlight, an eye or the edge of a helmet, while two
nearly equal greys that cover half the sheet both survived. With this cost
the two greys melt into one, which costs almost nothing, and the highlight
stays.

It never invents a colour: the one that stays was already in the picture. It
is also deterministic. The costs are integers, and every tie is broken by the
colour, red first.

## How it packs

Best fit, with the tiles that have the most colours first. Each tile goes
into the palette that grows the least, and on a tie into the first one.
Tiles with the same number of colours are taken in the order of their
colours. The answer depends only on which tiles there are, never on the
order they were handed in.

## Exit codes

`1` when the answer is no: the colours cannot be merged far enough. `2` when
the call is wrong. The message goes to standard error.

## Tests

`tests/python.rs` builds its colours and tiles with a small generator and
compares the answers against the hashes of what the Python version gave for
the same input. They need no picture.
