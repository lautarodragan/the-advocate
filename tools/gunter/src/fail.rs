//! The one error type, and what it is for.
//!
//! Every message names the file it came from and what was expected there. That
//! is the whole point of a tool meant to be driven from a script by somebody
//! who has not read its source: "invalid input" sends them here, and
//! "song.wav: 24-bit samples; only 8 and 16 are read" does not.

use std::fmt;

#[derive(Debug)]
pub struct Bad(pub String);

impl fmt::Display for Bad {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for Bad {}

pub type Result<T> = std::result::Result<T, Bad>;
