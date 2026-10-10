//! An image that fills the whole screen, compressed into one LZ2 stream:
//! the title's and the Game Over's.
//!
//! The image is the stage's —scaled to 256x224, at 8 bits per pixel on
//! BG1, which in mode 3 addresses all of CGRAM—, and what goes into the
//! cartridge is **a single stream** with the three things the ROM uploads,
//! one after the other: the tiles, 64 bytes each; the 32x32 tilemap, 2048
//! bytes; and the colours, two bytes each. The ROM decompresses it whole
//! into WRAM and uploads it with three DMAs: see `screen_upload` in the
//! runtime's `game_over.s`.
//!
//! **Why compressed, and not a light one in the ROM with the quality one
//! in the `.msu`**, like the battle backdrops: measured on 2026-09-28 with
//! the RTP's Game Over image, at full quality it is 36,224 B of raw tiles
//! and 11,530 with LZ2; a light one would save about 9 KB of cartridge and
//! cost a second path in the ROM that no core in the suite exercises in
//! full. The numbers are in `workflow/tasks/*/la-pantalla-de-game-over.md`
//! and `la-pantalla-de-titulo-comprimida.md`.

use crate::fail::{Result, Stop};
use crate::images;
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
}

impl Screen {
    /// As `rm2k-snes-mapdata emit` takes it.
    pub fn request(&self) -> Value {
        json!({"tiles": self.tiles, "colors": self.colors, "first_color": self.first_color,
               "stream": crate::text::hex(&self.stream)})
    }
}

fn color(c: &Value) -> [u8; 3] {
    [c[0].as_u64().unwrap_or(0) as u8, c[1].as_u64().unwrap_or(0) as u8, c[2].as_u64().unwrap_or(0) as u8]
}

/// The image at `path`, from CGRAM entry `first_color` with `cap` colours
/// left. Index 0 is also the PPU's backdrop colour, and the reduction
/// leaves black there. `below` are colours that are not the image's and go
/// in CGRAM right before its own —on the title, the menu's—: they travel
/// in the same stream and are uploaded with the same DMA, so the stream's
/// first colour drops by as many as they take.
pub fn compressed(path: &Path, first_color: i64, cap: i64, below: &[[u8; 3]]) -> Result<Screen> {
    if below.len() as i64 > first_color {
        crate::stop!("{} colors below the image, and the image starts at {first_color}", below.len());
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
                                .map(|r| r.as_array().map(|r| r.iter().map(|v| v.as_u64().unwrap_or(0) as u8).collect()).unwrap_or_default())
                                .collect()
                        })
                        .unwrap_or_default()
                })
                .collect()
        })
        .unwrap_or_default();
    let tilemap: Vec<u32> =
        a["tilemap"].as_array().map(|t| t.iter().map(|v| v.as_u64().unwrap_or(0) as u32).collect()).unwrap_or_default();
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
    let palette: Vec<[u8; 3]> = a["palette"].as_array().map(|p| p.iter().map(color).collect()).unwrap_or_default();
    let mut colors: Vec<[u8; 3]> = below.to_vec();
    colors.extend(palette);
    for c in &colors {
        raw.extend_from_slice(&(cgram_word(*c) as u16).to_le_bytes());
    }
    let stream = rm2k_snes_mapdata::compress::compress(&raw).map_err(|e| Stop::new(e.to_string()))?;
    Ok(Screen {
        stream,
        raw: raw.len(),
        tiles: tiles.len(),
        colors: colors.len(),
        first_color: first_color - below.len() as i64,
    })
}
