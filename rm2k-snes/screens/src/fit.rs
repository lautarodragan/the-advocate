//! The screens whose windows go into a bank of tiles, and what is done when
//! they do not fit: the actor choice, the item and equipment screens, the
//! shop and the battle.
//!
//! A System whose background is a gradient, stretched as RM2k stretches it,
//! is a different cell on every row of the gradient, and so is the frame
//! over it where it shows through: on a window the size of the screen that
//! is a hundred tiles, and these banks hold tens. So a screen that does not
//! fit is **redrawn with fewer cells**: Adeleine's
//! `merge_least_visible_tiles` merges the cell that shows the least into
//! its nearest, mirrors included, until the bank holds them —two rows of
//! the gradient one step apart go first, and a letter, which is far from
//! everything, last—. The cursors and the text written in the windows are
//! cells like the others and count the same.
//!
//! **What is redrawn is decided here and only here**, with what each
//! screen's bank holds by itself, and it travels in the System —see
//! `Skin::redraw`—, so that `convert` —what the cartridge carries— and
//! `render` —what the console has to show— draw the same. The converter
//! then checks the same screens against the maps' layouts, as it did
//! before. A screen that fits is not touched.

use crate::borders::{self, Screen as Layer};
use crate::cells::{self, BLACK, COLS, ROWS};
use crate::checks::SLOT_VRAM_WORDS;
use crate::fail::Result;
use crate::game::{Game, Skin};
use crate::layout::*;
use adeleine::Tile;
use rm2k_render::picture::Picture;
use std::collections::HashMap;
use std::rc::Rc;

/// The screens whose windows can be redrawn.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Screen {
    /// The actor choice, with the pause menu's bar: their tiles go from
    /// `TARGET_VRAM` up to their tilemap.
    Target,
    /// The item and equipment screens, which share their windows.
    Items,
    /// The shop's three layouts.
    Shop,
    /// The battle's windows.
    Battle,
}

/// The most 8bpp tiles the actor choice's windows take: up to their
/// tilemap.
pub const TARGET_TILES_MAX: usize = (TARGET_MAP - TARGET_VRAM) / 32;
/// The most 8bpp tiles the item and equipment windows take: they go right
/// before their tilemap, and below them the text needs at least its pair
/// 0, the blank one —see `items_border_first`—.
pub const ITEMS_TILES_MAX: usize = (ITEM_BORDER_MAP - SLOT_VRAM_WORDS) / 32 - 1;
/// The most 8bpp tiles the shop's windows take: from their base up to where
/// the actor choice's tilemap ends, which is as far as the BG1 bank of every
/// map's layout reaches —the converter checks it against each—.
pub const SHOP_TILES_MAX: usize = (TARGET_MAP + 32 * 32 - TI_VRAM) / 32;

/// How a screen's windows are redrawn: each cell that is drawn differently,
/// by what it had, with what it gets. A transparent pixel and a black one
/// are the same here, as they are in the bank: both are entry 0.
#[derive(Debug, Clone, Default)]
pub struct Redrawn {
    cells: HashMap<Tile, Tile>,
}

/// A cell as the bank tells it apart: black is transparent.
fn plain(tile: Tile) -> Tile {
    tile.map(|row| row.map(|p| p.filter(|c| *c != BLACK)))
}

impl Redrawn {
    /// Redraws the cells of a screen-sized `layer`.
    pub fn apply(&self, layer: &mut Picture) {
        for row in 0..ROWS {
            for col in 0..COLS {
                if let Some(to) = self.cells.get(&plain(cells::tile_at(layer, col, row))) {
                    cells::paint_tile(layer, col, row, to);
                }
            }
        }
    }
}

/// The pictures of `screen` that `borders` cuts, drawn with `skin`.
fn layers(game: &Game, skin: &Skin, screen: Screen) -> Result<Vec<Layer>> {
    Ok(match screen {
        Screen::Target => vec![borders::target_layer(game, skin)?, borders::menu_bar_layer(skin)],
        Screen::Items => vec![borders::item_layers(skin), borders::equipment_layers(skin)],
        Screen::Shop => borders::shop_layers(skin),
        Screen::Battle => crate::battle::layers(skin),
    })
}

