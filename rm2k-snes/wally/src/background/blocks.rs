//! The map as indices into a table of 16x16 blocks.
//!
//! What a cartridge stores is not the expanded tilemap —the heaviest map
//! would take more than the whole cartridge—: an RM2k cell is four 8x8
//! cells of each layer, it is the unit the game was drawn with, and it
//! repeats a lot. So the map is one index per cell into a table of blocks,
//! each with its four cells of the background, its four of the layer above,
//! its passability and its terrain.
//!
//! Passability and terrain go into what makes a block distinct, and not
//! for free: two cells drawn the same can come from tiles with different
//! permissions or terrain, and the console reads both per block.
//!
//! And so does a tile a `TileSubstitution` names, for the same reason: the
//! console swaps blocks, so a block a substitution swaps can only be drawn
//! by cells that carry that tile. See [`Map::apart`].

use crate::background::fail::{Bad, Result};
use std::collections::BTreeSet;

/// A block in the table: four background cells and four above, one word
/// each.
pub const BLOCK_BYTES: usize = 16;

/// The most blocks the table takes: it is read with `lda table, x`, in bank
/// 0 with the code.
pub const MAX_BLOCKS: usize = 1024;

/// The map in blocks.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Blocks {
    /// One block number per map cell, row by row: how the console walks
    /// them.
    pub cells: Vec<u16>,
    /// `BLOCK_BYTES` per block: the four background cells, then the four
    /// above, each top-left, top-right, bottom-left, bottom-right.
    pub table: Vec<u8>,
    /// Each block's passability and terrain.
    pub passability: Vec<u8>,
    pub terrain: Vec<u8>,
    /// Which block each `(lower tile, upper tile)` pair of the map ended up
    /// in, in the order they are first met, with the RM2k tile ids. They
    /// change nothing of the above: they are what a `TileSubstitution` needs
    /// to find the block a tile is swapped into, since the bytecode talks of
    /// tiles and the console of blocks.
    pub combos: Vec<((i32, i32), u16)>,
    /// The block of each cell of the rows a map draws below itself and then
    /// cuts off, in order: empty until the caller cuts them.
    pub extension: Vec<u16>,
}

/// What of the map the blocks are made of.
pub struct Map<'a> {
    pub width: usize,
    pub height: usize,
    pub lower: &'a [i32],
    pub upper: &'a [i32],
    /// Each cell's passability, already resolved from both layers.
    pub passability: &'a [u8],
    /// Each cell's terrain.
    pub terrain: &'a [i32],
    /// The RM2k tile ids a `TileSubstitution` of the map names, going out
    /// or coming in: a cell that carries one is never the same block as a
    /// cell that does not, however alike they are drawn. The console's
    /// substitution rewrites a block wherever it is, so a block shared by
    /// two tiles would be swapped for both —Zounds' map 59 draws lower tile
    /// 1 exactly like its floor, and its spikes swap through tile 1: shared,
    /// the whole floor would come out as spikes—.
    pub apart: &'a BTreeSet<i32>,
}

/// What of a cell's two tiles keeps it apart from cells drawn alike: each
/// tile if `apart` names it, -1 if not.
pub fn tag(apart: &BTreeSet<i32>, (low, high): (i32, i32)) -> (i32, i32) {
    let kept = |t: i32| if apart.contains(&t) { t } else { -1 };
    (kept(low), kept(high))
}

