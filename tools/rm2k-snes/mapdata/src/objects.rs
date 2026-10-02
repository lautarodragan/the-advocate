//! The characters as the console's objects, as far as the emission writes
//! them: their priorities, their colours, the poses in the cartridge and
//! where a 32x32 block of the sprite bank starts, and what a page draws.

use crate::request::Draws;
use wally::sprites::character;

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

/// A sprite palette's colours: objects are always 4 bits a pixel —there is
/// no mode 3 for them—, and 0 is transparent.
///
/// A pose in the cartridge: the sixteen tiles of a 32x32 object, in a row.
/// The console has no 24x32 objects; the smallest that covers a pose is
/// 32x32, padded with transparency at the sides. Splitting it into 16x32
/// objects would spend the same and multiply the OAM entries.
///
/// Both are `rm2k-snes-map-sprites`', which cuts the poses and lays out the
/// sprite bank: the emission writes what that stage decided.
pub use wally::sprites::character::{OBJ_COLORS, POSE_BYTES};

/// A CharSet's poses: three walking frames for four directions, each
/// 24x32. `rm2k-snes-map-sprites`' number, as the emission counts.
pub const SPRITE_POSES: usize = character::SPRITE_POSES as usize;

/// The tile a 32x32 block of the sprite bank starts at:
/// `rm2k-snes-map-sprites`' layout, where the poses were put.
pub fn block_tile(block: u32) -> u32 {
    character::block_tile(block as usize) as u32
}

/// RM2k's layers of an event: under the hero, the hero's —the only one that
/// collides with him— and above.
pub const LAYER_BELOW: i64 = 0;
pub const LAYER_SAME: i64 = 1;
pub const LAYER_ABOVE: i64 = 2;

/// What a page of an event that changes graphic draws, already as OAM
/// wants it —tile, attributes, pose, passage—: what the console copies to
/// the event's row when that page becomes the active one.
///
/// The pose goes with bit 7, which is "this page draws something", and
/// the passage is $FF when its graphic is not a tile. One that only
/// appears carries no tile or attributes: its own row points at its slot
/// of twelve poses, and the console does not touch them.
pub fn page_oam(draws: &Draws, layer: i64) -> [u8; 4] {
    let pose = (draws.pose | 0x80) as u8;
    let passage = draws.tile_pass.map_or(0xFF, |p| p as u8);
    let Some(block) = draws.block else {
        return [0, 0, pose, passage];
    };
    let tile = block_tile(block);
    let priority = if layer == LAYER_ABOVE {
        OBJ_PRIORITY_ABOVE
    } else {
        OBJ_PRIORITY
    };
    [
        (tile & 0xFF) as u8,
        (priority | ((draws.palette & 0x07) << 1) | ((tile >> 8) & 1)) as u8,
        pose,
        passage,
    ]
}

#[cfg(test)]
mod tests {
    #[test]
    fn a_block_starts_four_tiles_across_and_a_row_of_blocks_is_sixty_four() {
        assert_eq!(super::block_tile(0), 0);
        assert_eq!(super::block_tile(3), 12);
        assert_eq!(super::block_tile(5), 68);
    }

    #[test]
    fn a_page_draws_its_block_or_only_its_pose() {
        use super::*;
        let draws = |block, tile_pass| Draws {
            block,
            palette: 3,
            pose: 7,
            tile_pass,
        };
        assert_eq!(page_oam(&draws(Some(17), None), LAYER_SAME), [0x04, 0x17, 0x87, 0xFF]);
        assert_eq!(page_oam(&draws(Some(0), Some(2)), LAYER_ABOVE), [0, 0x26, 0x87, 2]);
        assert_eq!(page_oam(&draws(None, Some(1)), LAYER_ABOVE), [0, 0, 0x87, 1]);
    }
}
