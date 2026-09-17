//! The whole path, on pictures small enough to reason about by hand.
//!
//! Every picture here is built in the test, so these depend on nothing: what
//! they check is that the pieces still add up to the same answer when they are
//! put together.
//!
//! The pictures are indexed and their indices are colour-memory entries, so a
//! case reads as which entry each pixel draws with: at 4bpp, entry 17 is
//! colour 1 of palette 1.

use std::path::PathBuf;
use std::process::Command;
use tiles::convert::Options;
use tiles::grid::{Picture, ENTRIES};
use tiles::image;

/// Every entry gets a colour, so a case only has to care about indices.
fn every_colour() -> Vec<Option<tiles::Rgb15>> {
    (0..ENTRIES)
        .map(|e| Some(((e % 32) as u8, (e / 32) as u8, 0)))
        .collect()
}

/// A picture from a function of (x, y), so a case reads as what it draws.
fn picture(width: usize, height: usize, paint: impl Fn(usize, usize) -> u8) -> Picture {
    Picture {
        width,
        height,
        pixels: (0..height)
            .flat_map(|y| (0..width).map(move |x| (x, y)))
            .map(|(x, y)| paint(x, y))
            .collect(),
        colors: every_colour(),
    }
}

fn convert(picture: &Picture, bpp: usize) -> tiles::Result<tiles::Converted> {
    tiles::convert(picture, &Options::at(bpp))
}

fn answer(result: tiles::Result<tiles::Converted>) -> String {
    match result {
        Err(tiles::Bad::Answer(message)) => message,
        Err(other) => panic!("expected an answer, got a usage error: {other}"),
        Ok(_) => panic!("expected it to be refused"),
    }
}

#[test]
fn one_solid_cell_is_one_tile_besides_the_empty_one() {
    let done = convert(&picture(8, 8, |_, _| 17), 4).unwrap();
    assert_eq!(done.report.tiles, 2); // tile 0 is the empty one
    assert_eq!(done.report.colors, 1);
    assert_eq!(done.report.palettes, 1);
    assert_eq!(done.tiles.len(), 64); // two 4bpp tiles
    // Tile 1, palette 1: the palette comes from the index, not from a choice.
    assert_eq!(done.tilemap[0][0], 1 | (1 << 10));
}

/// The whole point of the flip bits: a cell that is another cell mirrored
/// costs nothing but a bit in the tilemap.
#[test]
fn a_mirrored_cell_reuses_the_tile_and_sets_the_flip_bits() {
    let mark = |x: usize, y: usize| if x == 0 && y == 0 { 1 } else { 2 };
    let done = convert(
        &picture(16, 8, |x, y| if x < 8 { mark(x, y) } else { mark(15 - x, y) }),
        4,
    )
    .unwrap();
    assert_eq!(done.report.tiles, 2);
    assert_eq!(done.tilemap[0][0] & 0x03FF, done.tilemap[0][1] & 0x03FF);
    assert_eq!(done.tilemap[0][0] & 0x4000, 0);
    assert_eq!(done.tilemap[0][1] & 0x4000, 0x4000);
}

/// A tilemap entry names one palette, so a cell drawing with two is the
/// picture breaking the format. It is refused, and not repaired: repairing it
/// would be choosing which pixels change.
#[test]
fn a_cell_drawing_with_two_palettes_says_which_cell_and_which_palettes() {
    let message = answer(convert(
        &picture(16, 8, |x, y| if x == 12 && y == 3 { 33 } else { 17 }),
        4,
    ));
    assert!(message.contains("column 1, row 0"), "{message}");
    assert!(message.contains("palettes 1 and 2"), "{message}");
}

#[test]
fn a_palette_a_tilemap_cannot_name_is_refused() {
    let message = answer(convert(&picture(8, 8, |_, _| 8 * 16 + 1), 4));
    assert!(message.contains("palette 8"), "{message}");
}

/// The first entry of every palette draws nothing, whichever palette it is:
/// a transparent pixel is not a second palette.
#[test]
fn the_transparent_entry_of_another_palette_is_still_transparent() {
    let done = convert(&picture(8, 8, |x, _| if x == 0 { 48 } else { 17 }), 4).unwrap();
    assert_eq!(done.report.palettes, 1);
    assert_eq!(done.tilemap[0][0] >> 10 & 7, 1);
}

#[test]
fn the_same_drawing_in_two_palettes_is_two_tiles() {
    let done = convert(&picture(16, 8, |x, _| if x < 8 { 17 } else { 33 }), 4).unwrap();
    assert_eq!(done.report.tiles, 3);
    assert_eq!(done.report.palettes, 2);
}

#[test]
fn at_eight_bits_a_cell_may_draw_with_far_more_than_fifteen_entries() {
    let done = convert(&picture(8, 8, |x, y| (8 + y * 8 + x) as u8), 8).unwrap();
    assert_eq!(done.report.colors, 64);
    assert_eq!(done.report.tiles, 2);
    assert_eq!(done.tilemap[0][0], 1);
}

