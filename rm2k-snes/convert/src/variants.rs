//! `ChangeMapTileset`: a map drawn and walked with another ChipSet, over
//! the same cells, until the next teleport —RPG_RT's
//! `Game_Map::SetChipset`—.
//!
//! The console cannot draw a map with a ChipSet it was not converted with,
//! so the map is converted **once more for each ChipSet its own pages swap
//! in** —Wally, with `chipsets` in its request—, and each conversion is a
//! variant of the map the runtime swaps in by its place: the emission gives
//! it a record of its own, a copy of the map's with what the ChipSet
//! changes, and `OP_CHANGE_TILESET` points the console at it. See
//! `tileset_change` in the runtime's `tileset.s`.
//!
//! **The grid is the map's, whatever the ChipSet**: the runtime does not
//! decompress it again on a swap, and the bytecode lives right behind the
//! block table, so the table cannot change size. So the blocks are numbered
//! by every conversion at once —a cell's block is the tuple of the blocks
//! it got from each, [`join`]—, and each variant's table says what each of
//! those blocks draws and lets through with its ChipSet. It costs a few
//! blocks more than the map alone, measured in the task
//! `changemaptileset-is-not-compiled.md`, in the-advocate-work.
//!
//! **A variant whose ChipSet has the map's own picture and animation does
//! not draw**: it takes only its passability and terrain, and the map keeps
//! its drawing —its layer above included—. That is Vampires Dawn's bat, a
//! copy of each ChipSet with every cell open and nothing above the hero, and
//! Frozen World's map 129, which opens a cliff. What it loses: what the
//! copy puts above the hero and the map does not, or the other way round,
//! stays where the map has it.
//!
//! What is not done, and keeps its `tileset-not-changed`: a swap in a
//! common event, which knows no map, and one on a map that cannot take a
//! variant that draws —see [`refused`]—.

use crate::fail::Result;
use crate::game::{Game, GameMap};
use crate::maps::{self, MapInfo};
use crate::stage;
use rm2k_project::outln;
use rm2k_snes_events::codes::{CHANGE_MAP_TILESET, TILE_SUBSTITUTION};
use rm2k_snes_mapdata::materials::{cell_bytes, BLOCK_BYTES};
use rm2k_snes_mapdata::vram;
use std::collections::{BTreeMap, HashMap};

/// The most blocks a map's table takes: Wally's `MAX_BLOCKS`.
const MAX_BLOCKS: usize = 1024;

/// The ChipSets a map's own pages swap in with `ChangeMapTileset`, in the
/// order they are first met, without the map's own —which 0 also names—
/// and without one the database does not have.
pub fn asked(game: &Game, map: &GameMap) -> Vec<i32> {
    let mut out = Vec::new();
    for c in map.all_commands() {
        if c.code != CHANGE_MAP_TILESET {
            continue;
        }
        let id = c.parameters.first().copied().unwrap_or(0);
        if id == 0 || id == map.chipset_id || out.contains(&id) || game.chipset(id).is_err() {
            continue;
        }
        out.push(id);
    }
    out
}

/// Whether ChipSet `other` draws a map drawn with `own` the same: the same
/// picture and the same animation. Then a variant with it takes only its
/// passability and terrain.
pub fn draws_alike(game: &Game, own: i32, other: i32) -> bool {
    match (game.chipset(own), game.chipset(other)) {
        (Ok(a), Ok(b)) => {
            a.chipset_name.eq_ignore_ascii_case(&b.chipset_name)
                && a.animation_type == b.animation_type
                && a.animation_speed == b.animation_speed
        }
        _ => false,
    }
}

/// Wally's request for the map with ChipSet `chipset` instead of its own.
pub fn request(main: &wally::request::Asked, map: i32, chipset: i32) -> wally::request::Asked {
    wally::request::Asked {
        chipsets: BTreeMap::from([(map, chipset)]),
        ..main.clone()
    }
}

/// A map's blocks: one per cell, and each block's sixteen bytes, its
/// passability and its terrain.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Blocks {
    pub cells: Vec<u16>,
    pub table: Vec<u8>,
    pub pass: Vec<u8>,
    pub terrain: Vec<u8>,
}

