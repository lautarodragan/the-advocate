//! A map's panorama —RM2k's parallax background— as a tile layer of its own.
//!
//! Mode 3 has two background layers and the map takes both, so a panorama
//! goes one of two ways, and which one is the map's to say, not this
//! module's:
//!
//! * **in mode 3, in BG2, at 4 bits**, where the layer above the hero would
//!   go: only a map that draws nothing above the hero. Its palettes are the
//!   ones the 8-bit background leaves, as the layer above's would be;
//! * **in mode 1, in BG3, at 2 bits**, behind everything: the map keeps its
//!   two layers, at 4 bits each. A 2-bit palette is three colours, and BG3
//!   names the first 32 entries of colour memory: palettes 0 to 3 fall on
//!   the message window's, so the panorama gets 4 to 7, entries 16 to 31.
//!   The colour it draws most goes to entry 0, the screen's backdrop, which
//!   shows wherever no layer draws: that is a fourth colour in every cell.
//!
//! Either way the panorama has far more distinct cells than video memory
//! holds next to a map —a 640x320 one with grain, well over a thousand—,
//! so they are grouped into as many as fit: Adeleine's `group_tiles`.

use crate::background::fail::{Bad, Result};
use crate::background::grid::{colors, counts, Cell, Grid, CELL};
use crate::background::layers::{memory, paint, COLORS_PER_PALETTE, MAX_TILES};
use crate::background::Merge;
use adeleine::Color;
use std::collections::{BTreeSet, HashMap};
use voodoo::{Options, Picture};

/// The first BG3 palette the panorama takes in mode 1: 0 to 3 are the
/// message window's entries.
pub const MODE1_FIRST_PALETTE: usize = 4;
/// BG3 palettes the panorama can take: 4 to 7.
pub const MODE1_PALETTES: usize = 4;
/// Colours in a 2-bit palette, the transparent one left out.
pub const MODE1_COLORS: usize = 3;
/// Entries in a 2-bit palette.
const MODE1_ENTRIES: usize = 4;

/// `adeleine::reduce_colors`, for grids: groups their places by colour and
/// chooses a palette for each group. Answers the remapped grids, the palettes
/// and the palette-local changes.
pub(crate) fn reduce(
    grids: &[&Grid],
    limit: usize,
    per: usize,
) -> Result<(Vec<Grid>, Vec<Vec<Color>>, Vec<Merge>)> {
    let totals = counts(grids);
    let tiles: Vec<BTreeSet<Color>> = grids
        .iter()
        .flat_map(|g| g.at.iter().map(|&i| colors(&g.cells[i])))
        .collect();
    let reduced = adeleine::reduce_colors(&totals, &tiles, limit, per)?;
    let mappings: Vec<HashMap<Color, Color>> = tiles
        .iter()
        .zip(&reduced.tiles)
        .map(|(tile, decided)| {
            tile.iter()
                .copied()
                .zip(decided.mapping.iter().copied())
                .collect()
        })
        .collect();
    let mut at = 0;
    let mapped = grids
        .iter()
        .map(|grid| {
            let end = at + grid.at.len();
            let out = grid.remap_places(&mappings[at..end]);
            at = end;
            out
        })
        .collect();
    Ok((
        mapped,
        reduced
            .palettes
            .into_iter()
            .map(|g| g.into_iter().collect())
            .collect(),
        reduced.merges.into_iter().map(Merge::from).collect(),
    ))
}

