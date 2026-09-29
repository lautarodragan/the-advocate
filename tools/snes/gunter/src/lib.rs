//! BRR, and where samples come from: the codec for the SPC700's sample
//! format, and a SoundFont reader to get PCM worth encoding.
//!
//! The `gunter` binary is this library behind a command line; a program
//! that builds many samples uses it directly and skips a process per sample.
//! Nothing here knows what the samples are for.

pub mod codec;
pub mod extract;
pub mod fail;
pub mod sf2;
pub mod wav;
