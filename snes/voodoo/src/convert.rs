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

use crate::color::{cgram_word, Rgb15};
use crate::fail::{Bad, Result};
use crate::grid::{cut_cells, Cell, Grid, Picture, CELL};
use crate::pack::{entry, flips, pack_tile, Indices};
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
    /// Bits per pixel: 2, 4 or 8.
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
    /// At 2 and 4bpp, the palettes the cells use; at 8bpp, 1 if anything is
    /// drawn.
    pub palettes: usize,
    /// Colour-memory entries some pixel draws with.
    pub colors: usize,
}

/// Where an animation's tiles landed, and what they hold in every frame.
#[derive(Debug)]
pub struct Animation {
    /// The first tile of its run. Zero tiles when no cell animates with it.
    pub first: usize,
    pub count: usize,
    /// One entry per frame, the base picture first: the run's tiles as they
    /// are in that frame, back to back. Stepping the animation is uploading
    /// one of these over the run.
    pub frames: Vec<Vec<u8>>,
}

#[derive(Debug)]
pub struct Converted {
    /// The tile data, back to back, `tile_bytes(bpp)` each, as the base
    /// picture draws them.
    pub tiles: Vec<u8>,
    /// All of colour memory as little-endian words, from the picture's
    /// palette: entries it has no colour for are zero.
    pub cgram: Vec<u8>,
    /// One entry per cell, row-major.
    pub tilemap: Vec<Vec<u16>>,
    /// One per animation, in the order they were given.
    pub animations: Vec<Animation>,
    pub report: Report,
}

/// Whether an index draws nothing. At 2 and 4bpp that is the first entry of
/// every palette, because the hardware counts the index inside its own four
/// or sixteen; at 8bpp it is entry 0 alone.
pub fn transparent(index: u8, bpp: usize) -> bool {
    if bpp < 8 {
        (index as usize).is_multiple_of(palette_size(bpp))
    } else {
        index == 0
    }
}

/// The entries a palette holds at a depth with palettes: four at 2bpp,
/// sixteen at 4bpp. At 2bpp a tilemap entry's three palette bits name the
/// first 32 entries of colour memory, four by four.
pub fn palette_size(bpp: usize) -> usize {
    1 << bpp
}

/// A picture, and its animations: each one is the frames **other than** the
/// base picture, which is every animation's first frame.
///
/// A cell animates with an animation if some frame of it differs from the base
/// there, and then its tile is its own: animating is overwriting the tile data
/// without touching the tilemap, so a tile shared with a still cell would make
/// that cell move too. Those tiles go last, one contiguous run per animation,
/// so that a step of the animation is one upload.
pub fn convert(
    picture: &Picture,
    animations: &[Vec<Picture>],
    options: &Options,
) -> Result<Converted> {
    if ![2, 4, 8].contains(&options.bpp) {
        return Err(Bad::usage(format!(
            "{} bits per pixel: only 2, 4 and 8 are planar formats this writes",
            options.bpp
        )));
    }
    if picture.width < CELL || picture.height < CELL {
        return Err(Bad::answer(format!(
            "the picture is {}x{} and a cell is 8x8: there is not one whole cell in it",
            picture.width, picture.height
        )));
    }
    for (a, frames) in animations.iter().enumerate() {
        for (f, frame) in frames.iter().enumerate() {
            if (frame.width, frame.height) != (picture.width, picture.height) {
                return Err(Bad::usage(format!(
                    "frame {} of animation {a} is {}x{} and the picture is {}x{}",
                    f + 1,
                    frame.width,
                    frame.height,
                    picture.width,
                    picture.height
                )));
            }
        }
    }
    let base = cut_cells(picture);
    let groups: Vec<Vec<Grid>> = animations
        .iter()
        .map(|frames| frames.iter().map(cut_cells).collect())
        .collect();

    let everything: Vec<&Picture> = std::iter::once(picture)
        .chain(animations.iter().flatten())
        .collect();
    let colors = shared_colors(&everything, options.bpp)?;
    let mut drawn = drawn_entries(&base, options.bpp);
    for grid in groups.iter().flatten() {
        drawn.extend(drawn_entries(grid, options.bpp));
    }

    let laid_out = lay_out(&base, &groups, options)?;

    let mut cgram = Vec::with_capacity(2 * colors.len());
    for color in &colors {
        cgram.extend_from_slice(&cgram_word(color.unwrap_or((0, 0, 0))).to_le_bytes());
    }
    let report = Report {
        columns: base.columns,
        rows: base.height(),
        cells: base.columns * base.height(),
        tiles: laid_out.count,
        palettes: laid_out.palettes.len(),
        colors: drawn.len(),
    };
    Ok(Converted {
        tiles: laid_out.tiles,
        cgram,
        tilemap: laid_out.tilemap,
        animations: laid_out.animations,
        report,
    })
}

