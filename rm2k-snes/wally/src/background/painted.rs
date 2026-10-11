//! A painted map: the whole map is one picture —its panorama, fixed to it,
//! with what the ChipSet and the map's pictures draw over it— and it goes
//! in BG1, in mode 1, at 4 bits, **one tile per cell and no grouping**.
//!
//! A painting of 640x480 has 4,800 cells and almost all of them are
//! different, and no layout holds more than a thousand tiles: grouped into
//! the 576 a panorama gets in mode 3, the squares of Sunset Over Imdahl
//! came out as a mosaic of the wrong cells. So the console holds only the
//! cells the screen can show —33 columns by 29 rows, one slot each, by
//! where they are on the map— and uploads the column or the row that comes
//! into view, from the cartridge, while the camera moves: see
//! `runtime/painted.s`. The cartridge carries every cell once, column by
//! column, so that a column goes up in one DMA.
//!
//! What is left of the 4-bit format is the colours: the painting is split
//! into palettes of fifteen by Adeleine, as a panorama in mode 3 is, and
//! each cell takes the first palette that has all its colours. What goes in
//! front of the hero is the priority bit of its cells, as in a flattened
//! map: see `raise` in `map_pictures.rs`, at the crate's top.

use crate::background::fail::{Bad, Result};
use crate::background::grid::{colors, counts, Grid, CELL};
use crate::background::layers::{memory, paint, COLORS_PER_PALETTE};
use crate::background::panorama::{reduce, Mode, Panorama};
use adeleine::Color;
use std::collections::{BTreeSet, HashMap};
use voodoo::Picture;

/// The painting's first palette: palette 0 is the backdrop and the message
/// window's, as in every map.
pub const FIRST_PALETTE: usize = 1;
/// And how many it takes: all the others of the lower half.
pub const PALETTES: usize = 7;

/// Bytes of a cell at 4 bits.
pub const CELL_BYTES: usize = 32;

