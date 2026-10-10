//! What goes wrong. Everything here is the answer being no —a map whose
//! colours cannot be split, a layer with more tiles than the hardware
//! addresses—: this is a library and takes no call that could be wrong.

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Bad(pub String);

impl Bad {
    pub fn new<S: Into<String>>(message: S) -> Self {
        Bad(message.into())
    }
}

impl fmt::Display for Bad {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Bad {}

impl From<adeleine::Bad> for Bad {
    fn from(bad: adeleine::Bad) -> Self {
        Bad(bad.to_string())
    }
}

impl From<voodoo::Bad> for Bad {
    fn from(bad: voodoo::Bad) -> Self {
        Bad(bad.to_string())
    }
}

pub type Result<T> = std::result::Result<T, Bad>;
