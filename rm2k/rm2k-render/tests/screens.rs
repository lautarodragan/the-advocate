//! Faces, windows and pictures, generated inside this file, which need no
//! game and no RTP.
//!
//! The inputs touch what can differ: an indexed System —the colour key at
//! index 0— and an RGBA one with half-transparent pixels; windows whose
//! size is not a multiple of the background's, and edges that do not repeat
//! every 8 pixels; a FaceSet smaller than the faces it is asked for.
//!
//! **The path it guards**: those sizes and the RGBA System, which a game's
//! screens do not have. What a real window, cursor or face looks like is A
//! Blurred Line's goldens'. What is checked is that each is drawn at the
//! size asked for, and what RM2k does with the tiled background, the
//! cursor's second drawing, a face past its FaceSet and a `ShowPicture`'s
//! transparency, pixel by pixel.

use rm2k_render::picture::{self, Picture};
use rm2k_render::{face, show_picture, system};
use rm2k_rules::system::Background;
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir =
        std::env::temp_dir().join(format!("rm2k-render-screens-{}-{name}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// An indexed picture: a palette and every pixel from formulas.
fn indexed(
    path: &Path,
    width: usize,
    height: usize,
    palette: impl Fn(usize) -> [u8; 3],
    pixel: impl Fn(usize, usize) -> u8,
) {
    let mut encoder = png::Encoder::new(
        std::fs::File::create(path).unwrap(),
        width as u32,
        height as u32,
    );
    encoder.set_color(png::ColorType::Indexed);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_palette((0..256).flat_map(&palette).collect::<Vec<u8>>());
    let pixels: Vec<u8> = (0..height)
        .flat_map(|y| (0..width).map(move |x| (x, y)))
        .map(|(x, y)| pixel(x, y))
        .collect();
    let mut writer = encoder.write_header().unwrap();
    writer.write_image_data(&pixels).unwrap();
}

/// An indexed System whose edges do not repeat every 8 pixels, with the
/// colour key scattered through it.
fn indexed_system(path: &Path) {
    indexed(
        path,
        160,
        80,
        |i| {
            [
                (i * 37 % 256) as u8,
                (i * 101 % 256) as u8,
                (i * 211 % 256) as u8,
            ]
        },
        |x, y| {
            if (x * 3 + y) % 7 == 0 {
                0
            } else {
                ((x * 7 + y * 13 + (x / 5) * (y / 3)) % 256) as u8
            }
        },
    );
}

/// An RGBA System with half-transparent pixels.
fn rgba_system(path: &Path) {
    const ALPHAS: [u8; 5] = [0, 255, 128, 37, 200];
    let mut rgba = Vec::with_capacity(160 * 80 * 4);
    for y in 0..80usize {
        for x in 0..160usize {
            rgba.extend_from_slice(&[
                (x * 3 % 256) as u8,
                (y * 5 % 256) as u8,
                ((x + y) % 256) as u8,
                ALPHAS[(x * y + x) % 5],
            ]);
        }
    }
    picture::write_png(
        path,
        &Picture {
            width: 160,
            height: 80,
            rgba,
        },
    )
    .unwrap();
}

/// An indexed FaceSet, or picture, of any size.
fn indexed_sheet(path: &Path, width: usize, height: usize) {
    indexed(
        path,
        width,
        height,
        |i| {
            [
                (i * 53 % 256) as u8,
                (i * 29 % 256) as u8,
                (i * 197 % 256) as u8,
            ]
        },
        |x, y| {
            if (x + y) % 4 == 0 {
                0
            } else {
                ((x * 11 + y * 5 + (x / 7) * (y / 4)) % 256) as u8
            }
        },
    );
}

fn systems(dir: &Path) -> [(&'static str, Picture); 2] {
    indexed_system(&dir.join("indexed.png"));
    rgba_system(&dir.join("rgba.png"));
    [
        (
            "indexed",
            picture::read_rm2k(&dir.join("indexed.png")).unwrap(),
        ),
        ("rgba", picture::read_rm2k(&dir.join("rgba.png")).unwrap()),
    ]
}

/// Windows and cursors of sizes the System's pieces do not divide, down
/// to a single frame's, at the size they were asked for; and the 16x16
/// blocks the text, its shadow and the timer take their pixels from.
#[test]
fn every_piece_is_drawn_at_its_size() {
    let s = systems(&scratch("sizes"));
    for (kind, system) in &s {
        for (w, h) in [
            (256, 80),
            (80, 48),
            (17, 23),
            (320, 240),
            (16, 16),
            (100, 16),
        ] {
            let window = system::window(system, w, h, Background::Stretched);
            assert_eq!((window.width, window.height), (w, h), "{kind} window");
        }
        for (w, h) in [(100, 16), (57, 33), (16, 16), (240, 32)] {
            let cursor = system::cursor(system, w, h, 0);
            assert_eq!((cursor.width, cursor.height), (w, h), "{kind} cursor");
        }
        for color in [0, 13, 19] {
            let block = system::text_color(system, color);
            assert_eq!(
                (block.width, block.height),
                (16, 16),
                "{kind} colour {color}"
            );
        }
        let shadow = system::shadow(system);
        assert_eq!((shadow.width, shadow.height), (16, 16), "{kind} shadow");
    }
}

/// With `message_stretch` 1 the background is the 32x32 square repeated
/// from the window's corner, and the frame is the stretched window's.
#[test]
fn a_tiled_window_repeats_the_background() {
    let dir = scratch("tiled");
    indexed_system(&dir.join("indexed.png"));
    let system = picture::read_rm2k(&dir.join("indexed.png")).unwrap();
    let square = system.crop(0, 0, 32, 32);
    let (w, h) = (83, 57);
    let tiled = system::window(&system, w, h, Background::Tiled);
    let stretched = system::window(&system, w, h, Background::Stretched);
    let stretched_background = system::stretched(&square, w, h);
    let mut framed = 0;
    for y in 0..h as i64 {
        for x in 0..w as i64 {
            let border = x < 8 || y < 8 || x >= w as i64 - 8 || y >= h as i64 - 8;
            if !border {
                assert_eq!(tiled.get(x, y), square.get(x % 32, y % 32), "({x}, {y})");
            } else if stretched.get(x, y) != stretched_background.get(x, y) {
                // The frame drew here, and it is opaque: it is the same
                // frame over either background.
                assert_eq!(tiled.get(x, y), stretched.get(x, y), "({x}, {y})");
                framed += 1;
            } else if tiled.get(x, y) != square.get(x % 32, y % 32) {
                assert_eq!(tiled.get(x, y), stretched.get(x, y), "({x}, {y})");
            }
        }
    }
    assert!(framed > 0, "no pixel of the frame was checked");
}

/// The cursor's second drawing is laid out from the square at (96, 0) the
/// way the first is from the one at (64, 0).
#[test]
fn the_second_cursor_is_laid_out_like_the_first() {
    let s = systems(&scratch("second-cursor"));
    for (kind, system) in &s {
        let mut moved = system.clone();
        let square = system.crop(96, 0, 32, 32);
        moved.put(64, 0, &square);
        for (w, h) in [(100, 16), (57, 33), (16, 16)] {
            assert_eq!(
                system::cursor(system, w, h, 1),
                system::cursor(&moved, w, h, 0),
                "{kind} {w}x{h}"
            );
        }
    }
}

/// A face is its 48x48 square of the FaceSet; one partly outside a small
/// FaceSet comes out transparent where there is nothing, and one wholly
/// outside, all transparent.
#[test]
fn a_face_is_its_square_and_transparent_past_the_faceset() {
    let dir = scratch("faces");
    indexed_sheet(&dir.join("faceset.png"), 192, 192);
    indexed_sheet(&dir.join("faceset-small.png"), 100, 100);
    let read = |name: &str| picture::read_rm2k(&dir.join(format!("{name}.png"))).unwrap();
    let (whole, small) = (read("faceset"), read("faceset-small"));
    for index in [0, 5, 15] {
        let x = (index % 4) as i64 * 48;
        let y = (index / 4) as i64 * 48;
        assert_eq!(
            face::face(&whole, index),
            whole.crop(x, y, 48, 48),
            "face {index}"
        );
    }
    let partly = face::face(&small, 1);
    for y in 0..48 {
        for x in 0..48 {
            let inside = 48 + x < 100;
            let pixel = partly.get(x, y);
            if inside {
                assert_eq!(pixel, small.get(48 + x, y), "({x}, {y})");
            } else {
                assert_eq!(pixel[3], 0, "({x}, {y}) past the FaceSet");
            }
        }
    }
    let outside = face::face(&small, 15);
    assert!(outside.rgba.chunks(4).all(|p| p[3] == 0));
}

#[test]
fn a_picture_is_drawn_as_rm2k_shows_it() {
    let dir = scratch("pictures");
    let path = dir.join("picture.png");
    indexed_sheet(&path, 64, 40);
    let plain = picture::read_unkeyed(&path).unwrap();
    let keyed = picture::read_rm2k(&path).unwrap();

    // Opaque and without its transparent colour: every pixel opaque, with
    // the colours of the file.
    let drawn = show_picture::picture(&plain, &keyed, false, 0);
    assert_eq!(drawn, plain);
    assert!(drawn.rgba.chunks(4).all(|p| p[3] == 255));

    // With the transparent colour: index 0 transparent, as RM2k reads any
    // picture with its colour key.
    let drawn = show_picture::picture(&plain, &keyed, true, 0);
    assert_eq!(drawn, keyed);

    // At a transparency, every pixel that is drawn is at its opacity, and
    // the colours do not change.
    for (top_trans, alpha) in [(50, 127), (100, 0), (1, 252)] {
        let drawn = show_picture::picture(&plain, &keyed, true, top_trans);
        for (p, k) in drawn.rgba.chunks(4).zip(keyed.rgba.chunks(4)) {
            assert_eq!(p[..3], k[..3]);
            assert_eq!(
                p[3],
                if k[3] == 0 { 0 } else { alpha },
                "top_trans {top_trans}"
            );
        }
    }
}
