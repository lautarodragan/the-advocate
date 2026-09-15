//! The whole path, on pictures small enough to reason about by hand.
//!
//! Every picture here is built in the test, so these depend on nothing: what
//! they check is that the pieces still add up to the same answer when they are
//! put together, which is where a port goes wrong long after each piece has
//! been checked on its own.

use tiles::color::Rgb15;
use tiles::convert::Options;
use tiles::grid::Picture;
use tiles::Pixel;

/// A picture from a function of (x, y), so a case reads as what it draws.
fn picture(width: usize, height: usize, paint: impl Fn(usize, usize) -> Pixel) -> Picture {
    Picture {
        width,
        height,
        rows: (0..height)
            .map(|y| (0..width).map(|x| paint(x, y)).collect())
            .collect(),
    }
}

fn red() -> Pixel {
    Some((31, 0, 0))
}

fn options(bpp: usize) -> Options {
    Options::at(bpp)
}

#[test]
fn one_solid_cell_is_one_tile_besides_the_empty_one() {
    let done = tiles::convert(&picture(8, 8, |_, _| red()), &options(4)).unwrap();
    assert_eq!(done.report.tiles, 2); // tile 0 is the empty one
    assert_eq!(done.report.colors_used, 1);
    assert_eq!(done.tiles.len(), 64); // two 4bpp tiles
    assert_eq!(done.tilemap[0][0] & 0x03FF, 1);
}

/// The whole point of the flip bits: a cell that is another cell mirrored
/// costs nothing but a bit in the tilemap.
#[test]
fn a_mirrored_cell_reuses_the_tile_and_sets_the_flip_bits() {
    // A 24x16 picture: a corner mark, the same mirrored across x next to it,
    // and mirrored across y underneath.
    let mark = |x: usize, y: usize| x < 2 && y < 2;
    let done = tiles::convert(
        &picture(24, 16, |x, y| {
            let (cx, cy) = (x / 8, y / 8);
            let (mut lx, mut ly) = (x % 8, y % 8);
            if cx == 1 {
                lx = 7 - lx;
            }
            if cy == 1 {
                ly = 7 - ly;
            }
            if cx == 2 {
                return None;
            }
            if mark(lx, ly) {
                red()
            } else {
                Some((0, 0, 31))
            }
        }),
        &options(4),
    )
    .unwrap();

    assert_eq!(done.report.tiles, 2, "one empty tile and one real one");
    assert_eq!(done.tilemap[0][0] & 0xC000, 0x0000);
    assert_eq!(done.tilemap[0][1] & 0xC000, 0x4000, "mirrored across x");
    assert_eq!(done.tilemap[1][0] & 0xC000, 0x8000, "mirrored across y");
    assert_eq!(done.tilemap[1][1] & 0xC000, 0xC000, "both");
}

/// A cell with more colours than a palette holds is refused, and the message
/// names the cell and both numbers, because editing that cell is what happens
/// next.
#[test]
fn a_cell_with_too_many_colours_says_which_cell_and_how_many() {
    let picture = picture(16, 8, |x, y| {
        if x < 8 {
            red()
        } else {
            Some(((x - 8) as u8 * 2 + y as u8 * 3, 0, 0))
        }
    });
    let e = tiles::convert(&picture, &options(4)).unwrap_err();
    let message = e.message();
    assert!(message.contains("column 1, row 0"), "{message}");
    assert!(message.contains("15"), "{message}");
    assert!(message.contains("--merge"), "{message}");
}

/// The same picture with `--merge` is not refused: the cheapest colours are
/// given up until it fits, and the report says how many went.
#[test]
fn the_same_picture_fits_once_colours_may_be_merged() {
    let picture = picture(16, 8, |x, y| {
        if x < 8 {
            red()
        } else {
            Some(((x - 8) as u8 * 2 + y as u8 * 3, 0, 0))
        }
    });
    let mut options = options(4);
    options.merge = true;
    let done = tiles::convert(&picture, &options).unwrap();
    assert!(done.report.merged > 0, "nothing was merged");
    assert!(done.report.colors_used <= 15, "{}", done.report.colors_used);
    for palette in &done.palettes {
        assert!(palette.len() <= 15);
    }
}

/// At 8bpp there are no palettes to spread over: one run of colours, and an
/// index that reaches all of colour memory.
#[test]
fn at_eight_bits_a_cell_may_use_far_more_than_fifteen_colours() {
    let done = tiles::convert(
        &picture(8, 8, |x, y| Some((x as u8 * 2, y as u8 * 2, 0))),
        &options(8),
    )
    .unwrap();
    assert_eq!(done.report.palettes, 1);
    assert_eq!(done.report.colors_used, 64);
    assert_eq!(done.tiles.len(), 128); // two 8bpp tiles
    assert_eq!(done.cgram.len(), 64 * 2);
}

/// Refusing is not the same as failing: a picture with too many colours for
/// the depth it was asked for is an answer about the picture.
#[test]
fn too_many_colours_for_eight_bits_says_how_many_would_have_to_go() {
    let picture = picture(8, 8, |x, y| Some((x as u8 * 4, y as u8 * 4, 0)));
    let mut options = options(8);
    options.max_colors = 10;
    let e = tiles::convert(&picture, &options).unwrap_err();
    assert!(e.message().contains("10 were allowed"), "{}", e.message());
    assert!(e.message().contains("--merge"), "{}", e.message());
}

/// A picture with nothing in it is not an error: it is a tilemap of empty
/// cells, and colour memory still gets a palette, because a transfer of
/// length zero is rarely what anybody means.
#[test]
fn a_fully_transparent_picture_is_all_empty_cells() {
    let done = tiles::convert(&picture(16, 16, |_, _| None), &options(4)).unwrap();
    assert_eq!(done.report.tiles, 1);
    assert_eq!(done.report.palettes, 0);
    assert_eq!(done.cgram.len(), 32);
    for row in &done.tilemap {
        for cell in row {
            assert_eq!(*cell, 0);
        }
    }
}

/// Where the palette sits in colour memory is the caller's, and it moves the
/// indices with it.
#[test]
fn a_base_other_than_one_shifts_every_index() {
    let mut options = options(8);
    options.base = 32;
    let done = tiles::convert(&picture(8, 8, |_, _| red()), &options).unwrap();
    let indices = tiles::unpack_tile(&done.tiles[64..128], 8);
    assert_eq!(indices[0][0], 32);
}

/// Two cells with the same drawing in different palettes are two tiles at
/// 4bpp, because an index only means a colour inside its own palette.
#[test]
fn the_same_drawing_in_two_palettes_is_two_tiles() {
    let a: Rgb15 = (31, 0, 0);
    let b: Rgb15 = (0, 31, 0);
    // Two cells that cannot share a palette: each one carries eight colours,
    // and together they are more than fifteen.
    let done = tiles::convert(
        &picture(16, 8, |x, y| {
            let base = if x < 8 { a } else { b };
            Some((base.0, base.1, y as u8 * 4))
        }),
        &{
            let mut o = options(4);
            o.palettes = 2;
            o
        },
    )
    .unwrap();
    assert_eq!(done.report.palettes, 2);
    assert_eq!(done.report.tiles, 3, "the empty tile and one per palette");
}
