//! An image that fills the whole screen, compressed into one LZ2 stream:
//! the title's and the Game Over's.
//!
//! The image is the stage's —scaled to 256x224, at 8 bits per pixel on
//! BG1, which in mode 3 addresses all of CGRAM—, and what goes into the
//! cartridge is **a single stream** with the three things the ROM uploads,
//! one after the other: the tiles, 64 bytes each; the 32x32 tilemap, 2048
//! bytes; and the colours, two bytes each.
//!
//! **Or at 4 bits per pixel, the title that does not fit at 8**: see
//! [`compressed_4bpp`]. The stream is the same three things, with tiles of
//! 32 bytes. The ROM decompresses it whole
//! into WRAM and uploads it with three DMAs: see `screen_upload` in the
//! runtime's `game_over.s`.
//!
//! **Why compressed, and not a light one in the ROM with the quality one
//! in the `.msu`**, like the battle backdrops: measured on 2026-09-28 with
//! the RTP's Game Over image, at full quality it is 36,224 B of raw tiles
//! and 11,530 with LZ2; a light one would save about 9 KB of cartridge and
//! cost a second path in the ROM that no core in the suite exercises in
//! full. The numbers are in `tasks/game-over-screen.md` in the-advocate-work
//! and `compressed-title-screen.md`.

use crate::fail::{Result, Stop};
use crate::images;
use crate::pictures::png_size;
use rm2k_snes_mapdata::snes::{cgram_word, entry, pack_tile};
use serde_json::{json, Value};
use std::path::Path;

/// The console screen, in pixels and in 8x8 cells.
pub const WIDTH: i64 = 256;
pub const HEIGHT: i64 = 224;
pub const CELL: i64 = 8;
/// How many CGRAM entries the title's menu takes, since it sits on BG2 at
/// four bits per pixel: palette 0, the **first** ones, because a 4bpp BG
/// only reaches the low ones; so the image starts shifted.
pub const MENU_CGRAM: i64 = rm2k_snes_mapdata::engine::MENU_CGRAM as i64;
/// How many colours are left for the image.
pub const COLORS: i64 = 256 - MENU_CGRAM;

/// A full screen, compressed.
#[derive(Debug, Clone)]
pub struct Screen {
    pub stream: Vec<u8>,
    pub raw: usize,
    pub tiles: usize,
    pub colors: usize,
    pub first_color: i64,
    /// Bits per pixel of its tiles: 8, or 4 for a title that does not fit
    /// at 8.
    pub bpp: usize,
}

impl Screen {
    /// As `rm2k-snes-mapdata emit` takes it.
    pub fn request(&self) -> Value {
        json!({"tiles": self.tiles, "colors": self.colors, "first_color": self.first_color,
               "bpp": self.bpp, "stream": crate::text::hex(&self.stream)})
    }
}

fn color(c: &Value) -> [u8; 3] {
    [
        c[0].as_u64().unwrap_or(0) as u8,
        c[1].as_u64().unwrap_or(0) as u8,
        c[2].as_u64().unwrap_or(0) as u8,
    ]
}

/// The image at `path`, from CGRAM entry `first_color` with `cap` colours
/// left. Index 0 is also the PPU's backdrop colour, and the reduction
/// leaves black there. `below` are colours that are not the image's and go
/// in CGRAM right before its own —on the title, the menu's—: they travel
/// in the same stream and are uploaded with the same DMA, so the stream's
/// first colour drops by as many as they take.
pub fn compressed(path: &Path, first_color: i64, cap: i64, below: &[[u8; 3]]) -> Result<Screen> {
    if below.len() as i64 > first_color {
        crate::stop!(
            "{} colors below the image, and the image starts at {first_color}",
            below.len()
        );
    }
    let a = images::fullscreen(path, WIDTH, HEIGHT, CELL, first_color, cap)?;
    let tiles: Vec<Vec<Vec<u8>>> = a["tiles"]
        .as_array()
        .map(|cells| {
            cells
                .iter()
                .map(|cell| {
                    cell.as_array()
                        .map(|rows| {
                            rows.iter()
                                .map(|r| {
                                    r.as_array()
                                        .map(|r| {
                                            r.iter()
                                                .map(|v| v.as_u64().unwrap_or(0) as u8)
                                                .collect()
                                        })
                                        .unwrap_or_default()
                                })
                                .collect()
                        })
                        .unwrap_or_default()
                })
                .collect()
        })
        .unwrap_or_default();
    let tilemap: Vec<u32> = a["tilemap"]
        .as_array()
        .map(|t| t.iter().map(|v| v.as_u64().unwrap_or(0) as u32).collect())
        .unwrap_or_default();
    let mut raw = Vec::new();
    for cell in &tiles {
        raw.extend(pack_tile(cell, 8));
    }
    // The tilemap the ROM uploads: 32x32 entries, even though the screen
    // shows 28 rows. It is the size the PPU reads.
    for index in 0..32 * 32 {
        let number = tilemap.get(index).copied().unwrap_or(0);
        raw.extend_from_slice(&(entry(number, false, false, 0) as u16).to_le_bytes());
    }
    let palette: Vec<[u8; 3]> = a["palette"]
        .as_array()
        .map(|p| p.iter().map(color).collect())
        .unwrap_or_default();
    let mut colors: Vec<[u8; 3]> = below.to_vec();
    colors.extend(palette);
    for c in &colors {
        raw.extend_from_slice(&(cgram_word(*c) as u16).to_le_bytes());
    }
    let stream =
        rm2k_snes_mapdata::compress::compress(&raw).map_err(|e| Stop::new(e.to_string()))?;
    Ok(Screen {
        stream,
        raw: raw.len(),
        tiles: tiles.len(),
        colors: colors.len(),
        first_color: first_color - below.len() as i64,
        bpp: 8,
    })
}

