//! The tile layers of an RPG Maker 2000 map, as pictures.
//!
//! A map is two layers of tile ids and a ChipSet; this expands the ChipSet
//! into every tile it can draw —the autotiles combined with their
//! neighbours— and draws the map as RM2k stacks it: what goes behind the
//! hero, what goes in front, and the other drawings of the ChipSet's
//! animation, the water's and the animated tiles'.
//!
//! No panorama, no events, no picture of the hero: those are drawn by
//! whoever uses the layers. Nothing here knows which game the map is from.

pub mod chipset;
pub mod fail;
pub mod layers;
pub mod picture;
pub mod source;

pub use chipset::Atlas;
pub use fail::{Bad, Result};
pub use layers::{Family, Layers, Map};
pub use picture::Picture;

use std::path::Path;

/// The file the picture behind the hero is written to.
pub const LOWER_FILE: &str = "lower.png";
/// The file the picture in front of the hero is written to.
pub const UPPER_FILE: &str = "upper.png";

/// The file drawing `d` of a family is written to: `water-1.png`,
/// `animated-3.png`. Drawing 0 is `lower.png`.
pub fn variant_file(family: Family, d: usize) -> String {
    format!("{}-{d}.png", family.name())
}

/// Writes the layers into `dir`, which is created if it is not there.
///
/// A family the map does not use gets no files, and **any file of one left
/// by an earlier map is removed**: whoever reads the directory finds out
/// which families there are by which files exist.
pub fn write(dir: &Path, layers: &Layers) -> Result<()> {
    std::fs::create_dir_all(dir).map_err(|e| Bad::usage(format!("{}: {e}", dir.display())))?;
    for family in Family::ALL {
        for d in 1..family.drawings() {
            let path = dir.join(variant_file(family, d));
            if path.exists() {
                std::fs::remove_file(&path)
                    .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
            }
        }
    }
    picture::write_png(&dir.join(LOWER_FILE), &layers.lower)?;
    picture::write_png(&dir.join(UPPER_FILE), &layers.upper)?;
    for (family, drawings) in &layers.variants {
        for (i, drawing) in drawings.iter().enumerate() {
            picture::write_png(&dir.join(variant_file(*family, i + 1)), drawing)?;
        }
    }
    Ok(())
}