/// How a map shows its panorama, which the map and the panorama decide
/// alone —see `convert` in `layers.rs`, at the crate's top—:
///
/// * **hidden**: the layer behind the hero covers it everywhere, so it is
///   never seen and nothing is spent on it;
/// * **baked**: it does not move against the map —a map of one RM2k
///   screen, which RM2k's camera never scrolls, and a panorama that does
///   not scroll on its own—, so it is drawn into the background as the
///   converter reads it, with no layer of its own;
/// * **mode 3**: the panorama in BG2 at 4 bits, where the layer above the
///   hero would be: a map that draws nothing above him;
/// * **flattened**: the same, for a map that does draw above the hero: what
///   it draws there goes into the background, and the 8x8 cells it covers
///   at least half of go to BG1's priority 1, in front of the hero;
/// * **mode 1**: the map at 4 bits in BG1 and BG2 and the panorama at 2 in
///   BG3: for a map that would put much on the wrong side of the hero
///   flattened —see `ABOVE_LOST_MAX` in `layers.rs`—;
/// * **painted**: the panorama is the map —fixed to it, and the ChipSet
///   draws nothing—, and the whole map goes in BG1 at 4 bits, a tile per
///   cell, which the console uploads as they come into view: see
///   [`crate::background::painted`]. Only if the project asks for it;
/// * **black**: it fits none of those, and the map is black where it would
///   show, as before there were panoramas.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Way {
    Hidden,
    Baked,
    Mode3,
    Flattened,
    Mode1,
    Painted,
    Black,
}

impl Way {
    /// The name the request and the answer give it.
    pub fn name(self) -> &'static str {
        match self {
            Way::Hidden => "hidden",
            Way::Baked => "baked",
            Way::Mode3 => "mode3",
            Way::Flattened => "flattened",
            Way::Mode1 => "mode1",
            Way::Painted => "painted",
            Way::Black => "black",
        }
    }

    pub fn from_name(name: &str) -> Option<Way> {
        [
            Way::Hidden,
            Way::Baked,
            Way::Mode3,
            Way::Flattened,
            Way::Mode1,
            Way::Painted,
            Way::Black,
        ]
        .into_iter()
        .find(|w| w.name() == name)
    }
}

/// How a map shows its panorama, once the way says it gets a layer.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    /// Mode 3, the panorama in BG2 at 4 bits.
    Three,
    /// Mode 1, the panorama in BG3 at 2 bits.
    One,
    /// Mode 1, the panorama is the map, in BG1 at 4 bits: a painted map.
    Painted,
}

impl Mode {
    /// The BGMODE value.
    pub fn number(self) -> u8 {
        match self {
            Mode::Three => 3,
            Mode::One => 1,
            // Not BGMODE: the number the layouts and the `.inc` know it by.
            Mode::Painted => 4,
        }
    }
}

/// The panorama, converted.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Panorama {
    pub mode: Mode,
    /// Its tiles, at 4 or 2 bits, tile 0 blank.
    pub tiles: Vec<u8>,
    /// One entry per cell of the converted stretch, rows of columns. The
    /// tile numbers count from the layer's base and from 0: where they land
    /// is the VRAM layout's.
    pub tilemap: Vec<Vec<u16>>,
    /// The colour-memory entry its colours start at, and its words.
    pub first: usize,
    pub cgram: Vec<u16>,
    /// In mode 1, the colour that goes to the screen's backdrop.
    pub backdrop: Option<u16>,
    /// How many distinct tiles it had, with flips, before grouping; how many
    /// colours, and how many it kept.
    pub distinct: usize,
    pub colors: usize,
    pub kept: usize,
    pub merges: Vec<Merge>,
    /// The other pictures a `ChangePBG` names, converted the same way and
    /// in the same tiles of VRAM, in the order they were asked for: each
    /// one, or why it could not be. In mode 3 they all start at the same
    /// colour-memory entry, the first of the most palettes any of them
    /// takes, so that swapping them is swapping their words; in mode 1
    /// they are BG3's palettes 4 to 7, as this one.
    pub extras: Vec<std::result::Result<Panorama, String>>,
}

impl Panorama {
    /// Its words with as many empty ones in front as take it back to
    /// colour-memory entry `first`, which is not after its own.
    pub fn from_entry(&mut self, first: usize) {
        let pad = self.first - first;
        self.cgram.splice(0..0, std::iter::repeat_n(0, pad));
        self.first = first;
    }
}

