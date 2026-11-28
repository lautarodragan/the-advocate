//! What goes wrong, and which of the two kinds of wrong it is.
//!
//! "The party's experience does not fit in the save" is this tool answering
//! no about its input; a missing file or a request that is not JSON is the
//! call being wrong. They were the binary's two exit codes until it went,
//! on 2026-11-27.

use std::fmt;

#[derive(Debug)]
pub enum Bad {
    /// The answer is no: the game does not fit, or its dump is broken.
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
