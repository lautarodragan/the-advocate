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
//! front of the hero is the painting itself: see [`roofs`].

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
    if grid
        .cells
        .iter()
        .any(|c| c.iter().flatten().any(Option::is_none))
    {
        return Err(Bad::new("a painted map has to be opaque everywhere"));
    }
    let colors_before = counts(&[&grid]).len();
    let distinct = grid.cells.len();
    let (mut grids, palettes, merges) = reduce(&[&grid], PALETTES, adeleine::USABLE_COLORS)?;
    let grid = grids.remove(0);
    let sets: Vec<BTreeSet<Color>> = palettes
        .iter()
        .map(|p| p.iter().copied().collect())
        .collect();
    let tables: Vec<HashMap<Color, u8>> = palettes
        .iter()
        .map(|palette| {
            palette
                .iter()
                .enumerate()
                .map(|(k, &c)| (c, (k + 1) as u8))
                .collect()
        })
        .collect();
    let mut tiles = vec![0u8; grid.columns * grid.rows * CELL_BYTES];
    let mut tilemap = vec![vec![0u16; grid.columns]; grid.rows];
    let mut palette_of = vec![0usize; grid.columns * grid.rows];
    for cy in 0..grid.rows {
        for cx in 0..grid.columns {
            let cell = grid.cell(cx, cy);
            let wanted = colors(cell);
            let p = sets
                .iter()
                .position(|s| wanted.is_subset(s))
                .ok_or_else(|| {
                    Bad::new(format!(
                        "the painting's cell at column {cx}, row {cy} fits in none of its palettes"
                    ))
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
            t.iter()
                .map(|(&c, &k)| (c, (base + k as usize) as u8))
                .collect()
        })
        .collect();
    let pixels = paint(&grid, &entry_tables, |cx, cy, _| {
        Some(palette_of[cy * grid.columns + cx])
    });
    let mut entries: Vec<Option<Color>> = vec![None; voodoo::ENTRIES];
    let mut cgram = Vec::with_capacity(PALETTES * COLORS_PER_PALETTE);
    for p in 0..PALETTES {
        let base = (FIRST_PALETTE + p) * COLORS_PER_PALETTE;
        entries[base] = Some([0, 0, 0]);
        cgram.push(0);
        for k in 0..COLORS_PER_PALETTE - 1 {
            let c = palettes
                .get(p)
                .and_then(|pal| pal.get(k))
                .copied()
                .unwrap_or([0, 0, 0]);
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

/// What goes in front of the hero in a painted map, from `front` —one flag
/// per pixel of the map, `width` across, what an opaque picture covers—:
/// the cells it covers whole go to BG1's priority 1; the ones it covers in
/// part get, in BG2 at priority 1, **the painting's own cell with only the
/// covered pixels**, in its palette: exact, with no colour of its own. BG2
/// has `budget` tiles for that besides its blank one, so if there are more
/// edges than that the ones that would put fewer pixels on the wrong side
/// go by the whole cell, as in a flattened map —in front if half of it is
/// covered—.
///
/// Answers BG2's tiles —the blank one first—, its tilemap, and the pixels
/// on the wrong side of the hero and how many `front` has.
pub fn roofs(
    pano: &mut Panorama,
    front: &[bool],
    width: usize,
    budget: usize,
) -> (Vec<u8>, Vec<Vec<u16>>, usize, usize) {
    let rows = pano.tilemap.len();
    let cols = pano.tilemap.first().map_or(0, Vec::len);
    let height = front.len() / width.max(1);
    let mut above = vec![vec![0u16; cols]; rows];
    let mut tiles = vec![0u8; CELL_BYTES];
    let (mut wrong, mut total) = (0, 0);
    // The edges, each with what it saves and its masked tile.
    let mut edges: Vec<(usize, usize, usize, Vec<u8>)> = Vec::new();
    for cy in 0..rows {
        for cx in 0..cols {
            let covered = |x: usize, y: usize| {
                let (px, py) = (cx * CELL + x, cy * CELL + y);
                px < width && py < height && front[py * width + px]
            };
            let n = (0..CELL)
                .flat_map(|y| (0..CELL).map(move |x| (x, y)))
                .filter(|&(x, y)| covered(x, y))
                .count();
            total += n;
            if n == 0 {
                continue;
            }
            if n == CELL * CELL {
                pano.tilemap[cy][cx] |= PRIORITY;
                continue;
            }
            let at = (cx * rows + cy) * CELL_BYTES;
            let mut indices = voodoo::unpack_tile(&pano.tiles[at..at + CELL_BYTES], 4);
            for (y, line) in indices.iter_mut().enumerate() {
                for (x, i) in line.iter_mut().enumerate() {
                    if !covered(x, y) {
                        *i = 0;
                    }
                }
            }
            edges.push((
                n.min(CELL * CELL - n),
                cx,
                cy,
                voodoo::pack_tile(&indices, 4),
            ));
        }
    }
    // The ones that save the most first; equal tiles in the same palette
    // share one.
    edges.sort_by(|a, b| b.0.cmp(&a.0).then((a.2, a.1).cmp(&(b.2, b.1))));
    let mut index: std::collections::HashMap<(Vec<u8>, u16), u16> =
        std::collections::HashMap::new();
    for (saves, cx, cy, tile) in edges {
        let palette = (pano.tilemap[cy][cx] >> 10) & 7;
        let key = (tile, palette);
        let number = match index.get(&key) {
            Some(&k) => Some(k),
            None if index.len() < budget => {
                let k = (index.len() + 1) as u16;
                tiles.extend_from_slice(&key.0);
                index.insert(key, k);
                Some(k)
            }
            None => None,
        };
        match number {
            Some(k) => above[cy][cx] = voodoo::entry(k, 0, 0, 1, palette as u8),
            None => {
                // By the whole cell: `saves` is what goes to the wrong side.
                wrong += saves;
                let covered_half = {
                    let (mut c, mut t) = (0, 0);
                    for y in 0..CELL {
                        for x in 0..CELL {
                            let (px, py) = (cx * CELL + x, cy * CELL + y);
                            t += 1;
                            if px < width && py < height && front[py * width + px] {
                                c += 1;
                            }
                        }
                    }
                    c * 2 >= t
                };
                if covered_half {
                    pano.tilemap[cy][cx] |= PRIORITY;
                }
            }
        }
    }
    (tiles, above, wrong, total)
}

/// The tilemap's priority bit: in mode 1 a BG1 or BG2 cell with it goes in
/// front of the objects of priority 2, where a painted map puts the hero
/// —one step above mode 3's, see `emit_object` in the runtime—, and behind
/// those of 3, the ones above him.
const PRIORITY: u16 = 0x2000;

#[cfg(test)]
mod tests {
    use super::*;

    fn picture(w: usize, h: usize, at: impl Fn(usize, usize) -> [u8; 3]) -> rm2k_render::Picture {
        let mut p = rm2k_render::Picture::transparent(w, h);
        for y in 0..h {
            for x in 0..w {
                let c = at(x, y);
                p.rgba[(y * w + x) * 4..(y * w + x) * 4 + 4]
                    .copy_from_slice(&[c[0], c[1], c[2], 255]);
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
        let index = |t: usize| {
            voodoo::unpack_tile(&done.tiles[t * CELL_BYTES..(t + 1) * CELL_BYTES], 4)[0][0]
        };
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
    fn a_roof_goes_whole_cells_by_priority_and_edges_exactly() {
        // Three cells across: the first covered whole, the second its left
        // half, the third nothing.
        let p = picture(24, 8, |x, _| [(x * 10) as u8, 0, 0]);
        let (mut done, _) = painted(&p).unwrap();
        let front: Vec<bool> = (0..24 * 8).map(|i| i % 24 < 12).collect();
        let (tiles, above, wrong, total) = roofs(&mut done, &front, 24, 127);
        assert_eq!((wrong, total), (0, 96));
        assert_eq!(done.tilemap[0][0] & PRIORITY, PRIORITY);
        assert_eq!(done.tilemap[0][1] & PRIORITY, 0);
        assert_eq!(
            above[0],
            vec![
                0,
                voodoo::entry(1, 0, 0, 1, ((done.tilemap[0][1] >> 10) & 7) as u8),
                0
            ]
        );
        // The edge is the painting's cell with only the covered half.
        let edge = voodoo::unpack_tile(&tiles[CELL_BYTES..], 4);
        let cell = voodoo::unpack_tile(&done.tiles[CELL_BYTES..2 * CELL_BYTES], 4);
        for y in 0..CELL {
            for x in 0..CELL {
                assert_eq!(edge[y][x], if x < 4 { cell[y][x] } else { 0 });
            }
        }
        // With no room for it, it goes by the whole cell: in front, half.
        let (mut again, _) = painted(&p).unwrap();
        let (tiles, _, wrong, _) = roofs(&mut again, &front, 24, 0);
        assert_eq!((tiles.len(), wrong), (CELL_BYTES, 32));
        assert_eq!(again.tilemap[0][1] & PRIORITY, PRIORITY);
    }

    #[test]
    fn a_hole_is_refused() {
        let mut p = picture(8, 8, |_, _| [9, 9, 9]);
        p.rgba[3] = 0;
        assert!(painted(&p).is_err());
    }
}
