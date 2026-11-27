//! The party in the shop: `Window_ShopParty`.
//!
//! When buying, RM2k shows each party member's CharSet facing down and
//! walking —frames 0, 1, 2, 1—, still and in grey whoever cannot equip the
//! item the cursor marks, and next to each one an arrow from the System
//! that says whether the item would raise or lower their parameters: easyrpg's
//! `CmpEquip`, the four of them added up. The window's geometry is in
//! `layout` (`TI_PARTY_*`).
//!
//! On the console the members and the arrows are **objects**, 8x8 each: a
//! member is a 24x32 frame, three tiles by four, and every possible member
//! brings its three front frames to the cartridge, which uploads the one it
//! shows. The grey is a second palette of the same fifteen colours —their
//! luminance, `saturation_tone` at gray 0—, so it costs no tiles. The arrows
//! are the System's sixteen 8x8 at x 128: four rows —up, same, down, already
//! on— of four frames.
//!
//! What a member is drawn with is the database's CharSet: a
//! `ChangeSpriteAssociation` is not followed here (see the shop's page in
//! the book).

use crate::cells::{rgb15, Color, CELL};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::*;
use rm2k_render::picture::Picture;
use std::collections::{BTreeSet, HashMap};
use voodoo::pack::Indices;
use wally::sprites::character::{self, SPRITE_H, SPRITE_W};

/// A frame's tiles across and down.
pub const FRAME_COLS: usize = SPRITE_W / CELL;
pub const FRAME_ROWS: usize = SPRITE_H / CELL;
pub const FRAME_TILES: usize = FRAME_COLS * FRAME_ROWS;
/// The three walking frames facing down: poses 6, 7 and 8 of the CharSet.
pub const FRAMES: usize = 3;
const FACING_DOWN: i32 = 2;
/// An object palette: fifteen colours and the transparent one.
pub const PALETTE: usize = 15;
/// Where the arrows are in the System, and how many tiles they are.
pub const ARROWS_X: i64 = 128;
pub const ARROWS_Y: i64 = 0;
pub const ARROW_TILES: usize = TI_ARROW_KINDS * TI_ARROW_FRAMES;

/// RM2k's luminance weights, which add up to 65536: easyrpg's
/// `saturation_tone` at gray 0 leaves every channel at this.
const LUMA: [u32; 3] = [19595, 38470, 7471];

/// A member as the cartridge carries it: its three frames, twelve tiles
/// each by rows, and its fifteen colours in colour and in grey.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct Member {
    pub frames: Vec<Vec<Indices>>,
    pub colors: Vec<Color>,
    pub greys: Vec<Color>,
}

/// A colour's grey: its luminance in the three channels.
pub fn grey(c: Color) -> Color {
    let l = (LUMA[0] * c[0] as u32 + LUMA[1] * c[1] as u32 + LUMA[2] * c[2] as u32) >> 16;
    [l as u8; 3]
}

/// Actor `actor`'s member, or None if it has no CharSet, or one the game
/// does not have: then the shop draws nobody in its place, and its arrow.
pub fn member(game: &Game, actor: i32) -> Result<Option<Member>> {
    let Some(sheet) = game.charset(actor)? else {
        return Ok(None);
    };
    let a = &game.actors[&actor];
    let index = a.character_index;
    let poses: BTreeSet<i32> = (0..FRAMES as i32).map(|f| FACING_DOWN * 3 + f).collect();
    let (colors, lookup, mapping) = character::character_palette(&sheet, index, None, Some(&poses))
        .map_err(|e| Bad::answer(e.0))?;
    let mut frames = Vec::new();
    for &pose in &poses {
        frames.push(frame_tiles(&sheet, index, pose, &lookup, &mapping)?);
    }
    let greys = colors.iter().map(|&c| grey(c)).collect();
    Ok(Some(Member {
        frames,
        colors,
        greys,
    }))
}

/// A frame's twelve tiles, by rows, without the 32x32 object's margins.
fn frame_tiles(
    sheet: &Picture,
    index: i32,
    pose: i32,
    lookup: &HashMap<Color, u8>,
    mapping: &HashMap<Color, Color>,
) -> Result<Vec<Indices>> {
    let (ox, oy) = character::pose_origin(index, pose);
    let mut tiles = Vec::with_capacity(FRAME_TILES);
    for ty in 0..FRAME_ROWS {
        for tx in 0..FRAME_COLS {
            let mut cell = [[0u8; CELL]; CELL];
            for (y, row) in cell.iter_mut().enumerate() {
                for (x, entry) in row.iter_mut().enumerate() {
                    let p = sheet.get(ox + (tx * CELL + x) as i64, oy + (ty * CELL + y) as i64);
                    if p[3] == 0 {
                        continue;
                    }
                    let c = rgb15(p);
                    *entry = *mapping.get(&c).and_then(|m| lookup.get(m)).ok_or_else(|| {
                        Bad::answer(format!("colour {c:?} of pose {pose} has no palette entry"))
                    })?;
                }
            }
            tiles.push(cell);
        }
    }
    Ok(tiles)
}

/// The System's arrows: sixteen tiles, row by row —a kind per row, its four
/// frames across—, and the fifteen colours they are drawn with, the least
/// visible merged if there are more.
pub fn arrows(skin: &Skin) -> Result<(Vec<Indices>, Vec<Color>)> {
    let system = &skin.picture;
    let mut order = Vec::new();
    let mut counts: HashMap<Color, u64> = HashMap::new();
    for y in 0..(TI_ARROW_KINDS * CELL) as i64 {
        for x in 0..(TI_ARROW_FRAMES * CELL) as i64 {
            let p = system.get(ARROWS_X + x, ARROWS_Y + y);
            if p[3] == 0 {
                continue;
            }
            let c = rgb15(p);
            *counts.entry(c).or_insert_with(|| {
                order.push(c);
                0
            }) += 1;
        }
    }
    let counted: Vec<(Color, u64)> = order.iter().map(|&c| (c, counts[&c])).collect();
    let mapping: HashMap<Color, Color> = if counted.len() <= PALETTE {
        counted.iter().map(|&(c, _)| (c, c)).collect()
    } else {
        let merged = adeleine::merge_least_visible(&counted, PALETTE)?;
        counted
            .iter()
            .map(|&(c, _)| c)
            .zip(merged.mapping)
            .collect()
    };
    let colors: Vec<Color> = mapping
        .values()
        .copied()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let index: HashMap<Color, u8> = colors
        .iter()
        .enumerate()
        .map(|(i, &c)| (c, i as u8 + 1))
        .collect();
    let mut tiles = Vec::with_capacity(ARROW_TILES);
    for kind in 0..TI_ARROW_KINDS {
        for frame in 0..TI_ARROW_FRAMES {
            let mut cell = [[0u8; CELL]; CELL];
            for (y, row) in cell.iter_mut().enumerate() {
                for (x, entry) in row.iter_mut().enumerate() {
                    let p = system.get(
                        ARROWS_X + (frame * CELL + x) as i64,
                        ARROWS_Y + (kind * CELL + y) as i64,
                    );
                    if p[3] != 0 {
                        *entry = index[&mapping[&rgb15(p)]];
                    }
                }
            }
            tiles.push(cell);
        }
    }
    Ok((tiles, colors))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn grey_is_the_luminance() {
        assert_eq!(grey([31, 31, 31]), [31, 31, 31]);
        assert_eq!(grey([0, 0, 0]), [0, 0, 0]);
        assert_eq!(grey([31, 0, 0]), [9, 9, 9]);
    }
}