/// How many palettes of sixteen a title at four bits gets: the BG's eight,
/// but the first, which is the menu's —it sits on BG2, also at four bits in
/// mode 1, and its palette is palette 0, as in mode 3—.
pub const PALETTES_4BPP: i64 = 7;
/// Tiles a title at four bits may take: the ten bits of a tilemap entry.
/// The worst case, every cell of the screen distinct plus the blank tile,
/// is 897, and at sixteen words each they end at $3810, below the menu's
/// tilemap: that is why this path always fits.
pub const TILES_4BPP: i64 = 1024;

/// The title at `path` at four bits per pixel, for BG1 in mode 1: the
/// layer of a big `ShowPicture` —`rm2k-snes-images background`, with its
/// colours chosen by Adeleine in seven palettes— with its corner at the
/// screen's, where RM2k draws the title, and `below`, the menu's colours,
/// as palette 0. The colours go from CGRAM 0. Also gives back the screen
/// as Adeleine left it, indexed by CGRAM entry: what goes to the build's
/// `adeleine/`.
pub fn compressed_4bpp(path: &Path, below: &[[u8; 3]]) -> Result<(Screen, Vec<u8>)> {
    let palette_size = 16;
    if below.len() > palette_size {
        crate::stop!(
            "{} colors below the title, and palette 0 holds {palette_size}",
            below.len()
        );
    }
    let (width, height) = png_size(path)?;
    let rows = HEIGHT / CELL;
    let layer = images::background(
        path,
        false,
        width.div_euclid(2),
        height.div_euclid(2),
        100,
        None,
        PALETTES_4BPP,
        1,
        TILES_4BPP,
        rows,
        false,
    )?
    .ok_or_else(|| {
        Stop::new(format!(
            "{}: the title doesn't fit at 4bpp either",
            path.display()
        ))
    })?;
    let tiles = crate::text::unhex(layer["tiles"].as_str().unwrap_or(""));
    let count = layer["tile_count"].as_u64().unwrap_or(0) as usize;
    let cells: Vec<u16> = layer["tilemap"]
        .as_array()
        .map(|t| t.iter().map(|v| v.as_u64().unwrap_or(0) as u16).collect())
        .unwrap_or_default();
    let mut raw = tiles.clone();
    // 32x32 entries, as the 8bpp one; the rows past the layer's are tile
    // 0, blank, in palette 0: the backdrop.
    for index in 0..32 * 32 {
        raw.extend_from_slice(&cells.get(index).copied().unwrap_or(0).to_le_bytes());
    }
    let mut colors: Vec<[u8; 3]> = below.to_vec();
    colors.resize(palette_size, [0, 0, 0]);
    for p in layer["palettes"].as_array().cloned().unwrap_or_default() {
        colors.extend(p.as_array().cloned().unwrap_or_default().iter().map(color));
    }
    for c in &colors {
        raw.extend_from_slice(&(cgram_word(*c) as u16).to_le_bytes());
    }
    let png = indexed_png(&tiles, &cells, &colors)?;
    let stream =
        rm2k_snes_mapdata::compress::compress(&raw).map_err(|e| Stop::new(e.to_string()))?;
    Ok((
        Screen {
            stream,
            raw: raw.len(),
            tiles: count,
            colors: colors.len(),
            first_color: 0,
            bpp: 4,
        },
        png,
    ))
}

/// The 4bpp screen as the PPU draws it: each cell's tile, flipped and in
/// its palette, as an indexed PNG of CGRAM entries with `colors` as its
/// palette.
fn indexed_png(tiles: &[u8], cells: &[u16], colors: &[[u8; 3]]) -> Result<Vec<u8>> {
    let (width, height) = (WIDTH as usize, HEIGHT as usize);
    let mut pixels = vec![0u8; width * height];
    for (k, &entry) in cells.iter().enumerate().take(width / 8 * (height / 8)) {
        let tile = &tiles[(entry as usize & 0x3FF) * 32..][..32];
        let palette = (entry as usize >> 10 & 7) * 16;
        let (hflip, vflip) = (entry & 0x4000 != 0, entry & 0x8000 != 0);
        for y in 0..8 {
            let row = if vflip { 7 - y } else { y };
            for x in 0..8 {
                let bit = if hflip { x } else { 7 - x };
                let value = (0..4).fold(0, |v, plane| {
                    let byte = tile[(plane / 2) * 16 + row * 2 + plane % 2];
                    v | ((byte >> bit & 1) as usize) << plane
                });
                if value != 0 {
                    pixels[(k / 32 * 8 + y) * width + k % 32 * 8 + x] = (palette + value) as u8;
                }
            }
        }
    }
    let mut out = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut out, width as u32, height as u32);
        encoder.set_color(png::ColorType::Indexed);
        encoder.set_depth(png::BitDepth::Eight);
        // The console's fifteen bits, at eight per channel as Adeleine's
        // images of the maps show them.
        encoder.set_palette(
            colors
                .iter()
                .flat_map(|c| c.map(|v| v << 3))
                .collect::<Vec<u8>>(),
        );
        let mut writer = encoder
            .write_header()
            .map_err(|e| Stop::new(e.to_string()))?;
        writer
            .write_image_data(&pixels)
            .map_err(|e| Stop::new(e.to_string()))?;
    }
    Ok(out)
}
