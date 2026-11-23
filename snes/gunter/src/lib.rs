//! BRR, and where samples come from: the codec for the SPC700's sample
//! format, and a SoundFont reader to get PCM worth encoding.
//!
//! Nothing here knows what the samples are for.

pub mod codec;
pub mod extract;
pub mod fail;
pub mod sf2;