fn tiles_max(screen: Screen) -> usize {
    match screen {
        Screen::Target => TARGET_TILES_MAX,
        Screen::Items => ITEMS_TILES_MAX,
        Screen::Shop => SHOP_TILES_MAX,
        Screen::Battle => crate::battle::BATTLE_WINDOW_TILES_MAX,
    }
}

/// The cells `borders` cuts of `layers`: each background whole, and each
/// cursor position its rows.
fn cut_cells(layers: &[Layer]) -> Vec<Tile> {
    let mut out = Vec::new();
    for layer in layers {
        for row in 0..ROWS {
            for col in 0..COLS {
                out.push(plain(cells::tile_at(&layer.background, col, row)));
            }
        }
        for (picture, row0, rows) in &layer.bars {
            for row in *row0..row0 + rows {
                for col in 0..COLS {
                    out.push(plain(cells::tile_at(picture, col, row)));
                }
            }
        }
    }
    out
}

/// The cells of a bank as `borders` keeps them: one per drawing and its
/// mirrors, the empty one first. For each distinct cell, the tile it is
/// drawn with and the mirror.
struct Bank {
    tiles: Vec<Tile>,
    weights: Vec<u64>,
    of: HashMap<Tile, (usize, bool, bool)>,
}

impl Bank {
    fn new(cells: &[Tile]) -> Bank {
        let empty: Tile = [[None; cells::CELL]; cells::CELL];
        let mut bank = Bank { tiles: vec![empty], weights: vec![0], of: HashMap::from([(empty, (0, false, false))]) };
        for cell in cells {
            let at = match bank.of.get(cell) {
                Some(&at) => at,
                None => {
                    let found = [(true, false), (false, true), (true, true)].iter().find_map(|&(fx, fy)| {
                        let (n, gx, gy) = *bank.of.get(&adeleine::fuse::flipped(cell, fx, fy))?;
                        // `cell` mirrored is tile `n` mirrored by (gx, gy):
                        // so `cell` is tile `n` mirrored by both.
                        Some((n, fx ^ gx, fy ^ gy))
                    });
                    let at = found.unwrap_or_else(|| {
                        bank.tiles.push(*cell);
                        bank.weights.push(0);
                        (bank.tiles.len() - 1, false, false)
                    });
                    bank.of.insert(*cell, at);
                    at
                }
            };
            bank.weights[at.0] += 1;
        }
        bank
    }
}

/// The System `screen` is drawn with: the game's, or the game's with what
/// its windows are redrawn with, if they do not fit their bank as RM2k draws
/// them; and then how many tiles they took, and how many they were left
/// with.
///
/// `text` is what else the bank has to hold: for the item and equipment
/// screens, the pairs their text asks for —`convert::item_pairs`—, which
/// go below the windows. Their windows are redrawn too when they fit the
/// bank but leave the text without room: a System with a gradient left
/// The Frozen World's item text 82 pairs of the 132 it asks for. If the
/// text alone takes the whole bank there is nothing to give it: the windows
/// fit the bank, and the converter says the text does not.
pub fn skin_for(game: &Game, skin: &Skin, screen: Screen, text: usize) -> Result<(Skin, Option<(usize, usize)>)> {
    let whole = tiles_max(screen);
    let max = if text < whole { whole - text } else { whole };
    let bank = Bank::new(&cut_cells(&layers(game, skin, screen)?));
    if bank.tiles.len() <= max {
        return Ok((skin.clone(), None));
    }
    let mut weights = bank.weights.clone();
    // The empty cell is always tile 0 of the bank: others can become it,
    // but it does not go.
    weights[0] = u64::MAX / 2;
    let drawn = adeleine::merge_least_visible_tiles(&bank.tiles, &weights, max, true);
    let mut redrawn = Redrawn::default();
    for (cell, &(n, fx, fy)) in &bank.of {
        let d = drawn[n];
        if d.tile != n {
            let to = adeleine::fuse::flipped(&bank.tiles[d.tile], d.flip_x ^ fx, d.flip_y ^ fy);
            redrawn.cells.insert(*cell, to);
        }
    }
    let fitted = Skin { redrawn: Some(Rc::new(redrawn)), ..skin.clone() };
    Ok((fitted, Some((bank.tiles.len(), max))))
}
