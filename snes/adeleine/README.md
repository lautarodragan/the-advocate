# Adeleine: which colours a picture loses

Adeleine decides **which colours a picture loses and how the ones left are
grouped into palettes**. It is the half of a graphics pipeline that changes
what is seen. The other half, cutting tiles and writing colour memory, is
Voodoo's, and Voodoo never touches a pixel. To tell which side something
belongs to, ask whether it changes a pixel.

    let merged = adeleine::merge_least_visible(&counts, 15)?;
    let palettes = adeleine::try_pack(&tiles, 8, USABLE_COLORS);
    let reduced = adeleine::reduce_colors(&counts, &tiles, 8, USABLE_COLORS)?;

A library, and `cargo test` tests it. It is not a command: the stages that
bring a picture down to the console's palettes —the maps, the screens, the
pictures— call it in their own process.

Nothing here knows what the pictures are of. A colour is three channels. A
tile is the set of colours it draws with. A palette has sixteen entries, and
the first one is transparent, so a tile gets fifteen unless the caller says
otherwise.

## The three questions

* **`merge_least_visible`**: bring these colours down to N. It is for a sprite, a face or a
  backdrop, where every pixel can use every colour.
* **`try_pack`**: split these tiles' colours into at most N palettes, so
  that each tile draws with one. Nothing is merged. The answer is none if
  they do not fit.
* **`reduce_colors`**: group nearby tiles into N palettes and choose the
  colours of each palette. This is `try_pack` for a picture that does not fit as it is. The
  real limit is how the colours are spread, not how many there are: a tile
  with 14 colours asks one palette to represent all 14.

## How `merge_least_visible` merges

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

## How `reduce_colors` groups

Tiles start in groups by their pixel-weighted mean colour, with far-apart
means chosen first. Each group then fills its palette greedily with the colour
that minimises its total luma-weighted error, followed by two best swaps to
undo an early greedy choice, and tiles move to the palette that represents
them best. A source colour may therefore go to different targets in different
palettes. The answer gives every tile's palette and local mapping.

It uses only colours from the picture, integer costs and sorted tie breaks, so
it invents no colour and is deterministic. If `try_pack` already succeeds,
`reduce_colors` returns exactly those palettes and changes no pixel.

## Keeping the most used

There is a blunter way down to N colours, `keep_most_used`: keep the colours that cover the most pixels, and send each of
the others to its nearest neighbour among them —plain Euclidean distance,
ties broken by the colour—. One colour the caller names goes first whether
the picture has it or not, which is how a picture keeps the colour a
screen paints where there is nothing at index 0. It is blunter than
merging, because a highlight of a few pixels goes wherever is nearest; it
is here because pictures converted with it look like that, and changing a
picture's reducer changes its pixels.

## Fewer tiles

`group_tiles`: for a picture with
more distinct 8x8 tiles than video memory holds, which tile draws each one
so that at most N are left. A k-means over the tiles averaged two by two,
each group drawn by its medoid, seeded without chance: see `tiles.rs`. It
is here and not in Voodoo because it changes what is seen.

## How it packs

Best fit, with the tiles that have the most colours first. Each tile goes
into the palette that grows the least, and on a tie into the first one.
Tiles with the same number of colours are taken in the order of their
colours. The answer depends only on which tiles there are, never on the
order they were handed in.

## Two kinds of no

`Bad::Answer` when the answer is no: the colours cannot be merged far
enough. `Bad::Usage` when the call is wrong: a colour given twice.

## Tests

`tests/generated.rs` builds its colours and tiles with a small generator
and checks what every answer owes the console: no more colours than asked
for, every colour mapped to one that stayed, every tile in a palette that
holds its colours. `tests/answers.rs` has three answers small enough to
read whole, as JSON. They need no picture.

`tests/superfamiconv.rs` uses [SuperFamiconv](https://github.com/Optiroc/SuperFamiconv)
as a referee for `try_pack`. It builds pictures from seeds, gives each one to
both packers and fails when SuperFamiconv's `palette`, without `-Q`, needs
fewer palettes. That includes fitting a picture `try_pack` answers none
for. Without `-Q` SuperFamiconv keeps every colour, so the result with
fewer palettes is better, and the test checks that claim before using the
answer. Seeds where SuperFamiconv already wins are listed in `KNOWN`, grouped
by reason. Without `superfamiconv` on the PATH the test is skipped, which is
how it runs in CI. `cargo test --test superfamiconv -- --ignored --nocapture`
prints how many palettes each packer needs over `ADELEINE_ORACLE_SEEDS` seeds.
