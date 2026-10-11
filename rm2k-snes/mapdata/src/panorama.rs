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

use crate::asm::{msu_block, pointer};
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