impl Blocks {
    fn count(&self) -> usize {
        self.pass.len()
    }
}

/// The map's blocks and its variants', numbered by all of them at once: a
/// new block per distinct tuple of the blocks a cell got from each
/// conversion, in the order they are first met. A variant that does not
/// draw —`false` beside it— takes the map's bytes and its own passability
/// and terrain. None if the conversions do not cover the same cells.
pub fn join(main: &Blocks, variants: &[(&Blocks, bool)]) -> Option<(Blocks, Vec<Blocks>)> {
    if variants
        .iter()
        .any(|(v, _)| v.cells.len() != main.cells.len())
    {
        return None;
    }
    let mut numbers: HashMap<Vec<u16>, u16> = HashMap::new();
    let mut keys: Vec<Vec<u16>> = Vec::new();
    let mut cells = Vec::with_capacity(main.cells.len());
    for (at, &own) in main.cells.iter().enumerate() {
        let mut key = vec![own];
        key.extend(variants.iter().map(|(v, _)| v.cells[at]));
        let next = keys.len() as u16;
        let number = *numbers.entry(key.clone()).or_insert_with(|| {
            keys.push(key);
            next
        });
        cells.push(number);
    }
    let pick = |from: &Blocks, block: u16, drawn: &Blocks, out: &mut Blocks| -> Option<()> {
        let b = block as usize;
        let at = drawn.table.get(BLOCK_BYTES * b..BLOCK_BYTES * (b + 1))?;
        out.table.extend_from_slice(at);
        out.pass.push(*from.pass.get(b)?);
        out.terrain.push(*from.terrain.get(b)?);
        Some(())
    };
    let mut joined = Blocks {
        cells: cells.clone(),
        ..Blocks::default()
    };
    let mut theirs: Vec<Blocks> = variants
        .iter()
        .map(|_| Blocks {
            cells: cells.clone(),
            ..Blocks::default()
        })
        .collect();
    for key in &keys {
        pick(main, key[0], main, &mut joined)?;
        for (k, (v, draws)) in variants.iter().enumerate() {
            if *draws {
                pick(v, key[k + 1], v, &mut theirs[k])?;
            } else {
                // The map's drawing, with the variant's passability and
                // terrain.
                let b = key[0] as usize;
                let out = &mut theirs[k];
                out.table
                    .extend_from_slice(main.table.get(BLOCK_BYTES * b..BLOCK_BYTES * (b + 1))?);
                out.pass.push(*v.pass.get(key[k + 1] as usize)?);
                out.terrain.push(*v.terrain.get(key[k + 1] as usize)?);
            }
        }
    }
    Some((joined, theirs))
}

/// A variant of a map, as the emission takes it: see `Variant` in
/// rm2k-snes-mapdata's `request.rs`.
#[derive(Clone, Debug)]
pub struct Variant {
    pub chipset: i32,
    /// Whether it draws: if not, its tiles, colours and animation are the
    /// map's, and the console uploads nothing to swap it in.
    pub draws: bool,
    pub tile_data: Vec<u8>,
    pub cgram: Vec<u8>,
    pub above_tiles: Vec<u8>,
    pub above_cgram: Vec<u8>,
    pub above_first: i64,
    pub runs: Vec<rm2k_snes_mapdata::request::Run>,
    pub blocks: Blocks,
    pub terrain_outside: i32,
}

impl Variant {
    /// Its entry in the emission's map request.
    pub fn request(&self) -> rm2k_snes_mapdata::request::Variant {
        rm2k_snes_mapdata::request::Variant {
            chipset: self.chipset.into(),
            draws: self.draws,
            tiles: self.tile_data.clone(),
            cgram: self.cgram.clone(),
            above_tiles: self.above_tiles.clone(),
            above_cgram: self.above_cgram.clone(),
            above_first: self.above_first,
            runs: self.runs.clone(),
            blocks: self.blocks.table.clone(),
            block_pass: self.blocks.pass.clone(),
            block_terrain: self.blocks.terrain.clone(),
            terrain_outside: self.terrain_outside.into(),
        }
    }
}

