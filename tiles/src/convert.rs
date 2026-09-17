//! The whole job: an indexed picture in, tiles and a tilemap and colour memory
//! out.
//!
//! **Nothing here decides anything a viewer could see.** Which colours a
//! picture keeps and which palette each cell uses were settled before the
//! picture was written: its indices are colour-memory entries. What is left is
//! bookkeeping that changes bytes and never pixels — cutting the cells,
//! numbering the distinct ones, reusing a mirrored one — so the same picture
//! always comes back out of `render` exactly as it went in.
//!
//! A picture that breaks the format is refused, never repaired: repairing it
//! would be choosing what to lose, and that choice belongs to whoever made the
//! picture.

use crate::color::cgram_word;
use crate::fail::{Bad, Result};
use crate::grid::{cut_cells, Cell, Grid, Picture, CELL};
use crate::pack::{entry, flips, pack_tile, tile_bytes, Indices};
use std::collections::{BTreeSet, HashMap};

/// The widest a tilemap entry's tile number goes: ten bits.
pub const MAX_TILE_NUMBER: usize = 0x400;

/// Colours in a palette at 4bpp, the transparent entry included.
pub const COLORS_PER_PALETTE: usize = 16;

/// Palettes a tilemap entry can name: three bits.
pub const TILEMAP_PALETTES: usize = 8;

/// What to ask for. The defaults are in `Options::at`.
#[derive(Clone)]
pub struct Options {
    /// Bits per pixel: 4 or 8.
    pub bpp: usize,
    /// The priority bit written into every tilemap entry that draws something.
    pub priority: u8,
    /// Refuse a picture that needs more distinct tiles than this.
    pub max_tiles: usize,
    /// Keep tile 0 for the empty cell, whether or not the picture has one.
    /// Whatever a tilemap points at before anybody writes it is tile 0, so it
    /// is usually worth one tile to have that be the empty one.
    pub blank_tile: bool,
}

impl Options {
    pub fn at(bpp: usize) -> Options {
        Options {
            bpp,
            priority: 0,
            max_tiles: MAX_TILE_NUMBER,
            blank_tile: true,
        }
    }
}

/// What came out.
#[derive(Debug)]
pub struct Report {
    pub columns: usize,
    pub rows: usize,
    pub cells: usize,
    pub tiles: usize,
    /// At 4bpp, the palettes the cells use; at 8bpp, 1 if anything is drawn.
    pub palettes: usize,
    /// Colour-memory entries some pixel draws with.
    pub colors: usize,
}

#[derive(Debug)]
pub struct Converted {
    /// The tile data, back to back, `tile_bytes(bpp)` each.
    pub tiles: Vec<u8>,
    /// All of colour memory as little-endian words, from the picture's
    /// palette: entries it has no colour for are zero.
    pub cgram: Vec<u8>,
    /// One entry per cell, row-major.
    pub tilemap: Vec<Vec<u16>>,
    pub report: Report,
}

/// Whether an index draws nothing. At 4bpp that is the first entry of every
/// palette, because the hardware counts a 4-bit index inside its own sixteen;
/// at 8bpp it is entry 0 alone.
pub fn transparent(index: u8, bpp: usize) -> bool {
    if bpp == 4 {
        index as usize % COLORS_PER_PALETTE == 0
    } else {
        index == 0
    }
}

pub fn convert(picture: &Picture, options: &Options) -> Result<Converted> {
    if options.bpp != 4 && options.bpp != 8 {
        return Err(Bad::usage(format!(
            "{} bits per pixel: only 4 and 8 are planar formats this writes",
            options.bpp
        )));
    }
    if picture.width < CELL || picture.height < CELL {
        return Err(Bad::answer(format!(
            "the picture is {}x{} and a cell is 8x8: there is not one whole cell in it",
            picture.width, picture.height
        )));
    }
    let grid = cut_cells(picture);
    let drawn = drawn_entries(&grid, options.bpp);
    if let Some(&missing) = drawn.iter().find(|&&e| picture.colors[e as usize].is_none()) {
        return Err(Bad::answer(format!(
            "some pixel draws with colour-memory entry {missing}, and the picture's \
             palette has no colour for it"
        )));
    }
    let laid_out = lay_out(&grid, options)?;

    let mut cgram = Vec::with_capacity(2 * picture.colors.len());
    for color in &picture.colors {
        cgram.extend_from_slice(&cgram_word(color.unwrap_or((0, 0, 0))).to_le_bytes());
    }
    let report = Report {
        columns: grid.columns,
        rows: grid.height(),
        cells: grid.columns * grid.height(),
        tiles: laid_out.count,
        palettes: laid_out.palettes.len(),
        colors: drawn.len(),
    };
    Ok(Converted {
        tiles: laid_out.tiles,
        cgram,
        tilemap: laid_out.tilemap,
        report,
    })
}

