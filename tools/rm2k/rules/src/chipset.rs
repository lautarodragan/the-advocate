//! The ChipSet: which tile id is which piece of its picture, and the tables
//! the map reads through it —passability and terrain—.
//!
//! A map layer holds **tile ids**, and an id is not an index into anything:
//! the autotiles take 50 or 1000 ids each, one per combination of edges the
//! editor already chose, and a single entry in the ChipSet's tables. The
//! blocks are easyrpg's `map_data.h`; the offsets in the picture, EasyRPG
//! Tools' `lmu2png`.

use ditto::schema::Chipset;

/// A tile is 16x16 pixels.
pub const TILE: i32 = 16;

/// What a ChipSet's picture measures.
pub const CHIPSET_WIDTH: i32 = 480;
pub const CHIPSET_HEIGHT: i32 = 256;

/// Where each family of tile ids starts: the three waters take 0 to 2999
/// —A and B 1000 each, and the deep water C—, then the three animated tiles,
/// the twelve terrain autotiles, and the two pages of plain tiles.
pub const WATER: i32 = 0;
pub const ANIMATED: i32 = 3000;
pub const TERRAIN: i32 = 4000;
/// The first plain tile of the lower layer: the format's "block E", the 144
/// the editor's palette shows below the autotiles.
pub const LOWER: i32 = 5000;
/// The first tile of the upper layer.
pub const UPPER: i32 = 10000;
/// How many plain tiles each layer has.
pub const TILES_PER_LAYER: i32 = 144;

/// How many entries the lower layer's tables have: 18 autotiles and the 144
/// plain tiles. The terrain table has only these; the passability of the
/// upper layer is a table of its own, of `TILES_PER_LAYER`.
pub const LOWER_ENTRIES: usize = 162;

/// The format's six blocks of tile ids, as easyrpg's `map_data.h` has them:
/// `(first id, how many, ids each one takes, first entry)`.
pub const BLOCKS: [(i32, i32, i32, i32); 6] = [
    (WATER, 2, 1000, 0),
    (2000, 1, 1000, 2),
    (ANIMATED, 3, 50, 3),
    (TERRAIN, 12, 50, 6),
    (LOWER, TILES_PER_LAYER, 1, 18),
    (UPPER, TILES_PER_LAYER, 1, 162),
];

/// `ChipIdToIndex`: the ChipSet entry of a tile id —what its terrain and its
/// passability are read with—. An id outside every block is entry 0.
pub fn chip_index(id: i32) -> i32 {
    for (base, count, step, index) in BLOCKS {
        if (base..base + count * step).contains(&id) {
            return index + (id - base) / step;
        }
    }
    0
}

/// `GetTerrainTag`: the terrain of a lower-layer tile.
///
/// A ChipSet whose terrain is all 1 **may not store the table**: it is an
/// RPG_RT optimization the format lets show, and the answer is then 1.
pub fn terrain_of(chipset: &Chipset, id: i32) -> i32 {
    if chipset.terrain_data.is_empty() {
        return 1;
    }
    chipset
        .terrain_data
        .get(chip_index(id) as usize)
        .map_or(1, |&t| t as i32)
}

/// The passability of every tile id, 65536 of them, as `lmu2png` builds it:
/// one entry per family for the autotiles, one per tile for the plain ones.
/// An id no block covers has none: 0.
///
/// `lower` and `upper` are the ChipSet's `passable_data_lower` and
/// `passable_data_upper`: it takes them and not the `Chipset` so a caller
/// that only has the two tables needs no whole one. Tables shorter than the
/// format's —162 and 144— leave the ids past their end at 0 too.
pub fn passability_table(lower: &[u8], upper: &[u8]) -> Vec<u8> {
    let entry = |t: &[u8], i: usize| t.get(i).copied().unwrap_or(0);
    let mut flags = vec![0u8; 65536];
    for i in 0..3 {
        // the waters A, B and C
        flags[1000 * i..1000 * i + 1000].fill(entry(lower, i));
    }
    for i in 0..3 {
        // the animated tiles
        flags[3000 + i * 50..3050 + i * 50].fill(entry(lower, 3 + i));
    }
    for i in 0..12 {
        // the terrain autotiles
        flags[4000 + i * 50..4050 + i * 50].fill(entry(lower, 6 + i));
    }
    for i in 0..TILES_PER_LAYER as usize {
        // the plain tiles, of each layer
        flags[LOWER as usize + i] = entry(lower, 18 + i);
        flags[UPPER as usize + i] = entry(upper, i);
    }
    flags
}

/// Where, in the ChipSet's picture, the 48x64 block of terrain autotile `n`
/// —0 to 11, the one the map names with ids `TERRAIN + n * 50`— starts.
pub fn terrain_origin(n: i32) -> (i32, i32) {
    let terrain = n + 4;
    (
        (terrain % 2) * 48 + (terrain / 8) * 96,
        ((terrain / 2) % 4) * 64,
    )
}

/// Where plain tile `i` starts —0 to 287, the three pages of 96 in the right
/// half—. The first 144 are the lower layer's (ids `LOWER + i`) and the next
/// 144 the upper layer's (ids `UPPER + i - 144`).
pub fn common_origin(i: i32) -> (i32, i32) {
    (
        192 + (i % 6) * TILE + (i / 96) * 96,
        ((i / 6) % TILE) * TILE,
    )
}
