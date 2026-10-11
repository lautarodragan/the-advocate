//! The panoramas: one record per map that shows its panorama, with what
//! the console needs to load it and to move it as RM2k does
//! —`Game_Map::Parallax`—, and its tiles and tilemap.
//!
//! The map record is full, so this is a table of its own, which only the
//! maps with a panorama are in, and only a cartridge that shows some carries
//! it: one without any gets the `.inc` it always got, and the runtime puts
//! an empty table in its place. `pano_find` in the runtime looks the loaded
//! map up in it.
//!
//! ```text
//!   +0  word   the map's index in `map_table`; $FFFF ends the table
//!   +2  byte   the mode: 3, the panorama in BG2; 1, in BG3
//!   +3  byte   bit 0: it loops across; bit 1: down; bit 2: the map raised
//!              what it draws above the hero to BG1 priority 1
//!   +4  word   how far it moves on its own each frame, signed, in 1/32 px:
//!              RM2k's speed `s` is -(1 << s), or 1 << -s if negative
//!   +6  word   and down
//!   +8  word   the stretch the cartridge carries, in pixels: the whole
//!   +10 word   picture on an axis it loops on, as far as the camera
//!              reaches on the others
//!   +12 word   not looping, it moves `num * camera / den`, RM2k's camera:
//!   +14 word   `num` across and down,
//!   +16 word   and `den`, 0 if it does not move with the camera
//!   +18 word
//!   +20 word   lcm(512, width) and lcm(256, height): where the console's
//!   +22 word   running position wraps, see `pano.s`
//!   +24 word   the stretch in 8x8 cells
//!   +26 word
//!   +28 long   its tilemap, a word per cell, rows of columns
//!   +32 long   its tiles
//!   +36 word   bytes of the first stretch of tiles, and its VRAM word;
//!   +38 word
//!   +40 word   and of the second, 0 if there is none
//!   +42 word
//!   +44 word   where its 64x32 tilemap goes in VRAM
//!   +46 word   the backdrop's colour in mode 1, $FFFF if it keeps its own
//!   +48 byte   BG3SC and BG34NBA in mode 1
//!   +49 byte
//!   +50 word   how far RM2k's camera goes: the map less RM2k's screen
//!   +52 word
//! ```

use crate::asm::{block, msu_block, pointer};
use crate::fail::{Bad, Result};
use crate::request::Map;
use crate::vram;
use std::fmt::Write;

/// A record's size.
pub const PANO_STRIDE: usize = 64;

/// RM2k's screen, in pixels and in 16x16 cells.
const RM2K_W: i64 = 320;
const RM2K_H: i64 = 240;

/// How far RM2k scrolls a panorama per frame on its own, in 1/32 px:
/// `Game_Map::Parallax::Update`'s `scroll_amt`.
pub fn auto_step(speed: i64) -> i64 {
    match speed {
        0 => 0,
        s if s < 0 => 1 << -s,
        s => -(1 << s),
    }
}

/// `num` and `den` of `Game_Map::Parallax::ResetPositionX` on one axis:
/// a panorama that does not loop moves `min(w, pano - screen) * camera /
/// w`, with `w` how far the camera goes. `(0, 0)` if it does not move.
pub fn proportion(map_cells: i64, screen: i64, pano: i64) -> (i64, i64) {
    let per_screen = (screen + 15) / 16;
    if map_cells > per_screen && pano > screen {
        let w = (map_cells - per_screen) * 16;
        (w.min(pano - screen), w)
    } else {
        (0, 0)
    }
}

fn gcd(a: i64, b: i64) -> i64 {
    if b == 0 {
        a
    } else {
        gcd(b, a % b)
    }
}

fn lcm(a: i64, b: i64) -> i64 {
    a / gcd(a, b) * b
}

