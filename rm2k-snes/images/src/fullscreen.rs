//! A picture that fills the screen at 8 bits a pixel: the title's, the
//! Game Over's.
//!
//! It is scaled to the screen —RM2k's 320x240 to the console's, 20%
//! narrower, which the original's aspect ratio costs— with LANCZOS, the
//! filter that smears the edges of the title's text the least; brought to
//! fifteen bits; and down to `cap` colours keeping the most used, black
//! first because it is the PPU's backdrop. Then it is cut into 8x8 cells,
//! each distinct cell once, row by row.

use crate::pixels::{most_used, rgb_to_15_bits, scaled_rgb};
use adeleine::Color;
use rm2k_render::Picture;
use std::collections::HashMap;

/// A tile: 8x8 CGRAM indices, row by row.
pub type Cell = Vec<Vec<usize>>;

pub struct Screen {
    /// The distinct cells, in the order they first appear.
    pub tiles: Vec<Cell>,
    /// The colours, fifteen bits each; they go to CGRAM from `first_color`.
    pub palette: Vec<Color>,
    /// For each cell of the screen, row by row, which tile it is.
    pub tilemap: Vec<usize>,
}

/// `picture` at `width` x `height` —whole cells of `cell` pixels— with
/// `cap` colours, its indices already shifted by `first_color`, so whoever
/// emits them adds nothing.
pub fn convert(
    picture: &Picture,
    width: usize,
    height: usize,
    cell: usize,
    first_color: usize,
    cap: usize,
) -> Screen {
    let pixels = rgb_to_15_bits(&scaled_rgb(picture, width, height));
    let (palette, mapping) = most_used(&pixels, cap);
    let index: HashMap<Color, usize> = palette
        .iter()
        .enumerate()
        .map(|(i, &c)| (c, i + first_color))
        .collect();
    let at = |x: usize, y: usize| index[&mapping[&pixels[y * width + x]]];
    let mut tiles: Vec<Cell> = Vec::new();
    let mut known: HashMap<Cell, usize> = HashMap::new();
    let mut tilemap = Vec::new();
    for ty in 0..height / cell {
        for tx in 0..width / cell {
            let one: Cell = (0..cell)
                .map(|y| {
                    (0..cell)
                        .map(|x| at(tx * cell + x, ty * cell + y))
                        .collect()
                })
                .collect();
            let n = *known.entry(one.clone()).or_insert_with(|| {
                tiles.push(one);
                tiles.len() - 1
            });
            tilemap.push(n);
        }
    }
    Screen {
        tiles,
        palette,
        tilemap,
    }
}
