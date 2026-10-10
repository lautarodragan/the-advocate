//! `TileSubstitution` translated from RM2k tiles to the map's 16x16 blocks.
//!
//! RM2k substitutes by **tile number**: every cell of the map that draws the
//! old tile starts drawing the new one. On the console there are no RM2k
//! tiles, there are blocks that carry both layers and the passability
//! together, so a substitution is as many block pairs as (lower, upper)
//! combinations of the map carry that tile.
//!
//! The destination block may not exist —nobody drew that combination
//! anywhere in the map— and then it is built: the four 8x8 cells of the
//! layer that changes come from another block that already draws the new
//! tile, those of the other layer from the source block, and the
//! passability and terrain are recomputed with RM2k's rules. That is where
//! the only real limit comes from: **the new tile has to be drawn in some
//! cell of the map**, on its layer; if it is not, its 8x8 cells did not go
//! into VRAM and there is nothing to draw it with.
//!
//! All the blocks are built **before** any page is compiled, and not as the
//! commands show up: substitutions chain —turning a light on is 80→80A and
//! off is 80A→80—, so the block one needs is created by another, and the
//! order the pages are compiled in cannot decide what compiles.

use crate::fail::{Bad, Result};
use ditto::schema::Chipset;
use rm2k_rules::chipset::{terrain_of, LOWER, TILES_PER_LAYER, UPPER};
use rm2k_rules::passability::{cell, ABOVE};
use crate::background::blocks::{Blocks, BLOCK_BYTES, MAX_BLOCKS};
use std::collections::{BTreeMap, HashMap};

/// A `TileSubstitution`: whether it is the upper layer's, and the old and
/// new tile, numbered within the layer.
pub type Triple = (bool, i32, i32);

/// A substitution translated: `(old block, new block)` for each block that
/// draws the old tile.
pub type Pairs = Vec<(u16, u16)>;

/// What makes a block distinct: its sixteen bytes, its passability and its
/// terrain.
type Fingerprint = (Vec<u8>, u8, u8);

/// The map's blocks, growing with what the substitutions need.
pub struct Substitutions<'a> {
    id: i32,
    blocks: &'a mut Blocks,
    flags: &'a [u8],
    /// Whether every upper tile is drawn into the background: a map whose
    /// panorama took the layer above's place, see `Way::Flattened`.
    flattened: bool,
    chipset: &'a Chipset,
    /// Which block each `(lower, upper)` pair draws, sorted: that is the
    /// order the pairs are walked in.
    combos: BTreeMap<(i32, i32), u16>,
    /// The eight bytes each RM2k tile is drawn with, per layer, from the
    /// blocks that existed before substituting: a tile the map does not
    /// draw anywhere is not here and cannot be substituted into.
    cells: [HashMap<i32, Vec<u8>>; 2],
    /// The blocks by what they are, to share a built block with an equal
    /// one: two combinations that already share a block —two water
    /// autotiles that draw the same— have to keep sharing it after
    /// substituting, or a single block would have to go two ways.
    by_bytes: HashMap<Fingerprint, u16>,
}

impl<'a> Substitutions<'a> {
    /// The substitutions of map `id`, over its blocks. `flags` are its
    /// ChipSet's passability by tile id.
    pub fn new(id: i32, blocks: &'a mut Blocks, flags: &'a [u8], chipset: &'a Chipset, flattened: bool) -> Self {
        let mut cells: [HashMap<i32, Vec<u8>>; 2] = [HashMap::new(), HashMap::new()];
        for &((low, high), block) in &blocks.combos {
            // **The lower half is only usable if the upper tile of that
            // block is not baked into it.** An upper tile without "Above"
            // is drawn stuck to the background, so the lower half of that
            // block is the two together and not the lower tile alone.
            if !bakes(flags, high, flattened) {
                cells[0]
                    .entry(low)
                    .or_insert_with(|| half(blocks, block, 0));
            }
            cells[1]
                .entry(high)
                .or_insert_with(|| half(blocks, block, 1));
        }
        let mut by_bytes = HashMap::new();
        for block in 0..blocks.passability.len() {
            by_bytes
                .entry(fingerprint(blocks, block))
                .or_insert(block as u16);
        }
        Substitutions {
            id,
            combos: blocks.combos.iter().copied().collect(),
            blocks,
            flags,
            flattened,
            chipset,
            cells,
            by_bytes,
        }
    }