/// A cell turned four ways: as it is, mirrored across x, across y, both.
fn flipped(cell: &Cell, k: usize) -> Cell {
    let mut out = *cell;
    if k & 1 != 0 {
        for row in out.iter_mut() {
            row.reverse();
        }
    }
    if k & 2 != 0 {
        out.reverse();
    }
    out
}

/// The way of turning a cell that comes first: what two mirrored cells
/// share, and which of the four turns gives it.
fn canonical(cell: &Cell) -> (Cell, usize) {
    (0..4)
        .map(|k| (flipped(cell, k), k))
        .min_by(|a, b| a.0.cmp(&b.0))
        .unwrap()
}

/// The grid with at most `max` distinct cells, mirrors counted as one: each
/// group of alike cells drawn with one of them, turned the way each cell
/// was. Answers the grid and how many distinct cells there were.
fn grouped(grid: &Grid, max: usize) -> (Grid, usize) {
    let mut index: HashMap<Cell, usize> = HashMap::new();
    let mut tiles: Vec<Cell> = Vec::new();
    let mut weights: Vec<f32> = Vec::new();
    let mut of_cell: Vec<(usize, usize)> = Vec::with_capacity(grid.cells.len());
    let mut uses = vec![0f32; grid.cells.len()];
    for &n in &grid.at {
        uses[n] += 1.0;
    }
    for (i, cell) in grid.cells.iter().enumerate() {
        let (canon, k) = canonical(cell);
        let t = *index.entry(canon).or_insert_with(|| {
            tiles.push(canon);
            weights.push(0.0);
            tiles.len() - 1
        });
        weights[t] += uses[i];
        of_cell.push((t, k));
    }
    let distinct = tiles.len();
    let drawn = adeleine::group_tiles(&tiles, &weights, max);
    let cells = of_cell
        .iter()
        // Turning twice the same way undoes it, so the cell's own turn takes
        // the canonical drawing back to how the cell had it.
        .map(|&(t, k)| flipped(&tiles[drawn[t]], k))
        .collect();
    (
        Grid {
            columns: grid.columns,
            rows: grid.rows,
            at: grid.at.clone(),
            cells,
        },
        distinct,
    )
}

/// Groups and converts, and if the palettes split some group into more
/// tiles than `budget`, groups tighter and tries again.
fn fitted(
    grid: &Grid,
    budget: usize,
    convert: impl Fn(
        &Grid,
    ) -> Result<(
        voodoo::Converted,
        Picture,
        Vec<Vec<Color>>,
        Vec<Merge>,
        Grid,
    )>,
) -> Result<(
    voodoo::Converted,
    Picture,
    Vec<Vec<Color>>,
    Vec<Merge>,
    usize,
)> {
    // Tile 0 is the blank one.
    let mut max = budget - 1;
    loop {
        let (grid_now, distinct) = grouped(grid, max);
        let (done, picture, palettes, merges, _) = convert(&grid_now)?;
        if done.report.tiles <= budget {
            return Ok((done, picture, palettes, merges, distinct));
        }
        let over = done.report.tiles - budget;
        if max <= over + 1 {
            return Err(Bad::new(format!(
                "the panorama does not fit in {budget} tiles however its cells are grouped"
            )));
        }
        max -= over;
    }
}

