//! The whole job: a picture in, tiles and palettes and a tilemap out.
//!
//! The three outputs are one decision and have to be made together — which
//! palette a cell gets decides what its indices are, which decides whether it
//! is the same tile as another cell — so there is one function and not three.

use crate::color::{cgram_word, Rgb15};
use crate::fail::{Bad, Result};
use crate::grid::{color_counts, cut_tiles, tile_colors, Grid, Picture, Tile};
use crate::pack::{entry, flips, pack_tile, tile_bytes, to_indices, Indices};
use crate::palette::{
    as_palettes, merge_to, palette_for, reduce_colors, try_pack, COLORS_PER_PALETTE, USABLE_COLORS,
};
use std::collections::{BTreeSet, HashMap};

/// The widest a tilemap entry's tile number goes: ten bits.
pub const MAX_TILE_NUMBER: usize = 0x400;

/// What to ask for. The defaults are in `Options::at`.
#[derive(Clone)]
pub struct Options {
    /// Bits per pixel: 4 or 8.
    pub bpp: usize,
    /// At 4bpp, how many palettes may be used.
    pub palettes: usize,
    /// At 8bpp, how many colours the one palette may hold.
    pub max_colors: usize,
    /// Which colour-memory entry the palette starts at. Index 0 is
    /// transparent, so this is 1 unless something is reserved below.
    pub base: u8,
    /// The palette number written into tilemap entries, at 4bpp.
    pub first_palette: u8,
    /// The priority bit written into every tilemap entry.
    pub priority: u8,
    /// Merge colours when they do not fit, instead of refusing.
    pub merge: bool,
    /// Refuse a picture that needs more distinct tiles than this.
    pub max_tiles: usize,
    /// Keep tile 0 for an all-index-0 cell, whether or not the picture has
    /// one. Whatever a tilemap points at before anybody writes it is tile 0,
    /// so it is usually worth one tile to have that be the empty one.
    pub blank_tile: bool,
}

impl Options {
    pub fn at(bpp: usize) -> Options {
        Options {
            bpp,
            palettes: 8,
            max_colors: 255,
            base: 1,
            first_palette: 0,
            priority: 0,
            merge: false,
            max_tiles: MAX_TILE_NUMBER,
            blank_tile: true,
        }
    }
}

/// What came out, and what it cost.
#[derive(Debug)]
pub struct Report {
    pub columns: usize,
    pub rows: usize,
    pub cells: usize,
    pub colors_before: usize,
    pub colors_used: usize,
    pub merged: usize,
    pub tiles: usize,
    pub palettes: usize,
}

#[derive(Debug)]
pub struct Converted {
    /// The tile data, back to back, `tile_bytes(bpp)` each.
    pub tiles: Vec<u8>,
    /// The palettes, in the order the tilemap's palette numbers count them.
    pub palettes: Vec<Vec<Rgb15>>,
    /// Those palettes as colour-memory words, little endian.
    pub cgram: Vec<u8>,
    /// One entry per cell, row-major.
    pub tilemap: Vec<Vec<u16>>,
    pub report: Report,
}

pub fn convert(picture: &Picture, options: &Options) -> Result<Converted> {
    if options.bpp != 4 && options.bpp != 8 {
        return Err(Bad::usage(format!(
            "{} bits per pixel: only 4 and 8 are planar formats this writes",
            options.bpp
        )));
    }
    if picture.width < 8 || picture.height < 8 {
        return Err(Bad::answer(format!(
            "the picture is {}x{} and a cell is 8x8: there is not one whole cell in it",
            picture.width, picture.height
        )));
    }
    let grid = cut_tiles(picture);
    let before = color_counts(&[&grid]).len();

    let (grid, palettes, merged) = if options.bpp == 4 {
        split_into_palettes(grid, options)?
    } else {
        one_flat_palette(grid, options)?
    };

    let used: usize = if options.bpp == 4 {
        let all: BTreeSet<Rgb15> = palettes.iter().flatten().copied().collect();
        all.len()
    } else {
        palettes.first().map_or(0, |p| p.len())
    };
    let widest = palettes.iter().map(|p| p.len()).max().unwrap_or(0);
    if options.base as usize + widest > 256 {
        return Err(Bad::answer(format!(
            "a palette of {widest} colours starting at colour-memory entry {} runs past \
             entry 255",
            options.base
        )));
    }

    let laid_out = lay_out(&grid, &palettes, options)?;
    let cgram = colour_memory(&palettes, options);

    let report = Report {
        columns: grid.columns,
        rows: grid.height(),
        cells: grid.columns * grid.height(),
        colors_before: before,
        colors_used: used,
        merged,
        tiles: laid_out.count,
        palettes: palettes.len(),
    };
    Ok(Converted {
        tiles: laid_out.tiles,
        palettes,
        cgram,
        tilemap: laid_out.tilemap,
        report,
    })
}