/// What a conversion of the map with another ChipSet answered, as much of
/// it as a variant takes and [`refused`] compares.
pub struct Drawn {
    pub chipset: i32,
    pub draws: bool,
    pub tile_data: Vec<u8>,
    pub cgram: Vec<u8>,
    pub above_tiles: Vec<u8>,
    pub above_cgram: Vec<u8>,
    pub above_first: i64,
    pub bpp: i64,
    pub runs: Vec<rm2k_snes_mapdata::request::Run>,
    pub blocks: Blocks,
    pub panorama: bool,
    /// What it drew of the events, to hold against the map's.
    pub events: Events,
}

/// What a conversion drew of the events, by index: those painted into the
/// background, those baked into the layer above, those drawn as objects
/// and those drawn into the background's cells. A refusal says it as JSON.
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
pub struct Events {
    pub decorative: Vec<usize>,
    pub baked: Vec<usize>,
    pub npcs: Vec<usize>,
    pub posed: Vec<usize>,
}

impl std::fmt::Display for Events {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&serde_json::to_string(self).map_err(|_| std::fmt::Error)?)
    }
}

fn file<'a>(written: &'a BTreeMap<String, Vec<u8>>, name: &str) -> Result<&'a Vec<u8>> {
    written
        .get(name)
        .ok_or_else(|| crate::fail::Stop::new(format!("wally did not write {name}")))
}

/// What the events of an answer came out as: see [`Drawn::events`].
pub fn map_events(answer: &wally::answer::Map) -> Events {
    Events {
        decorative: answer.decorative.clone(),
        baked: answer.baked.iter().map(|b| b.0).collect(),
        npcs: answer.npcs.iter().map(|n| n.npc.event).collect(),
        posed: answer.posed.iter().map(|p| p.event).collect(),
    }
}

/// Reads what Wally answered for the map with `chipset`.
pub fn drawn(written: &stage::Files, chipset: i32, draws: bool) -> Result<Drawn> {
    let answer = maps::wally_answer(written)?;
    let bg = &answer.layers.background;
    Ok(Drawn {
        chipset,
        draws,
        tile_data: file(written, "background.bin")?.clone(),
        cgram: maps::words(&bg.cgram),
        above_tiles: file(written, "above.bin")?.clone(),
        above_cgram: file(written, "above-cgram.bin")?.clone(),
        above_first: answer.layers.above.first as i64,
        bpp: bg.bpp as i64,
        runs: maps::runs(bg, written)?,
        blocks: Blocks {
            cells: answer.layers.blocks.cells.clone(),
            table: file(written, "blocks.bin")?.clone(),
            pass: file(written, "block-passability.bin")?.clone(),
            terrain: file(written, "block-terrain.bin")?.clone(),
        },
        panorama: answer.layers.panorama.is_some(),
        events: map_events(&answer.map),
    })
}

/// The map's blocks, as [`MapInfo`] keeps them.
fn map_blocks(m: &MapInfo) -> Blocks {
    Blocks {
        cells: m
            .cells
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]))
            .collect(),
        table: m.blocks.clone(),
        pass: m.block_pass.clone(),
        terrain: m.block_terrain.clone(),
    }
}

