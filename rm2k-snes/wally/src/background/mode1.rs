//! A map with a panorama and something above the hero: mode 1.
//!
//! Mode 3 has two layers and that map needs three —the panorama, the map
//! behind the hero and the layer in front of it—, so it goes in mode 1:
//! BG1 is the map at 4 bits, BG2 the layer above and the message window as
//! in mode 3, and BG3 the panorama at 2 bits, behind everything.
//!
//! The map loses what the 8-bit background never had to do: **split its
//! colours into palettes of fifteen**, one per cell. The lower half of
//! colour memory goes, in order:
//!
//! ```text
//!   palette 0     the backdrop and the message window, as in mode 3
//!   palette 1     the panorama: BG3's palettes 4 to 7, three colours each
//!   palettes 2..  the map, as few as fit it, five at most
//!   the last ones the layer above, as many as are left —one at least—
//! ```
//!
//! The map chooses first, as the 8-bit background does: it keeps the
//! palettes it needs for its colours without merging, if five are enough,
//! and the layer above takes what is left.

use crate::background::fail::{Bad, Result};
use crate::background::grid::{colors, counts, Grid, CELL};
use crate::background::layers::{
    cgram_reserved, convert_above, memory, paint, split_above, Background, Converted, Decided,
    PanoramaAsk, Run, BG_PALETTES, COLORS_PER_PALETTE, MAX_TILES,
};
use crate::background::panorama;
use crate::background::Merge;
use adeleine::Color;
use rm2k_render::{Family, Layers};
use std::collections::{BTreeSet, HashMap};
use voodoo::{Options, Picture};

/// The map's first palette: after the window's and the panorama's.
pub const FIRST_MAP_PALETTE: usize = 2;
/// The most the map can take, so that the layer above keeps one.
pub const MAX_MAP_PALETTES: usize = BG_PALETTES - FIRST_MAP_PALETTE - 1;

/// [`panorama::reduce`] for the places of the map: the colours each place
/// draws in any drawing of the animation have to fit in one palette.
fn reduce_places(
    grids: &[&Grid],
    places: &[BTreeSet<Color>],
) -> Result<(Vec<HashMap<Color, Color>>, Vec<Vec<Color>>, Vec<Merge>)> {
    let totals = counts(grids);
    let reduced =
        adeleine::reduce_colors(&totals, places, MAX_MAP_PALETTES, adeleine::USABLE_COLORS)?;
    let mappings = places
        .iter()
        .zip(&reduced.tiles)
        .map(|(tile, decided)| {
            tile.iter()
                .copied()
                .zip(decided.mapping.iter().copied())
                .collect()
        })
        .collect();
    Ok((
        mappings,
        reduced
            .palettes
            .into_iter()
            .map(|g| g.into_iter().collect())
            .collect(),
        reduced.merges.into_iter().map(Merge::from).collect(),
    ))
}

