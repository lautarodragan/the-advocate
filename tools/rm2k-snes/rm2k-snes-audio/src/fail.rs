//! The one error type.
//!
//! Two kinds, because a build script wants to tell them apart without
//! reading the message: the music does not fit or a song does not encode —
//! this tool answering no— and a call that makes no sense.

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Bad {
    /// The answer is no: the samples do not fit even at the minimum, a
    /// stream would not write what it has to.
    Answer(String),
    /// The call is wrong: a missing flag, a file that cannot be read.
    Usage(String),
}

impl Bad {
    pub fn answer(message: impl Into<String>) -> Bad {
        Bad::Answer(message.into())
    }

    pub fn usage(message: impl Into<String>) -> Bad {
        Bad::Usage(message.into())
    }
}

impl fmt::Display for Bad {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Bad::Answer(m) | Bad::Usage(m) => f.write_str(m),
        }
    }
}

impl std::error::Error for Bad {}

impl From<rm2k_project::Error> for Bad {
    fn from(e: rm2k_project::Error) -> Bad {
        Bad::Usage(e.0)
    }
}

impl From<gunter::fail::Bad> for Bad {
    fn from(e: gunter::fail::Bad) -> Bad {
        Bad::Usage(e.0)
    }
}

pub type Result<T> = std::result::Result<T, Bad>;