    /// Builds the blocks the substitutions `triples` are going to need, and
    /// answers the ones it could not. It repeats until none creates a new
    /// block, because the block one creates is the source of the next.
    pub fn close(&mut self, triples: &[Triple]) -> Result<Vec<Triple>> {
        let mut missing: Vec<Triple> = Vec::new();
        let note = |t: Triple, missing: &mut Vec<Triple>| {
            if !missing.contains(&t) {
                missing.push(t);
            }
        };
        loop {
            let before = self.combos.len();
            for &(upper, old, new) in triples {
                if !(in_layer(old) && in_layer(new)) {
                    continue;
                }
                let layer = usize::from(upper);
                let (old_id, new_id) = ids(upper, old, new);
                if !self.cells[layer].contains_key(&new_id) {
                    note((upper, old, new), &mut missing);
                    continue;
                }
                let sources: Vec<(i32, i32)> = self.combos.keys().copied().collect();
                for combination in sources {
                    if side(combination, layer) != old_id {
                        continue;
                    }
                    let dest = with_side(combination, layer, new_id);
                    if self.create(dest)?.is_none() {
                        note((upper, old, new), &mut missing);
                    }
                }
            }
            if self.combos.len() == before {
                return Ok(missing);
            }
        }
    }

    /// The `(old block, new block)` pairs of a substitution, or `None`:
    /// "the page that asks for it does not compile".
    pub fn pairs(&self, (upper, old, new): Triple) -> Option<Pairs> {
        if !(in_layer(old) && in_layer(new)) {
            return None;
        }
        let layer = usize::from(upper);
        let (old_id, new_id) = ids(upper, old, new);
        let mut out = Vec::new();
        let mut seen: HashMap<u16, u16> = HashMap::new();
        for (&combination, &block) in &self.combos {
            if side(combination, layer) != old_id {
                continue;
            }
            // `close` should have created it.
            let new_block = *self.combos.get(&with_side(combination, layer, new_id))?;
            // Two combinations that draw the same share a block, and then
            // the substitution cannot be expressed: the block would have
            // to go two ways.
            if *seen.entry(block).or_insert(new_block) != new_block {
                return None;
            }
            out.push((block, new_block));
        }
        // The count operand is one byte.
        if out.len() > 0xFF {
            return None;
        }
        Some(out)
    }

    /// The block of a combination the map does not draw anywhere, or `None`
    /// if it cannot be built without drawing the map again: the upper tile
    /// is baked into the background, or one of the two tiles is not drawn
    /// on its layer anywhere.
    fn create(&mut self, combination: (i32, i32)) -> Result<Option<u16>> {
        if let Some(&block) = self.combos.get(&combination) {
            return Ok(Some(block));
        }
        let (low, high) = combination;
        if bakes(self.flags, high, self.flattened) {
            return Ok(None);
        }
        let (Some(lower_half), Some(upper_half)) =
            (self.cells[0].get(&low), self.cells[1].get(&high))
        else {
            return Ok(None);
        };
        let bytes: Vec<u8> = lower_half.iter().chain(upper_half).copied().collect();
        let terrain = terrain_of(self.chipset, low);
        let terrain = u8::try_from(terrain).map_err(|_| {
            Bad::answer(format!(
                "a tile with terrain {terrain} and the ROM's table carries one byte per block"
            ))
        })?;
        let print = (bytes, cell(self.flags, low, high), terrain);
        let number = match self.by_bytes.get(&print) {
            Some(&n) => n,
            None => {
                let n = self.blocks.passability.len();
                if n >= MAX_BLOCKS {
                    return Err(Bad::answer(format!(
                        "map {} goes over {MAX_BLOCKS} blocks building the ones `TileSubstitution` \
                         needs",
                        self.id
                    )));
                }
                self.blocks.table.extend_from_slice(&print.0);
                self.blocks.passability.push(print.1);
                self.blocks.terrain.push(print.2);
                self.by_bytes.insert(print, n as u16);
                n as u16
            }
        };
        self.combos.insert(combination, number);
        self.blocks.combos.push((combination, number));
        Ok(Some(number))
    }
}

