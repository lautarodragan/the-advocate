//! An RPG Maker 2000 map's background, for a Super Nintendo in mode 3.
//!
//! A map is drawn as two pictures —what goes behind the hero and what goes
//! in front—, which `rm2k-render` draws. This takes them to the console:
//!
//! * [`layers`]: the lower half of colour memory split between the two, the
//!   colours at 15 bits, what is lost when they do not fit —Adeleine's
//!   decision— and each layer cut into tiles —Voodoo's work—;
//! * [`blocks`]: the map as indices into a table of 16x16 blocks, each with
//!   its cells of both layers, its passability and its terrain.
//!
//! It knows nothing of the sprites, which get the upper half of colour
//! memory and their own VRAM bank, and nothing of which game the map is
//! from.

pub mod blocks;
pub mod fail;
pub mod fuse;
pub mod grid;
pub mod layers;
pub mod mode1;
pub mod panorama;

pub use fail::{Bad, Result};
pub use layers::{convert, convert_with, Above, Background, Converted, Decided, PanoramaAsk, Run};

/// A colour change. A global merge has no palette; a palette-local one does,
/// because the same source colour can go somewhere else in another tile.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Merge {
    pub palette: Option<usize>,
    pub victim: adeleine::Color,
    pub target: adeleine::Color,
    pub pixels: u64,
}

impl From<adeleine::Merge> for Merge {
    fn from(merge: adeleine::Merge) -> Self {
        Merge {
            palette: None,
            victim: merge.victim,
            target: merge.target,
            pixels: merge.pixels,
        }
    }
}

impl From<adeleine::PaletteMerge> for Merge {
    fn from(merge: adeleine::PaletteMerge) -> Self {
        Merge {
            palette: Some(merge.palette),
            victim: merge.victim,
            target: merge.target,
            pixels: merge.pixels,
        }
    }
}