/// The painting converted: its cells as 4-bit tiles, **column by column**
/// —cell (x, y) is tile `x * rows + y`—, and in `tilemap`, one entry per
/// cell, rows of columns, the palette and the priority each one is drawn
/// with; its tile number is the console's, which depends on where the
/// camera is, and goes at zero. Answers it with the picture of what was
/// decided, as colour-memory entries.
pub fn painted(picture: &rm2k_render::Picture) -> Result<(Panorama, Picture)> {
    let grid = Grid::quantize(picture);
    if grid.cells.iter().any(|c| c.iter().flatten().any(Option::is_none)) {
        return Err(Bad::new("a painted map has to be opaque everywhere"));
    }
    let colors_before = counts(&[&grid]).len();
    let distinct = grid.cells.len();
    let (mut grids, palettes, merges) = reduce(&[&grid], PALETTES, adeleine::USABLE_COLORS)?;
    let grid = grids.remove(0);
    let sets: Vec<BTreeSet<Color>> = palettes.iter().map(|p| p.iter().copied().collect()).collect();
    let tables: Vec<HashMap<Color, u8>> = palettes
        .iter()
        .map(|palette| palette.iter().enumerate().map(|(k, &c)| (c, (k + 1) as u8)).collect())
        .collect();
    let mut tiles = vec![0u8; grid.columns * grid.rows * CELL_BYTES];
    let mut tilemap = vec![vec![0u16; grid.columns]; grid.rows];
    let mut palette_of = vec![0usize; grid.columns * grid.rows];
    for cy in 0..grid.rows {
        for cx in 0..grid.columns {
            let cell = grid.cell(cx, cy);
            let wanted = colors(cell);
            let p = sets.iter().position(|s| wanted.is_subset(s)).ok_or_else(|| {
                Bad::new(format!("the painting's cell at column {cx}, row {cy} fits in none of its palettes"))
            })?;
            let mut indices = [[0u8; CELL]; CELL];
            for (y, line) in cell.iter().enumerate() {
                for (x, c) in line.iter().enumerate() {
                    indices[y][x] = tables[p][&c.expect("opaque")];
                }
            }
            let at = (cx * grid.rows + cy) * CELL_BYTES;
            tiles[at..at + CELL_BYTES].copy_from_slice(&voodoo::pack_tile(&indices, 4));
            tilemap[cy][cx] = voodoo::entry(0, 0, 0, 0, (FIRST_PALETTE + p) as u8);
            palette_of[cy * grid.columns + cx] = p;
        }
    }
    // The picture of what was decided: each pixel its colour-memory entry.
    let entry_tables: Vec<HashMap<Color, u8>> = tables
        .iter()
        .enumerate()
        .map(|(p, t)| {
            let base = (FIRST_PALETTE + p) * COLORS_PER_PALETTE;
            t.iter().map(|(&c, &k)| (c, (base + k as usize) as u8)).collect()
        })
        .collect();
    let pixels = paint(&grid, &entry_tables, |cx, cy, _| Some(palette_of[cy * grid.columns + cx]));
    let mut entries: Vec<Option<Color>> = vec![None; voodoo::ENTRIES];
    let mut cgram = Vec::with_capacity(PALETTES * COLORS_PER_PALETTE);
    for p in 0..PALETTES {
        let base = (FIRST_PALETTE + p) * COLORS_PER_PALETTE;
        entries[base] = Some([0, 0, 0]);
        cgram.push(0);
        for k in 0..COLORS_PER_PALETTE - 1 {
            let c = palettes.get(p).and_then(|pal| pal.get(k)).copied().unwrap_or([0, 0, 0]);
            entries[base + k + 1] = Some(c);
            cgram.push(voodoo::cgram_word((c[0], c[1], c[2])));
        }
    }
    let decided = Picture {
        width: grid.columns * CELL,
        height: grid.rows * CELL,
        pixels,
        colors: memory(&entries),
    };
    Ok((
        Panorama {
            mode: Mode::Painted,
            tiles,
            tilemap,
            first: FIRST_PALETTE * COLORS_PER_PALETTE,
            cgram,
            backdrop: None,
            distinct,
            colors: colors_before,
            kept: palettes.iter().flatten().collect::<BTreeSet<_>>().len(),
            merges,
        },
        decided,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn picture(w: usize, h: usize, at: impl Fn(usize, usize) -> [u8; 3]) -> rm2k_render::Picture {
        let mut p = rm2k_render::Picture::transparent(w, h);
        for y in 0..h {
            for x in 0..w {
                let c = at(x, y);
                p.rgba[(y * w + x) * 4..(y * w + x) * 4 + 4].copy_from_slice(&[c[0], c[1], c[2], 255]);
            }
        }
        p
    }

    #[test]
    fn every_cell_is_its_own_tile_column_by_column() {
        // Two columns, three rows, each cell a flat colour of its own: none
        // is grouped and they come down the first column first.
        let p = picture(16, 24, |x, y| [(x / 8 * 64) as u8, (y / 8 * 64) as u8, 0]);
        let (done, _) = painted(&p).unwrap();
        assert_eq!(done.tiles.len(), 6 * CELL_BYTES);
        assert_eq!(done.tilemap.len(), 3);
        assert_eq!(done.tilemap[0].len(), 2);
        // Each tile is one index everywhere: its colour's in its palette.
        let index = |t: usize| voodoo::unpack_tile(&done.tiles[t * CELL_BYTES..(t + 1) * CELL_BYTES], 4)[0][0];
        let colour = |t: usize| {
            let (cx, cy) = (t / 3, t % 3);
            let palette = ((done.tilemap[cy][cx] >> 10) & 7) as usize;
            done.cgram[(palette - FIRST_PALETTE) * COLORS_PER_PALETTE + index(t) as usize]
        };
        for t in 0..6 {
            let (cx, cy) = (t / 3, t % 3);
            let c = [((cx * 64) >> 3) as u8, ((cy * 64) >> 3) as u8, 0];
            assert_eq!(colour(t), voodoo::cgram_word((c[0], c[1], c[2])));
        }
    }

    #[test]
    fn a_hole_is_refused() {
        let mut p = picture(8, 8, |_, _| [9, 9, 9]);
        p.rgba[3] = 0;
        assert!(painted(&p).is_err());
    }
}