/// Why a variant that draws cannot be swapped into the map, if it cannot:
/// the runtime swaps tiles, colours, the animation and the blocks, and
/// nothing else, so everything else has to come out the same.
///
/// * **No panorama, on either**: its tiles and colours share the layer
///   above's, and the swap does not upload them. None of the maps that swap
///   one in has a panorama.
/// * **The same depth**, and **a VRAM layout that holds both**: the swap
///   uploads to the map's.
/// * **No `TileSubstitution` and no still event drawn into the
///   background**: both name blocks, which [`join`] numbers again.
/// * **The same events drawn the same way**: painted into the background,
///   baked into the layer above, as objects. An event drawn with a ChipSet
///   tile as an object keeps the map's ChipSet's drawing.
pub fn refused(m: &MapInfo, map_events: &Events, d: &Drawn) -> Option<String> {
    if !d.draws {
        return None;
    }
    if m.panorama.is_some() || d.panorama {
        return Some("the map shows a panorama".into());
    }
    if d.bpp != m.bpp {
        return Some(format!("it goes at {}bpp and the map at {}", d.bpp, m.bpp));
    }
    if m.map.all_commands().any(|c| c.code == TILE_SUBSTITUTION) {
        return Some("the map has a TileSubstitution, which names blocks".into());
    }
    if !m.posed.is_empty() {
        return Some("the map draws still events into its background's cells".into());
    }
    let animation: usize = d.runs.iter().flat_map(|r| &r.drawings).map(Vec::len).sum();
    if animation > rm2k_snes_mapdata::materials::LZ2_CAP_ANIM {
        // The emission cuts a map's that does not fit, and not a variant's.
        return Some(format!(
            "its ChipSet animation's drawings are {animation} bytes, and {} fit in WRAM",
            rm2k_snes_mapdata::materials::LZ2_CAP_ANIM
        ));
    }
    if d.events != *map_events {
        return Some(format!(
            "its events come out drawn otherwise: {} against the map's {}",
            d.events, map_events
        ));
    }
    None
}

/// The layout that holds the map and its variants that draw, if the map's
/// does not: the first that holds the most each of them takes.
fn layout_for(m: &MapInfo, drawn: &[&Drawn]) -> Option<&'static str> {
    let sprites = (m.sprite.tiles.len() / 32) as u32;
    let bg = drawn
        .iter()
        .map(|d| d.tile_data.len())
        .chain([m.tile_data.len()])
        .max()
        .unwrap_or(0)
        / rm2k_snes_mapdata::snes::BYTES_PER_TILE;
    let above = drawn
        .iter()
        .map(|d| d.above_tiles.len())
        .chain([m.above_tiles.len()])
        .max()
        .unwrap_or(0)
        / 32;
    vram::vram_layout(bg as u32, sprites, above as u32)
        .ok()
        .map(|l| l.name)
}