/// The panorama in mode 3: BG2 at 4 bits, in at most `free` palettes, the
/// last ones of the lower half of colour memory, and `budget` tiles.
/// Answers it with what was decided, as an indexed picture of colour-memory
/// entries.
pub fn mode3(
    picture: &rm2k_render::Picture,
    free: usize,
    budget: usize,
) -> Result<(Panorama, Picture)> {
    let grid = Grid::quantize(picture);
    let colors_before = counts(&[&grid]).len();
    let (done, decided, palettes, merges, distinct) = fitted(&grid, budget, |g| {
        let (mut grids, palettes, merges) = reduce(&[g], free, adeleine::USABLE_COLORS)?;
        let g = grids.remove(0);
        let first = crate::background::layers::BG_PALETTES - palettes.len();
        let (done, picture) = four_bits(&g, &palettes, first)?;
        Ok((done, picture, palettes, merges, g))
    })?;
    let first = (crate::background::layers::BG_PALETTES - palettes.len()) * COLORS_PER_PALETTE;
    let cgram = (first..first + palettes.len() * COLORS_PER_PALETTE)
        .map(|e| u16::from_le_bytes([done.cgram[2 * e], done.cgram[2 * e + 1]]))
        .collect();
    Ok((
        Panorama {
            mode: Mode::Three,
            tiles: done.tiles,
            tilemap: done.tilemap,
            first,
            cgram,
            backdrop: None,
            distinct,
            colors: colors_before,
            kept: palettes.iter().flatten().collect::<BTreeSet<_>>().len(),
            merges,
            extras: Vec::new(),
        },
        decided,
    ))
}

/// A grid at 4 bits in `palettes` from palette `first`: each cell takes the
/// first palette that has all its colours.
fn four_bits(
    grid: &Grid,
    palettes: &[Vec<Color>],
    first: usize,
) -> Result<(voodoo::Converted, Picture)> {
    let sets: Vec<BTreeSet<Color>> = palettes
        .iter()
        .map(|p| p.iter().copied().collect())
        .collect();
    let tables: Vec<HashMap<Color, u8>> = palettes
        .iter()
        .enumerate()
        .map(|(i, palette)| {
            let base = (first + i) * COLORS_PER_PALETTE;
            palette
                .iter()
                .enumerate()
                .map(|(k, &c)| (c, (base + k + 1) as u8))
                .collect()
        })
        .collect();
    let mut missing = None;
    let pixels = paint(grid, &tables, |cx, cy, cell| {
        let wanted = colors(cell);
        if wanted.is_empty() {
            return None;
        }
        let found = sets.iter().position(|s| wanted.is_subset(s));
        if found.is_none() {
            missing = Some((cx, cy));
        }
        found
    });
    if let Some((x, y)) = missing {
        return Err(Bad::new(format!(
            "the panorama's cell at column {x}, row {y} fits in none of its palettes"
        )));
    }
    let mut entries: Vec<Option<Color>> = vec![None; voodoo::ENTRIES];
    for (i, palette) in palettes.iter().enumerate() {
        let base = (first + i) * COLORS_PER_PALETTE;
        entries[base] = Some([0, 0, 0]);
        for k in 0..COLORS_PER_PALETTE - 1 {
            entries[base + k + 1] = Some(palette.get(k).copied().unwrap_or([0, 0, 0]));
        }
    }
    let picture = Picture {
        width: grid.columns * CELL,
        height: grid.rows * CELL,
        pixels,
        colors: memory(&entries),
    };
    let mut options = Options::at(4);
    options.max_tiles = MAX_TILES;
    let done = voodoo::convert(&picture, &[], &options)?;
    Ok((done, picture))
}