#[test]
fn a_fully_transparent_picture_is_all_empty_cells() {
    let done = convert(&picture(16, 16, |_, _| 0), 4).unwrap();
    assert_eq!(done.report.tiles, 1);
    assert_eq!(done.report.palettes, 0);
    assert!(done.tilemap.iter().flatten().all(|&e| e == 0));
}

/// The priority bit goes on what draws; an empty cell is a plain 0, which is
/// what an unwritten tilemap holds anyway.
#[test]
fn priority_is_set_on_the_cells_that_draw() {
    let options = Options {
        priority: 1,
        ..Options::at(4)
    };
    let done = tiles::convert(&picture(16, 8, |x, _| if x < 8 { 1 } else { 0 }), &options)
        .unwrap();
    assert_eq!(done.tilemap[0][0] & 0x2000, 0x2000);
    assert_eq!(done.tilemap[0][1], 0);
}

#[test]
fn an_entry_the_palette_has_no_colour_for_is_refused() {
    let mut p = picture(8, 8, |_, _| 17);
    p.colors[17] = None;
    let message = answer(convert(&p, 4));
    assert!(message.contains("entry 17"), "{message}");
}

/// Colour memory is the picture's palette, entry for entry: nothing is
/// chosen, reordered or dropped.
#[test]
fn colour_memory_is_the_palette_of_the_picture() {
    let done = convert(&picture(8, 8, |_, _| 17), 4).unwrap();
    assert_eq!(done.cgram.len(), 2 * ENTRIES);
    for (entry, word) in done.cgram.chunks_exact(2).enumerate() {
        let expected = tiles::cgram_word(((entry % 32) as u8, (entry / 32) as u8, 0));
        assert_eq!(u16::from_le_bytes([word[0], word[1]]), expected, "entry {entry}");
    }
}

/// The property the whole design rests on: converting changes bytes and never
/// pixels, so rendering what came out gives back the same indices.
#[test]
fn render_gives_back_the_picture_that_went_in() {
    let dir = scratch("round-trip");
    for bpp in [4usize, 8] {
        let source = picture(24, 16, |x, y| {
            let (cx, cy) = (x / 8, y / 8);
            if (cx + cy) % 3 == 2 {
                return 0; // an empty cell
            }
            if bpp == 8 {
                return (8 + (x * 7 + y * 3) % 200) as u8;
            }
            // One palette per cell; the transparent pixels are that
            // palette's first entry, which is what render writes back.
            let palette = (cx + cy) % 8;
            let color = ((x * 5 + y) % 16) as u8;
            (palette * 16) as u8 + color
        });
        let input = dir.join(format!("in{bpp}.png"));
        let output = dir.join(format!("out{bpp}.png"));
        image::write(&input, &source).unwrap();
        run(&[
            "convert",
            input.to_str().unwrap(),
            "--bpp",
            &bpp.to_string(),
            "-o",
            dir.join("t.bin").to_str().unwrap(),
            "--palette",
            dir.join("c.bin").to_str().unwrap(),
            "--tilemap",
            dir.join("m.bin").to_str().unwrap(),
        ]);
        run(&[
            "render",
            dir.join("t.bin").to_str().unwrap(),
            "--bpp",
            &bpp.to_string(),
            "--palette",
            dir.join("c.bin").to_str().unwrap(),
            "--tilemap",
            dir.join("m.bin").to_str().unwrap(),
            "--columns",
            "3",
            "-o",
            output.to_str().unwrap(),
        ]);
        let back = image::read(&output).unwrap();
        assert_eq!(back.pixels, source.pixels, "at {bpp}bpp");
        assert_eq!(back.colors, source.colors, "at {bpp}bpp");
    }
}

#[test]
fn a_picture_that_is_not_indexed_is_a_usage_error() {
    let dir = scratch("not-indexed");
    let path = dir.join("rgba.png");
    let file = std::fs::File::create(&path).unwrap();
    let mut encoder = png::Encoder::new(std::io::BufWriter::new(file), 8, 8);
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    encoder
        .write_header()
        .unwrap()
        .write_image_data(&[0; 8 * 8 * 4])
        .unwrap();
    match image::read(&path) {
        Err(tiles::Bad::Usage(message)) => assert!(message.contains("indexed"), "{message}"),
        other => panic!("expected a usage error, got {:?}", other.map(|_| ())),
    }
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("tiles-test-{}-{name}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn run(args: &[&str]) {
    let status = Command::new(env!("CARGO_BIN_EXE_tiles"))
        .args(args)
        .output()
        .unwrap();
    assert!(
        status.status.success(),
        "tiles {args:?}: {}",
        String::from_utf8_lossy(&status.stderr)
    );
}
