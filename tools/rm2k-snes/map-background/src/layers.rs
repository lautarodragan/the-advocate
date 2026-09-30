//! The map's two background layers in mode 3: how the lower half of colour
//! memory is split between them, and each one converted to tiles.
//!
//! The input is the two layers already drawn —by `rm2k-render`— and the
//! other drawings of the ChipSet's animation; the output, per layer, its
//! tiles, its colour-memory words and its tilemap.
//!
//! Which colours are lost and how they are grouped is Adeleine's; cutting
//! the tiles and reusing mirrored ones, Voodoo's. What is left here is what
//! depends on the hardware:
//!
//! * **colour is 15 bits**, five per channel;
//! * **the background goes at 8 bits per pixel**: each pixel is a colour
//!   memory entry and there is no palette per tile, so its colours are one
//!   pool and never have to be split into groups. It costs twice the VRAM a
//!   tile;
//! * **the layer above the hero goes at 4 bits**, in palettes of sixteen,
//!   because it shares BG2 with the message window, which is 4bpp.
//!
//! Every index stays in the lower half of colour memory: the upper half is
//! the sprites'.

use crate::fail::{Bad, Result};
use crate::grid::{colors, counts, Cell, Grid, CELL};
use adeleine::{Color, Merge};
use rm2k_render::{Family, Layers};
use std::collections::{BTreeSet, HashMap};
use voodoo::{Options, Picture, Rgb15};

/// Tiles one layer can address: ten bits in each tilemap cell.
pub const MAX_TILES: usize = 1024;

/// Entries in a 4bpp palette, the transparent one included.
pub const COLORS_PER_PALETTE: usize = 16;

/// The lower half of colour memory, in palettes of sixteen. The upper half
/// belongs to the sprites. Where the split between the background and the
/// layer above falls inside it is decided map by map, in [`convert`].
pub const BG_PALETTES: usize = 8;

/// The background has to keep at least one palette: the most the layer
/// above can take.
pub const MAX_ABOVE_PALETTES: usize = BG_PALETTES - 1;

/// The entries at the very bottom the background cannot use: entry 0, the
/// screen's backdrop, and the eight of the message window, which lives in
/// palette 0 for every map. **Eight and not seven**: one of the window's
/// colours is pure black, whose word is zero, and counting the non-zero
/// words gives seven; what rules is the highest entry the window draws with.
pub const WINDOW_COLORS: usize = 8;
pub const CGRAM_RESERVED: usize = 1 + WINDOW_COLORS;

/// The BG2 priority bit of the layer above. In mode 3 the order from front
/// to back is objects 3, BG1 1, objects 2, BG2 1, objects 1, BG1 0, objects
/// 0: the map in BG1 at 0, the hero at 1, the layer above in BG2 at 1 and
/// the events "above the hero" at 2. RM2k's order, with no tricks.
pub const PRIORITY_ABOVE: u8 = 1;

/// Colour memory's entry 0, the backdrop: black, which is what RM2k draws
/// where the map has nothing and past its edges.
pub const BACKDROP: Color = [0, 0, 0];

/// Where the layer above starts in colour memory, in palettes, if it takes
/// this many.
pub fn above_split(palettes: usize) -> usize {
    BG_PALETTES - palettes
}

/// The colours left for the background below the layer above, which starts
/// at palette `first`: without the backdrop and the window.
pub fn bg_budget(first: usize) -> usize {
    first * COLORS_PER_PALETTE - CGRAM_RESERVED
}

/// One family of the ChipSet's animation as it lands in VRAM: its tiles are
/// a contiguous run at the end of the bank, and animating it is uploading
/// one drawing over the run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Run {
    pub family: Family,
    /// The run's first tile.
    pub base: usize,
    pub tiles: usize,
    /// The run as each drawing has it, drawing 0 first.
    pub drawings: Vec<Vec<u8>>,
}

/// The layer behind the hero.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Background {
    /// 8bpp tiles, back to back.
    pub tiles: Vec<u8>,
    /// The words of its colours, from entry [`CGRAM_RESERVED`] up: what is
    /// below belongs to the whole cartridge.
    pub cgram: Vec<u16>,
    pub tilemap: Vec<Vec<u16>>,
    /// How many distinct colours the drawing brought, before merging.
    pub colors: usize,
    /// How many it keeps.
    pub used: usize,
    /// How many entries the layer above left it.
    pub budget: usize,
    pub merges: Vec<Merge>,
    pub cells: usize,
    pub runs: Vec<Run>,
}

