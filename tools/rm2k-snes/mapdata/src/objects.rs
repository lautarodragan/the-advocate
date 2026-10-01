//! The characters as the console's objects, as far as the emission writes
//! them: their priorities, their colours, the poses in the cartridge and
//! where a 32x32 block of the sprite bank starts.

/// The objects' priorities, already shifted into their place in the
/// `vhoopppN` byte: the priority is bits 5 and 4, not 0 and 1. Writing $20
/// thinking it is priority 1 gives priority 2, which in mode 3 crosses
/// exactly the upper layer: the sprite is still visible, on the wrong side
/// of the roof it should walk under.
///
/// Priority 1: below BG2 at 1, which is where the hero and the usual
/// events go.
pub const OBJ_PRIORITY: u32 = 0x10;
/// Priority 2: above it, for the events marked "above".
pub const OBJ_PRIORITY_ABOVE: u32 = 0x20;

/// A sprite palette's colours: 4 bits a pixel, and 0 is transparent.
pub const OBJ_COLORS: usize = 15;
/// A CharSet's poses: three walking frames for four directions.
pub const SPRITE_POSES: usize = 12;
/// A pose in the cartridge: the sixteen tiles of a 32x32 object, in a row.
pub const POSE_BYTES: usize = 16 * 32;

/// How many 32x32 blocks fit across the sprite bank's name grid, which is
/// sixteen tiles wide.
pub const BLOCKS_PER_ROW: u32 = 4;

/// The tile a 32x32 block starts at.
pub fn block_tile(block: u32) -> u32 {
    (block / BLOCKS_PER_ROW) * 64 + (block % BLOCKS_PER_ROW) * 4
}

/// RM2k's layers of an event: under the hero, the hero's —the only one that
/// collides with him— and above.
pub const LAYER_BELOW: i64 = 0;
pub const LAYER_SAME: i64 = 1;
pub const LAYER_ABOVE: i64 = 2;

#[cfg(test)]
mod tests {
    #[test]
    fn a_block_starts_four_tiles_across_and_a_row_of_blocks_is_sixty_four() {
        assert_eq!(super::block_tile(0), 0);
        assert_eq!(super::block_tile(3), 12);
        assert_eq!(super::block_tile(5), 68);
    }
}
