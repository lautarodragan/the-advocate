//! A big picture as a mode 7 texture, for a `MovePicture` that zooms it:
//! the layer's own pixels —the same colour-memory entries, so nothing
//! changes in the palette when the console switches modes— in 8x8 tiles of
//! a byte a pixel, and a map of a byte a cell.
//!
//! **The map names 256 tiles, and a photo the size of the screen has 896
//! cells**, almost all different when it has grain. So the cells are
//! grouped into as many as fit, by **vector quantisation**: a k-means over
//! the tiles, and each group drawn with one of its own tiles. Two choices,
//! both measured in the pilot —`el-piloto-del-modo-7.md` in A Blurred
//! Line's tasks—:
//!
//! * **They are grouped by their shape, not pixel by pixel**: each tile
//!   averaged two by two, so that the grain of grass or of earth, which is
//!   noise, does not decide which group a piece of tree joins.
//! * **The group is drawn with the tile of the picture closest to the
//!   others** —its medoid—, not with their mean: the mean of tiles with
//!   grain is a smooth tile, in colours the picture does not have, and it
//!   shows as stains.
//!
//! The k-means is seeded without chance —each new centre is the tile
//! farthest from the ones already chosen—, so the same picture gives the
//! same texture on every run.

use adeleine::Color;
use std::collections::HashMap;

/// The side of a cell, and its pixels.
const CELL: usize = 8;
const PIXELS: usize = CELL * CELL;
/// A tile averaged two by two: sixteen pixels of three channels.
const SHAPE: usize = 3 * PIXELS / 4;
/// How many rounds the k-means goes at most; it usually settles before.
const ROUNDS: usize = 40;

/// The texture.
pub struct Texture {
    /// Its tiles, a byte a pixel row by row, tile 0 blank.
    pub tiles: Vec<u8>,
    pub tile_count: usize,
    /// A tile per cell, row by row, as many columns as the layer.
    pub map: Vec<u8>,
    /// How many different tiles the picture had, the blank one included:
    /// over `tile_count`, the rest were grouped.
    pub distinct: usize,
}

/// The texture of a layer `columns` cells wide whose pixels are `pixels`
/// —colour-memory entries, 0 where nothing is drawn— in at most `max_tiles`
/// tiles, the blank one included. `colors` gives each entry's colour.
pub fn texture(pixels: &[u8], columns: usize, colors: &[Color], max_tiles: usize) -> Texture {
    let width = columns * CELL;
    let rows = pixels.len() / width / CELL;
    let mut cells: Vec<[u8; PIXELS]> = Vec::with_capacity(rows * columns);
    for cy in 0..rows {
        for cx in 0..columns {
            let mut tile = [0u8; PIXELS];
            for y in 0..CELL {
                let at = (cy * CELL + y) * width + cx * CELL;
                tile[y * CELL..(y + 1) * CELL].copy_from_slice(&pixels[at..at + CELL]);
            }
            cells.push(tile);
        }
    }
    // The distinct tiles that draw something, in the order they are met,
    // each with how many cells it is.
    let mut distinct: Vec<[u8; PIXELS]> = Vec::new();
    let mut weight: Vec<f32> = Vec::new();
    let mut index: HashMap<[u8; PIXELS], usize> = HashMap::new();
    let mut of_cell: Vec<Option<usize>> = Vec::with_capacity(cells.len());
    for tile in &cells {
        if tile.iter().all(|&p| p == 0) {
            of_cell.push(None);
            continue;
        }
        let k = *index.entry(*tile).or_insert_with(|| {
            distinct.push(*tile);
            weight.push(0.0);
            distinct.len() - 1
        });
        weight[k] += 1.0;
        of_cell.push(Some(k));
    }
    let room = max_tiles.saturating_sub(1);
    // Which distinct tile draws each distinct tile: itself, if they fit.
    let drawn_by: Vec<usize> = if distinct.len() <= room {
        (0..distinct.len()).collect()
    } else {
        let shapes: Vec<[f32; SHAPE]> = distinct.iter().map(|t| shape(t, colors)).collect();
        let group = kmeans(&shapes, &weight, room);
        medoids(&shapes, &weight, &group, room)
    };
    // The texture: tile 0 blank, then the ones that draw, in order.
    let mut tiles = vec![0u8; PIXELS];
    let mut number: HashMap<usize, u8> = HashMap::new();
    for &k in &drawn_by {
        if let std::collections::hash_map::Entry::Vacant(e) = number.entry(k) {
            e.insert((tiles.len() / PIXELS) as u8);
            tiles.extend_from_slice(&distinct[k]);
        }
    }
    let map = of_cell
        .iter()
        .map(|c| c.map_or(0, |k| number[&drawn_by[k]]))
        .collect();
    Texture {
        tile_count: tiles.len() / PIXELS,
        tiles,
        map,
        distinct: distinct.len() + 1,
    }
}

/// A tile's shape: its colours averaged two by two, what is not drawn
/// black, which is the screen's backdrop under it.
fn shape(tile: &[u8; PIXELS], colors: &[Color]) -> [f32; SHAPE] {
    let mut out = [0.0f32; SHAPE];
    for y in 0..CELL {
        for x in 0..CELL {
            let entry = tile[y * CELL + x] as usize;
            let c = if entry == 0 { [0, 0, 0] } else { colors[entry] };
            let at = ((y / 2) * (CELL / 2) + x / 2) * 3;
            for ch in 0..3 {
                out[at + ch] += c[ch] as f32 / 4.0;
            }
        }
    }
    out
}

fn distance(a: &[f32; SHAPE], b: &[f32; SHAPE]) -> f32 {
    a.iter().zip(b).map(|(x, y)| (x - y) * (x - y)).sum()
}

