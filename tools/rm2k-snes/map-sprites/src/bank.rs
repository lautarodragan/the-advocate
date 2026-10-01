//! The sprite bank that goes to VRAM —one pose per slot— and the bank of
//! poses the cartridge carries for each character that changes pose.

use crate::character::{
    block_tile, character_palette, nearest, pose_tiles, sheet, Key, Sheets, OBJ_ROW, SPRITE_POSES,
};
use crate::fail::{Bad, Result};
use crate::split::{PaletteOf, Split};
use adeleine::Color;
use std::collections::HashMap;

/// Whose a VRAM slot is.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Slot {
    /// The hero, in block 0.
    Hero,
    /// An event that walks: each has its own, and changes pose on its own.
    Event(usize),
    /// A still pose, shared by every event that shows it: (CharSet, index,
    /// pose).
    Still(String, i32, i32),
    /// The one a still event that turns toward the hero moves to.
    Turn,
    /// One that still events showing different poses take turns in, because
    /// no camera shows two of them at once: see [`crate::share`]. It holds
    /// whichever pose the console last uploaded.
    Shared(usize),
}

/// A slot of the bank: whose it is, and the pose it holds.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SlotPose {
    pub slot: Slot,
    pub charset: String,
    pub index: i32,
    pub pose: i32,
}

/// How a character's colours become indices: its lookup into the palette
/// it ended up in, and its mapping onto its own palette.
pub type Colors = HashMap<Key, (HashMap<Color, u8>, HashMap<Color, Color>)>;

/// What the bank came out as.
pub struct Bank {
    /// 4bpp tiles, with the gaps a 4x4 block leaves in the sixteen-wide
    /// grid.
    pub tiles: Vec<u8>,
    pub palettes: Vec<Vec<Color>>,
    /// Each slot's block and palette, in the order of the slots.
    pub place: Vec<(Slot, usize, usize)>,
    pub palette_of: PaletteOf,
    pub colors: Colors,
}

/// The bank that goes to VRAM: one pose per slot. `characters` are the
/// characters that need a palette, in the order they are handed out;
/// `slots` get a block of sixteen tiles each, in that order.
///
/// **Palettes are not decided here**: they come in `split`. Here only each
/// colour's index inside its own is built; a colour that is not in the
/// palette it got —it was lent someone else's— goes to the nearest of the
/// ones there are.
pub fn build_characters(sheets: &Sheets, characters: &[Key], slots: &[SlotPose], split: &Split) -> Result<Bank> {
    let mut colors: Colors = HashMap::new();
    for key in characters {
        if colors.contains_key(key) {
            continue;
        }
        let image = sheet(sheets, &key.0)?;
        let (palette, lookup, mapping) =
            character_palette(image, key.1, split.caps.get(key).copied(), split.poses.get(key))?;
        let Some(number) = split.palette_of.get(key) else {
            return Err(Bad::new(format!("{}:{} is not in the palette split", key.0, key.1)));
        };
        if split.own.contains(key) {
            colors.insert(key.clone(), (lookup, mapping));
            continue;
        }
        let union = &split.palettes[number];
        let position = |c: &Color| union.iter().position(|u| u == c).unwrap() as u8 + 1;
        let lookup = palette
            .iter()
            .map(|c| {
                let at = if union.contains(c) { position(c) } else { position(&nearest(union, *c)) };
                (*c, at)
            })
            .collect();
        colors.insert(key.clone(), (lookup, mapping));
    }

    let mut tiles: Vec<u8> = Vec::new();
    let mut place = Vec::with_capacity(slots.len());
    for (block, s) in slots.iter().enumerate() {
        let key = (s.charset.clone(), s.index);
        let (lookup, mapping) = &colors[&key];
        let palette = split
            .palette_of
            .get(&key)
            .ok_or_else(|| Bad::new(format!("{}:{} is not in the palette split", key.0, key.1)))?;
        place.push((s.slot.clone(), block, palette));
        let first = block_tile(block);
        let needed = (first + 3 * OBJ_ROW + 4) * 32;
        if tiles.len() < needed {
            tiles.resize(needed, 0);
        }
        for (i, tile) in pose_tiles(sheet(sheets, &s.charset)?, s.index, s.pose, lookup, mapping)?
            .into_iter()
            .enumerate()
        {
            let number = first + (i / 4) * OBJ_ROW + i % 4;
            tiles[number * 32..(number + 1) * 32].copy_from_slice(&tile);
        }
    }
    Ok(Bank {
        tiles,
        palettes: split.palettes.clone(),
        place,
        palette_of: split.palette_of.clone(),
        colors,
    })
}

/// The twelve poses of each character that changes pose, for the
/// cartridge: 512 bytes a pose, in pose order. With the lookup of the
/// palette it ended up in: a pose uploaded on the fly is drawn with the
/// palette already in colour memory.
pub fn pose_bank(sheets: &Sheets, characters: &[Key], colors: &Colors) -> Result<Vec<(Key, Vec<u8>)>> {
    let mut banks = Vec::with_capacity(characters.len());
    for key in characters {
        let (lookup, mapping) = &colors[key];
        let image = sheet(sheets, &key.0)?;
        let mut data = Vec::new();
        for pose in 0..SPRITE_POSES {
            for tile in pose_tiles(image, key.1, pose, lookup, mapping)? {
                data.extend_from_slice(&tile);
            }
        }
        banks.push((key.clone(), data));
    }
    Ok(banks)
}