/// The variants a map takes, numbered with its blocks: on success, the
/// map's blocks and layout are the joined ones. What is refused is printed
/// and left out, and its `ChangeMapTileset`s keep their loss.
pub fn take(game: &Game, m: &mut MapInfo, map_events: &Events, drawn: Vec<Drawn>) -> Vec<Variant> {
    let mut kept: Vec<Drawn> = Vec::new();
    for d in drawn {
        match refused(m, map_events, &d) {
            Some(why) => outln!(
                "  map {}: WARNING, ChipSet {} is not swapped in: {why}",
                m.id,
                d.chipset
            ),
            None => kept.push(d),
        }
    }
    if kept.is_empty() {
        return Vec::new();
    }
    let drawing: Vec<&Drawn> = kept.iter().filter(|d| d.draws).collect();
    let layout = if drawing.is_empty() {
        None
    } else {
        layout_for(m, &drawing)
    };
    if !drawing.is_empty() && layout.is_none() {
        outln!(
            "  map {}: WARNING, its ChipSets are not swapped in: no VRAM layout holds the map with all of them",
            m.id
        );
        return Vec::new();
    }
    let main = map_blocks(m);
    let others: Vec<(&Blocks, bool)> = kept.iter().map(|d| (&d.blocks, d.draws)).collect();
    let Some((joined, theirs)) = join(&main, &others) else {
        outln!(
            "  map {}: WARNING, its ChipSets are not swapped in: their conversions do not cover the same cells",
            m.id
        );
        return Vec::new();
    };
    let ram = BLOCK_BYTES * joined.count() + joined.count();
    if joined.count() > MAX_BLOCKS || cell_bytes(joined.cells.len(), joined.count(), ram).is_none()
    {
        outln!(
            "  map {}: WARNING, its ChipSets are not swapped in: numbered by all of them it takes {} blocks, and its grid does not fit",
            m.id,
            joined.count()
        );
        return Vec::new();
    }
    outln!(
        "  map {}: ChipSets {} swapped in by its pages, its blocks numbered by all: {} where it had {}",
        m.id,
        kept.iter()
            .map(|d| format!("{}{}", d.chipset, if d.draws { "" } else { " (passability)" }))
            .collect::<Vec<_>>()
            .join(", "),
        joined.count(),
        main.count()
    );
    m.cells = joined.cells.iter().flat_map(|c| c.to_le_bytes()).collect();
    m.blocks = joined.table;
    m.block_pass = joined.pass;
    m.block_terrain = joined.terrain;
    if let Some(name) = layout {
        m.layout_name = name.to_string();
    }
    kept.into_iter()
        .zip(theirs)
        .map(|(d, blocks)| {
            // The terrain of a cell outside the map: the ChipSet's first tile's,
            // as `map_info` says.
            let terrain_outside = game
                .chipset(d.chipset)
                .map_or(m.terrain_outside, |c| rm2k_rules::chipset::terrain_of(c, 0));
            if d.draws {
                Variant {
                    chipset: d.chipset,
                    draws: true,
                    tile_data: d.tile_data,
                    cgram: d.cgram,
                    above_tiles: d.above_tiles,
                    above_cgram: d.above_cgram,
                    above_first: d.above_first,
                    runs: d.runs,
                    blocks,
                    terrain_outside,
                }
            } else {
                Variant {
                    chipset: d.chipset,
                    draws: false,
                    tile_data: m.tile_data.clone(),
                    cgram: m.cgram.clone(),
                    above_tiles: m.above_tiles.clone(),
                    above_cgram: m.above_cgram.clone(),
                    above_first: m.above_first,
                    runs: m.runs.clone(),
                    blocks,
                    terrain_outside,
                }
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn blocks(cells: &[u16], n: usize, pass: u8) -> Blocks {
        Blocks {
            cells: cells.to_vec(),
            table: (0..n).flat_map(|b| [b as u8; BLOCK_BYTES]).collect(),
            pass: vec![pass; n],
            terrain: (0..n).map(|b| b as u8).collect(),
        }
    }

    /// Two cells one block under the map's ChipSet and two under the
    /// variant's are two blocks for both: each table says what its ChipSet
    /// draws there.
    #[test]
    fn the_blocks_are_numbered_by_every_chipset() {
        let main = blocks(&[0, 0, 1], 2, 0x0F);
        let other = blocks(&[0, 1, 1], 2, 0x00);
        let (joined, theirs) = join(&main, &[(&other, true)]).unwrap();
        assert_eq!(joined.cells, [0, 1, 2]);
        assert_eq!(joined.count(), 3);
        // The map's: blocks 0, 0, 1.
        assert_eq!(joined.table[..BLOCK_BYTES], [0; BLOCK_BYTES]);
        assert_eq!(joined.table[BLOCK_BYTES..2 * BLOCK_BYTES], [0; BLOCK_BYTES]);
        assert_eq!(joined.table[2 * BLOCK_BYTES..], [1; BLOCK_BYTES]);
        assert_eq!(joined.pass, [0x0F; 3]);
        // The variant's: blocks 0, 1, 1, with its passability.
        assert_eq!(
            theirs[0].table[BLOCK_BYTES..2 * BLOCK_BYTES],
            [1; BLOCK_BYTES]
        );
        assert_eq!(theirs[0].pass, [0; 3]);
        assert_eq!(theirs[0].terrain, [0, 1, 1]);
        assert_eq!(theirs[0].cells, joined.cells);
    }

    /// A variant that does not draw keeps the map's bytes and brings only
    /// its passability and terrain.
    #[test]
    fn a_variant_that_does_not_draw_takes_only_what_lets_through() {
        let main = blocks(&[0, 1], 2, 0x00);
        let mut open = blocks(&[0, 0], 1, 0x0F);
        open.table = vec![9; BLOCK_BYTES];
        let (joined, theirs) = join(&main, &[(&open, false)]).unwrap();
        assert_eq!(joined.cells, [0, 1]);
        assert_eq!(theirs[0].table, joined.table);
        assert_eq!(theirs[0].pass, [0x0F, 0x0F]);
    }

    #[test]
    fn conversions_of_other_cells_do_not_join() {
        let main = blocks(&[0, 0, 1], 2, 0);
        let other = blocks(&[0, 1], 2, 0);
        assert!(join(&main, &[(&other, true)]).is_none());
    }
}
