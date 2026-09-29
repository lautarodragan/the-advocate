//! What goes wrong, and which of the two kinds of wrong it is.
//!
//! "This page does not compile" is not here: it is the normal answer for a
//! page, and it is [`crate::compile::Cannot`]. What is here stops the whole
//! conversion: a text with a letter the font does not have, a request that
//! is not JSON.

use std::fmt;

#[derive(Debug)]
pub enum Bad {
    /// The answer is no: the game cannot be compiled, or its dump is broken.
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

/// Why a page stopped compiling: it has something the ROM does not know how
/// to do —the normal answer, and the page is left out—, or something that
/// stops the whole conversion.
#[derive(Debug)]
pub enum Stop {
    Cannot,
    Fatal(Bad),
}

impl From<Bad> for Stop {
    fn from(bad: Bad) -> Stop {
        Stop::Fatal(bad)
    }
}

/// What compiling one piece of a page gives.
pub type Step<T> = std::result::Result<T, Stop>;
