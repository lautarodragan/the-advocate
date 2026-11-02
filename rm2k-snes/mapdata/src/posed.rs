//! The still events drawn into the background's cells —see `posed` in
//! Wally—, as the console reads them: `posed.s` in the runtime.
//!
//! Their rows stay in the map's table, with the page's graphic, pose and
//! visibility as any still row; what tells them apart is the attribute
//! byte, whose priority bits say 3 —no character's object has it: priority
//! 3 is the pictures', the timer's, the arrow's— and whose palette bits say
//! which of the event's characters it shows; and the tile byte, which holds
//! the event's number in this table instead of a tile.

use crate::asm::{block, pointer};
use crate::fail::{Bad, Result};
use crate::request::Map;

/// The attribute byte of a row drawn into the background: priority 3 and
/// the character in the palette's bits. `posed_row` in `posed.s` tells the
/// rows apart by it.
pub fn attributes(graphic: u8) -> u8 {
    0x30 | ((graphic & 0x07) << 1)
}

/// The grid's place in WRAM: see `GRID` in the runtime's `far_ram.s`. Its
/// second 32 KB are the upper half of bank $7F.
const GRID: u32 = 0x7E8000;
const GRID_HIGH: u32 = 0x7F8000;

/// How many a map can have: the row's tile byte numbers them, and the
/// console's table of what each one shows has this many bytes.
pub const POSED_MAX: usize = 104;

/// One record per event, [`POSED_STRIDE`] bytes:
///
/// ```text
///   +0  long   its cell of the grid in WRAM
///   +3  word   its cell in 8x8 cells, x and y
///   +7  word   the block of its cell without it
///   +9  word   where its blocks start, from the map's record
///   +11 byte   the key it starts with: character * 12 + pose, $FF hidden
/// ```
///
/// and after them each one's blocks, twelve words per character, one per
/// pose.
pub const POSED_STRIDE: usize = 12;

/// The table of every map that has some: `posed_table`, five bytes a map —its
/// index in `map_table` and where its record is— ended by $FFFF; and each
/// map's record, its count first. See `posed_find` in the runtime.
pub fn posed_table(maps: &[Map]) -> Result<String> {
    let mut out = vec![
        "; The still events drawn into the background: see `posed.rs` in rm2k-snes-mapdata and `posed.s`."
            .to_string(),
        "posed_stills = 1".to_string(),
        format!("POSED_STRIDE = {POSED_STRIDE}"),
        format!("POSED_MAX = {POSED_MAX}"),
    ];
    let mut entries = Vec::new();
    for (number, map) in maps.iter().enumerate() {
        if map.posed.is_empty() {
            continue;
        }
        if map.posed.len() > POSED_MAX {
            return Err(Bad::answer(format!(
                "map {}: {} events drawn into the background and the console numbers {POSED_MAX}",
                map.id,
                map.posed.len()
            )));
        }
        let bytes = if map.narrow() { 1 } else { 2 };
        let width = map.size[0];
        let head = 1 + POSED_STRIDE * map.posed.len();
        let mut data = vec![map.posed.len() as u8];
        let mut blocks = Vec::new();
        for p in &map.posed {
            let offset = ((p.y * width + p.x) * bytes) as u32;
            let at = if offset < 0x8000 {
                GRID + offset
            } else {
                GRID_HIGH + offset - 0x8000
            };
            data.extend_from_slice(&at.to_le_bytes()[..3]);
            data.extend_from_slice(&((p.x * 2) as u16).to_le_bytes());
            data.extend_from_slice(&((p.y * 2) as u16).to_le_bytes());
            data.extend_from_slice(&(p.none as u16).to_le_bytes());
            let from = (head + 2 * blocks.len()) as u16;
            data.extend_from_slice(&from.to_le_bytes());
            data.push(p.start as u8);
            blocks.extend(p.blocks.iter().map(|&b| b as u16));
        }
        for b in blocks {
            data.extend_from_slice(&b.to_le_bytes());
        }
        let label = format!("posed_{number}");
        out.push(block(&label, &data));
        entries.push(format!("    .word {number}\n    .byte {}", pointer(&label)));
    }
    out.push(format!(".block {}", 5 * entries.len() + 2));
    out.push("posed_table:".into());
    out.extend(entries);
    out.push("    .word $FFFF".into());
    Ok(out.join("\n"))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The first map of `tests/maps.json` with one event drawn into the
    /// background, at (3, 2).
    fn with_one() -> Map {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json");
        let mut map = crate::request::read::<crate::request::Maps>(&path)
            .unwrap()
            .maps
            .remove(0);
        let mut blocks = vec![7u32; 12];
        blocks[10] = 8;
        map.posed = vec![crate::request::Posed {
            event: 5,
            x: 3,
            y: 2,
            blocks,
            none: 6,
            start: 7,
        }];
        map
    }

    /// The record says where its cell is in the grid and in 8x8 cells,
    /// the cell without it, where its blocks are and the key it starts
    /// with; its blocks follow, a word each.
    #[test]
    fn an_event_s_record_and_its_blocks() {
        let map = with_one();
        let text = posed_table(&[map]).unwrap();
        assert!(text.contains("posed_stills = 1"));
        assert!(text.contains("posed_table:"));
        assert!(text.contains("    .word 0\n    .byte <(posed_0), >(posed_0), ^(posed_0)"));
        let first = text.lines().position(|l| l == "posed_0:").unwrap();
        let bytes: Vec<u8> = text
            .lines()
            .skip(first + 1)
            .take_while(|l| l.starts_with("    .byte $"))
            .flat_map(|l| {
                l.trim_start_matches("    .byte ")
                    .split(',')
                    .map(|b| u8::from_str_radix(b.trim().trim_start_matches('$'), 16).unwrap())
                    .collect::<Vec<_>>()
            })
            .collect();
        let map = with_one();
        let cell = (2 * map.size[0] + 3) as u32 * if map.narrow() { 1 } else { 2 };
        assert_eq!(bytes[0], 1);
        assert_eq!(&bytes[1..4], &(GRID + cell).to_le_bytes()[..3]);
        assert_eq!(&bytes[4..8], &[6, 0, 4, 0]);
        assert_eq!(&bytes[8..10], &[6, 0]);
        assert_eq!(&bytes[10..12], &13u16.to_le_bytes());
        assert_eq!(bytes[12], 7);
        assert_eq!(&bytes[13..15], &[7, 0]);
        assert_eq!(&bytes[13 + 20..13 + 22], &[8, 0]);
    }

    #[test]
    fn a_posed_row_has_the_priority_no_character_has() {
        assert_eq!(super::attributes(0), 0x30);
        assert_eq!(super::attributes(5), 0x3A);
    }
}