/// The entries some pixel draws with.
fn drawn_entries(grid: &Grid, bpp: usize) -> BTreeSet<u8> {
    grid.cells()
        .flatten()
        .flatten()
        .copied()
        .filter(|&i| !transparent(i, bpp))
        .collect()
}

struct LaidOut {
    tiles: Vec<u8>,
    tilemap: Vec<Vec<u16>>,
    count: usize,
    palettes: BTreeSet<usize>,
}

/// Number the distinct tiles and write the tilemap.
///
/// A cell that is another cell mirrored is not a new tile: the hardware can
/// flip one when it draws it, so the four orientations are tried against what
/// is already there before anything is added. Tiles are numbered in the order
/// their first cell is met, row-major.
fn lay_out(grid: &Grid, options: &Options) -> Result<LaidOut> {
    let planes = options.bpp;
    let blank: Indices = [[0; CELL]; CELL];

    let mut pool: HashMap<(usize, Indices), u16> = HashMap::new();
    let mut tiles: Vec<u8> = Vec::new();
    if options.blank_tile {
        pool.insert((0, blank), 0);
        tiles.extend(std::iter::repeat_n(0, tile_bytes(planes)));
    }
    let mut palettes = BTreeSet::new();

    let mut tilemap = Vec::with_capacity(grid.height());
    for (y, row) in grid.rows.iter().enumerate() {
        let mut line = Vec::with_capacity(row.len());
        for (x, cell) in row.iter().enumerate() {
            line.push(place(cell, x, y, options, &mut pool, &mut tiles, &mut palettes)?);
        }
        tilemap.push(line);
    }
    Ok(LaidOut {
        count: tiles.len() / tile_bytes(planes),
        tiles,
        tilemap,
        palettes,
    })
}

/// Which palette a 4bpp cell draws with, or `None` if it draws nothing.
///
/// A cell drawing with two is not something a tilemap can say: it names one
/// palette per cell. Whoever wrote the picture promised that, so breaking it
/// is their mistake, and the message says where.
fn palette_of_cell(cell: &Cell, x: usize, y: usize) -> Result<Option<usize>> {
    let used: BTreeSet<usize> = cell
        .iter()
        .flatten()
        .filter(|&&i| !transparent(i, 4))
        .map(|&i| i as usize / COLORS_PER_PALETTE)
        .collect();
    let mut found = used.iter();
    let Some(&palette) = found.next() else { return Ok(None) };
    if let Some(&other) = found.next() {
        return Err(Bad::answer(format!(
            "the cell at column {x}, row {y} draws with palettes {palette} and {other}, \
             and a tilemap entry names one palette per cell"
        )));
    }
    if palette >= TILEMAP_PALETTES {
        return Err(Bad::answer(format!(
            "the cell at column {x}, row {y} draws with palette {palette}, and a tilemap \
             entry has three bits for it"
        )));
    }
    Ok(Some(palette))
}

fn place(
    cell: &Cell,
    x: usize,
    y: usize,
    options: &Options,
    pool: &mut HashMap<(usize, Indices), u16>,
    tiles: &mut Vec<u8>,
    palettes: &mut BTreeSet<usize>,
) -> Result<u16> {
    let planes = options.bpp;
    let draws = cell.iter().flatten().any(|&i| !transparent(i, planes));
    if !draws && options.blank_tile {
        // A cell that draws nothing: its priority and palette say nothing
        // either, and 0 is what an unwritten tilemap holds.
        return Ok(0);
    }
    // At 8bpp the index already reaches all of colour memory, so there is one
    // palette and a mirrored match is a match wherever it was found. At 4bpp
    // the indices only mean the same thing inside the same palette, which is
    // why the palette is part of the key.
    let (palette, indices) = if planes == 4 {
        let palette = palette_of_cell(cell, x, y)?.unwrap_or(0);
        let mut indices: Indices = [[0; CELL]; CELL];
        for (row, source) in indices.iter_mut().zip(cell) {
            for (value, &index) in row.iter_mut().zip(source) {
                *value = index % COLORS_PER_PALETTE as u8;
            }
        }
        (palette, indices)
    } else {
        (0, *cell)
    };
    if draws {
        palettes.insert(palette);
    }

    for (oriented, horizontal, vertical) in flips(&indices) {
        if let Some(number) = pool.get(&(palette, oriented)) {
            return Ok(entry(*number, horizontal, vertical, options.priority, palette as u8));
        }
    }
    let number = tiles.len() / tile_bytes(planes);
    if number >= options.max_tiles || number >= MAX_TILE_NUMBER {
        return Err(Bad::answer(format!(
            "the picture needs more than {} distinct tiles; a tilemap entry has ten bits \
             for the tile number",
            options.max_tiles.min(MAX_TILE_NUMBER)
        )));
    }
    pool.insert((palette, indices), number as u16);
    tiles.extend_from_slice(&pack_tile(&indices, planes));
    Ok(entry(number as u16, 0, 0, options.priority, palette as u8))
}
