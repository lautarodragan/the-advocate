# tiles

    tiles convert town.png --bpp 4 -o town.4bpp --palette town.cgram --tilemap town.map
    tiles convert sky.png  --bpp 8 -o sky.8bpp --palette sky.cgram --tilemap sky.map
    tiles render town.4bpp --palette town.cgram --tilemap town.map --columns 40 -o back.png

`cargo build --release`, or `cargo test`. `--help` on any subcommand prints the
rules below.

An indexed picture in; tiles, a tilemap and colour memory out.

**This tool makes no decision anyone could see.** The picture arrives with its
palettes already chosen — which colours survive, how they are grouped, where
each group sits in colour memory — because those are choices about what the
picture looks like, and they belong to whoever made it. What is left is
bookkeeping that changes bytes and never pixels: cutting the cells, numbering
the distinct ones, reusing a mirrored one. That is a property, not a hope:
`render` gives back exactly the indices `convert` was given.

A picture the format cannot hold is refused, never repaired. Repairing it would
be choosing what to lose.

Where the files go is the caller's business. Nothing here has a default path, a
directory it knows about, or any idea what the tiles are of.

## The picture

An **8-bit indexed PNG whose indices are colour-memory entries**. Index 37 is
entry 37, in every picture. So the palette a pixel belongs to is in the pixel
itself, and nothing outside the file has to say where a palette starts:

* at **4bpp**, `index >> 4` is the palette and `index & 15` the colour inside
  it. Every cell has to draw with one palette, and the palette has to be one of
  the first eight, because a tilemap entry has three bits for it;
* at **8bpp**, the index is the entry, and a cell can draw with any of them.

A PNG cannot say "my sixteen colours start at entry N" — there is no such field,
and a private chunk saying so does not survive the first editor that saves the
file. Eight bits of index with the whole of colour memory as the palette does:
any editor with an indexed mode keeps it.

So every picture carries a full copy of colour memory. That is deliberate. The
colour an entry has is what anyone sees when they open the file, and a caller
that hands over several pictures meant to be shown together is the one that
checks their copies agree.

## What the format is

A tile is 8x8 pixels. Its bytes are **bit planes**, not two pixels to a byte:
every plane holds one bit of every pixel, one row per byte, leftmost pixel in
the high bit. Planes go in pairs, sixteen bytes at a time — 0 and 1, then 2 and
3, and so on — which is why a 4bpp tile is exactly the first half of an 8bpp
one, and why one piece of code writes both.

Colour is **15 bits**, five per channel, stored as `0BBB BBGG GGGR RRRR`, little
endian. The palette's 8-bit channels are truncated to five; that is a
convention of the format, not a choice.

A tilemap entry is `vhop ppcc cccc cccc`: ten bits of tile number, three of
palette, one of priority, then the x and y flips.

The first entry of every palette draws nothing at 4bpp, because the hardware
counts a 4-bit index inside its own sixteen; at 8bpp only entry 0 does. A pixel
on the transparent entry of another palette is still transparent, and does not
count as a second palette.

## Saying no is most of the job

    $ tiles convert busy.png --bpp 4
    error: the cell at column 12, row 3 draws with palettes 1 and 2, and a
    tilemap entry names one palette per cell

The message names the cell, because the thing a caller does next is fix that
cell. The other refusals: a palette a tilemap cannot name, an entry the
picture's palette has no colour for, and more distinct tiles than a tilemap
entry can number.

## Mirrored cells are free

A tilemap entry carries an x and a y flip, so a cell that is another cell
mirrored is not a new tile. All four orientations are tried against the tiles
already placed before a new one is added, and tiles are numbered in the order
their first cell is met, row-major. At 4bpp the match also has to be in the
same palette, because an index only means a colour inside one.

Tile 0 is kept for the empty cell unless `--no-blank-tile` says otherwise:
whatever a tilemap points at before anybody writes it is tile 0, so it is
usually worth one tile to have that be the empty one. An empty cell is written
as a plain 0 — its priority and palette would say nothing — and `--priority`
goes on the cells that draw.

## Exit codes

    0   done
    1   the answer is no
    2   the call was wrong

**1** is this tool working correctly and saying no: the picture breaks the
format, or needs more than 1024 distinct tiles. **2** is a broken call: a file
that is not an indexed PNG, a tilemap that does not divide into rows. A script
should not have to read the message to tell those apart.

## Testing

`cargo test` needs nothing: the pictures are built inside the tests, and half
the cases are the refusals, because a tool whose refusals are vague is one
people work around instead of reading. The one the design rests on converts a
picture and renders it back, at both depths, and asks for the same indices.

## What is deliberately not here

* **Choosing colours.** Merging, grouping colours into palettes, deciding which
  palette a layer starts at: that is deciding what the picture looks like, and
  it happens before this tool runs. This tool used to do it, with a `--merge`
  flag; it was taken out so that there is exactly one answer to "which colour
  was given up", and it is not here.
* **Anything that knows what the picture is of.** Sprite sheets, animation
  strips, autotiles, fonts: those are all somebody's file format, and this is
  only the part every one of them ends with.
* **Deciding where things go in memory.** Which tiles are uploaded where, and
  what is reserved at the bottom of colour memory, is the caller's.