/// The table, and each panorama's tiles and tilemap.
///
/// With `msu`, the tiles go marked as pieces that may travel in the `.msu`:
/// `pano_load` uploads them whole, with the screen off, through `msu_dma0`.
/// Not the tilemap, which the streaming reads row by row while the map is
/// played.
pub fn panorama_table(maps: &[Map], msu: bool) -> Result<String> {
    let mut out = vec![
        "; The panoramas: see `panorama.rs` in rm2k-snes-mapdata and `pano.s`.".to_string(),
        format!("PANO_STRIDE = {PANO_STRIDE}"),
    ];
    let mut records = Vec::new();
    let mut emitted: std::collections::HashMap<(String, Vec<u8>), String> = std::collections::HashMap::new();
    for (number, map) in maps.iter().enumerate() {
        let Some(p) = &map.panorama else { continue };
        // A painted map has its own table: see `paint_table`.
        if p.mode == 4 {
            continue;
        }
        let layout = crate::record::layout_of(map)?;
        let pieces = layout.panorama.ok_or_else(|| {
            Bad::answer(format!("map {}: it shows a panorama and its layout {} has none", map.id, layout.name))
        })?;
        if pieces.mode != p.mode {
            return Err(Bad::answer(format!(
                "map {}: its panorama goes in mode {} and the layout {} is for mode {}",
                map.id, p.mode, layout.name, pieces.mode
            )));
        }
        let bytes_per_tile = if p.mode == 3 { 32 } else { 16 };
        let count = (p.tiles.len() / bytes_per_tile) as u32;
        if count > pieces.count() {
            return Err(Bad::answer(format!(
                "map {}: its panorama has {count} tiles and the layout leaves it {}",
                map.id,
                pieces.count()
            )));
        }
        // The tilemap with its tile numbers where the tiles land.
        let base = if p.mode == 3 { layout.above.base } else { pieces.tiles[0].base };
        let mut cells = Vec::new();
        for row in &p.tilemap {
            for &entry in row {
                let k = u32::from(entry & 0x3FF);
                let renumbered = (entry & !0x3FF) | pieces.number(k, base) as u16;
                cells.extend_from_slice(&renumbered.to_le_bytes());
            }
        }
        let cols = p.tilemap.first().map_or(0, Vec::len) as i64;
        let rows = p.tilemap.len() as i64;
        let first = (pieces.tiles[0].count.min(count) as usize) * bytes_per_tile;
        let second = p.tiles.len() - first;
        // Also on an axis that loops: a `ChangePBG` can stop it, and then it
        // moves with the camera.
        let (num_x, den_x) = proportion(map.size[0], RM2K_W, p.size[0]);
        let (num_y, den_y) = proportion(map.size[1], RM2K_H, p.size[1]);
        let flags = u8::from(p.looped[0]) | (u8::from(p.looped[1]) << 1) | (u8::from(p.above_bg1) << 2);
        let words = |v: &[i64]| v.iter().map(|w| format!("${:04X}", w & 0xFFFF)).collect::<Vec<_>>().join(", ");
        let mut r = String::new();
        let _ = writeln!(r, "    ; --- map {} {:?}: {} in mode {} ---", map.id, map.name, p.name, p.mode);
        let _ = writeln!(r, "    .word {number}");
        let _ = writeln!(r, "    .byte {}, {flags}", p.mode);
        let _ = writeln!(r, "    .word {}", words(&[auto_step(p.auto[0]), auto_step(p.auto[1])]));
        let _ = writeln!(r, "    .word {}", words(&[p.stretch[0], p.stretch[1]]));
        let _ = writeln!(r, "    .word {}", words(&[num_x, num_y, den_x, den_y]));
        let _ = writeln!(r, "    .word {}", words(&[lcm(512, p.stretch[0]), lcm(256, p.stretch[1])]));
        let _ = writeln!(r, "    .word {}", words(&[cols, rows]));
        // Two maps that converted the same panorama the same way —the two
        // missile maps of A Blurred Line— share its tiles and tilemap.
        let mut shared = |kind: &str, bytes: Vec<u8>| -> String {
            if let Some(label) = emitted.get(&(kind.to_string(), bytes.clone())) {
                return label.clone();
            }
            let label = format!("pano_{kind}_{number}");
            out.push(msu_block(&label, &bytes, msu && kind == "tiles"));
            emitted.insert((kind.to_string(), bytes), label.clone());
            label
        };
        let map_label = shared("map", cells);
        let tiles_label = shared("tiles", p.tiles.clone());
        let _ = writeln!(r, "    .byte {}, 0", pointer(&map_label));
        let _ = writeln!(r, "    .byte {}, 0", pointer(&tiles_label));
        let _ = writeln!(
            r,
            "    .word {}",
            words(&[
                first as i64,
                pieces.tiles[0].base.into(),
                second as i64,
                pieces.tiles[1].base.into(),
                pieces.map.into(),
                p.backdrop.map_or(0xFFFF, i64::from),
            ])
        );
        let bg3sc = (pieces.map >> 8) as u8 | vram::MAP_LAYOUT as u8;
        let bg34nba = (pieces.tiles[0].base / 0x1000) as u8;
        let _ = writeln!(r, "    .byte ${bg3sc:02X}, ${bg34nba:02X}");
        let _ = writeln!(
            r,
            "    .word {}",
            words(&[(map.size[0] * 16 - RM2K_W).max(0), (map.size[1] * 16 - RM2K_H).max(0)])
        );
        let _ = writeln!(r, "    .res {}", PANO_STRIDE - 54);
        records.push(r);
    }
    out.push(format!(".block {}", PANO_STRIDE * records.len() + 2));
    out.push("pano_table:".into());
    for r in records {
        out.push(r.trim_end().to_string());
    }
    out.push("    .word $FFFF".into());
    Ok(out.join("\n"))
}

/// A painted map's record.
pub const PAINT_STRIDE: usize = 16;

