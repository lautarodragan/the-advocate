//! The screen a cartridge that needs the MSU-1 shows when it is not there.
//!
//! A cartridge whose ROM does not reach carries in the `.msu` what does not
//! fit —see `pack_with_msu` in `rm2k-snes-cartridge`—, and without the
//! MSU-1, or with a `.msu` from another build, it cannot start: the runtime
//! checks it at boot and, if it fails, shows this and stops. See
//! `msu_required` in the runtime's `msu1.s`.
//!
//! It is a full screen like the Game Over —the same row in `screens_table`,
//! the same upload— so it costs the ROM a stream and no code of its own to
//! draw. The text is drawn here with the game's font, white with a shadow,
//! over black, and **in English**: RM2k has no term for this, and the
//! player who reads it is the one who has to find an emulator or a cart
//! with the chip, not the one who plays the game in its language.

use crate::fail::{Result, Stop};
use crate::fullscreen::{self, Screen, HEIGHT, WIDTH};
use rm2k_snes_text::font::Font;
use std::path::Path;

/// What it says, one line per row; an empty one is a blank row.
pub const LINES: [&str; 6] = [
    "This game needs an MSU-1.",
    "",
    "Play it on a console or emulator",
    "that has one, with the .msu file",
    "next to the ROM and with its name:",
    "part of the game travels in it.",
];

/// Between one row's top and the next's.
const LINE: i64 = 16;
const WHITE: [u8; 3] = [248, 248, 248];
const SHADOW: [u8; 3] = [64, 64, 64];

/// The picture, as RGB rows, and its compressed screen. The picture is
/// written to `png` too, to look at it without running the ROM.
pub fn screen(font: &Font, png: &Path) -> Result<Screen> {
    let (w, h) = (WIDTH as usize, HEIGHT as usize);
    let mut rgb = vec![0u8; w * h * 3];
    let top = (HEIGHT - LINE * LINES.len() as i64) / 2;
    for (row, text) in LINES.iter().enumerate() {
        let width = font.width(text) as i64;
        if width > WIDTH - 16 {
            return Err(Stop::new(format!(
                "the MSU-1 screen's line {text:?} is {width} pixels wide with this font, and {} fit",
                WIDTH - 16
            )));
        }
        let mut x = (WIDTH - width) / 2;
        let y = top + LINE * row as i64;
        for ch in text.chars() {
            for (d, color) in [(1, SHADOW), (0, WHITE)] {
                for (px, py) in font.pixels(ch) {
                    let (dx, dy) = (x + px as i64 + d, y + py as i64 + d);
                    if (0..WIDTH).contains(&dx) && (0..HEIGHT).contains(&dy) {
                        let at = (dy as usize * w + dx as usize) * 3;
                        rgb[at..at + 3].copy_from_slice(&color);
                    }
                }
            }
            x += font.advance(ch) as i64;
        }
    }
    let file = std::fs::File::create(png).map_err(|e| crate::fail::io(png, e))?;
    let mut encoder = png::Encoder::new(std::io::BufWriter::new(file), w as u32, h as u32);
    encoder.set_color(png::ColorType::Rgb);
    encoder.set_depth(png::BitDepth::Eight);
    let mut writer = encoder.write_header().map_err(|e| Stop::new(format!("{}: {e}", png.display())))?;
    writer.write_image_data(&rgb).map_err(|e| Stop::new(format!("{}: {e}", png.display())))?;
    writer.finish().map_err(|e| Stop::new(format!("{}: {e}", png.display())))?;
    fullscreen::compressed(png, 0, 256, &[])
}