/// The group of each shape, `k` groups, weighted by how many cells each is.
///
/// The first centre is the heaviest shape —the first of them, on a tie—,
/// and each next one the shape farthest from all the centres so far,
/// weighted: k-means++ without its dice.
fn kmeans(shapes: &[[f32; SHAPE]], weight: &[f32], k: usize) -> Vec<usize> {
    let first = (0..shapes.len())
        .fold(0, |best, i| if weight[i] > weight[best] { i } else { best });
    let mut centres = vec![shapes[first]];
    let mut near: Vec<f32> = shapes.iter().map(|s| distance(s, &shapes[first])).collect();
    while centres.len() < k {
        let far = (0..shapes.len()).fold(0, |best, i| {
            if near[i] * weight[i] > near[best] * weight[best] {
                i
            } else {
                best
            }
        });
        centres.push(shapes[far]);
        for (i, s) in shapes.iter().enumerate() {
            near[i] = near[i].min(distance(s, &shapes[far]));
        }
    }
    let nearest = |s: &[f32; SHAPE], centres: &[[f32; SHAPE]]| {
        let mut best = (0, f32::INFINITY);
        for (j, c) in centres.iter().enumerate() {
            let d = distance(s, c);
            if d < best.1 {
                best = (j, d);
            }
        }
        best.0
    };
    let mut group: Vec<usize> = shapes.iter().map(|s| nearest(s, &centres)).collect();
    for _ in 0..ROUNDS {
        let mut sums = vec![[0.0f32; SHAPE]; k];
        let mut totals = vec![0.0f32; k];
        for (i, s) in shapes.iter().enumerate() {
            let g = group[i];
            totals[g] += weight[i];
            for (sum, v) in sums[g].iter_mut().zip(s) {
                *sum += v * weight[i];
            }
        }
        for j in 0..k {
            // A group left empty keeps its centre.
            if totals[j] > 0.0 {
                for v in sums[j].iter_mut() {
                    *v /= totals[j];
                }
                centres[j] = sums[j];
            }
        }
        let next: Vec<usize> = shapes.iter().map(|s| nearest(s, &centres)).collect();
        if next == group {
            break;
        }
        group = next;
    }
    group
}

/// Each shape's group drawn by its medoid: the member with the least
/// weighted distance to the rest of its group.
fn medoids(shapes: &[[f32; SHAPE]], weight: &[f32], group: &[usize], k: usize) -> Vec<usize> {
    let mut members: Vec<Vec<usize>> = vec![Vec::new(); k];
    for (i, &g) in group.iter().enumerate() {
        members[g].push(i);
    }
    let mut medoid = vec![0usize; k];
    for (g, m) in members.iter().enumerate() {
        let mut best = (usize::MAX, f32::INFINITY);
        for &i in m {
            let cost: f32 = m.iter().map(|&j| weight[j] * distance(&shapes[i], &shapes[j])).sum();
            if cost < best.1 {
                best = (i, cost);
            }
        }
        medoid[g] = best.0;
    }
    group.iter().map(|&g| medoid[g]).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Entry `i` is a grey of `i`.
    fn greys() -> Vec<Color> {
        (0..256).map(|i| [(i % 32) as u8; 3]).collect()
    }

    /// A layer of `columns` cells in one row, cell `c` filled with `fill(c)`.
    fn row(columns: usize, fill: impl Fn(usize) -> u8) -> Vec<u8> {
        let mut out = vec![0u8; columns * PIXELS];
        for y in 0..CELL {
            for c in 0..columns {
                for x in 0..CELL {
                    out[y * columns * CELL + c * CELL + x] = fill(c);
                }
            }
        }
        out
    }

    #[test]
    fn what_fits_is_kept_as_it_is() {
        // Four cells: blank, 5, 7 and 5 again.
        let pixels = row(4, |c| [0, 5, 7, 5][c]);
        let t = texture(&pixels, 4, &greys(), 256);
        assert_eq!(t.map, [0, 1, 2, 1]);
        assert_eq!((t.tile_count, t.distinct), (3, 3));
        assert!(t.tiles[..PIXELS].iter().all(|&p| p == 0), "tile 0 is blank");
        assert!(t.tiles[PIXELS..2 * PIXELS].iter().all(|&p| p == 5));
    }

    #[test]
    fn what_does_not_fit_is_drawn_by_the_closest_of_its_own() {
        // Six flat cells, 1, 2, 3 and 20, 21, 22, in two tiles and the
        // blank one: the dark ones together and the light ones together,
        // each drawn by its middle one.
        let shades = [1u8, 2, 3, 20, 21, 22];
        let pixels = row(6, |c| shades[c]);
        let t = texture(&pixels, 6, &greys(), 3);
        assert_eq!(t.tile_count, 3);
        assert_eq!(t.distinct, 7);
        assert_eq!(t.map[0], t.map[1]);
        assert_eq!(t.map[0], t.map[2]);
        assert_eq!(t.map[3], t.map[4]);
        assert_eq!(t.map[3], t.map[5]);
        let drawn = |cell: usize| t.tiles[t.map[cell] as usize * PIXELS];
        assert_eq!(drawn(0), 2, "the dark ones' medoid");
        assert_eq!(drawn(3), 21, "the light ones'");
    }

    #[test]
    fn the_same_picture_gives_the_same_texture() {
        let pixels = row(40, |c| (c * 7 % 31 + 1) as u8);
        let a = texture(&pixels, 40, &greys(), 9);
        let b = texture(&pixels, 40, &greys(), 9);
        assert_eq!((a.tiles, a.map), (b.tiles, b.map));
    }
}
