//! The last resort for a background with more distinct tiles than any VRAM
//! layout holds: the cells that look most alike are drawn with one of them.
//!
//! **It changes what is seen**, so the choice is Adeleine's —
//! [`adeleine::group_tiles`], the same grouping that fits the grain of a
//! mode 7 texture—; what is here is the plumbing: counting the tiles the
//! way the console will, and writing the chosen cells back into the picture
//! before anything else reads it. Nothing else changes: the map's cells keep
//! their passability, because the fusion is only a drawing.
//!
//! A picture that already fits is not touched, not even by a pixel.

use crate::background::grid::{Cell, Grid, CELL};
use rm2k_render::{Layers, Picture};
use std::collections::HashSet;

/// A cell as the hardware can draw it from another: the least of its four
/// orientations, so that two cells that are mirrors of each other count once.
fn canonical(cell: &Cell) -> Cell {
    let mut flipped_x = *cell;
    for line in flipped_x.iter_mut() {
        line.reverse();
    }
    let mut flipped_y = *cell;
    flipped_y.reverse();
    let mut both = flipped_x;
    both.reverse();
    [*cell, flipped_x, flipped_y, both].into_iter().min().unwrap()
}

/// How many tiles a grid costs: its distinct cells, a mirror counting as its
/// original, which is what Voodoo does.
fn spent(grid: &Grid) -> usize {
    grid.cells.iter().map(canonical).collect::<HashSet<_>>().len()
}

fn paint_cell(picture: &mut Picture, x: usize, y: usize, cell: &Cell) {
    for (j, line) in cell.iter().enumerate() {
        for (i, pixel) in line.iter().enumerate() {
            let at = ((y * CELL + j) * picture.width + x * CELL + i) * 4;
            // Five bits back to eight such that the same five come out when
            // they are read again.
            let wide = |c: u8| (c << 3) | (c >> 2);
            let rgba = match pixel {
                Some([r, g, b]) => [wide(*r), wide(*g), wide(*b), 255],
                None => [0, 0, 0, 0],
            };
            picture.rgba[at..at + 4].copy_from_slice(&rgba);
        }
    }
}

/// Draws the lower layer of `layers` with at most `max` tiles, fusing the
/// cells that look most alike, and says how many distinct cells went. The
/// drawings of an animated family follow wherever they were the same cell as
/// the background's; where they were not, they are as they were. Zero, and
/// nothing touched, if it already fits.
pub fn fuse_lower(layers: &mut Layers, max: usize) -> usize {
    let grid = Grid::quantize(&layers.lower);
    let mirrored = spent(&grid);
    if mirrored <= max {
        return 0;
    }
    let mut weights = vec![0.0f32; grid.cells.len()];
    for &n in &grid.at {
        weights[n] += 1.0;
    }
    // The grouping counts cells, and the mirrors make the console need
    // fewer: so it is asked for as many as `max` plus what the mirrors save,
    // and again for fewer until the count the console will make is within
    // `max`.
    let mut ask = max + (grid.cells.len() - mirrored);
    let group = loop {
        let group = adeleine::group_tiles(&grid.cells, &weights, ask.min(grid.cells.len()));
        let kept: HashSet<Cell> = group.iter().map(|&g| canonical(&grid.cells[g])).collect();
        if kept.len() <= max || ask <= 1 {
            break group;
        }
        ask = ask.saturating_sub(kept.len() - max).max(1);
    };
    let before = grid.cells.len();
    let after = group.iter().collect::<HashSet<_>>().len();
    let drawings: Vec<Grid> = layers
        .variants
        .iter()
        .flat_map(|(_, drawings)| drawings.iter().map(Grid::quantize))
        .collect();
    let mut painted = Vec::new();
    for y in 0..grid.rows {
        for x in 0..grid.columns {
            let n = grid.at[y * grid.columns + x];
            if group[n] != n {
                painted.push((x, y, n));
            }
        }
    }
    let mut seen = 0;
    for (_, pictures) in layers.variants.iter_mut() {
        for picture in pictures.iter_mut() {
            for &(x, y, n) in &painted {
                if drawings[seen].cell(x, y) == &grid.cells[n] {
                    paint_cell(picture, x, y, &grid.cells[group[n]]);
                }
            }
            seen += 1;
        }
    }
    for &(x, y, n) in &painted {
        paint_cell(&mut layers.lower, x, y, &grid.cells[group[n]]);
    }
    before - after
}
