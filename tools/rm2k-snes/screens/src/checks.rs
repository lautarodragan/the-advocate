//! Where the screens land in video memory, against the maps' layouts.
//!
//! The screens are opened over a map and closed back to it, and what
//! brings the map back is reloading its BG1 bank —nothing else—. So
//! everything a screen writes has to fall **inside the BG1 bank of every
//! layout** a map can have, and nothing of one screen can step on another
//! it is shown with. The layouts are the maps' business and come in the
//! request; this checks the screens against them.
//!
//! Addresses and sizes are in video-memory words.

use crate::fail::{Bad, Result};
use crate::layout::*;

/// What the request says of video memory.
#[derive(Debug, Clone, Default)]
pub struct Vram {
    /// Where the slot screen's and the menu's tiles start: the base of BG1
    /// and BG2 while they are open.
    pub slot_vram: usize,
    /// Where their tilemap goes.
    pub slot_map: usize,
    /// Each layout's BG1 bank: its name, and the words from and to.
    pub bg1_banks: Vec<(String, usize, usize)>,
}

/// The first 8bpp tile of the item and equipment windows, counted from the
/// slot screen's base: the first free one after the `source` 4bpp tiles of
/// the text screens' font, which are half the size.
pub fn items_border_first(source: usize) -> usize {
    source.div_ceil(2)
}

impl Vram {
    fn within(&self, what: &str, first: usize, last: usize) -> Result<()> {
        for (name, base, cap) in &self.bg1_banks {
            if first < *base || last > *cap {
                return Err(Bad::answer(format!(
                    "{what} at ${first:04X}..${last:04X}, and the BG1 bank of the layout {name} is \
                     ${base:04X}..${cap:04X}: coming back to the map would not restore it"
                )));
            }
        }
        Ok(())
    }

    /// That the slot screen —and End Game, whose tiles go in the same
    /// place— lands in the BG1 bank of every layout.
    pub fn slots(&self, tiles: usize) -> Result<()> {
        let end_tiles = self.slot_vram + tiles * 16;
        let end_map = self.slot_map + 32 * 32;
        if !(end_tiles <= self.slot_map || end_map <= self.slot_vram) {
            return Err(Bad::answer(format!(
                "the {tiles} tiles of the slot screen reach ${end_tiles:04X} and overwrite its \
                 tilemap at ${:04X}",
                self.slot_map
            )));
        }
        self.within("the slot screen's tiles", self.slot_vram, end_tiles)?;
        self.within("the slot screen's tilemap", self.slot_map, end_map)
    }

    /// That the text screens' font and the item and equipment windows, one
    /// after the other, do not reach the windows' tilemap, and that it all
    /// stays in the BG1 bank of the layouts.
    pub fn items_border(&self, source: usize, border: usize) -> Result<()> {
        let end = self.slot_vram + (items_border_first(source) + border) * 32;
        if end > ITEM_BORDER_MAP {
            return Err(Bad::answer(format!(
                "the text screens' font ({source} 4bpp tiles) and the item and equipment windows \
                 ({border} 8bpp ones) reach ${end:04X} and the windows' tilemap is at \
                 ${ITEM_BORDER_MAP:04X}"
            )));
        }
        self.within(
            "the item and equipment windows",
            self.slot_vram,
            ITEM_BORDER_MAP + 32 * 32,
        )
    }

    /// That the actor choice's windows fit between their base and their
    /// tilemap, outside what the menu uses, and in the BG1 bank of every
    /// layout.
    pub fn target(&self, tiles: usize) -> Result<()> {
        let end_tiles = TARGET_VRAM + tiles * 32;
        if end_tiles > TARGET_MAP {
            return Err(Bad::answer(format!(
                "the actor choice's windows are {tiles} 8bpp tiles and reach ${end_tiles:04X}, \
                 and their tilemap is at ${TARGET_MAP:04X}"
            )));
        }
        if TARGET_VRAM < self.slot_map + 32 * 32 {
            return Err(Bad::answer("the actor choice's windows overwrite the menu's tilemap"));
        }
        self.within("the actor choice's windows", TARGET_VRAM, TARGET_MAP + 32 * 32)
    }

    /// That the shop's windows, from their base, stay in the BG1 bank of
    /// every layout and off the text's tilemap. Their tilemap is the item
    /// screen's, which `items_border` checks.
    pub fn shop(&self, tiles: usize) -> Result<()> {
        if TI_VRAM < self.slot_map + 32 * 32 {
            return Err(Bad::answer("the shop's windows overwrite the text tilemap"));
        }
        self.within("the shop's windows", TI_VRAM, TI_VRAM + tiles * 32)
    }
}