/// Colour memory, from pictures that each carry a copy of it.
///
/// The copies are allowed to differ only where nobody draws: an entry some
/// picture draws with has to hold the same colour in every picture that draws
/// with it, or the pictures cannot be shown together. Where nobody draws, the
/// first picture's copy is kept.
fn shared_colors(pictures: &[&Picture], bpp: usize) -> Result<Vec<Option<Rgb15>>> {
    let mut colors = pictures[0].colors.clone();
    let mut owner: Vec<Option<usize>> = vec![None; colors.len()];
    for (p, picture) in pictures.iter().enumerate() {
        for entry in drawn_entries(&cut_cells(picture), bpp) {
            let e = entry as usize;
            let Some(color) = picture.colors[e] else {
                return Err(Bad::answer(format!(
                    "{} draws with colour-memory entry {e}, and its palette has no colour \
                     for it",
                    which(p)
                )));
            };
            match owner[e] {
                None => {
                    owner[e] = Some(p);
                    colors[e] = Some(color);
                }
                Some(first) if colors[e] != Some(color) => {
                    return Err(Bad::answer(format!(
                        "colour-memory entry {e} is {:?} in {} and {:?} in {}, and both draw \
                         with it: pictures shown together have to agree",
                        colors[e].unwrap(),
                        which(first),
                        color,
                        which(p)
                    )));
                }
                Some(_) => {}
            }
        }
    }
    Ok(colors)
}

/// How a message names a picture: by its place in the order it was given.
fn which(index: usize) -> String {
    match index {
        0 => "the picture".to_string(),
        n => format!("frame picture {n}"),
    }
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
    animations: Vec<Animation>,
}

/// Which animation a cell moves with, or `None` if it is still.
///
/// A cell that moved with two would need every combination of their frames,
/// not two runs, so it is refused rather than written half right.
fn class_of(base: &Grid, groups: &[Vec<Grid>], x: usize, y: usize) -> Result<Option<usize>> {
    let moving: Vec<usize> = groups
        .iter()
        .enumerate()
        .filter(|(_, frames)| frames.iter().any(|g| g.rows[y][x] != base.rows[y][x]))
        .map(|(a, _)| a)
        .collect();
    match moving.as_slice() {
        [] => Ok(None),
        [one] => Ok(Some(*one)),
        [a, b, ..] => Err(Bad::answer(format!(
            "the cell at column {x}, row {y} moves with animations {a} and {b}, and a \
             tile can only be overwritten by one"
        ))),
    }
}

