//! The data `.inc` of an rm2k-snes cartridge: what every domain of the
//! conversion answered —the maps, the screens, the pictures, the battle,
//! the compiled pages—, written for ca65.
//!
//! It decides nothing that is not about how the cartridge carries it:
//! which blocks are shared, how they are cut into LZ2 streams and whether
//! each stream fits where the console decompresses it, which segment each
//! table goes in. And it owns the cartridge's VRAM layouts —[`vram`]—,
//! which are the contract with the runtime: the maps and the screens read
//! them from here.

pub mod asm;
pub mod cgram;
pub mod compress;
pub mod emit;
pub mod engine;
pub mod fail;
pub mod hex;
pub mod json;
pub mod materials;
pub mod objects;
pub mod pyfmt;
pub mod record;
pub mod request;
pub mod scene;
pub mod snes;
pub mod text;
pub mod vram;

pub use fail::{Bad, Result};