/// Whether an upper tile is baked into the background instead of going to
/// BG2: it goes above the hero only with `ABOVE`. The empty tile bakes
/// nothing.
fn bakes(flags: &[u8], high: i32, flattened: bool) -> bool {
    high != UPPER && (flattened || flags[high as usize] & ABOVE == 0)
}

fn half(blocks: &Blocks, block: u16, layer: usize) -> Vec<u8> {
    let first = usize::from(block) * BLOCK_BYTES + layer * 8;
    blocks.table[first..first + 8].to_vec()
}

fn fingerprint(blocks: &Blocks, block: usize) -> Fingerprint {
    let first = block * BLOCK_BYTES;
    (
        blocks.table[first..first + BLOCK_BYTES].to_vec(),
        blocks.passability[block],
        blocks.terrain[block],
    )
}

fn in_layer(tile: i32) -> bool {
    (0..TILES_PER_LAYER).contains(&tile)
}

/// The RM2k ids of the tile that goes out and the one that comes in.
fn ids(upper: bool, old: i32, new: i32) -> (i32, i32) {
    let base = if upper { UPPER } else { LOWER };
    (base + old, base + new)
}

fn side(combination: (i32, i32), layer: usize) -> i32 {
    if layer == 0 {
        combination.0
    } else {
        combination.1
    }
}

fn with_side(combination: (i32, i32), layer: usize, tile: i32) -> (i32, i32) {
    if layer == 0 {
        (tile, combination.1)
    } else {
        (combination.0, tile)
    }
}

/// The `(lower, upper)` pairs `triples` take the map's cells to, one after
/// another as they chain, that the map does not draw itself, in order: what
/// a map that draws both layers as one has to draw anyway —see
/// `Drawn::extended`—, since it cannot build them out of halves.
pub fn unseen(lower: &[i32], upper: &[i32], triples: &[Triple]) -> Vec<(i32, i32)> {
    let drawn: std::collections::BTreeSet<(i32, i32)> = lower.iter().copied().zip(upper.iter().copied()).collect();
    let mut all = drawn.clone();
    let mut out = Vec::new();
    loop {
        let before = all.len();
        for &(up, old, new) in triples {
            if !(in_layer(old) && in_layer(new)) {
                continue;
            }
            let layer = usize::from(up);
            let (old_id, new_id) = ids(up, old, new);
            let sources: Vec<(i32, i32)> = all.iter().copied().filter(|&c| side(c, layer) == old_id).collect();
            for c in sources {
                let dest = with_side(c, layer, new_id);
                if all.insert(dest) {
                    out.push(dest);
                }
            }
        }
        if all.len() == before {
            return out;
        }
    }
}

/// What a map answers of its substitutions: each one it can run —its own
/// and its test pages', which are closed, then the common events' that are
/// not among them, which are only translated— with its pairs, and the ones
/// whose blocks could not be built.
#[derive(Clone, Debug, Default)]
pub struct Answer {
    pub table: Vec<(Triple, Option<Pairs>)>,
    pub missing: Vec<Triple>,
}

