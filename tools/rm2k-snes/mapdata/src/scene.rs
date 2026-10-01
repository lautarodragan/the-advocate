//! The battle scene, as the `.inc` carries it: the backdrops and the
//! battlers separately, which the console composes when a battle starts.
//!
//! What a backdrop and a battler look like, where each member stands and in
//! which order they are drawn are the scene's —the converter's `scene.py`—
//! and come in the request already as bytes and numbers: see `scene` in the
//! request. Here they are only written.

use crate::asm::block;
use crate::fail::{Bad, Result};
use crate::json::{at, bytes_at, colors, int, int_at, ints, ints_at, list, list_at};
use crate::snes::{cgram_bytes, pack_tile};
use serde_json::Value;
use std::collections::HashMap;

/// What goes in the backdrop tables instead of a backdrop's number: the
/// plain one, and the place's, which the console resolves with the terrain.
pub const FLAT_BACKDROP: u8 = 0xFF;
pub const PLACE_BACKDROP: u8 = 0xFE;

/// The upper half of an 8bpp tile of the fallback: planes 4 to 7, which are
/// those of `cgram_base` in every pixel, and which the console appends
/// after each 4bpp tile.
fn fallback_height(cgram_base: u8, planes: usize) -> Vec<u8> {
    let full = vec![vec![cgram_base; 8]; 8];
    pack_tile(&full, 8)[planes * 8..].to_vec()
}

/// The table `scn_double` enlarges the fallback with: per byte, a word with
/// its two nibbles doubled bit by bit, the high one in the low byte.
fn fallback_double() -> Vec<u8> {
    let double = |nibble: u32| {
        (0..4)
            .filter(|b| nibble >> b & 1 != 0)
            .map(|b| 0b11 << (2 * b))
            .sum::<u32>()
    };
    (0..256u32)
        .flat_map(|s| {
            let w = double(s >> 4) | double(s & 0xF) << 8;
            [(w & 0xFF) as u8, (w >> 8) as u8]
        })
        .collect()
}

fn byte_list(values: Vec<i64>, empty: u8) -> Vec<u8> {
    if values.is_empty() {
        vec![empty]
    } else {
        values.into_iter().map(|v| v as u8).collect()
    }
}

