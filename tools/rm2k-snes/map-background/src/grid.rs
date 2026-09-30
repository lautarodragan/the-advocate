//! A drawn layer as the PPU shows it: a grid of 8x8 cells of 15-bit colours.
//!
//! Most of a map is the same few cells over and over —Lashe City is 22500
//! cells and a few hundred distinct ones—, so a grid keeps each distinct
//! cell once and says which one goes where. Everything that walks a layer
//! walks the distinct cells and multiplies.

use adeleine::Color;
use rm2k_render::Picture;
use std::collections::{BTreeSet, HashMap};

/// A cell's side, in pixels: the hardware's, and not a setting.
pub const CELL: usize = 8;

/// One cell: eight rows of eight colours, `None` where nothing is drawn.
pub type Cell = [[Option<Color>; CELL]; CELL];

/// A layer cut into cells.
#[derive(Clone, Debug)]
pub struct Grid {
    pub columns: usize,
    pub rows: usize,
    /// For each place, row-major, which of `cells` goes there.
    pub at: Vec<usize>,
    /// The distinct cells, in the order they are first met.
    pub cells: Vec<Cell>,
}

impl Grid {
    /// The picture at 15 bits, cut into cells. A pixel with no alpha at all
    /// is transparent, whatever its colour; any other keeps its colour, five
    /// bits a channel. A strip past the last whole cell is dropped.
    pub fn quantize(picture: &Picture) -> Grid {
        let columns = picture.width / CELL;
        let rows = picture.height / CELL;
        let mut index: HashMap<Cell, usize> = HashMap::new();
        let mut cells = Vec::new();
        let mut at = Vec::with_capacity(columns * rows);
        for cy in 0..rows {
            for cx in 0..columns {
                let mut cell: Cell = [[None; CELL]; CELL];
                for (y, line) in cell.iter_mut().enumerate() {
                    let row = (cy * CELL + y) * picture.width + cx * CELL;
                    for (x, pixel) in line.iter_mut().enumerate() {
                        let p = &picture.rgba[(row + x) * 4..(row + x) * 4 + 4];
                        if p[3] != 0 {
                            *pixel = Some([p[0] >> 3, p[1] >> 3, p[2] >> 3]);
                        }
                    }
                }
                let number = *index.entry(cell).or_insert_with(|| {
                    cells.push(cell);
                    cells.len() - 1
                });
                at.push(number);
            }
        }
        Grid {
            columns,
            rows,
            at,
            cells,
        }
    }

    /// The cell at column `x`, row `y`.
    pub fn cell(&self, x: usize, y: usize) -> &Cell {
        &self.cells[self.at[y * self.columns + x]]
    }

    /// The same grid with every colour sent where `to` says. Two cells that
    /// become equal stay two entries: nothing reads a grid by identity.
    pub fn remap(&self, to: &HashMap<Color, Color>) -> Grid {
        let cells = self
            .cells
            .iter()
            .map(|cell| cell.map(|line| line.map(|p| p.map(|c| *to.get(&c).unwrap_or(&c)))))
            .collect();
        Grid {
            columns: self.columns,
            rows: self.rows,
            at: self.at.clone(),
            cells,
        }
    }

    /// How many times each distinct cell is used.
    fn uses(&self) -> Vec<u64> {
        let mut uses = vec![0u64; self.cells.len()];
        for &n in &self.at {
            uses[n] += 1;
        }
        uses
    }
}

/// The colours a cell draws with.
pub fn colors(cell: &Cell) -> BTreeSet<Color> {
    cell.iter().flatten().flatten().copied().collect()
}

/// How many pixels of each colour these grids draw, in the order the colours
/// are first met walking each grid's distinct cells. The order changes no
/// decision —Adeleine breaks every tie by the colour— but a fixed one keeps
/// the answer the same from run to run.
pub fn counts(grids: &[&Grid]) -> Vec<(Color, u64)> {
    let mut order: Vec<Color> = Vec::new();
    let mut total: HashMap<Color, u64> = HashMap::new();
    for grid in grids {
        for (cell, uses) in grid.cells.iter().zip(grid.uses()) {
            if uses == 0 {
                continue;
            }
            for color in cell.iter().flatten().flatten() {
                let n = total.entry(*color).or_insert_with(|| {
                    order.push(*color);
                    0
                });
                *n += uses;
            }
        }
    }
    order.into_iter().map(|c| (c, total[&c])).collect()
}
