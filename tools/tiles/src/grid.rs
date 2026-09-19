//! The picture, and the picture cut into cells, which is the unit everything
//! else works in.
//!
//! A picture here is **indexed, and its indices are colour-memory entries**:
//! index 37 is entry 37, whatever the picture is. So the palette a pixel
//! belongs to is in the pixel itself — at 4bpp, `index >> 4` — and nothing
//! outside the file has to say where a palette starts. That is what lets the
//! choice of palettes happen before this tool runs, and arrive here already
//! made.
//!
//! A tile is 8x8 and nothing here is parameterised on that: the hardware this
//! feeds is not, and a "cell size" knob would be a setting nobody can ever
//! change.

use crate::color::Rgb15;

pub const CELL: usize = 8;

/// Entries of colour memory, and so of an index.
pub const ENTRIES: usize = 256;

/// One 8x8 cell, as colour-memory indices.
pub type Cell = [[u8; CELL]; CELL];

/// An indexed picture: one colour-memory index per pixel, and what colour
/// each entry holds.
pub struct Picture {
    pub width: usize,
    pub height: usize,
    /// Row-major.
    pub pixels: Vec<u8>,
    /// The file's palette, entry by entry. `None` past the end of it.
    pub colors: Vec<Option<Rgb15>>,
}

/// The picture as a grid of cells, row-major.
pub struct Grid {
    pub columns: usize,
    pub rows: Vec<Vec<Cell>>,
}

impl Grid {
    pub fn cells(&self) -> impl Iterator<Item = &Cell> {
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
/// would invent pixels, and this is not the place to decide what invented
/// pixels are.
pub fn cut_cells(picture: &Picture) -> Grid {
    let mut rows = Vec::new();
    for ty in 0..picture.height / CELL {
        let mut line = Vec::new();
        for tx in 0..picture.width / CELL {
            let mut cell: Cell = [[0; CELL]; CELL];
            for (y, cell_row) in cell.iter_mut().enumerate() {
                let start = (ty * CELL + y) * picture.width + tx * CELL;
                cell_row.copy_from_slice(&picture.pixels[start..start + CELL]);
            }
            line.push(cell);
        }
        rows.push(line);
    }
    Grid {
        columns: picture.width / CELL,
        rows,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn solid(width: usize, height: usize, index: u8) -> Picture {
        Picture {
            width,
            height,
            pixels: vec![index; width * height],
            colors: vec![None; ENTRIES],
        }
    }

    #[test]
    fn a_16x16_picture_is_four_cells() {
        let grid = cut_cells(&solid(16, 16, 3));
        assert_eq!(grid.columns, 2);
        assert_eq!(grid.height(), 2);
        assert!(grid.cells().all(|c| c.iter().flatten().all(|&i| i == 3)));
    }

    #[test]
    fn a_partial_cell_on_the_edge_is_dropped() {
        let grid = cut_cells(&solid(20, 12, 1));
        assert_eq!(grid.columns, 2);
        assert_eq!(grid.height(), 1);
    }
}
