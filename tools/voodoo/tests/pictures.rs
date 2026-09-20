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
use voodoo::convert::Options;
use voodoo::grid::{Picture, ENTRIES};
use voodoo::image;

/// Every entry gets a colour, so a case only has to care about indices.
fn every_colour() -> Vec<Option<voodoo::Rgb15>> {
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

fn convert(picture: &Picture, bpp: usize) -> voodoo::Result<voodoo::Converted> {
    voodoo::convert(picture, &[], &Options::at(bpp))
}

fn answer(result: voodoo::Result<voodoo::Converted>) -> String {
    match result {
        Err(voodoo::Bad::Answer(message)) => message,
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
    let done = voodoo::convert(&picture(16, 8, |x, _| if x < 8 { 1 } else { 0 }), &[], &options)
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
        let expected = voodoo::cgram_word(((entry % 32) as u8, (entry / 32) as u8, 0));
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
        Err(voodoo::Bad::Usage(message)) => assert!(message.contains("indexed"), "{message}"),
        other => panic!("expected a usage error, got {:?}", other.map(|_| ())),
    }
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("voodoo-test-{}-{name}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn run(args: &[&str]) {
    let status = Command::new(env!("CARGO_BIN_EXE_voodoo"))
        .args(args)
        .output()
        .unwrap();
    assert!(
        status.status.success(),
        "voodoo {args:?}: {}",
        String::from_utf8_lossy(&status.stderr)
    );
}

// --- animations -------------------------------------------------------------

fn animated(picture: &Picture, animations: &[Vec<Picture>]) -> voodoo::Result<voodoo::Converted> {
    voodoo::convert(picture, animations, &Options::at(8))
}

/// Two cells that look the same in the base picture, one of them animated:
/// the animated one cannot share, or the still one would move with it.
#[test]
fn an_animated_cell_gets_its_own_tile_in_a_run_after_the_still_ones() {
    let base = picture(24, 8, |x, _| if x < 16 { 9 } else { 10 });
    let frame = picture(24, 8, |x, _| if x < 8 { 9 } else if x < 16 { 11 } else { 10 });
    let done = animated(&base, &[vec![frame]]).unwrap();
    // Still: blank, the 9 cell, the 10 cell. Then the run: the moving 9 cell.
    assert_eq!(done.report.tiles, 4);
    assert_eq!(done.tilemap[0][0] & 0x03FF, 1);
    assert_eq!(done.tilemap[0][2] & 0x03FF, 2);
    assert_eq!(done.tilemap[0][1] & 0x03FF, 3);
    let run = &done.animations[0];
    assert_eq!((run.first, run.count, run.frames.len()), (3, 1, 2));
    assert_eq!(run.frames[0], voodoo::pack_tile(&[[9; 8]; 8], 8));
    assert_eq!(run.frames[1], voodoo::pack_tile(&[[11; 8]; 8], 8));
    // What the tile data holds for the run is the base picture's frame.
    assert_eq!(&done.tiles[3 * 64..], &run.frames[0][..]);
}

#[test]
fn each_animation_gets_its_own_run_in_the_order_given() {
    let base = picture(16, 8, |_, _| 9);
    let water = picture(16, 8, |x, _| if x < 8 { 12 } else { 9 });
    let other = picture(16, 8, |x, _| if x < 8 { 9 } else { 13 });
    let done = animated(&base, &[vec![water.clone_picture()], vec![other]]).unwrap();
    // Both cells move, so the only still tile is the empty one.
    let (a, b) = (&done.animations[0], &done.animations[1]);
    assert_eq!((a.first, a.count), (1, 1));
    assert_eq!((b.first, b.count), (2, 1));
    assert_eq!(done.tilemap[0][0] & 0x03FF, 1);
    assert_eq!(done.tilemap[0][1] & 0x03FF, 2);
}

#[test]
fn an_animation_nothing_moves_with_is_an_empty_run() {
    let base = picture(8, 8, |_, _| 9);
    let done = animated(&base, &[vec![picture(8, 8, |_, _| 9)]]).unwrap();
    let run = &done.animations[0];
    assert_eq!((run.first, run.count), (0, 0));
    assert!(run.frames.iter().all(|f| f.is_empty()));
}

#[test]
fn a_cell_moving_with_two_animations_is_refused() {
    let base = picture(8, 8, |_, _| 9);
    let message = answer(animated(
        &base,
        &[vec![picture(8, 8, |_, _| 10)], vec![picture(8, 8, |_, _| 11)]],
    ));
    assert!(message.contains("animations 0 and 1"), "{message}");
}

/// The hardware flips the tile, not each frame: a mirrored match has to hold
/// in every frame at once.
#[test]
fn a_mirrored_animated_cell_is_reused_only_if_every_frame_mirrors() {
    let mark = |x: usize, y: usize, a: u8, b: u8| if x == 0 && y == 0 { a } else { b };
    let base = picture(16, 8, |x, y| if x < 8 { mark(x, y, 1, 2) } else { mark(15 - x, y, 1, 2) });
    // Frame 1: the left cell mirrors into the right one; the right cell's
    // frame is its own mirror too, so they share.
    let same = picture(16, 8, |x, y| if x < 8 { mark(x, y, 3, 2) } else { mark(15 - x, y, 3, 2) });
    let done = animated(&base, &[vec![same]]).unwrap();
    assert_eq!(done.animations[0].count, 1);
    // Frame 1 again, but the right cell does not mirror the left one there.
    let apart = picture(16, 8, |x, y| if x < 8 { mark(x, y, 3, 2) } else { mark(15 - x, y, 4, 2) });
    let done = animated(&base, &[vec![apart]]).unwrap();
    assert_eq!(done.animations[0].count, 2);
}

/// Pictures shown together carry copies of colour memory, and the copies have
/// to agree wherever somebody draws.
#[test]
fn frames_that_disagree_on_a_drawn_entry_are_refused() {
    let base = picture(8, 8, |_, _| 9);
    let mut frame = picture(8, 8, |_, _| 10);
    frame.colors[9] = Some((1, 1, 1));
    // Entry 9 is drawn by the base only, so its copy wins and nothing clashes.
    assert!(animated(&base, &[vec![frame.clone_picture()]]).is_ok());
    let mut clashing = picture(8, 8, |_, _| 9);
    clashing.colors[9] = Some((1, 1, 1));
    clashing.pixels[0] = 10;
    let message = answer(animated(&base, &[vec![clashing]]));
    assert!(message.contains("entry 9"), "{message}");
}

#[test]
fn a_frame_of_another_size_is_a_usage_error() {
    let base = picture(16, 8, |_, _| 9);
    match animated(&base, &[vec![picture(8, 8, |_, _| 9)]]) {
        Err(voodoo::Bad::Usage(message)) => assert!(message.contains("frame 1"), "{message}"),
        other => panic!("expected a usage error, got {:?}", other.map(|_| ())),
    }
}

trait ClonePicture {
    fn clone_picture(&self) -> Picture;
}

impl ClonePicture for Picture {
    fn clone_picture(&self) -> Picture {
        Picture {
            width: self.width,
            height: self.height,
            pixels: self.pixels.clone(),
            colors: self.colors.clone(),
        }
    }
}
