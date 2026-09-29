//! An indexed picture into 8x8 tiles, a tilemap and colour memory, packed the
//! way a planar PPU reads them.
//!
//! The picture arrives with its palettes already chosen: its indices are
//! colour-memory entries. Choosing them — which colours survive, how they are
//! grouped, where each group sits — is a decision about what the picture looks
//! like, and this crate makes none of those. It converts a picture the format
//! can hold, or says exactly why the format cannot hold it.
//!
//! Nothing here reads or writes anything except through the paths it is
//! handed, and nothing here knows what the tiles are of.

pub mod color;
pub mod convert;
pub mod fail;
pub mod grid;
pub mod image;
pub mod pack;

pub use color::{cgram_word, Rgb15};
pub use convert::{convert, transparent, Converted, Options, Report};
pub use fail::{Bad, Result};
pub use grid::{cut_cells, Cell, Grid, Picture, CELL, ENTRIES};
pub use pack::{entry, flips, pack_tile, unpack_tile, Indices};
