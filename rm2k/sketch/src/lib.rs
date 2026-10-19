//! A map's tile layers, sketched as text.
//!
//! A Ditto dump keeps a map's two layers in a `.tiles`: one tile id per
//! cell, a grid of numbers. That is legible to diff, but not to draw: RM2k's
//! ids —4000 and up for the terrain autotiles, 5000 for the lower layer's
//! plain tiles, 10000 for the upper layer's— say nothing of what is there.
//! A sketch draws the map as characters instead, one per cell, and a legend
//! says which lower and which upper tile each character stands for:
//!
//! ```toml
//! grid = '''
//! #####
//! #.*.#
//! #####
//! '''
//!
//! [legend]
//! "." = { lower = 4000 }                  # grass
//! "*" = { lower = 4000, upper = 10018 }   # flowers over the grass
//! "#" = { lower = 4000, upper = 10007 }   # a bush
//! ```
//!
//! What comes out is the `.tiles` beside the map's JSON, written by Ditto's
//! own writer (`ditto::dump::grid`), so `ditto pack` reads it like any
//! other. The map's size is the grid's; the JSON has to say the same, and
//! `pack` stops if it does not.
//!
//! **What a sketch does not do**, yet: choose an autotile's pattern from its
//! neighbours, as the editor does. A legend entry is one id, so a terrain
//! autotile is drawn with the pattern the legend names everywhere it
//! appears —the plain middle one, `TERRAIN + n * 50`, for a field—.

use rm2k_rules::chipset::{TILES_PER_LAYER, UPPER};
use serde::Deserialize;
use std::collections::BTreeMap;
use std::fmt;

/// The upper tile a legend entry gets when it names none: the first one,
/// which is empty and lets everything through —what the editor leaves
/// where nothing was drawn above—.
pub const EMPTY_UPPER: i16 = UPPER as i16;

/// Why a sketch could not be read, with where.
#[derive(Debug, PartialEq)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Error {}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Sketch {
    grid: String,
    legend: BTreeMap<String, Cell>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Cell {
    lower: i16,
    #[serde(default = "empty_upper")]
    upper: i16,
}

fn empty_upper() -> i16 {
    EMPTY_UPPER
}

/// A map's two layers, in reading order.
#[derive(Debug, PartialEq)]
pub struct Layers {
    pub width: usize,
    pub height: usize,
    pub lower: Vec<i16>,
    pub upper: Vec<i16>,
}

impl Layers {
    /// The `.tiles` Ditto reads them from.
    pub fn tiles(&self) -> String {
        ditto::dump::grid(self.width, self.height, &self.lower, &self.upper)
    }
}

/// The layers a sketch draws.
pub fn read(text: &str) -> Result<Layers, Error> {
    let sketch: Sketch = toml::from_str(text).map_err(|e| Error(e.to_string()))?;
    let mut legend = BTreeMap::new();
    for (key, cell) in sketch.legend {
        let mut chars = key.chars();
        let (Some(c), None) = (chars.next(), chars.next()) else {
            return Err(Error(format!("legend: {key:?} is not one character")));
        };
        // An upper tile in the lower layer, or a lower one in the upper, is
        // a sketch that mixed up its two numbers: the binary would take it
        // and the editor would draw something else.
        if !(0..UPPER as i16).contains(&cell.lower) {
            return Err(Error(format!(
                "legend: {key:?} has lower = {}, which is not a lower-layer tile",
                cell.lower
            )));
        }
        if !(UPPER as i16..(UPPER + TILES_PER_LAYER) as i16).contains(&cell.upper) {
            return Err(Error(format!(
                "legend: {key:?} has upper = {}, which is not an upper-layer tile",
                cell.upper
            )));
        }
        legend.insert(c, cell);
    }
    // The grid's first and last lines may be empty —a `'''` on a line of its
    // own leaves them—, and only those: an empty line inside is a row
    // missing.
    let rows: Vec<&str> = sketch.grid.trim_matches('\n').split('\n').collect();
    let width = rows[0].chars().count();
    if width == 0 {
        return Err(Error("grid: it is empty".into()));
    }
    let mut layers = Layers {
        width,
        height: rows.len(),
        lower: Vec::new(),
        upper: Vec::new(),
    };
    for (y, row) in rows.iter().enumerate() {
        let n = row.chars().count();
        if n != width {
            return Err(Error(format!(
                "grid: row {y} has {n} cells and the first one {width}"
            )));
        }
        for (x, c) in row.chars().enumerate() {
            let cell = legend.get(&c).ok_or_else(|| {
                Error(format!(
                    "grid: {c:?}, at column {x} of row {y}, is not in the legend"
                ))
            })?;
            layers.lower.push(cell.lower);
            layers.upper.push(cell.upper);
        }
    }
    Ok(layers)
}

#[cfg(test)]
mod tests {
    use super::*;

    const LEGEND: &str =
        "[legend]\n\".\" = { lower = 4000 }\n\"#\" = { lower = 5001, upper = 10007 }\n";

    fn sketch(grid: &str) -> String {
        format!("grid = '''\n{grid}'''\n{LEGEND}")
    }

    #[test]
    fn each_character_is_its_two_tiles_in_reading_order() {
        let layers = read(&sketch("###\n#..\n")).unwrap();
        assert_eq!((layers.width, layers.height), (3, 2));
        assert_eq!(layers.lower, [5001, 5001, 5001, 5001, 4000, 4000]);
        assert_eq!(layers.upper, [10007, 10007, 10007, 10007, 10000, 10000]);
    }

    #[test]
    fn the_tiles_are_what_ditto_reads_back() {
        let tiles = read(&sketch("#.\n")).unwrap().tiles();
        assert_eq!(
            tiles,
            ditto::dump::grid(2, 1, &[5001, 4000], &[10007, 10000])
        );
        assert!(
            tiles.contains("# lower\n  5001  4000\n# upper\n 10007 10000\n"),
            "{tiles}"
        );
    }

    #[test]
    fn a_character_out_of_the_legend_says_where_it_is() {
        let e = read(&sketch("..\n.x\n")).unwrap_err();
        assert_eq!(e.0, "grid: 'x', at column 1 of row 1, is not in the legend");
    }

    #[test]
    fn a_ragged_grid_is_refused() {
        let e = read(&sketch("...\n..\n")).unwrap_err();
        assert_eq!(e.0, "grid: row 1 has 2 cells and the first one 3");
    }

    #[test]
    fn an_empty_line_inside_the_grid_is_a_missing_row() {
        assert!(read(&sketch("..\n\n..\n")).is_err());
    }

    #[test]
    fn a_legend_key_is_one_character() {
        let e = read("grid = '..'\n[legend]\n\"..\" = { lower = 4000 }\n").unwrap_err();
        assert_eq!(e.0, "legend: \"..\" is not one character");
    }

    #[test]
    fn the_two_layers_are_not_mixed_up() {
        assert!(read("grid = '.'\n[legend]\n\".\" = { lower = 10007 }\n").is_err());
        assert!(read("grid = '.'\n[legend]\n\".\" = { lower = 4000, upper = 5001 }\n").is_err());
        assert!(read("grid = '.'\n[legend]\n\".\" = { lower = 4000, upper = 10144 }\n").is_err());
    }

    #[test]
    fn an_unknown_key_is_refused_and_not_ignored() {
        assert!(read("grid = '.'\n[legend]\n\".\" = { lower = 4000, uper = 10007 }\n").is_err());
    }
}