/// Closes `own` over the map's blocks and translates `own` and `common`.
pub fn substitute(
    id: i32,
    blocks: &mut Blocks,
    flags: &[u8],
    chipset: &Chipset,
    own: &[Triple],
    common: &[Triple],
    flattened: bool,
) -> Result<Answer> {
    let mut subs = Substitutions::new(id, blocks, flags, chipset, flattened);
    let missing = subs.close(own)?;
    let mut asked: Vec<Triple> = own.to_vec();
    for t in common {
        if !asked.contains(t) {
            asked.push(*t);
        }
    }
    let table = asked.into_iter().map(|t| (t, subs.pairs(t))).collect();
    Ok(Answer { table, missing })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn flags_with(above: &[i32]) -> Vec<u8> {
        let mut flags = vec![0x0Fu8; 65536];
        for &t in above {
            flags[t as usize] |= ABOVE;
        }
        flags
    }

    /// Two cells: lower tiles 0 and 1 under the empty upper tile, and upper
    /// tile 2 (with "Above") over lower 0. Each block is its bytes: the
    /// lower half carries the lower tile, the upper half the upper tile.
    fn blocks() -> Blocks {
        let row = |low: u8, high: u8| {
            let mut b = vec![low; 8];
            b.extend(vec![high; 8]);
            b
        };
        let mut table = row(0, 0xEE);
        table.extend(row(1, 0xEE));
        table.extend(row(0, 2));
        Blocks {
            cells: vec![0, 1, 2],
            table,
            passability: vec![15, 15, 15],
            terrain: vec![1, 1, 1],
            combos: vec![
                ((LOWER, UPPER), 0),
                ((LOWER + 1, UPPER), 1),
                ((LOWER, UPPER + 2), 2),
            ],
        }
    }

    #[test]
    fn a_substitution_into_a_drawn_tile_maps_each_block() {
        let flags = flags_with(&[UPPER + 2]);
        let chipset = Chipset::default();
        let mut b = blocks();
        let answer = substitute(7, &mut b, &flags, &chipset, &[(false, 0, 1)], &[], false).unwrap();
        assert!(answer.missing.is_empty());
        // (0, empty) -> (1, empty) exists; (0, 2) -> (1, 2) is built.
        assert_eq!(
            answer.table,
            vec![((false, 0, 1), Some(vec![(0, 1), (2, 3)]))]
        );
        assert_eq!(b.passability.len(), 4);
        assert_eq!(
            &b.table[48..64],
            &[1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2]
        );
    }

    #[test]
    fn a_tile_the_map_does_not_draw_cannot_come_in() {
        let flags = flags_with(&[UPPER + 2]);
        let chipset = Chipset::default();
        let mut b = blocks();
        let answer = substitute(
            7,
            &mut b,
            &flags,
            &chipset,
            &[(false, 0, 9)],
            &[(true, 2, 3)],
            false,
        )
        .unwrap();
        assert_eq!(answer.missing, vec![(false, 0, 9)]);
        assert_eq!(
            answer.table,
            vec![((false, 0, 9), None), ((true, 2, 3), None)]
        );
        assert_eq!(b.passability.len(), 3, "nothing was built");
    }

    #[test]
    fn an_upper_tile_without_above_is_baked_and_cannot_be_built_on() {
        // Without "Above", upper tile 2 is drawn into the background.
        let flags = flags_with(&[]);
        let chipset = Chipset::default();
        let mut b = blocks();
        let answer = substitute(7, &mut b, &flags, &chipset, &[(false, 0, 1)], &[], false).unwrap();
        assert_eq!(answer.missing, vec![(false, 0, 1)]);
        assert_eq!(answer.table, vec![((false, 0, 1), None)]);
    }

    #[test]
    fn substitutions_chain_both_ways() {
        let flags = flags_with(&[UPPER + 2]);
        let chipset = Chipset::default();
        let mut b = blocks();
        let triples = [(false, 1, 0), (false, 0, 1)];
        let answer = substitute(7, &mut b, &flags, &chipset, &triples, &[], false).unwrap();
        assert!(answer.missing.is_empty());
        assert_eq!(answer.table[0], ((false, 1, 0), Some(vec![(1, 0), (3, 2)])));
        assert_eq!(answer.table[1], ((false, 0, 1), Some(vec![(0, 1), (2, 3)])));
    }
}