/// The map in blocks, from the two tilemaps the layers were converted to.
pub fn blocks(map: &Map, background: &[Vec<u16>], above: &[Vec<u16>]) -> Result<Blocks> {
    type Key = ([u16; 4], [u16; 4], u8, i32, (i32, i32));
    let mut numbers: std::collections::HashMap<Key, u16> = std::collections::HashMap::new();
    let mut keys: Vec<Key> = Vec::new();
    let mut cells = Vec::with_capacity(map.width * map.height);
    let mut combos = Vec::new();
    let mut seen = std::collections::HashSet::new();
    let quarter = |tilemap: &[Vec<u16>], bx: usize, by: usize| {
        let mut four = [0u16; 4];
        for (i, (dy, dx)) in [(0, 0), (0, 1), (1, 0), (1, 1)].into_iter().enumerate() {
            four[i] = tilemap[by * 2 + dy][bx * 2 + dx];
        }
        four
    };
    for by in 0..map.height {
        for bx in 0..map.width {
            let at = by * map.width + bx;
            let key = (
                quarter(background, bx, by),
                quarter(above, bx, by),
                map.passability[at],
                map.terrain[at],
                tag(map.apart, (map.lower[at], map.upper[at])),
            );
            let number = *numbers.entry(key).or_insert_with(|| {
                keys.push(key);
                (keys.len() - 1) as u16
            });
            cells.push(number);
            let pair = (map.lower[at], map.upper[at]);
            if seen.insert(pair) {
                combos.push((pair, number));
            }
        }
    }
    if keys.len() > MAX_BLOCKS {
        return Err(Bad::new(format!(
            "the map uses {} distinct blocks and the table can't go over {MAX_BLOCKS}",
            keys.len()
        )));
    }
    let mut table = Vec::with_capacity(BLOCK_BYTES * keys.len());
    let mut passability = Vec::with_capacity(keys.len());
    let mut terrain = Vec::with_capacity(keys.len());
    for (bg, above, pass, ter, _) in keys {
        for cell in bg.iter().chain(&above) {
            table.extend_from_slice(&cell.to_le_bytes());
        }
        passability.push(pass);
        terrain.push(u8::try_from(ter).map_err(|_| {
            Bad::new(format!(
                "a tile with terrain {ter} and the ROM's table carries one byte per block"
            ))
        })?);
    }
    Ok(Blocks {
        cells,
        table,
        passability,
        terrain,
        combos,
        extension: Vec::new(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Two cells drawn the same, with the same passability and terrain, are
    /// one block; a different terrain alone makes another one.
    #[test]
    fn a_block_is_what_is_drawn_and_what_it_lets_through() {
        let bg = vec![vec![1, 2, 1, 2, 1, 2], vec![3, 4, 3, 4, 3, 4]];
        let above = vec![vec![0; 6], vec![0; 6]];
        let map = Map {
            width: 3,
            height: 1,
            lower: &[5000, 5001, 5000],
            upper: &[10000, 10000, 10000],
            passability: &[15, 15, 15],
            terrain: &[1, 1, 2],
            apart: &BTreeSet::new(),
        };
        let made = blocks(&map, &bg, &above).unwrap();
        assert_eq!(made.cells, [0, 0, 1]);
        assert_eq!(made.table.len(), 2 * BLOCK_BYTES);
        assert_eq!(&made.table[..8], &[1, 0, 2, 0, 3, 0, 4, 0]);
        assert_eq!(made.terrain, [1, 2]);
        // Each pair of tiles, the first time it is met.
        assert_eq!(made.combos, [((5000, 10000), 0), ((5001, 10000), 0)]);

        // Unless a substitution names one of the two tiles drawn alike.
        let apart: BTreeSet<i32> = [5001].into();
        let made = blocks(
            &Map {
                apart: &apart,
                ..map
            },
            &bg,
            &above,
        )
        .unwrap();
        assert_eq!(made.cells, [0, 1, 2]);
        assert_eq!(made.combos, [((5000, 10000), 0), ((5001, 10000), 1)]);
    }

    #[test]
    fn a_terrain_past_a_byte_is_refused() {
        let map = Map {
            width: 1,
            height: 1,
            lower: &[5000],
            upper: &[10000],
            passability: &[0],
            terrain: &[256],
            apart: &BTreeSet::new(),
        };
        let one = vec![vec![0; 2]; 2];
        assert!(blocks(&map, &one, &one).is_err());
    }
}
