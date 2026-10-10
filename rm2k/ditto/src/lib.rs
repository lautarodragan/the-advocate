//! Ditto: reads the RPG Maker 2000 files and dumps them to JSON, and back.
//!
//! What makes this useful is that the way back is **byte for byte**: only then
//! can a game be opened with the real RPG Maker, saved, and still be the same
//! repository. See `README.md`.

pub mod describe;
pub mod dump;
pub mod file;
pub mod lcf;
pub mod raw;
pub mod schema;