/// The layer in front of the hero.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Above {
    /// 4bpp tiles, back to back.
    pub tiles: Vec<u8>,
    /// Its palettes' words, little-endian, from its first palette on; one
    /// empty palette if it has none, because a DMA of zero bytes moves
    /// 65536.
    pub cgram: Vec<u8>,
    pub tilemap: Vec<Vec<u16>>,
    /// The palette it starts at.
    pub first: usize,
    pub merges: Vec<Merge>,
}

/// What Adeleine decided, as indexed pictures whose indices are colour
/// memory entries: they can be opened and looked at without building
/// anything. `name` is `background`, `above`, or a family's drawing,
/// `water-1`.
pub struct Decided {
    pub name: String,
    pub picture: Picture,
}

/// Both layers converted, and the pictures of what was decided.
pub struct Converted {
    pub background: Background,
    pub above: Above,
    pub pictures: Vec<Decided>,
}

/// Both layers together, which is the only way to split colour memory well.
///
/// The split between the background and the layer above cannot be decided
/// by either on its own. **The background chooses first**: it keeps the
/// palettes it needs for the colours it really uses, because it goes at 8
/// bits and cannot split them into groups; the layer above takes what is
/// left —up to what it asks for, never more— and merges if that is not
/// enough. The other way round would take colours from the background of
/// every map so that the few whose layer above asks for seven palettes do
/// not merge.
///
/// All the drawings of the animation count for the background: the water
/// of a map can bring colours its drawing 0 does not have, and if the split
/// were decided without them there would be nowhere to put them when the
/// water moves.
pub fn convert(layers: &Layers) -> Result<Converted> {
    let base = Grid::quantize(&layers.lower);
    let above = Grid::quantize(&layers.upper);
    let variants: Vec<(Family, Vec<Grid>)> = layers
        .variants
        .iter()
        .map(|(family, drawings)| (*family, drawings.iter().map(Grid::quantize).collect()))
        .collect();

    let mut all: Vec<&Grid> = vec![&base];
    all.extend(variants.iter().flat_map(|(_, gs)| gs));
    let used = counts(&all).len();
    // The +1 of the backdrop and the window, and the palettes of sixteen
    // that makes.
    let needed = (used + CGRAM_RESERVED).div_ceil(COLORS_PER_PALETTE);
    let free = (BG_PALETTES as i64 - needed as i64).clamp(1, MAX_ABOVE_PALETTES as i64) as usize;

    let (above, above_palettes, above_merges) = split_above(&above, free)?;
    // Without a layer above nothing is reserved, but the DMA still sends an
    // empty palette, so the split counts one.
    let first = above_split(above_palettes.len().max(1));
    let (above, above_picture) = convert_above(&above, &above_palettes, first, above_merges)?;
    if first < 1 {
        return Err(Bad::new(
            "the upper layer took all eight palettes and none is left for the background",
        ));
    }

    // The background reaches up to where the layer above starts, with no
    // palettes in between: at 8 bits it needs no alignment.
    let budget = bg_budget(first);
    let others: Vec<&Grid> = variants.iter().flat_map(|(_, gs)| gs).collect();
    let colors_before = counts(&[&base]).len();
    let (palette, base, others, merges) = build_palette(&base, budget, &others)?;
    let mut drawings: Vec<(Family, Vec<Grid>)> = Vec::new();
    let mut rest = others.into_iter();
    for (family, gs) in &variants {
        drawings.push((*family, rest.by_ref().take(gs.len()).collect()));
    }
    let (background, mut pictures) =
        convert_background(&base, &palette, &drawings, colors_before, budget, merges)?;
    pictures.push(Decided {
        name: "above".to_string(),
        picture: above_picture,
    });
    Ok(Converted {
        background,
        above,
        pictures,
    })
}

