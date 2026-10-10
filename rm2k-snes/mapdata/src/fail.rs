//! What goes wrong, and which of the two kinds of wrong it is.
//!
//! "A map's background does not fit in its stream" is this tool answering
//! no about its input; "`--out` is missing" is the call being wrong. A
//! script wants to tell those apart without reading the message, so they
//! get different exit codes.

use std::fmt;

#[derive(Debug)]
pub enum Bad {
    /// The answer is no: something does not fit, or the dump is broken.
    Answer(String),
    /// The call is wrong: a missing file, a request that is not JSON.
    Usage(String),
}

impl Bad {
    pub fn answer<S: Into<String>>(message: S) -> Self {
        Bad::Answer(message.into())
    }

    pub fn usage<S: Into<String>>(message: S) -> Self {
        Bad::Usage(message.into())
    }

    pub fn message(&self) -> &str {
        match self {
            Bad::Answer(m) | Bad::Usage(m) => m,
        }
    }
}

impl fmt::Display for Bad {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message())
    }
}

impl std::error::Error for Bad {}

pub type Result<T> = std::result::Result<T, Bad>;