/// Number the distinct tiles and write the tilemap.
///
/// A cell that is another cell mirrored is not a new tile: the hardware can
/// flip one when it draws it, so the four orientations are tried against what
/// is already there before anything is added. For a cell that animates, a
/// match has to hold in every frame at once — the hardware flips the tile, not
/// each frame on its own — so the key is all of its frames.
///
/// Still cells are numbered first, then each animation's cells, each class in
/// the order its first cell is met, row-major.
fn lay_out(base: &Grid, groups: &[Vec<Grid>], options: &Options) -> Result<LaidOut> {
    let planes = options.bpp;
    let blank: Indices = [[0; CELL]; CELL];

    let mut classes = Vec::with_capacity(base.height());
    for y in 0..base.height() {
        let mut line = Vec::with_capacity(base.columns);
        for x in 0..base.columns {
            line.push(class_of(base, groups, x, y)?);
        }
        classes.push(line);
    }

    let mut tilemap = vec![vec![0u16; base.columns]; base.height()];
    // Every tile's indices in every frame of its class, by tile number.
    let mut numbered: Vec<Vec<Indices>> = Vec::new();
    if options.blank_tile {
        numbered.push(vec![blank]);
    }
    let mut palettes = BTreeSet::new();
    let mut animations = Vec::new();

    let order = std::iter::once(None).chain((0..groups.len()).map(Some));
    for class in order {
        let mut pool: HashMap<(usize, Vec<Indices>), u16> = HashMap::new();
        if class.is_none() && options.blank_tile {
            pool.insert((0, vec![blank]), 0);
        }
        let first = numbered.len();
        for y in 0..base.height() {
            for x in 0..base.columns {
                if classes[y][x] != class {
                    continue;
                }
                let mut cells = vec![&base.rows[y][x]];
                if let Some(a) = class {
                    cells.extend(groups[a].iter().map(|g| &g.rows[y][x]));
                }
                let draws = cells
                    .iter()
                    .any(|c| c.iter().flatten().any(|&i| !transparent(i, planes)));
                if class.is_none() && !draws && options.blank_tile {
                    // A still cell that draws nothing: its priority and
                    // palette say nothing either, and 0 is what an unwritten
                    // tilemap holds.
                    continue;
                }
                let palette = if planes < 8 {
                    palette_of_cells(&cells, x, y, planes)?.unwrap_or(0)
                } else {
                    0
                };
                if draws {
                    palettes.insert(palette);
                }
                let frames: Vec<Indices> = cells
                    .iter()
                    .map(|c| {
                        let mut indices: Indices = **c;
                        if planes < 8 {
                            for value in indices.iter_mut().flatten() {
                                *value %= palette_size(planes) as u8;
                            }
                        }
                        indices
                    })
                    .collect();
                tilemap[y][x] = place(&frames, palette, options, &mut pool, &mut numbered)?;
            }
        }
        if let Some(a) = class {
            let count = numbered.len() - first;
            let frames = (0..=groups[a].len())
                .map(|f| {
                    numbered[first..]
                        .iter()
                        .flat_map(|t| pack_tile(&t[f], planes))
                        .collect()
                })
                .collect();
            animations.push(Animation {
                first: if count == 0 { 0 } else { first },
                count,
                frames,
            });
        }
    }

    let tiles = numbered
        .iter()
        .flat_map(|t| pack_tile(&t[0], planes))
        .collect();
    Ok(LaidOut {
        count: numbered.len(),
        tiles,
        tilemap,
        palettes,
        animations,
    })
}

/// Which palette a 2 or 4bpp cell draws with in all its frames, or `None` if
/// it draws nothing.
///
/// A cell drawing with two is not something a tilemap can say: it names one
/// palette per cell, for every frame. Whoever wrote the picture promised that,
/// so breaking it is their mistake, and the message says where.
fn palette_of_cells(cells: &[&Cell], x: usize, y: usize, bpp: usize) -> Result<Option<usize>> {
    let used: BTreeSet<usize> = cells
        .iter()
        .flat_map(|c| c.iter().flatten())
        .filter(|&&i| !transparent(i, bpp))
        .map(|&i| i as usize / palette_size(bpp))
        .collect();
    let mut found = used.iter();
    let Some(&palette) = found.next() else {
        return Ok(None);
    };
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
    frames: &[Indices],
    palette: usize,
    options: &Options,
    pool: &mut HashMap<(usize, Vec<Indices>), u16>,
    numbered: &mut Vec<Vec<Indices>>,
) -> Result<u16> {
    let flipped: Vec<[(Indices, u8, u8); 4]> = frames.iter().map(flips).collect();
    for k in 0..4 {
        let key: Vec<Indices> = flipped.iter().map(|f| f[k].0).collect();
        if let Some(number) = pool.get(&(palette, key)) {
            let (_, horizontal, vertical) = flipped[0][k];
            return Ok(entry(
                *number,
                horizontal,
                vertical,
                options.priority,
                palette as u8,
            ));
        }
    }
    let number = numbered.len();
    if number >= options.max_tiles || number >= MAX_TILE_NUMBER {
        return Err(Bad::answer(format!(
            "the picture needs more than {} distinct tiles; a tilemap entry has ten bits \
             for the tile number",
            options.max_tiles.min(MAX_TILE_NUMBER)
        )));
    }
    pool.insert((palette, frames.to_vec()), number as u16);
    numbered.push(frames.to_vec());
    Ok(entry(number as u16, 0, 0, options.priority, palette as u8))
}
