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
#[derive(Debug, Clone)]
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
    let (colors, lookup, mapping) =
        character::character_palette(&sheet, index, None, Some(&poses)).map_err(|e| Bad::answer(e.0))?;
    let mut frames = Vec::new();
    for &pose in &poses {
        frames.push(frame_tiles(&sheet, index, pose, &lookup, &mapping)?);
    }
    let greys = colors.iter().map(|&c| grey(c)).collect();
    Ok(Some(Member { frames, colors, greys }))
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
        counted.iter().map(|&(c, _)| c).zip(merged.mapping).collect()
    };
    let colors: Vec<Color> = mapping.values().copied().collect::<BTreeSet<_>>().into_iter().collect();
    let index: HashMap<Color, u8> = colors.iter().enumerate().map(|(i, &c)| (c, i as u8 + 1)).collect();
    let mut tiles = Vec::with_capacity(ARROW_TILES);
    for kind in 0..TI_ARROW_KINDS {
        for frame in 0..TI_ARROW_FRAMES {
            let mut cell = [[0u8; CELL]; CELL];
            for (y, row) in cell.iter_mut().enumerate() {
                for (x, entry) in row.iter_mut().enumerate() {
                    let p = system.get(ARROWS_X + (frame * CELL + x) as i64, ARROWS_Y + (kind * CELL + y) as i64);
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

/// What the window shows of one member: whether it can equip the item, and
/// which arrow it gets, if any.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Shown {
    pub usable: bool,
    pub arrow: Option<usize>,
}

/// `Window_ShopParty::Refresh` for one member and the item the cursor
/// marks —0 for none, which an empty shop has—: greyed out if it cannot
/// equip it (`IsEquippable`), and if it can and the item is equipment,
/// "already on" if it has one on, or else up, same or down by `CmpEquip`:
/// attack, defense, spirit and agility added up, each clamped, with the
/// item on against without it.
pub fn shown(game: &Game, actor: i32, equipment: &[i32], item: i32) -> Result<Shown> {
    if item == 0 {
        return Ok(Shown { usable: true, arrow: None });
    }
    let it = game.item(item)?;
    let usable = rm2k_snes_battle::rules::item_usable_by(it, actor as i64);
    let kind = it.r#type.to_i32();
    if !usable || !(1..=5).contains(&kind) {
        return Ok(Shown { usable, arrow: None });
    }
    if equipment.contains(&item) {
        return Ok(Shown { usable, arrow: Some(TI_ARROW_EQUIPPED) });
    }
    let before: i64 = crate::texts::equipped_params(game, actor, equipment).iter().sum();
    let mut after_equipment = equipment.to_vec();
    let mut inventory = std::collections::BTreeMap::from([(item, 1)]);
    crate::render::equip(game, &mut after_equipment, &mut inventory, (kind - 1) as usize, item)?;
    let after: i64 = crate::texts::equipped_params(game, actor, &after_equipment).iter().sum();
    let arrow = match after.cmp(&before) {
        std::cmp::Ordering::Greater => TI_ARROW_UP,
        std::cmp::Ordering::Equal => TI_ARROW_SAME,
        std::cmp::Ordering::Less => TI_ARROW_DOWN,
    };
    Ok(Shown { usable, arrow: Some(arrow) })
}

/// The walking frame a member shows at `phase` —0 to 3, a step every
/// `TI_PARTY_RATE` frames—: 0, 1, 2, 1, and the middle one still when it
/// cannot equip the item.
pub fn walking_frame(phase: usize, usable: bool) -> usize {
    if !usable || phase == 3 {
        1
    } else {
        phase
    }
}

/// The arrow's frame at `phase`: the four in a row, but "already on", which
/// walks like the members.
pub fn arrow_frame(phase: usize, arrow: usize) -> usize {
    if arrow == TI_ARROW_EQUIPPED {
        walking_frame(phase, true)
    } else {
        phase
    }
}

/// Draws one 8x8 tile of `colors` (index 1 is the first) at `(x, y)`.
fn tile(on: &mut Picture, x: usize, y: usize, cell: &Indices, colors: &[Color]) {
    for (dy, row) in cell.iter().enumerate() {
        for (dx, &k) in row.iter().enumerate() {
            if k == 0 {
                continue;
            }
            let c = colors[k as usize - 1];
            let at = ((y + dy) * on.width + x + dx) * 4;
            on.rgba[at..at + 4].copy_from_slice(&[c[0] << 3, c[1] << 3, c[2] << 3, 255]);
        }
    }
}

/// The party window's members and arrows over `on`, as the console shows
/// them: `party` the actors with their equipment, `frames` the walking
/// frame each one has up —the console uploads them when the vblank has
/// room, so a capture can catch them a frame apart— and `phase` the
/// arrows'.
pub fn draw(
    game: &Game,
    skin: &Skin,
    on: &mut Picture,
    party: &[(i32, Vec<i32>)],
    item: i32,
    frames: &[usize],
    phase: usize,
) -> Result<()> {
    let (arrow_tiles, arrow_colors) = arrows(skin)?;
    for (i, (actor, equipment)) in party.iter().take(TI_PARTY_MEMBERS).enumerate() {
        let x = TI_PARTY_X0 + i * TI_PARTY_STEP;
        let s = shown(game, *actor, equipment, item)?;
        if let Some(m) = member(game, *actor)? {
            let frame = frames.get(i).copied().filter(|&f| f < FRAMES).unwrap_or(1);
            let colors = if s.usable { &m.colors } else { &m.greys };
            for (k, cell) in m.frames[frame].iter().enumerate() {
                tile(on, x + (k % FRAME_COLS) * CELL, TI_PARTY_Y0 + (k / FRAME_COLS) * CELL, cell, colors);
            }
        }
        if let Some(arrow) = s.arrow {
            let cell = &arrow_tiles[arrow * TI_ARROW_FRAMES + arrow_frame(phase, arrow)];
            tile(on, x + TI_ARROW_DX, TI_PARTY_Y0 + TI_ARROW_DY, cell, &arrow_colors);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_walk_goes_0_1_2_1_and_still_when_greyed_out() {
        let walk: Vec<usize> = (0..4).map(|p| walking_frame(p, true)).collect();
        assert_eq!(walk, [0, 1, 2, 1]);
        assert!((0..4).all(|p| walking_frame(p, false) == 1));
    }

    #[test]
    fn the_arrows_run_their_four_frames_and_already_on_walks() {
        let up: Vec<usize> = (0..4).map(|p| arrow_frame(p, TI_ARROW_UP)).collect();
        assert_eq!(up, [0, 1, 2, 3]);
        let on: Vec<usize> = (0..4).map(|p| arrow_frame(p, TI_ARROW_EQUIPPED)).collect();
        assert_eq!(on, [0, 1, 2, 1]);
    }

    #[test]
    fn grey_is_the_luminance() {
        assert_eq!(grey([31, 31, 31]), [31, 31, 31]);
        assert_eq!(grey([0, 0, 0]), [0, 0, 0]);
        assert_eq!(grey([31, 0, 0]), [9, 9, 9]);
    }
}
