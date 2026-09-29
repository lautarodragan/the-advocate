//! An rm2k-snes game's music, compiled for the SPC700.
//!
//! From the MIDI of each song and the SoundFont the game was composed with,
//! to what the ROM carries: one sample bank shared by every song, uploaded
//! to the SPC700 in packages —one per map—; one per-note stream per song,
//! which the 65816 expands into writes to the S-DSP; the sound effects,
//! sharing the directory's last entries; and their MSU-1 versions.
//!
//! ```text
//!     MIDI + SoundFont  --compile-->  musicdata.inc: the bank, a stream per
//!                                     song, the packages of each map
//!     stream per note   --the ROM-->  writes to the DSP, frame by frame
//! ```
//!
//! Until 2026-09-29 this was a Python program, and what it writes into a
//! cartridge has to keep coming out byte for byte the same: see [`num`].

pub mod bank;
pub mod ceilings;
pub mod compile;
pub mod effects;
pub mod emit;
pub mod fail;
pub mod game;
pub mod job;
pub mod midi;
pub mod msu;
#[rustfmt::skip]
pub mod music_opcodes;
pub mod num;
pub mod pyjson;
pub mod retro;
pub mod samples;
pub mod sdsp;
pub mod song;
pub mod spc700;
pub mod stream;
pub mod tracks;
pub mod voices;

pub use fail::{Bad, Result};
