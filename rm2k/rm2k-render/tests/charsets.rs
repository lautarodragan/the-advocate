//! CharSet sheets, an event drawn with a tile, and translucent sheets,
//! over CharSets, ChipSets and a background generated inside this file,
//! which need no game and no RTP.
//!
//! The inputs touch what can differ: an indexed CharSet —the colour key at
//! index 0— and an RGBA one with half-transparent pixels; tiles of an
//! indexed ChipSet and of a half-transparent one; and translucent sheets on
//! cells in the middle of the background and against its edges, where what
//! is behind is black.
//!
//! **The path it guards**: the RGBA pictures and the edges, which a game's
//! events do not bring. What a real event looks like is A Blurred Line's
//! goldens'. What is checked is what the drawing promises: a tile in each
//! of the twelve poses and nothing else, and a translucent pixel that is
//! opaque, between the sheet's colour and what is behind, and nearer the
//! sheet's.

mod common;

use common::{indexed_chipset, rgba_chipset};
use rm2k_render::charset::{tile_sheet, translucent, SHEET_HEIGHT, SHEET_WIDTH};
use rm2k_render::{picture, Picture};
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-render-charsets-{}-{name}",
        std::process::id()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// An indexed CharSet: a quarter of it the colour key, the rest from a
/// formula.
fn indexed_charset(path: &Path) {
    let mut encoder = png::Encoder::new(
        std::fs::File::create(path).unwrap(),
        SHEET_WIDTH as u32,
        SHEET_HEIGHT as u32,
    );
    encoder.set_color(png::ColorType::Indexed);
    encoder.set_depth(png::BitDepth::Eight);
    let palette: Vec<u8> = (0..256usize)
        .flat_map(|i| {
            [
                (i * 53 % 256) as u8,
                (i * 29 % 256) as u8,
                (i * 197 % 256) as u8,
            ]
        })
        .collect();
    encoder.set_palette(palette);
    let pixels: Vec<u8> = (0..SHEET_HEIGHT)
        .flat_map(|y| {
            (0..SHEET_WIDTH).map(move |x| {
                if (x + y) % 4 == 0 {
                    0
                } else {
                    ((x * 11 + y * 5 + (x / 7) * (y / 4)) % 256) as u8
                }
            })
        })
        .collect();
    let mut writer = encoder.write_header().unwrap();
    writer.write_image_data(&pixels).unwrap();
}

/// An RGBA CharSet with half-transparent pixels.
fn rgba_charset(path: &Path) {
    const ALPHAS: [u8; 4] = [0, 255, 90, 255];
    let mut rgba = Vec::with_capacity(SHEET_WIDTH * SHEET_HEIGHT * 4);
    for y in 0..SHEET_HEIGHT {
        for x in 0..SHEET_WIDTH {
            rgba.extend_from_slice(&[
                (x * 5 % 256) as u8,
                (y * 3 % 256) as u8,
                ((x * y) % 256) as u8,
                ALPHAS[(x + 3 * y) % 4],
            ]);
        }
    }
    let picture = Picture {
        width: SHEET_WIDTH,
        height: SHEET_HEIGHT,
        rgba,
    };
    picture::write_png(path, &picture).unwrap();
}

/// What is behind: 6 cells by 5, opaque, as a map's lower layer is.
fn behind() -> Picture {
    let (width, height) = (96, 80);
    let rgba = (0..height)
        .flat_map(|y: usize| {
            (0..width).flat_map(move |x: usize| {
                [
                    (x * 9 % 256) as u8,
                    (y * 7 % 256) as u8,
                    ((x + 2 * y) % 256) as u8,
                    255,
                ]
            })
        })
        .collect();
    Picture {
        width,
        height,
        rgba,
    }
}

/// The drawn pixels of a picture.
fn drawn(p: &Picture) -> usize {
    p.rgba.chunks_exact(4).filter(|px| px[3] != 0).count()
}

#[test]
fn a_tile_goes_in_each_of_the_twelve_poses_and_nowhere_else() {
    let dir = scratch("tiles");
    for (name, write) in [
        ("indexed", indexed_chipset as fn(&Path)),
        ("rgba", rgba_chipset),
    ] {
        let path = dir.join(format!("{name}.png"));
        write(&path);
        let chipset = picture::read_rm2k(&path).unwrap();
        for index in [0, 5, 7, 100, 143] {
            let sheet = tile_sheet(&chipset, index);
            assert_eq!((sheet.width, sheet.height), (SHEET_WIDTH, SHEET_HEIGHT));
            let poses = drawn(&sheet);
            assert_eq!(poses % 12, 0, "{name} tile {index}: {poses} pixels");
            // Pose 0 is the top-left one, and the others are copies of it.
            let pose = |n: usize| -> Vec<u8> {
                let (x0, y0) = ((n % 3) * 24, (n / 3) * 32);
                (y0..y0 + 32)
                    .flat_map(|y| {
                        let at = (y * sheet.width + x0) * 4;
                        sheet.rgba[at..at + 24 * 4].to_vec()
                    })
                    .collect()
            };
            for n in 1..12 {
                assert_eq!(pose(n), pose(0), "{name} tile {index}: pose {n}");
            }
        }
    }
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_translucent_pixel_is_opaque_and_nearer_the_sheet_than_what_is_behind() {
    let dir = scratch("translucent");
    let read = |name: &str, write: fn(&Path)| {
        let path = dir.join(name);
        write(&path);
        picture::read_rm2k(&path).unwrap()
    };
    let indexed = read("indexed-charset.png", indexed_charset);
    let rgba = read("rgba-charset.png", rgba_charset);
    let rgba_tile = tile_sheet(&read("rgba-chipset.png", rgba_chipset), 7);
    std::fs::remove_dir_all(&dir).unwrap();
    let behind = behind();
    for (name, sheet, x, y) in [
        ("indexed", &indexed, 0, 0),
        ("indexed", &indexed, 3, 2),
        ("indexed past the edge", &indexed, 5, 4),
        ("RGBA", &rgba, 2, 1),
        ("RGBA tile", &rgba_tile, 1, 1),
    ] {
        let out = translucent(sheet, &behind, x, y);
        let mut black = 0;
        for (k, (o, s)) in out
            .rgba
            .chunks_exact(4)
            .zip(sheet.rgba.chunks_exact(4))
            .enumerate()
        {
            if s[3] == 0 {
                assert_eq!(o, s, "{name}: pixel {k} was transparent");
                continue;
            }
            assert_eq!(o[3], 255, "{name}: pixel {k} not opaque");
            for c in 0..3 {
                // Nearer the sheet's colour: at least as far from black as
                // 160/255 of it, and no farther than that plus what is behind.
                let least = s[c] as u32 * 160 / 255;
                let most = least + 95 + 1;
                assert!(
                    (least..=most).contains(&(o[c] as u32)),
                    "{name}: pixel {k}, channel {c}: {} over {}",
                    o[c],
                    s[c]
                );
            }
            if o[..3]
                .iter()
                .zip(&s[..3])
                .all(|(o, s)| *o as u32 == *s as u32 * 160 / 255)
            {
                black += 1;
            }
        }
        if name.contains("edge") {
            assert!(black > 0, "{name}: nothing black behind past the edge");
        }
    }
}
