//! Where one can walk, and which tile goes in front of the hero.
//!
//! Each tile has four bits that say from which sides it can be crossed.
//! Moving from a cell to the next asks both: the origin has to let one out on
//! that side and the destination let one in on the opposite one.
//!
//! Two more bits say how it is drawn: `ABOVE` —over the hero— and `WALL`,
//! which on a terrain autotile marks the face of a wall. They are read
//! through [`crate::chipset::passability_table`], indexed by tile id.

/// The four sides a tile can be crossed from.
pub const DOWN: u8 = 0x01;
pub const LEFT: u8 = 0x02;
pub const RIGHT: u8 = 0x04;
pub const UP: u8 = 0x08;
/// Drawn over the hero —decoration—, and on the upper layer, "let the lower
/// layer decide".
pub const ABOVE: u8 = 0x10;
/// On a terrain autotile, the face of a wall.
pub const WALL: u8 = 0x20;
pub const ALL: u8 = DOWN | LEFT | RIGHT | UP;

/// The combinations of a terrain autotile —`(id - 4000) % 50`— that are the
/// face of a wall. With the `WALL` bit set, those can always be crossed.
pub const WALL_FACES: [i32; 13] = [20, 21, 22, 23, 33, 34, 35, 36, 37, 42, 43, 45, 46];

/// Whether the lower-layer tile `id` lets one through on `side`.
pub fn lower_passable(flags: &[u8], id: i32, side: u8) -> bool {
    let f = flags[id as usize];
    if (4000..5000).contains(&id) && f & WALL != 0 && WALL_FACES.contains(&((id - 4000) % 50)) {
        return true;
    }
    f & side != 0
}

/// A cell's four side bits, given its two tiles: easyrpg's
/// `Game_Map::IsPassableTile`.
///
/// The upper layer decides, unless it has `ABOVE`: then it is decoration,
/// and the lower one decides. Either way, a side the upper layer closes is
/// closed.
pub fn cell(flags: &[u8], lower: i32, upper: i32) -> u8 {
    let mut bits = 0;
    for side in [DOWN, LEFT, RIGHT, UP] {
        let f = flags[upper as usize];
        if f & side == 0 {
            continue;
        }
        if f & ABOVE == 0 || lower_passable(flags, lower, side) {
            bits |= side;
        }
    }
    bits
}

/// [`cell`] for every cell of a map, in the layers' order.
pub fn map(flags: &[u8], lower: &[i16], upper: &[i16]) -> Vec<u8> {
    lower
        .iter()
        .zip(upper)
        .map(|(&l, &u)| cell(flags, l as i32, u as i32))
        .collect()
}

/// Whether a lower-layer tile is drawn over the hero: with `ABOVE` or with
/// `WALL`. It is how `lmu2png` stacks the layers.
pub fn lower_above(flags: &[u8], id: i32) -> bool {
    flags[id as usize] & (ABOVE | WALL) != 0
}

/// Whether an upper-layer tile is drawn over the hero: with `ABOVE`.
pub fn upper_above(flags: &[u8], id: i32) -> bool {
    flags[id as usize] & ABOVE != 0
}
