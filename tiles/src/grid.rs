//! The picture cut into cells, which is the unit everything else works in.
//!
//! A tile is 8x8 and nothing here is parameterised on that: the hardware this
//! feeds is not, and a "cell size" knob would be a setting nobody can ever
//! change.

use crate::color::{Pixel, Rgb15};
use std::collections::BTreeSet;

pub const CELL: usize = 8;

/// One 8x8 cell of the picture, still in colours.
pub type Tile = [[Pixel; CELL]; CELL];

/// The picture as rows of pixels: what a decoder hands over.
pub struct Picture {
    pub width: usize,
    pub height: usize,
    pub rows: Vec<Vec<Pixel>>,
}

/// The picture as a grid of cells, row-major.
pub struct Grid {
    pub columns: usize,
    pub rows: Vec<Vec<Tile>>,
}

impl Grid {
    pub fn cells(&self) -> impl Iterator<Item = &Tile> {
        self.rows.iter().flat_map(|row| row.iter())
    }

    pub fn height(&self) -> usize {
        self.rows.len()
    }
}

/// Cut a picture into 8x8 cells.
///
/// A picture whose size is not a multiple of 8 keeps only the whole cells: the
/// leftover strip on the right and the bottom is dropped. Padding it instead
/// would invent pixels, and this is not the place to decide what colour
/// invented pixels are.
pub fn cut_tiles(picture: &Picture) -> Grid {
    let mut rows = Vec::new();
    for ty in 0..picture.height / CELL {
        let mut line = Vec::new();
        for tx in 0..picture.width / CELL {
            let mut tile: Tile = [[None; CELL]; CELL];
            for (y, tile_row) in tile.iter_mut().enumerate() {
                let source = &picture.rows[ty * CELL + y];
                tile_row.copy_from_slice(&source[tx * CELL..(tx + 1) * CELL]);
            }
            line.push(tile);
        }
        rows.push(line);
    }
    Grid {
        columns: picture.width / CELL,
        rows,
    }
}

/// The colours a cell uses, transparent pixels not counted.
pub fn tile_colors(tile: &Tile) -> BTreeSet<Rgb15> {
    let mut set = BTreeSet::new();
    for row in tile {
        for color in row.iter().flatten() {
            set.insert(*color);
        }
    }
    set
}

/// Every colour in the grid with how many pixels it covers.
pub fn color_counts(grids: &[&Grid]) -> std::collections::BTreeMap<Rgb15, u64> {
    let mut counts = std::collections::BTreeMap::new();
    for grid in grids {
        for tile in grid.cells() {
            for row in tile {
                for color in row.iter().flatten() {
                    *counts.entry(*color).or_insert(0) += 1;
                }
            }
        }
    }
    counts
}

#[cfg(test)]
mod tests {
    use super::*;

    fn solid(width: usize, height: usize, color: Pixel) -> Picture {
        Picture {
            width,
            height,
            rows: vec![vec![color; width]; height],
        }
    }

    #[test]
    fn a_16x16_picture_is_four_cells() {
        let grid = cut_tiles(&solid(16, 16, Some((1, 2, 3))));
        assert_eq!(grid.rows.len(), 2);
        assert_eq!(grid.columns, 2);
        assert_eq!(grid.cells().count(), 4);
    }

    /// The leftover strip is dropped rather than padded: padding would invent
    /// pixels, and nothing here knows what colour they should be.
    #[test]
    fn a_partial_cell_on_the_edge_is_dropped() {
        let grid = cut_tiles(&solid(20, 9, Some((1, 2, 3))));
        assert_eq!(grid.columns, 2);
        assert_eq!(grid.rows.len(), 1);
    }

    #[test]
    fn a_transparent_cell_uses_no_colours() {
        let grid = cut_tiles(&solid(8, 8, None));
        assert!(tile_colors(&grid.rows[0][0]).is_empty());
    }
}