/// Which palettes the layer above takes, with `limit` as the cap; if they
/// do not fit, merging until they do. Returns the grid —another one if
/// something merged—, the palettes, each sorted, and the merges.
///
/// There are two reasons for not fitting, and one fix: that the colours are
/// too many for the palettes granted, or that a single tile has more than
/// fifteen, which fits no palette however many there are. Both are fixed by
/// merging the colour that shows least into its nearest and trying again.
fn split_above(grid: &Grid, limit: usize) -> Result<(Grid, Vec<Vec<Color>>, Vec<Merge>)> {
    let sets: BTreeSet<BTreeSet<Color>> = grid
        .cells
        .iter()
        .map(colors)
        .filter(|s| !s.is_empty())
        .collect();
    let sets: Vec<BTreeSet<Color>> = sets.into_iter().collect();
    if sets.is_empty() {
        return Ok((grid.clone(), Vec::new(), Vec::new()));
    }
    if let Some(groups) = adeleine::try_pack(&sets, limit, adeleine::USABLE_COLORS) {
        let palettes = groups.into_iter().map(|g| g.into_iter().collect()).collect();
        return Ok((grid.clone(), palettes, Vec::new()));
    }
    let totals = counts(&[grid]);
    let tiles: Vec<BTreeSet<Color>> = grid.cells.iter().map(colors).collect();
    let reduced = adeleine::reduce_colors(&totals, &tiles, limit, adeleine::USABLE_COLORS)?;
    let to: HashMap<Color, Color> = totals
        .iter()
        .map(|&(c, _)| c)
        .zip(reduced.mapping.iter().copied())
        .collect();
    let palettes = reduced
        .palettes
        .into_iter()
        .map(|g| g.into_iter().collect())
        .collect();
    Ok((grid.remap(&to), palettes, reduced.merges))
}

/// Every colour-memory entry with a colour, black where the picture gives
/// none: what the picture's file says, so what Voodoo reads.
fn memory(colors: &[Option<Color>]) -> Vec<Option<Rgb15>> {
    colors
        .iter()
        .map(|c| {
            let [r, g, b] = c.unwrap_or([0, 0, 0]);
            Some((r, g, b))
        })
        .collect()
}

/// Paints `grid` into an indexed picture: each cell with the table of
/// `tables` that `choose` picks for it, or left transparent.
fn paint(
    grid: &Grid,
    tables: &[HashMap<Color, u8>],
    mut choose: impl FnMut(usize, usize, &Cell) -> Option<usize>,
) -> Vec<u8> {
    let width = grid.columns * CELL;
    let mut pixels = vec![0u8; width * grid.rows * CELL];
    for cy in 0..grid.rows {
        for cx in 0..grid.columns {
            let cell = grid.cell(cx, cy);
            let Some(table) = choose(cx, cy, cell) else {
                continue;
            };
            let entries = &tables[table];
            for (y, line) in cell.iter().enumerate() {
                let offset = (cy * CELL + y) * width + cx * CELL;
                for (x, color) in line.iter().enumerate() {
                    if let Some(c) = color {
                        pixels[offset + x] = entries[c];
                    }
                }
            }
        }
    }
    pixels
}

/// The layer above: its picture as Adeleine leaves it, and converted.
///
/// **It decides nothing**: the palettes were chosen by [`split_above`] and
/// where they start by [`convert`]. Colour `k` of palette `i` is entry
/// `(first + i) * 16 + k + 1`, and transparent is 0; each cell takes the
/// first palette that has all its colours.
fn convert_above(
    grid: &Grid,
    palettes: &[Vec<Color>],
    first: usize,
    merges: Vec<Merge>,
) -> Result<(Above, Picture)> {
    let sets: Vec<BTreeSet<Color>> = palettes.iter().map(|p| p.iter().copied().collect()).collect();
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
            "the cell of the upper layer at column {x}, row {y} fits in none of its palettes"
        )));
    }
    let mut entries: Vec<Option<Color>> = vec![None; voodoo::ENTRIES];
    for (i, palette) in palettes.iter().enumerate() {
        let base = (first + i) * COLORS_PER_PALETTE;
        entries[base] = Some(BACKDROP);
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
    options.priority = PRIORITY_ABOVE;
    options.max_tiles = MAX_TILES;
    let done = voodoo::convert(&picture, &[], &options)?;
    // The layer's palettes and nothing else: the rest of colour memory is
    // other layers'.
    let from = 2 * first * COLORS_PER_PALETTE;
    let to = 2 * (first + palettes.len()) * COLORS_PER_PALETTE;
    let mut cgram = done.cgram[from..to].to_vec();
    if cgram.is_empty() {
        cgram = vec![0; 2 * COLORS_PER_PALETTE];
    }
    Ok((
        Above {
            tiles: done.tiles,
            cgram,
            tilemap: done.tilemap,
            first,
            merges,
        },
        picture,
    ))
}