/// The painted maps —see `Way::Painted` in Wally and `painted.s`—: one
/// record per map, and each one's cells. Not emitted in a cartridge without
/// any: the runtime assembles none of its code then.
///
/// ```text
///   +0  word   the map's index in `map_table`; $FFFF ends the table
///   +2  word   its width and height, in 8x8 cells
///   +4  word
///   +6  long   each cell's tilemap entry without its tile number —the
///              palette and the priority, `(entry >> 8) & $FC`—, a byte
///              per cell, column by column
///   +9  long   where each column's tiles start, three bytes per column:
///              the column's cells top to bottom, 32 bytes each, never
///              across a bank
///   +12 word   the VRAM word of slot 0
///   +14 word   the tilemap entry of the blank tile
/// ```
pub fn paint_table(maps: &[Map]) -> Result<String> {
    let mut out = vec![
        "; The painted maps: see `panorama.rs` in rm2k-snes-mapdata and `painted.s`.".to_string(),
        format!("PAINT_STRIDE = {PAINT_STRIDE}"),
        format!("PAINT_COLUMNS = {}", vram::PAINTED_COLUMNS),
        format!("PAINT_ROWS = {}", vram::PAINTED_ROWS),
    ];
    let mut records = Vec::new();
    for (number, map) in maps.iter().enumerate() {
        let Some(p) = map.panorama.as_ref().filter(|p| p.mode == 4) else { continue };
        let layout = crate::record::layout_of(map)?;
        let pieces = layout.panorama.filter(|q| q.mode == 4).ok_or_else(|| {
            Bad::answer(format!("map {}: it is painted and its layout {} is not for a painted map", map.id, layout.name))
        })?;
        let rows = p.tilemap.len();
        let cols = p.tilemap.first().map_or(0, Vec::len);
        let column_bytes = rows * 32;
        if rows == 0 || p.tiles.len() != cols * column_bytes || rows * cols > 0x10000 || column_bytes > 0x8000 {
            return Err(Bad::answer(format!(
                "map {}: a painting of {cols}x{rows} cells with {} bytes of tiles",
                map.id,
                p.tiles.len()
            )));
        }
        // The runtime keeps its queue at the end of the grid's bank, $7EFE00:
        // the grid and what lives behind it have to end before. See
        // `PAINT_Q` in `painted.s`.
        let in_wram = map.cells.len() + map.blocks.len() + map.block_pass.len() + map.block_terrain.len();
        if in_wram > 0x7E00 {
            return Err(Bad::answer(format!(
                "map {}: it is painted and its grid takes {in_wram} bytes of WRAM, past the painted maps' queue",
                map.id
            )));
        }
        let mut attrs = Vec::with_capacity(rows * cols);
        for x in 0..cols {
            for row in &p.tilemap {
                attrs.push(((row[x] >> 8) & 0xFC) as u8);
            }
        }
        let attrs_label = format!("paint_attrs_{number}");
        out.push(block(&attrs_label, &attrs));
        // The tiles in pieces of whole columns that fit in half a bank: the
        // packing places a `.block` whole, and a column never crosses.
        let per_piece = (0x8000 / column_bytes).max(1);
        let mut columns = Vec::with_capacity(cols);
        for (k, piece) in p.tiles.chunks(per_piece * column_bytes).enumerate() {
            let label = format!("paint_tiles_{number}_{k}");
            out.push(block(&label, piece));
            for c in 0..piece.len() / column_bytes {
                columns.push(pointer(&format!("{label} + {}", c * column_bytes)));
            }
        }
        let columns_label = format!("paint_columns_{number}");
        out.push(format!(".block {}", cols * 3));
        out.push(format!("{columns_label}:"));
        for c in &columns {
            out.push(format!("    .byte {c}"));
        }
        let mut r = String::new();
        let _ = writeln!(r, "    ; --- map {} {:?}: {} painted ---", map.id, map.name, p.name);
        let _ = writeln!(r, "    .word {number}, {cols}, {rows}");
        let _ = writeln!(r, "    .byte {}", pointer(&attrs_label));
        let _ = writeln!(r, "    .byte {}", pointer(&columns_label));
        let _ = writeln!(r, "    .word ${:04X}, ${:04X}", pieces.tiles[0].base, vram::PAINTED_BLANK);
        records.push(r);
    }
    out.push(format!(".block {}", PAINT_STRIDE * records.len() + 2));
    out.push("paint_table:".into());
    for r in records {
        out.push(r.trim_end().to_string());
    }
    out.push("    .word $FFFF".into());
    Ok(out.join("\n"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_speeds_are_rm2ks() {
        assert_eq!(auto_step(1), -2);
        assert_eq!(auto_step(8), -256);
        assert_eq!(auto_step(-4), 16);
        assert_eq!(auto_step(0), 0);
    }

    /// The northern bridge: 70 cells across, a panorama of 640. RM2k's
    /// camera goes 800 pixels and the panorama 320 of them.
    #[test]
    fn a_panorama_that_does_not_loop_moves_with_the_camera() {
        assert_eq!(proportion(70, RM2K_W, 640), (320, 800));
        // Fifteen cells down is one screen: it does not move.
        assert_eq!(proportion(15, RM2K_H, 320), (0, 0));
        // One as wide as the screen does not either.
        assert_eq!(proportion(70, RM2K_W, 320), (0, 0));
    }

    #[test]
    fn the_running_position_wraps_where_both_do() {
        assert_eq!(lcm(512, 640), 2560);
        assert_eq!(lcm(256, 320), 1280);
        assert_eq!(lcm(256, 240), 3840);
    }
}
