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
        Stop {
            message: message.into(),
            code: 1,
        }
    }

    /// The call is wrong.
    pub fn usage<S: Into<String>>(message: S) -> Stop {
        Stop {
            message: message.into(),
            code: 2,
        }
    }

    /// The same stop, saying which map it is about **in its own first
    /// line**: whoever reads it is about to leave that map out of the
    /// cartridge, and the header the conversion printed for the map may be
    /// far above, or missing, when the stage runs them all at once. A
    /// message whose first line already names it stays as it is, so nothing
    /// says it twice.
    pub fn in_map(self, id: i32) -> Stop {
        let first = self.message.lines().next().unwrap_or("").to_lowercase();
        let named = format!("map {id}");
        let says_it = first.match_indices(&named).any(|(at, _)| {
            !first[at + named.len()..].starts_with(|c: char| c.is_ascii_digit())
                && !first[..at].ends_with(|c: char| c.is_ascii_alphanumeric())
        });
        if says_it {
            self
        } else {
            Stop {
                message: format!("map {id}: {}", self.message),
                code: self.code,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::Stop;

    #[test]
    fn a_stop_in_a_map_names_it_once() {
        let named = |m: &str| Stop::new(m).in_map(15).message;
        assert_eq!(
            named("this map can't carry a message window"),
            "map 15: this map can't carry a message window"
        );
        assert_eq!(
            named("map 15: fits no VRAM layout"),
            "map 15: fits no VRAM layout"
        );
        assert_eq!(
            named("wally: map 15: its panorama can't go"),
            "wally: map 15: its panorama can't go"
        );
        assert_eq!(
            named("map 15 has 9 events with a parallel page"),
            "map 15 has 9 events with a parallel page"
        );
        // Another map's number, or one that only starts the same, is not it.
        assert_eq!(named("map 150: no page 2"), "map 15: map 150: no page 2");
        assert_eq!(
            named("a teleport to map 1 fails\nmap 15"),
            "map 15: a teleport to map 1 fails\nmap 15"
        );
        assert_eq!(Stop::usage("x").in_map(3).code, 2);
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
