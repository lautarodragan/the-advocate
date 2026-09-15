//! A picture into 8x8 tiles, palettes and a tilemap, packed the way a planar
//! PPU reads them.
//!
//! The pieces are separate because they are separately useful — a caller that
//! already has its palettes wants `pack`, one that only wants to know whether
//! something fits wants `palette` — but the ordinary path is `convert`, which
//! is all of them in the one order they can be done in.
//!
//! Nothing here reads or writes anything except through the paths it is
//! handed, and nothing here knows what the tiles are of.

pub mod color;
pub mod convert;
pub mod fail;
pub mod grid;
pub mod image;
pub mod pack;
pub mod palette;

pub use color::{cgram_word, luma_distance, Pixel, Rgb15};
pub use convert::{convert, Converted, Options, Report};
pub use fail::{Bad, Result};
pub use grid::{cut_tiles, tile_colors, Grid, Picture, Tile, CELL};
pub use pack::{entry, flips, pack_tile, to_indices, unpack_tile, Indices};
pub use palette::{merge_to, merge_until, reduce_colors, try_pack, Merge, COLORS_PER_PALETTE};