/// The background's colours in one table, merging only if there are more
/// than `budget`. `others` are the grids of the animation's other drawings:
/// they count like drawing 0 and come out merged with the same mapping,
/// which is what keeps them comparable with each other.
fn build_palette(
    grid: &Grid,
    budget: usize,
    others: &[&Grid],
) -> Result<(Vec<Color>, Grid, Vec<Grid>, Vec<Merge>)> {
    let mut all = vec![grid];
    all.extend(others.iter().copied());
    let totals = counts(&all);
    if totals.len() <= budget {
        let mut palette: Vec<Color> = totals.iter().map(|&(c, _)| c).collect();
        palette.sort();
        return Ok((
            palette,
            grid.clone(),
            others.iter().map(|&g| g.clone()).collect(),
            Vec::new(),
        ));
    }
    let merged = adeleine::merge_least_visible(&totals, budget)?;
    let to: HashMap<Color, Color> = totals
        .iter()
        .map(|&(c, _)| c)
        .zip(merged.mapping.iter().copied())
        .collect();
    let palette: BTreeSet<Color> = merged.mapping.iter().copied().collect();
    Ok((
        palette.into_iter().collect(),
        grid.remap(&to),
        others.iter().map(|g| g.remap(&to)).collect(),
        merged.merges,
    ))
}

/// The background to tiles, its colours and its tilemap. **It decides
/// nothing**: the palette comes from [`build_palette`], and the grids come
/// merged with it. Colour `k` of the palette is entry `CGRAM_RESERVED + k`.
///
/// The cells that change from one drawing to another get their own tiles,
/// in a contiguous run per family at the end of the bank: Voodoo does that,
/// since it numbers them.
fn convert_background(
    grid: &Grid,
    palette: &[Color],
    drawings: &[(Family, Vec<Grid>)],
    colors_before: usize,
    budget: usize,
    merges: Vec<Merge>,
) -> Result<(Background, Vec<Decided>)> {
    let entry: HashMap<Color, u8> = palette
        .iter()
        .enumerate()
        .map(|(k, &c)| (c, (CGRAM_RESERVED + k) as u8))
        .collect();
    let mut entries: Vec<Option<Color>> = vec![None; voodoo::ENTRIES];
    for (&c, &e) in &entry {
        entries[e as usize] = Some(c);
    }
    let picture = |g: &Grid| Picture {
        width: g.columns * CELL,
        height: g.rows * CELL,
        pixels: paint(g, std::slice::from_ref(&entry), |_, _, _| Some(0)),
        colors: memory(&entries),
    };
    let mut pictures = vec![Decided {
        name: "background".to_string(),
        picture: picture(grid),
    }];
    let mut families = Vec::new();
    let mut animations = Vec::new();
    for (family, gs) in drawings {
        if gs.is_empty() {
            continue;
        }
        let drawn: Vec<Picture> = gs.iter().map(picture).collect();
        for (d, p) in drawn.iter().enumerate() {
            pictures.push(Decided {
                name: format!("{}-{}", family.name(), d + 1),
                picture: Picture {
                    width: p.width,
                    height: p.height,
                    pixels: p.pixels.clone(),
                    colors: p.colors.clone(),
                },
            });
        }
        families.push(*family);
        animations.push(drawn);
    }
    let mut options = Options::at(8);
    options.max_tiles = MAX_TILES;
    let done = voodoo::convert(&pictures[0].picture, &animations, &options)?;

    let mut runs = Vec::new();
    for (family, run) in families.into_iter().zip(done.animations) {
        if run.count == 0 {
            continue;
        }
        if run.frames.len() != family.drawings() {
            return Err(Bad::new(format!(
                "family {} asks for {} drawings and {} arrived",
                family.name(),
                family.drawings(),
                run.frames.len()
            )));
        }
        runs.push(Run {
            family,
            base: run.first,
            tiles: run.count,
            drawings: run.frames,
        });
    }
    // Colour memory: the map carries only its colours, uploaded from
    // `CGRAM_RESERVED` up.
    let cgram = (CGRAM_RESERVED..CGRAM_RESERVED + palette.len())
        .map(|e| u16::from_le_bytes([done.cgram[2 * e], done.cgram[2 * e + 1]]))
        .collect();
    Ok((
        Background {
            cells: done.tilemap.iter().map(Vec::len).sum(),
            tiles: done.tiles,
            cgram,
            tilemap: done.tilemap,
            colors: colors_before,
            used: palette.len(),
            budget,
            merges,
            runs,
        },
        pictures,
    ))
}