/// The panorama in mode 1: BG3 at 2 bits, palettes 4 to 7, the colour it
/// draws most on the backdrop, and `budget` tiles.
pub fn mode1(picture: &rm2k_render::Picture, budget: usize) -> Result<(Panorama, Picture)> {
    let grid = Grid::quantize(picture);
    let totals = counts(&[&grid]);
    let colors_before = totals.len();
    // The most drawn colour, the first of them on a tie.
    let backdrop = totals
        .iter()
        .fold(None::<(Color, u64)>, |best, &(c, n)| match best {
            Some((_, m)) if m >= n => best,
            _ => Some((c, n)),
        })
        .map(|(c, _)| c)
        .ok_or_else(|| Bad::new("the panorama draws nothing"))?;
    let (done, decided, palettes, merges, distinct) = fitted(&grid, budget, |g| {
        // The backdrop's pixels draw nothing: the screen's backdrop shows.
        let holed = Grid {
            columns: g.columns,
            rows: g.rows,
            at: g.at.clone(),
            cells: g
                .cells
                .iter()
                .map(|cell| cell.map(|row| row.map(|p| p.filter(|c| *c != backdrop))))
                .collect(),
        };
        let (holed, palettes, merges) = two_bit_palettes(&holed)?;
        let (done, picture) = two_bits(&holed, &palettes, backdrop)?;
        Ok((done, picture, palettes, merges, holed))
    })?;
    let first = MODE1_FIRST_PALETTE * MODE1_ENTRIES;
    let cgram = (first..first + MODE1_PALETTES * MODE1_ENTRIES)
        .map(|e| u16::from_le_bytes([done.cgram[2 * e], done.cgram[2 * e + 1]]))
        .collect();
    let mut kept: BTreeSet<Color> = palettes.iter().flatten().copied().collect();
    kept.insert(backdrop);
    Ok((
        Panorama {
            mode: Mode::One,
            tiles: done.tiles,
            tilemap: done.tilemap,
            first,
            cgram,
            backdrop: Some(voodoo::cgram_word((backdrop[0], backdrop[1], backdrop[2]))),
            distinct,
            colors: colors_before,
            kept: kept.len(),
            merges,
            extras: Vec::new(),
        },
        decided,
    ))
}

/// The 2-bit palettes: three colours each, merging the colour that shows
/// least until the cells fit.
fn two_bit_palettes(grid: &Grid) -> Result<(Grid, Vec<Vec<Color>>, Vec<Merge>)> {
    if grid.cells.iter().all(|c| colors(c).is_empty()) {
        return Ok((grid.clone(), Vec::new(), Vec::new()));
    }
    let (mut grids, palettes, merges) = reduce(&[grid], MODE1_PALETTES, MODE1_COLORS)?;
    Ok((grids.remove(0), palettes, merges))
}

/// A grid at 2 bits in BG3's palettes 4 to 7.
fn two_bits(
    grid: &Grid,
    palettes: &[Vec<Color>],
    backdrop: Color,
) -> Result<(voodoo::Converted, Picture)> {
    let sets: Vec<BTreeSet<Color>> = palettes
        .iter()
        .map(|p| p.iter().copied().collect())
        .collect();
    let tables: Vec<HashMap<Color, u8>> = palettes
        .iter()
        .enumerate()
        .map(|(i, palette)| {
            let base = (MODE1_FIRST_PALETTE + i) * MODE1_ENTRIES;
            palette
                .iter()
                .enumerate()
                .map(|(k, &c)| (c, (base + k + 1) as u8))
                .collect()
        })
        .collect();
    let mut missing = None;
    let pixels = paint(grid, &tables, |cx, cy, cell| {
        let wanted = colors(cell);
        if wanted.is_empty() {
            return None;
        }
        let found = sets.iter().position(|s| wanted.is_subset(s));
        if found.is_none() {
            missing = Some((cx, cy));
        }
        found
    });
    if let Some((x, y)) = missing {
        return Err(Bad::new(format!(
            "the panorama's cell at column {x}, row {y} fits in none of its palettes"
        )));
    }
    let mut entries: Vec<Option<Color>> = vec![None; voodoo::ENTRIES];
    entries[0] = Some(backdrop);
    for (i, palette) in palettes.iter().enumerate() {
        let base = (MODE1_FIRST_PALETTE + i) * MODE1_ENTRIES;
        entries[base] = Some(backdrop);
        for k in 0..MODE1_COLORS {
            entries[base + k + 1] = Some(palette.get(k).copied().unwrap_or([0, 0, 0]));
        }
    }
    let picture = Picture {
        width: grid.columns * CELL,
        height: grid.rows * CELL,
        pixels,
        colors: memory(&entries),
    };
    let mut options = Options::at(2);
    options.max_tiles = MAX_TILES;
    let done = voodoo::convert(&picture, &[], &options)?;
    Ok((done, picture))
}
