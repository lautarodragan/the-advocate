//! The events baked into the map: an opaque one drawn with a ChipSet tile,
//! always the same and always in the same cell, is painted into the upper
//! layer instead of being drawn as a sprite, and its row starts hidden. The
//! event stays whole for its logic —it triggers, blocks, is the target of a
//! page—; what is saved is its object and its pass through the console's
//! placing of sprites, which is what costs frames in the busiest maps.
//!
//! **Passability does not change**, and that is what allows hiding the row:
//! for an upper tile without the "above" bit the map's table resolves the
//! cell with that tile's bits, which are the ones the event's row imposed.

use crate::events::{route_target, tile_name, unbaked, Event, LAYER_BELOW, UPPER_BASE};
use crate::fail::Result;
use crate::sheets::Drawer;
use rm2k_render::Picture;
use rm2k_rules::charset::{OFFSET_X, OFFSET_Y};
use rm2k_rules::chipset::TILE;
use rm2k_rules::passability::{cell, ABOVE};
use rm2k_snes_map_sprites::npc::Npc;
use rm2k_snes_map_sprites::split::TILE_PREFIX;
use std::collections::hash_map::Entry;
use std::collections::{BTreeMap, HashMap, HashSet};

/// The commands that move an event to another cell or touch its drawing:
/// `MoveEvent`, `SetEventLocation`, `SwapEventLocations` and
/// `FlashSprite`, liblcf's codes. An event some page can move or flash is
/// not fixed, so it is not baked. The raw commands are looked at and not
/// the compiled pages: it is more conservative, and needs no compiling.
pub const MOVING_COMMANDS: [i32; 4] = [11330, 10860, 10870, 11320];

/// The alpha of the 16x16 pixels of upper-layer tile `index`, from the
/// sheet the event is drawn with: the tile stands on its cell in every
/// pose, so pose 0 has it whole where the cell is. `None` without the
/// ChipSet.
fn tile_alphas(drawer: &mut Drawer, chipset: &str, index: i32) -> Result<Option<Vec<u8>>> {
    let Some(sheet): Option<Picture> = drawer.draw(&tile_name(chipset, index))? else {
        return Ok(None);
    };
    let (x, y) = (-OFFSET_X as i64, -OFFSET_Y as i64);
    let tile = TILE as i64;
    let mut alphas = Vec::with_capacity((tile * tile) as usize);
    for dy in 0..tile {
        for dx in 0..tile {
            alphas.push(sheet.get(x + dx, y + dy)[3]);
        }
    }
    Ok(Some(alphas))
}

/// What of the map the decision reads.
pub struct Map<'a> {
    pub width: usize,
    pub lower: &'a [i32],
    pub upper: &'a [i32],
    /// The ChipSet's passability, per tile id.
    pub flags: &'a [u8],
    pub chipset: &'a str,
}

/// The events that can be baked, as `{event: (cell, tile id)}`.
///
/// The rule is deliberately small, because what holds it up is that **it
/// looks the same**; when in doubt the event keeps being drawn. It is drawn
/// with a tile of the upper layer, not tile 0; every page draws the same
/// tile on the layer below, without continuous animation, and the first has
/// no condition; nothing moves it —no move type, no route of its own, no
/// page that moves or flashes it—; the tile is opaque in all its 16x16 and
/// does not go above the hero; and the cell has room —an empty upper
/// layer— and baking does not open it.
///
/// A ChipSet whose tile 0 draws anything bakes nothing: that is what makes
/// putting the tile in the cell cover nothing, and it is checked.
pub fn bakeable(
    drawer: &mut Drawer,
    map: &Map,
    events: &[Event],
    npcs: &[Npc],
) -> Result<BTreeMap<usize, (usize, i32)>> {
    let mut out = BTreeMap::new();
    let Some(zero) = tile_alphas(drawer, map.chipset, 0)? else {
        return Ok(out);
    };
    if zero.iter().any(|&a| a != 0) {
        return Ok(out);
    }
    let mut touched = HashSet::new();
    for event in events {
        for page in &event.pages {
            for (code, parameters) in &page.commands {
                if !MOVING_COMMANDS.contains(code) || parameters.is_empty() {
                    continue;
                }
                if let Some(target) = route_target(events, parameters[0]).filter(|&t| t != 0) {
                    touched.insert(target - 1);
                }
            }
        }
    }
    let walking: HashSet<usize> = events
        .iter()
        .enumerate()
        .filter(|(_, e)| e.pages.iter().any(|p| p.move_type != 0 || p.own_route))
        .map(|(n, _)| n)
        .collect();
    let mut opaque: HashMap<i32, bool> = HashMap::new();
    for npc in npcs {
        let number = npc.event;
        let base = unbaked(&npc.charset);
        if !base.starts_with(TILE_PREFIX) || !npc.visible {
            continue;
        }
        if npc.changes || walking.contains(&number) || touched.contains(&number) {
            continue;
        }
        let pages = &events[number].pages;
        if !pages[0].conditions.is_empty() {
            continue;
        }
        let first = &npc.graphics[0];
        if first.is_none() || npc.graphics.iter().any(|g| g != first) {
            continue;
        }
        if npc.layers.iter().any(|&l| l != LAYER_BELOW) {
            continue;
        }
        if pages.iter().any(|p| matches!(p.animation, 1 | 3)) {
            continue;
        }
        let Some(index) = base.rsplit(':').next().and_then(|i| i.parse::<i32>().ok()) else {
            continue;
        };
        if index == 0 {
            continue; // tile 0 is "no graphic"
        }
        let tile = UPPER_BASE + index;
        if map.flags[tile as usize] & ABOVE != 0 {
            continue; // it would go above the hero
        }
        let at = npc.y as usize * map.width + npc.x as usize;
        if map.upper[at] != UPPER_BASE {
            continue; // the cell's upper layer is taken
        }
        // And baking cannot open the cell: a walkable tile over a cell the
        // map closes is a hole that until now only existed while the row
        // was visible.
        let imposed = npc.tile_pass.unwrap_or(0);
        if imposed & !cell(map.flags, map.lower[at], map.upper[at]) != 0 {
            continue;
        }
        if let Entry::Vacant(slot) = opaque.entry(index) {
            let alphas = tile_alphas(drawer, map.chipset, index)?;
            slot.insert(alphas.is_some_and(|a| a.iter().all(|&v| v == 255)));
        }
        if !opaque[&index] {
            continue;
        }
        out.insert(number, (at, tile));
    }
    Ok(out)
}