/// The whole map in mode 1: see the module.
pub fn convert(layers: &Layers, window_colors: usize, ask: &PanoramaAsk) -> Result<Converted> {
    let reserved = cgram_reserved(window_colors);
    if reserved > COLORS_PER_PALETTE {
        return Err(Bad::new(format!(
            "the message window takes {window_colors} colours and palette 0 holds {}",
            COLORS_PER_PALETTE - 1
        )));
    }
    let base = Grid::quantize(&layers.lower);
    let above = Grid::quantize(&layers.upper);
    let variants: Vec<(Family, Vec<Grid>)> = layers
        .variants
        .iter()
        .map(|(family, drawings)| (*family, drawings.iter().map(Grid::quantize).collect()))
        .collect();
    let mut all: Vec<&Grid> = vec![&base];
    all.extend(variants.iter().flat_map(|(_, gs)| gs));
    let colors_before = counts(&[&base]).len();

    // What each place of the map draws with, in every drawing of the
    // animation: a tilemap entry names one palette for all of them.
    let place_sets = |grids: &[&Grid]| -> Vec<BTreeSet<Color>> {
        let mut sets = Vec::with_capacity(base.columns * base.rows);
        for cy in 0..base.rows {
            for cx in 0..base.columns {
                let mut s = BTreeSet::new();
                for g in grids {
                    s.extend(colors(g.cell(cx, cy)));
                }
                sets.push(s);
            }
        }
        sets
    };
    let sets = place_sets(&all);
    // What a place draws in all the animation drawings goes together: its
    // tilemap entry names one palette for every drawing.
    let (mappings, palettes, merges) = reduce_places(&all, &sets)?;
    let base = base.remap_places(&mappings);
    let variants: Vec<(Family, Vec<Grid>)> = variants
        .iter()
        .map(|(f, gs)| (*f, gs.iter().map(|g| g.remap_places(&mappings)).collect()))
        .collect();
    let mut all: Vec<&Grid> = vec![&base];
    all.extend(variants.iter().flat_map(|(_, gs)| gs));
    let sets = place_sets(&all);

    // The layer above, in what the map left.
    let free = BG_PALETTES - FIRST_MAP_PALETTE - palettes.len();
    let (above, above_palettes, above_merges) = split_above(&above, free)?;
    let first_above = BG_PALETTES - above_palettes.len().max(1);
    let (above, above_picture) = convert_above(&above, &above_palettes, first_above, above_merges)?;

    // The map, each place in the first palette that has all it draws.
    let psets: Vec<BTreeSet<Color>> = palettes
        .iter()
        .map(|p| p.iter().copied().collect())
        .collect();
    let mut choice = Vec::with_capacity(sets.len());
    for (i, s) in sets.iter().enumerate() {
        if s.is_empty() {
            choice.push(None);
            continue;
        }
        let found = psets.iter().position(|p| s.is_subset(p)).ok_or_else(|| {
            Bad::new(format!(
                "the map's cell at column {}, row {} fits in none of its palettes",
                i % base.columns,
                i / base.columns
            ))
        })?;
        choice.push(Some(found));
    }
    let tables: Vec<HashMap<Color, u8>> = palettes
        .iter()
        .enumerate()
        .map(|(i, palette)| {
            let at = (FIRST_MAP_PALETTE + i) * COLORS_PER_PALETTE;
            palette
                .iter()
                .enumerate()
                .map(|(k, &c)| (c, (at + k + 1) as u8))
                .collect()
        })
        .collect();
    let (pano, pano_picture) = panorama::mode1(ask.picture, ask.tiles)?;
    let mut entries: Vec<Option<Color>> = vec![None; voodoo::ENTRIES];
    for (i, palette) in palettes.iter().enumerate() {
        let at = (FIRST_MAP_PALETTE + i) * COLORS_PER_PALETTE;
        entries[at] = Some([0, 0, 0]);
        for k in 0..COLORS_PER_PALETTE - 1 {
            entries[at + k + 1] = Some(palette.get(k).copied().unwrap_or([0, 0, 0]));
        }
    }
    let width = base.columns;
    let picture = |g: &Grid| Picture {
        width: g.columns * CELL,
        height: g.rows * CELL,
        pixels: paint(g, &tables, |cx, cy, _| choice[cy * width + cx]),
        colors: memory(&entries),
    };
    let mut pictures = vec![Decided {
        name: "background".to_string(),
        picture: picture(&base),
    }];
    let mut families = Vec::new();
    let mut animations = Vec::new();
    for (family, gs) in &variants {
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
    let mut options = Options::at(4);
    options.max_tiles = MAX_TILES;
    let done = voodoo::convert(&pictures[0].picture, &animations, &options)?;
    let mut runs = Vec::new();
    for (family, run) in families.into_iter().zip(done.animations) {
        if run.count == 0 {
            continue;
        }
        runs.push(Run {
            family,
            base: run.first,
            tiles: run.count,
            drawings: run.frames,
        });
    }
    // Colour memory from `reserved` up, as the 8-bit background's: the
    // two entries left in the window's palette, the panorama's palette and
    // the map's.
    let end = (FIRST_MAP_PALETTE + palettes.len()) * COLORS_PER_PALETTE;
    let mut cgram: Vec<u16> = (reserved..end)
        .map(|e| u16::from_le_bytes([done.cgram[2 * e], done.cgram[2 * e + 1]]))
        .collect();
    for (k, &word) in pano.cgram.iter().enumerate() {
        cgram[pano.first + k - reserved] = word;
    }
    let used = palettes.iter().flatten().collect::<BTreeSet<_>>().len();
    pictures.push(Decided {
        name: "above".to_string(),
        picture: above_picture,
    });
    pictures.push(Decided {
        name: "panorama".to_string(),
        picture: pano_picture,
    });
    // The record counts a background's tiles in 64-byte units, an 8-bit
    // tile's, and a DMA uploads that many: at 4 bits an odd count gets a
    // blank tile after it.
    let mut tiles = done.tiles;
    if tiles.len() % 64 != 0 {
        tiles.resize(tiles.len().next_multiple_of(64), 0);
    }
    Ok(Converted {
        background: Background {
            cells: done.tilemap.iter().map(Vec::len).sum(),
            tiles,
            bpp: 4,
            cgram,
            tilemap: done.tilemap,
            colors: colors_before,
            used,
            budget: palettes.len() * (COLORS_PER_PALETTE - 1),
            merges,
            runs,
        },
        above,
        panorama: Some(pano),
        way: None,
        tried: Vec::new(),
        above_lost: 0,
        in_front: None,
        pictures,
    })
}
