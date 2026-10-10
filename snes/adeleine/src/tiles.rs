//! Fewer tiles than a picture has: which ones are drawn with another.
//!
//! A tile layer names its tiles with ten bits, and video memory holds far
//! fewer than that when it is shared: a picture with grain, the size of a
//! few screens, has thousands of distinct cells. So the cells are grouped
//! into as many as fit, by **vector quantisation** —a k-means over the
//! tiles—, and each group is drawn with one of its own tiles. Two choices,
//! the ones `rm2k-snes-images` measured for its mode 7 textures:
//!
//! * **They are grouped by their shape, not pixel by pixel**: each tile
//!   averaged two by two, so that grain, which is noise, does not decide
//!   which group a piece of cloud joins.
//! * **The group is drawn with the member closest to the others** —its
//!   medoid—, not with their mean: the mean of tiles with grain is a smooth
//!   tile, in colours the picture does not have, and it shows as stains.
//!
//! The k-means is seeded without chance —each new centre is the tile
//! farthest from the ones already chosen—, so the same picture gives the
//! same grouping on every run.

use crate::Color;

/// The side of a tile, and its pixels.
pub const SIDE: usize = 8;
/// A tile: its pixels, row by row, `None` where it draws nothing —which
/// counts as black, the backdrop under it—.
pub type Tile = [[Option<Color>; SIDE]; SIDE];

/// A tile averaged two by two: sixteen pixels of three channels.
const SHAPE: usize = 3 * SIDE * SIDE / 4;
/// How many rounds the k-means goes at most; it usually settles before.
const ROUNDS: usize = 40;

type Shape = [f32; SHAPE];

/// For each tile, the tile that draws it, so that at most `max` different
/// ones are left: itself if they already fit. `weights` is how many cells
/// each tile is, which decides where the centres go.
pub fn group_tiles(tiles: &[Tile], weights: &[f32], max: usize) -> Vec<usize> {
    if tiles.len() <= max || max == 0 {
        return (0..tiles.len()).collect();
    }
    let shapes: Vec<Shape> = tiles.iter().map(shape).collect();
    let group = kmeans(&shapes, weights, max);
    medoids(&shapes, weights, &group, max)
}

fn shape(tile: &Tile) -> Shape {
    let mut out = [0.0f32; SHAPE];
    for (y, row) in tile.iter().enumerate() {
        for (x, pixel) in row.iter().enumerate() {
            let c = pixel.unwrap_or([0, 0, 0]);
            let at = ((y / 2) * (SIDE / 2) + x / 2) * 3;
            for ch in 0..3 {
                out[at + ch] += c[ch] as f32 / 4.0;
            }
        }
    }
    out
}

fn distance(a: &Shape, b: &Shape) -> f32 {
    a.iter().zip(b).map(|(x, y)| (x - y) * (x - y)).sum()
}

fn nearest(s: &Shape, centres: &[Shape]) -> usize {
    let mut best = (0, f32::INFINITY);
    for (j, c) in centres.iter().enumerate() {
        let d = distance(s, c);
        if d < best.1 {
            best = (j, d);
        }
    }
    best.0
}

/// The group of each shape, `k` groups, weighted by how many cells each is.
///
/// The first centre is the heaviest shape —the first of them, on a tie—,
/// and each next one the shape farthest from all the centres so far,
/// weighted: k-means++ without its dice.
fn kmeans(shapes: &[Shape], weight: &[f32], k: usize) -> Vec<usize> {
    let first = (0..shapes.len()).fold(0, |best, i| if weight[i] > weight[best] { i } else { best });
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
fn medoids(shapes: &[Shape], weight: &[f32], group: &[usize], k: usize) -> Vec<usize> {
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

    fn solid(c: u8) -> Tile {
        [[Some([c, c, c]); SIDE]; SIDE]
    }

    #[test]
    fn what_fits_is_kept_as_it_is() {
        let tiles = [solid(1), solid(2), solid(3)];
        assert_eq!(group_tiles(&tiles, &[1.0; 3], 3), vec![0, 1, 2]);
    }

    #[test]
    fn what_does_not_fit_is_drawn_by_one_of_its_own() {
        // Two near greys and one far: the near ones end up together, and
        // the far one keeps its own tile.
        let tiles = [solid(1), solid(2), solid(30)];
        let drawn = group_tiles(&tiles, &[1.0, 5.0, 1.0], 2);
        assert_eq!(drawn[0], drawn[1]);
        assert_eq!(drawn[2], 2);
        assert!(drawn[0] < 2);
    }

    #[test]
    fn the_same_tiles_give_the_same_grouping() {
        let tiles: Vec<Tile> = (0..40).map(|i| solid(i as u8 % 31)).collect();
        let weights = vec![1.0; 40];
        assert_eq!(group_tiles(&tiles, &weights, 7), group_tiles(&tiles, &weights, 7));
    }
}
