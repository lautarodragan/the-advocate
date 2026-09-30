//! Cutting a drawn screen into the 8x8 cells the console shows: the
//! colours at fifteen bits, the palettes they go in, and a tile bank that
//! several screens share.
//!
//! **A screen is drawn first, whole, and cut after**: every text and every
//! window goes onto a transparent 256x224 picture, and what the console
//! gets are its cells. It is slower than composing tiles directly, and it
//! is what makes the letters land exactly where RM2k puts them.

use crate::fail::{Bad, Result};
use rm2k_render::picture::Picture;
use std::collections::HashMap;
use voodoo::pack::Indices;

/// The console's screen, in pixels and in 8x8 cells.
pub const CELL: usize = 8;
pub const WIDTH: usize = 256;
pub const HEIGHT: usize = 224;
pub const COLS: usize = WIDTH / CELL;
pub const ROWS: usize = HEIGHT / CELL;

/// A colour at the console's fifteen bits: five per channel.
pub type Color = [u8; 3];

pub const BLACK: Color = [0, 0, 0];

/// The empty cell: index 0 everywhere, which is transparent.
pub const EMPTY: Indices = [[0; CELL]; CELL];

/// A pixel's colour at fifteen bits: each channel's high five bits.
pub fn rgb15(pixel: [u8; 4]) -> Color {
    [pixel[0] >> 3, pixel[1] >> 3, pixel[2] >> 3]
}

/// A transparent picture the size of the screen, to draw a layer on.
pub fn layer() -> Picture {
    Picture::transparent(WIDTH, HEIGHT)
}

/// Pastes `src` at `(x, y)` of `dest` through its alpha: a window, a
/// cursor, over what is there.
pub fn paste(dest: &mut Picture, src: &Picture, x: i64, y: i64) {
    dest.blit(x, y, src, 0, 0, src.width as i64, src.height as i64);
}

/// How many pixels of each colour, in the order the colours were first
/// seen.
#[derive(Debug, Clone, Default)]
pub struct Counts {
    order: Vec<Color>,
    count: HashMap<Color, u64>,
}

impl Counts {
    pub fn add(&mut self, color: Color, n: u64) {
        let entry = self.count.entry(color).or_insert_with(|| {
            self.order.push(color);
            0
        });
        *entry += n;
    }

    /// Every opaque pixel of `picture` —alpha not zero—, at fifteen bits.
    pub fn add_picture(&mut self, picture: &Picture) {
        for p in picture.rgba.chunks_exact(4) {
            if p[3] != 0 {
                self.add(rgb15([p[0], p[1], p[2], p[3]]), 1);
            }
        }
    }

    pub fn len(&self) -> usize {
        self.order.len()
    }

    pub fn is_empty(&self) -> bool {
        self.order.is_empty()
    }

    pub fn get(&self, color: &Color) -> u64 {
        self.count.get(color).copied().unwrap_or(0)
    }

    pub fn contains(&self, color: &Color) -> bool {
        self.count.contains_key(color)
    }

    /// The colours with their counts, in the order they were first seen.
    pub fn in_order(&self) -> Vec<(Color, u64)> {
        self.order.iter().map(|c| (*c, self.count[c])).collect()
    }

    /// The colours, the most used first, and by colour on a tie: the order
    /// palettes are made in.
    pub fn by_use(&self) -> Vec<Color> {
        let mut colors = self.order.clone();
        colors.sort_by(|a, b| self.count[b].cmp(&self.count[a]).then(a.cmp(b)));
        colors
    }
}

/// From a colour to its index in `palette`. A colour that is in the list
/// twice gets **the later** index: black goes first, as the transparent
/// one, and if the drawing also uses it, that one is its index.
pub fn index_of(palette: &[Color]) -> HashMap<Color, u8> {
    let mut out = HashMap::new();
    for (i, c) in palette.iter().enumerate() {
        out.insert(*c, i as u8);
    }
    out
}

/// A bank of tiles several blocks of cells index: the empty one first, and
/// each new one after. A tile is known by its indices, not its colours, so
/// the same drawing in two palettes is one tile.
#[derive(Debug, Clone)]
pub struct Bank {
    pub tiles: Vec<Indices>,
    offset: HashMap<Indices, usize>,
}

impl Default for Bank {
    fn default() -> Self {
        Bank {
            tiles: vec![EMPTY],
            offset: HashMap::from([(EMPTY, 0)]),
        }
    }
}

impl Bank {
    /// The tile's number, adding it if it is new.
    pub fn add(&mut self, cell: Indices) -> usize {
        if let Some(&at) = self.offset.get(&cell) {
            return at;
        }
        self.tiles.push(cell);
        self.offset.insert(cell, self.tiles.len() - 1);
        self.tiles.len() - 1
    }

    /// The tile's number and the tilemap's flip bits, trying it as it is
    /// and mirrored —across x, across y, both— before adding it.
    pub fn add_mirrored(&mut self, cell: Indices) -> (usize, u16) {
        for (shape, h, v) in voodoo::pack::flips(&cell) {
            if let Some(&at) = self.offset.get(&shape) {
                return (at, (h as u16) << 14 | (v as u16) << 15);
            }
        }
        (self.add(cell), 0)
    }

    pub fn len(&self) -> usize {
        self.tiles.len()
    }

    pub fn is_empty(&self) -> bool {
        self.tiles.is_empty()
    }
}

/// The 8x8 cell at cell `(col, row)` of `layer` as indices: `index` of each
/// opaque pixel's colour, and 0 for a transparent one or one past the
/// screen. A colour `index` does not have is an error and not a similar
/// colour, so that an extra colour gets noticed.
pub fn cut(layer: &Picture, col: usize, row: usize, index: &HashMap<Color, u8>) -> Result<Indices> {
    let mut cell = EMPTY;
    for (y, line) in cell.iter_mut().enumerate() {
        for (x, value) in line.iter_mut().enumerate() {
            let (sx, sy) = (col * CELL + x, row * CELL + y);
            if sy >= HEIGHT || sx >= WIDTH || sx >= layer.width || sy >= layer.height {
                continue;
            }
            let p = layer.get(sx as i64, sy as i64);
            if p[3] != 0 {
                let color = rgb15(p);
                *value = *index.get(&color).ok_or_else(|| {
                    Bad::answer(format!(
                        "the colour {color:?} at ({sx}, {sy}) is in no palette of this screen"
                    ))
                })?;
            }
        }
    }
    Ok(cell)
}

/// The cells of a rectangle of `layer` —`rows` from `row0`, `cols` from
/// `col0`— as tilemap words, row by row, adding new tiles to `bank`: the
/// tile's number with `palette` in the three bits above it.
#[allow(clippy::too_many_arguments)]
pub fn cell_block(
    layer: &Picture,
    row0: usize,
    rows: usize,
    bank: &mut Bank,
    index: &HashMap<Color, u8>,
    col0: usize,
    cols: usize,
    palette: u16,
) -> Result<Vec<u16>> {
    let mut out = Vec::with_capacity(rows * cols);
    for row in 0..rows {
        for col in col0..col0 + cols {
            let cell = cut(layer, col, row0 + row, index)?;
            out.push(bank.add(cell) as u16 | palette << 10);
        }
    }
    Ok(out)
}