/// 4bpp: spread the colours over palettes of sixteen, merging if asked.
fn split_into_palettes(grid: Grid, options: &Options) -> Result<(Grid, Vec<Vec<Rgb15>>, usize)> {
    let per_palette = COLORS_PER_PALETTE - options.base as usize;
    let sets: BTreeSet<BTreeSet<Rgb15>> = grid
        .cells()
        .map(tile_colors)
        .filter(|s| !s.is_empty())
        .collect();

    if sets.is_empty() {
        return Ok((grid, Vec::new(), 0));
    }
    // The busiest cell first, and separately: a cell with more colours than a
    // palette holds fits nowhere, and no number of palettes changes that.
    // Best-fit has no opinion about such a set —it opens a new group and the
    // group comes out oversized— so if this is not asked here it is not asked
    // at all, and what reaches the packer is indices too wide for the depth.
    let widest = widest_cell(&grid);
    if widest > per_palette && !options.merge {
        return Err(does_not_fit(&grid, options, per_palette));
    }
    if widest <= per_palette {
        if let Some(groups) = try_pack(&sets, options.palettes, per_palette) {
            return Ok((grid, as_palettes(&groups), 0));
        }
    }
    if !options.merge {
        return Err(does_not_fit(&grid, options, per_palette));
    }
    let reduced = reduce_colors(&grid, options.palettes, per_palette)?;
    let merged = reduced.merged.len();
    Ok((reduced.grid, as_palettes(&reduced.groups), merged))
}

/// 8bpp: one palette, and the only limit is how many entries there are.
fn one_flat_palette(grid: Grid, options: &Options) -> Result<(Grid, Vec<Vec<Rgb15>>, usize)> {
    let counts = color_counts(&[&grid]);
    if counts.len() <= options.max_colors {
        return Ok((grid, vec![counts.keys().copied().collect()], 0));
    }
    if !options.merge {
        return Err(Bad::answer(format!(
            "the picture uses {} colours and {} were allowed at 8bpp; pass --merge to \
             give up the {} cheapest of them",
            counts.len(),
            options.max_colors,
            counts.len() - options.max_colors
        )));
    }
    let merge = merge_to(&counts, options.max_colors)?;
    let remapped = Grid {
        columns: grid.columns,
        rows: grid
            .rows
            .iter()
            .map(|row| row.iter().map(|t| merge.tile(t)).collect())
            .collect(),
    };
    let left: BTreeSet<Rgb15> = merge.mapping.values().copied().collect();
    let merged = merge.merged.len();
    Ok((remapped, vec![left.into_iter().collect()], merged))
}

/// Why a picture did not fit, said in terms of the picture and not of the
/// algorithm. There are two different reasons and they used to be reported as
/// one: a single cell with too many colours is not fixed by any number of
/// palettes, while too many colours overall is.
fn does_not_fit(grid: &Grid, options: &Options, per_palette: usize) -> Bad {
    let worst = grid
        .rows
        .iter()
        .enumerate()
        .flat_map(|(y, row)| row.iter().enumerate().map(move |(x, t)| (x, y, t)))
        .map(|(x, y, t)| (tile_colors(t).len(), x, y))
        .max();
    if let Some((count, x, y)) = worst {
        if count > per_palette {
            return Bad::answer(format!(
                "the cell at column {x}, row {y} has {count} colours and a {}bpp palette \
                 holds {per_palette} besides the transparent one; pass --merge to give \
                 up the cheapest of them",
                options.bpp
            ));
        }
    }
    let total: BTreeSet<Rgb15> = grid.cells().flat_map(tile_colors).collect();
    Bad::answer(format!(
        "the {} colours of this picture do not spread over {} palettes of {per_palette}: \
         no cell has more than {} of them, but they cannot be grouped so that every cell \
         uses only one palette; pass --merge, or allow more palettes",
        total.len(),
        options.palettes,
        worst.map_or(0, |w| w.0)
    ))
}

struct LaidOut {
    tiles: Vec<u8>,
    tilemap: Vec<Vec<u16>>,
    count: usize,
}

