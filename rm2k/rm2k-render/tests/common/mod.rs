//! What more than one test builds: the ChipSets the Python drew from, and
//! the hash a drawing is checked by.

#![allow(dead_code)]

use rm2k_render::{picture, Picture};
use sha2::{Digest, Sha256};

/// An indexed ChipSet, every pixel from a formula: the colour key at index
/// 0, and no two neighbours alike.
pub fn indexed_chipset(path: &std::path::Path) {
    let mut encoder = png::Encoder::new(std::fs::File::create(path).unwrap(), 480, 256);
    encoder.set_color(png::ColorType::Indexed);
    encoder.set_depth(png::BitDepth::Eight);
    let palette: Vec<u8> = (0..256usize)
        .flat_map(|i| {
            [
                (i * 37 % 256) as u8,
                (i * 101 % 256) as u8,
                (i * 211 % 256) as u8,
            ]
        })
        .collect();
    encoder.set_palette(palette);
    let pixels: Vec<u8> = (0..256usize)
        .flat_map(|y| {
            (0..480usize).map(move |x| ((x * 7 + y * 13 + (x / 5) * (y / 3)) % 256) as u8)
        })
        .collect();
    let mut writer = encoder.write_header().unwrap();
    writer.write_image_data(&pixels).unwrap();
}

/// An RGBA ChipSet with half-transparent pixels, which is the only case
/// where the rounding of a blend shows.
pub fn rgba_chipset(path: &std::path::Path) {
    const ALPHAS: [u8; 5] = [0, 255, 128, 37, 200];
    let mut rgba = Vec::with_capacity(480 * 256 * 4);
    for y in 0..256usize {
        for x in 0..480usize {
            rgba.extend_from_slice(&[
                (x * 3 % 256) as u8,
                (y * 5 % 256) as u8,
                ((x + y) % 256) as u8,
                ALPHAS[(x * y + x) % 5],
            ]);
        }
    }
    let picture = Picture {
        width: 480,
        height: 256,
        rgba,
    };
    picture::write_png(path, &picture).unwrap();
}

/// The SHA-256 of a drawing's pixels, as the Python's hashes were taken:
/// the RGBA bytes, rows top to bottom.
pub fn sha(picture: &Picture) -> String {
    Sha256::digest(&picture.rgba)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}
