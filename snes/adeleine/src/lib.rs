//! Adeleine: which colours a picture loses, and how the ones left are grouped
//! into palettes.
//!
//! Everything here **changes what is seen**: merging one colour into another,
//! keeping the most used ones, deciding which colours go together in a
//! palette, measuring how much a picture moves if a colour is taken out of
//! it. It is the artistic half of a graphics pipeline. The other half
//! —cutting tiles, packing bit planes, writing colour memory— decides
//! nothing anyone could see, and lives in Voodoo, which takes a picture
//! that already fits and never touches a pixel. The test for which side
//! something goes on is whether it changes a pixel.
//!
//! Nothing here knows what the pictures are of. A colour is three channels,
//! a tile is the set of colours it draws with, and a palette has sixteen
//! entries of which the first is transparent.

pub mod fail;
pub mod fuse;
pub mod lab;
pub mod merge;
pub mod most_used;
pub mod pack;
pub mod request;
pub mod tiles;

pub use fail::{Bad, Result};
pub use fuse::{merge_least_visible_tiles, Drawn};
pub use lab::{lab, lab_distance};
pub use merge::{luma_distance, merge_least_visible, merge_until, Merge, Merged, Progress};
pub use most_used::{keep_most_used, Kept};
pub use pack::{reduce_colors, try_pack, Colors, PaletteMerge, Reduced, ReducedTile};
pub use tiles::{group_tiles, Tile};

/// A colour: red, green and blue, in whatever depth the caller works in —the
/// distances are the same function of the channels at any depth—. Colours
/// compare channel by channel, red first, and that order is the one every
/// tie is broken by.
pub type Color = [u8; 3];

/// Entries in a four-bit palette.
pub const COLORS_PER_PALETTE: usize = 16;

/// What a four-bit palette holds for a drawing: its entries minus the first,
/// which is transparent.
pub const USABLE_COLORS: usize = COLORS_PER_PALETTE - 1;
