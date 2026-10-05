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
pub mod grid;
pub mod layers;
pub mod mode1;
pub mod panorama;

pub use adeleine::Merge;
pub use fail::{Bad, Result};
pub use layers::{convert, convert_with, Above, Background, Converted, Decided, PanoramaAsk, Run};
