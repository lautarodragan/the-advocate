# tiles, a picture into what a planar PPU reads

    tiles convert town.png --bpp 4 -o town.4bpp --palette town.cgram --tilemap town.map
    tiles convert sky.png  --bpp 8 --merge --max-colors 200 -o sky.8bpp --palette sky.cgram
    tiles inspect town.png --bpp 4 --palettes 4
    tiles render town.4bpp --palette town.cgram --tilemap town.map --columns 40 -o back.png

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints the
rules below.

One picture in; tiles, palettes and a tilemap out. Those three are **one
decision**, which is why they are one command: which palette a cell is given
decides what its indices are, which decides whether it is the same tile as some
other cell. Splitting them into three tools would mean each one guessing what
the other two did.

Where the files go is the caller's business. Nothing here has a default path, a
directory it knows about, or any idea what the tiles are of.

## What the format is

A tile is 8x8 pixels. Its bytes are **bit planes**, not two pixels to a byte:
every plane holds one bit of every pixel, one row per byte, leftmost pixel in
the high bit. Planes go in pairs, sixteen bytes at a time — 0 and 1, then 2 and
3, and so on — which is why a 4bpp tile is exactly the first half of an 8bpp
one, and why one piece of code writes both.

Colour is **15 bits**, five per channel, stored as `0BBB BBGG GGGR RRRR`, little
endian. A picture is quantised to that before anything else happens, because
every later decision has to be made on what the hardware can actually show: two
24-bit colours that differ in the low three bits of a channel are one colour on
screen, and counting them as two makes every "does this fit" answer wrong.

A tilemap entry is `vhop ppcc cccc cccc`: ten bits of tile number, three of
palette, one of priority, then the x and y flips.

## 4 bits and 8 bits are different problems

At **4bpp** an index is counted inside its own palette of sixteen, so every cell
has to have all of its colours in one palette. Spreading the colours over as few
palettes as possible is the hard part, and `--palettes` is the budget.

At **8bpp** an index reaches all of colour memory on its own, so there is one
palette, there are no groups to work out, and the only limit is how many entries
there are: `--max-colors`.

Index 0 is transparent in both, which is why a palette of *n* colours occupies
entries `base .. base + n`. `--base` says where it starts; it is 1 unless
something else is parked below it.

## Saying no is most of the job

A picture that does not fit is refused, and the message names the cell:

    $ tiles convert busy.png --bpp 4
    error: the cell at column 12, row 3 has 19 colours and a 4bpp palette holds
    15 besides the transparent one; pass --merge to give up the cheapest of them

That is on purpose, and the two reasons a picture does not fit are reported
separately, because they call for different fixes. **One cell with too many
colours** fits nowhere, and no number of palettes helps. **Too many colours
overall** is about the budget, and one more palette may be all it takes.

`--merge` turns the refusal into an answer: colours are given up until it fits,
cheapest first — see below — and the report says how many went. Without it
nothing is ever quietly made worse.

## Which colour is given up

The cost of sending colour `a` to colour `b` is `pixels(a) * distance(a, b)`:
how many pixels move, times how far they move, which is the error the change
adds to the picture. The cheapest pair goes, the victim's pixels are added to
the survivor, and it repeats.

The obvious alternative — kill the least used colour — is worse, and visibly so.
A colour can cover four pixels and still *define* the drawing: a highlight, an
eye, the rim of a helmet. Meanwhile two near-identical greys covering half the
picture both survive, because neither is the least used. Weighting by distance
flips that around.

Distance is the usual luma weighting, 0.30 / 0.59 / 0.11, times a hundred so the
arithmetic is **integer**. The ordering is the same as with the fractional
coefficients, and in exchange two equal distances compare equal: this number
gets multiplied by a pixel count and sorted, and a tie broken by the last bit of
a float is the kind of difference that makes two runs disagree for no reason
anyone can see.

No colour is invented. The survivor is always one that was already in the
picture, so there is nothing to re-quantise afterwards and the result does not
depend on the arithmetic of whatever drew the picture.

## Mirrored cells are free

A tilemap entry carries an x and a y flip, so a cell that is another cell
mirrored is not a new tile. All four orientations are tried against the tiles
already placed before a new one is added. At 4bpp the match also has to be in
the same palette, because an index only means a colour inside one.

Tile 0 is kept for the empty cell unless `--no-blank-tile` says otherwise:
whatever a tilemap points at before anybody writes it is tile 0, so it is
usually worth one tile to have that be the empty one.

## Determinism, and where it has to be bought

None of these decisions has a single right answer — how the colours are grouped,
which pair is merged, which cell becomes which tile — so the property worth
having is not "good" but **"the same every time"**: same input, same bytes, on
every machine and in every order the caller hands things over.

That is not free. Grouping walks the colour sets largest first, and ties on size
are the common case, not the exception — every two-colour cell ties with every
other. So the order ends in the colours themselves, which is a total order.
Merging ends every comparison the same way. Anything that resolved these ties by
the iteration order of a hash table would give a different answer depending on
how its caller happened to build the input, which is not part of the input and
cannot be reproduced from it.

## Exit codes

    0   done
    1   the answer is no
    2   the call was wrong

**1** is this tool working correctly and saying no: the picture does not fit, it
needs more than 1024 distinct tiles, a palette runs past the end of colour
memory. **2** is a broken call: a file that is not a PNG, a tilemap that does not
divide into rows. A script should not have to read the message to tell those
apart.

## Testing

`cargo test` needs nothing: the pictures are built inside the tests — a solid
cell, a mirrored one, one that has to merge, one that cannot fit — and a good
half of the cases are the error messages, because a tool whose refusals are
vague is one people work around instead of reading.

There is also a replay against calls recorded from another implementation of the
same rules, for anyone porting one. Point `TILES_CORPUS` at a directory of
`<function>.jsonl` files, one recorded call per line as `{"in": ..., "out":
...}`; without the variable those tests say so and pass, because a corpus is
evidence and not a dependency.

    TILES_CORPUS=/some/recorded/calls cargo test --release -- --nocapture

Two of them compare for validity rather than equality, and `tests/corpus.rs`
says why: a recording made by an implementation that resolved its tie-breaks
with a hash table is not reproducible from its own inputs, so what is asserted
is that the result is valid and never worse than the recording, with the exact
matches counted and printed.

## What is deliberately not here

* **Anything that knows what the picture is of.** Sprite sheets, animation
  strips, autotiles, fonts: those are all somebody's file format, and this is
  only the part every one of them ends with.
* **Dithering, and inventing colours.** Merging picks a survivor from the
  picture. A tool that invents a colour has to re-quantise, and then its output
  depends on how it rounds.
* **Deciding where things go in memory.** Which tiles are uploaded where, which
  palette number a layer gets, what is reserved at the bottom of colour memory:
  all of that is the caller's, and `--base` and `--first-palette` are how the
  caller tells this tool what it decided.