/// The cartridge's battle scene. `used` are the troops in the order of
/// `troop_id`.
pub fn scenes_asm(scene: &Value, used: &[i64]) -> Result<String> {
    let g = at(scene, "geometry")?;
    let n = |name: &str| int_at(g, name);
    let backdrops = list_at(scene, "backdrops")?;
    let battlers = list_at(scene, "battlers")?;
    let terrains = ints_at(scene, "terrains")?;
    let mut out: Vec<String> = vec![
        "\n; --- the battle scene: the backdrops and the battlers ---".into(),
        ";".into(),
        "; They go separately and the ROM composes them in an 8bpp layer of".into(),
        "; 256x128, which is the seven text lines at the top. The reason is".into(),
        "; in tools/port/scene.py; only the bytes travel here.".into(),
        "; The game's backdrops, which the .msu carries all of, and the ROM's.".into(),
        format!("BACKDROPS_GAME  = {}", int_at(scene, "game")?),
        format!("SCENE_BACKDROPS = {}", backdrops.len()),
        format!("BACKDROP_PLAIN  = ${FLAT_BACKDROP:02X}"),
        format!("PLACE_BACKDROP = ${PLACE_BACKDROP:02X}"),
        format!("BACKDROP_TERRAINS = {}", terrains.len().max(1)),
        format!("SCENE_BATTLERS = {}", battlers.len()),
        format!("SCENE_WIDTH     = {}", n("WIDTH")?),
        format!("SCENE_HEIGHT    = {}", n("HEIGHT")?),
        format!("SCENE_TILES     = {}", n("TILES")?),
        format!("SCENE_ROWS      = {}", n("TILES_Y")?),
        format!("SCENE_COLUMNS = {}", n("TILES_X")?),
        format!("SCENE_COLORS    = {}", n("COLORS")?),
        format!("SCENE_CGRAM     = {}", n("CGRAM_BASE")?),
        format!("SCENE_VRAM      = ${:04X}", n("VRAM_TILES")?),
        format!("SCENE_MAP       = ${:04X}", n("VRAM_MAP")?),
        "; The ROM's light fallback: 4bpp and a single palette. See".into(),
        "; tools/port/scene.py.".into(),
        format!("FALLBACK_COLORS = {}", n("FALLBACK_COLORS")?),
        format!("FALLBACK_TILE   = {}", n("FALLBACK_PLANES")? * 8),
        format!(
            "FALLBACK_BYTES  = {}",
            n("FALLBACK_WIDTH")? * n("FALLBACK_HEIGHT")? * n("FALLBACK_PLANES")? / 8
        ),
        format!("FALLBACK_SCALE = {}", n("FALLBACK_SCALE")?),
        format!("SCENE_BAT_PALETTE = {}", n("BATTLER_PALETTE")?),
        "; The tile that covers what is left below the scene. It falls".into(),
        "; **outside** the tile block: 512 8bpp tiles are the 16,384 words".into(),
        "; that go from SCENE_VRAM to the end of VRAM, so 512 wraps around".into(),
        "; and lands on word 0, which during the battle is map VRAM that".into(),
        "; nobody uses.".into(),
        format!("SCENE_TARGET    = {}", n("TILES")?),
    ];
    let troop_backdrop: HashMap<i64, i64> = list_at(scene, "troop_backdrop")?
        .iter()
        .map(|p| {
            let p = ints(p)?;
            Ok((p[0], p[1]))
        })
        .collect::<Result<_>>()?;
    let by_troop: Vec<i64> = used
        .iter()
        .map(|t| troop_backdrop.get(t).copied().unwrap_or(0xFF))
        .collect();
    out.push(block("scene_troop_backdrop", &byte_list(by_troop, 0xFF)));
    out.push(block(
        "scene_map_backdrop",
        &byte_list(ints_at(scene, "map_backdrop")?, 0xFF),
    ));
    let terrain_bytes = if terrains.is_empty() {
        vec![FLAT_BACKDROP]
    } else {
        byte_list(terrains, FLAT_BACKDROP)
    };
    out.push(block("backdrop_terrain", &terrain_bytes));
    out.push(block(
        "backdrop_fallback",
        &byte_list(ints_at(scene, "fallback_of")?, 0),
    ));
    let mut pointers = vec![
        format!(".block {}", 4 * backdrops.len().max(1)),
        "backdrop_dir:".to_string(),
    ];
    for k in 0..backdrops.len() {
        pointers.push(format!("    .dword backdrop_{k}"));
    }
    if backdrops.is_empty() {
        pointers.push("    .dword 0".into());
    }
    out.push(pointers.join("\n"));
    let mut cgram = Vec::new();
    for b in backdrops {
        cgram.extend(bytes_at(b, "colors")?);
    }
    out.push(block(
        "backdrop_cgram",
        if cgram.is_empty() { &[0, 0] } else { &cgram },
    ));
    out.push(block(
        "fallback_height",
        &fallback_height(n("CGRAM_BASE")? as u8, n("FALLBACK_PLANES")? as usize),
    ));
    out.push(block("fallback_double", &fallback_double()));
    // Sixty-four zeros: the transparent tile under the scene, and the fixed
    // source of the DMA that fills the plain backdrop.
    out.push(block("scene_zero", &[0; 64]));
    // Each fallback in a block that does not cross a bank: the console reads
    // it with `[pointer]` and adds to it only the low sixteen bits.
    for (k, b) in backdrops.iter().enumerate() {
        out.push(block(&format!("backdrop_{k}"), &bytes_at(b, "tiles")?));
    }
    // The battlers: their tables and then their bytes.
    let columns: Vec<i64> = battlers
        .iter()
        .map(|b| int_at(b, "columns"))
        .collect::<Result<_>>()?;
    let heights: Vec<i64> = battlers
        .iter()
        .map(|b| int_at(b, "height"))
        .collect::<Result<_>>()?;
    out.push(block("battler_n", &byte_list(columns.clone(), 0)));
    out.push(block("battler_height", &byte_list(heights.clone(), 0)));
    let mut planes = Vec::new();
    for (c, h) in columns.iter().zip(&heights) {
        let size = ((c + 1) * h) as u16;
        planes.extend_from_slice(&size.to_le_bytes());
    }
    out.push(block(
        "battler_plane",
        if planes.is_empty() { &[0, 0] } else { &planes },
    ));
    let mut pointers = vec![
        format!(".block {}", 4 * battlers.len().max(1)),
        "battler_dir:".to_string(),
    ];
    pointers.extend((0..battlers.len()).map(|k| format!("    .dword battler_{k}")));
    if battlers.is_empty() {
        pointers.push("    .dword 0".into());
    }
    out.push(pointers.join("\n"));
    let mut cgram = Vec::new();
    for b in battlers {
        let mut palette = vec![[0u8, 0, 0]];
        palette.extend(colors(at(b, "palette")?)?);
        palette.resize(palette.len().max(16), [0, 0, 0]);
        cgram.extend(cgram_bytes(&palette));
    }
    out.push(block(
        "battler_cgram",
        if cgram.is_empty() { &[0, 0] } else { &cgram },
    ));
    // Per troop member, which battler, where its corner falls and which one
    // of the troop goes in that place of the drawing order.
    let mut placed: HashMap<i64, (&Vec<Value>, Vec<i64>)> = HashMap::new();
    for t in list_at(scene, "troops")? {
        let t = list(t)?;
        placed.insert(int(&t[0])?, (list(&t[1])?, ints(&t[2])?));
    }
    let (mut member_b, mut member_x, mut member_y, mut member_command) =
        (vec![], vec![], vec![], vec![]);
    for number in used {
        let (members, order) = placed
            .get(number)
            .ok_or_else(|| Bad::answer(format!("the scene has nothing of troop {number}")))?;
        for m in members.iter() {
            let m = ints(m)?;
            member_b.push(m[0]);
            member_x.push(m[1]);
            member_y.push(m[2]);
        }
        member_command.extend(order.iter().copied());
    }
    out.push(block("member_battler", &byte_list(member_b, 0xFF)));
    out.push(block("member_x", &byte_list(member_x, 0)));
    out.push(block("member_y", &byte_list(member_y, 0)));
    out.push(block("member_command", &byte_list(member_command, 0)));
    for (k, b) in battlers.iter().enumerate() {
        out.push(block(&format!("battler_{k}"), &bytes_at(b, "bytes")?));
    }
    Ok(out.join("\n") + "\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_doubling_table_spreads_each_nibble_bit_by_bit() {
        let t = fallback_double();
        assert_eq!(t.len(), 512);
        // 0x1F: the high nibble 1 doubles to 0b11 in the low byte, the low
        // nibble F to 0xFF in the high one.
        assert_eq!(&t[0x1F * 2..0x1F * 2 + 2], &[0x03, 0xFF]);
    }

    #[test]
    fn the_fallback_s_upper_half_carries_the_base_in_every_pixel() {
        // 32 is plane 5 alone: the second plane of the pair 4/5, every row;
        // the pair 6/7 stays empty.
        let h = fallback_height(32, 4);
        assert_eq!(h.len(), 32);
        assert!(h[..16].chunks(2).all(|pair| pair == [0x00, 0xFF]));
        assert!(h[16..].iter().all(|&b| b == 0));
    }
}
