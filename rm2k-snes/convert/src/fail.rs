//! What stops a conversion, and how it says so.
//!
//! The converter answers no in one way only: it prints why and exits with
//! 1. It is what the cartridges' builder looks at, and what it shows: the
//! message goes to standard error, after everything the conversion printed.
//! A command line that makes no sense exits with 2, the way the flags'
//! parser does.

use std::fmt;

#[derive(Debug)]
pub struct Stop {
    pub message: String,
    pub code: u8,
}

impl Stop {
    /// The answer is no: something does not fit, or a stage said no.
    pub fn new<S: Into<String>>(message: S) -> Stop {
        Stop { message: message.into(), code: 1 }
    }

    /// The call is wrong.
    pub fn usage<S: Into<String>>(message: S) -> Stop {
        Stop { message: message.into(), code: 2 }
    }
}

impl fmt::Display for Stop {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

pub type Result<T> = std::result::Result<T, Stop>;

/// `Err(Stop::new(...))`, with `format!`'s syntax.
#[macro_export]
macro_rules! stop {
    ($($arg:tt)*) => {
        return Err($crate::fail::Stop::new(format!($($arg)*)))
    };
}

impl From<rm2k_project::Error> for Stop {
    fn from(e: rm2k_project::Error) -> Stop {
        Stop::new(e.0)
    }
}

impl From<ditto::lcf::Error> for Stop {
    fn from(e: ditto::lcf::Error) -> Stop {
        Stop::new(e.0)
    }
}

/// An I/O error, with the path it happened on.
pub fn io(path: &std::path::Path, e: std::io::Error) -> Stop {
    Stop::new(format!("{}: {e}", path.display()))
}
