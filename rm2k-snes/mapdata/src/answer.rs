//! What `emit` answers besides the `.inc` and the raw data:
//! `mapdata.json`, as the type its caller reads it with. A field renamed
//! here does not compile there.

use serde::{Deserialize, Serialize};

/// `mapdata.json`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Answer {
    /// What it says while it writes, in order.
    pub notes: Vec<String>,
    /// What was shared and compressed.
    pub report: Vec<String>,
    /// Per map, in the request's order, how many frames the console takes
    /// to decompress it.
    pub frames: Vec<f64>,
    /// What it cut to fit, for the cartridge's degradations.
    pub losses: Vec<Loss>,
}

/// Something a map shows with less than RM2k because of how the cartridge
/// carries it: `kind`, a stable slug to count by, and what is lost.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Loss {
    pub map: i64,
    pub kind: String,
    pub text: String,
}

/// A ChipSet animation whose drawings do not fit in WRAM: see
/// [`crate::animation`].
pub const CHIPSET_ANIMATION_CUT: &str = "chipset-animation-cut";
/// An inn's gold window, on a map without room for it in the sprites.
pub const INN_NO_GOLD_WINDOW: &str = "inn-no-gold-window";