/// Number the distinct tiles and write the tilemap.
///
/// A cell that is another cell mirrored is not a new tile: the hardware can
/// flip one when it draws it, so the four orientations are tried against what
/// is already there before anything is added.
fn lay_out(grid: &Grid, palettes: &[Vec<Rgb15>], options: &Options) -> Result<LaidOut> {
    let planes = options.bpp;
    let blank: Indices = [[0; 8]; 8];

    let mut pool: HashMap<(usize, Indices), u16> = HashMap::new();
    let mut tiles: Vec<u8> = Vec::new();
    if options.blank_tile {
        pool.insert((0, blank), 0);
        tiles.extend(std::iter::repeat_n(0, tile_bytes(planes)));
    }

    let mut tilemap = Vec::with_capacity(grid.height());
    for (y, row) in grid.rows.iter().enumerate() {
        let mut line = Vec::with_capacity(row.len());
        for (x, tile) in row.iter().enumerate() {
            line.push(place(
                tile, x, y, palettes, options, &mut pool, &mut tiles, planes,
            )?);
        }
        tilemap.push(line);
    }
    Ok(LaidOut {
        count: tiles.len() / tile_bytes(planes),
        tiles,
        tilemap,
    })
}

#[allow(clippy::too_many_arguments)]
fn place(
    tile: &Tile,
    x: usize,
    y: usize,
    palettes: &[Vec<Rgb15>],
    options: &Options,
    pool: &mut HashMap<(usize, Indices), u16>,
    tiles: &mut Vec<u8>,
    planes: usize,
) -> Result<u16> {
    let colors = tile_colors(tile);
    if colors.is_empty() && options.blank_tile {
        return Ok(entry(0, 0, 0, options.priority, options.first_palette));
    }
    let index = match palette_for(&colors, palettes) {
        Some(i) => i,
        None => {
            return Err(Bad::answer(format!(
                "the cell at column {x}, row {y} uses {} colours that no single palette \
                 holds",
                colors.len()
            )))
        }
    };
    let indices = to_indices(tile, &palettes[index], options.base)?;
    // At 8bpp every cell shares the one palette, so a mirrored match is a
    // match whatever palette it was found under; at 4bpp the indices only mean
    // the same thing inside the same palette, which is why it is part of the
    // key.
    let key_palette = if options.bpp == 4 { index } else { 0 };
    let palette_bits = if options.bpp == 4 {
        options.first_palette + index as u8
    } else {
        options.first_palette
    };

    for (oriented, horizontal, vertical) in flips(&indices) {
        if let Some(number) = pool.get(&(key_palette, oriented)) {
            return Ok(entry(
                *number,
                horizontal,
                vertical,
                options.priority,
                palette_bits,
            ));
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
    pool.insert((key_palette, indices), number as u16);
    tiles.extend_from_slice(&pack_tile(&indices, planes));
    Ok(entry(
        number as u16,
        0,
        0,
        options.priority,
        palette_bits,
    ))
}

/// The palettes as the words colour memory holds, little endian.
///
/// At 4bpp each palette is padded to its full sixteen entries, because that is
/// how far apart they sit in colour memory, and entry 0 —which the hardware
/// never draws— is written as a black. At 8bpp there is one run of colours and
/// nothing to pad to: where it lands is `--base`, which is the caller's.
fn colour_memory(palettes: &[Vec<Rgb15>], options: &Options) -> Vec<u8> {
    let mut out = Vec::new();
    if options.bpp == 8 {
        for color in palettes.iter().flatten() {
            out.extend_from_slice(&cgram_word(*color).to_le_bytes());
        }
        return out;
    }
    if palettes.is_empty() {
        // Never nothing: a caller that turns this into a transfer of length
        // zero usually finds out that length zero means "all of it".
        return vec![0; 2 * COLORS_PER_PALETTE];
    }
    for palette in palettes {
        for _ in 0..options.base {
            out.extend_from_slice(&0u16.to_le_bytes());
        }
        for color in palette {
            out.extend_from_slice(&cgram_word(*color).to_le_bytes());
        }
        let written = options.base as usize + palette.len();
        out.extend(std::iter::repeat_n(0, 2 * (COLORS_PER_PALETTE - written)));
    }
    out
}

/// The most colours any one cell uses, which is the number that decides
/// whether a 4bpp packing can exist at all.
pub fn widest_cell(grid: &Grid) -> usize {
    grid.cells().map(|t| tile_colors(t).len()).max().unwrap_or(0)
}

/// How many colours a palette holds at a depth, transparent index excluded.
pub fn fits_per_palette(bpp: usize) -> usize {
    match bpp {
        4 => USABLE_COLORS,
        _ => 255,
    }
}
