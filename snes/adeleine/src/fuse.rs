//! Fewer tiles than a drawing has, by merging the pair that shows the
//! least: the tiles' version of [`crate::merge_least_visible`].
//!
//! [`crate::group_tiles`] is for pictures with thousands of distinct cells
//! —grain, clouds— that have to come down to a few hundred: a k-means
//! decides the groups at once. This is for drawings a little over their
//! bank —a window, its frame, its cursor and its text, where the gradient
//! behind them made a few rows more than fit—, and it goes one merge at a
//! time: **the tile whose pixels move least, times how many cells it
//! covers, becomes its nearest**. Two rows of a gradient one step apart
//! melt first; a letter, which is far from everything, goes last. A tile
//! is also near its mirrors, when the caller's hardware can flip them.
//!
//! It does not invent tiles: the one that stays is always one of those
//! there were. And it is deterministic: the cost is an integer and ties go
//! to the lowest index.

use crate::luma_distance;
use crate::tiles::Tile;

/// How tile `i` is drawn after merging: with tile `tile`, mirrored across
/// x if `flip_x` and across y if `flip_y`. Itself and no mirror if it
/// stayed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Drawn {
    pub tile: usize,
    pub flip_x: bool,
    pub flip_y: bool,
}

/// `tile` mirrored.
pub fn flipped(tile: &Tile, flip_x: bool, flip_y: bool) -> Tile {
    let mut out = *tile;
    if flip_x {
        for row in out.iter_mut() {
            row.reverse();
        }
    }
    if flip_y {
        out.reverse();
    }
    out
}

/// How far `a` is from `b` drawn mirrored: the sum of the luma distance of
/// each pixel, a transparent one counted as black.
fn distance(a: &Tile, b: &Tile, flip_x: bool, flip_y: bool) -> i64 {
    let b = flipped(b, flip_x, flip_y);
    a.iter()
        .flatten()
        .zip(b.iter().flatten())
        .map(|(p, q)| luma_distance(p.unwrap_or([0, 0, 0]), q.unwrap_or([0, 0, 0])))
        .sum()
}

/// Merges `tiles` until at most `keep` are left, and says how each one is
/// drawn. `weights` is how many cells each tile covers; `mirrors`, whether
/// a tile can be drawn mirrored. The tiles have to be distinct —as their
/// mirrors too, with `mirrors`—: they are the drawing's tile bank. If they
/// already fit, every tile is drawn with itself.
pub fn merge_least_visible_tiles(
    tiles: &[Tile],
    weights: &[u64],
    keep: usize,
    mirrors: bool,
) -> Vec<Drawn> {
    let n = tiles.len();
    let mut drawn: Vec<Drawn> = (0..n)
        .map(|i| Drawn {
            tile: i,
            flip_x: false,
            flip_y: false,
        })
        .collect();
    if n <= keep.max(1) {
        return drawn;
    }
    let flips: &[(bool, bool)] = if mirrors {
        &[(false, false), (true, false), (false, true), (true, true)]
    } else {
        &[(false, false)]
    };
    // How far each tile is from each other one drawn with its best mirror:
    // the drawings are a few hundred tiles, and this is computed once.
    let mut near = vec![(0i64, (false, false)); n * n];
    for a in 0..n {
        for b in 0..n {
            if a != b {
                near[a * n + b] = flips
                    .iter()
                    .map(|&(fx, fy)| (distance(&tiles[a], &tiles[b], fx, fy), (fx, fy)))
                    .min_by_key(|(d, _)| *d)
                    .expect("one mirror at least");
            }
        }
    }
    let mut weight: Vec<i64> = weights.iter().map(|&w| w as i64).collect();
    let mut alive = vec![true; n];
    // Each living tile's nearest living one: it does not depend on weights,
    // so it changes only when the nearest dies.
    let nearest_of = |a: usize, alive: &[bool]| -> usize {
        (0..n)
            .filter(|&b| b != a && alive[b])
            .min_by_key(|&b| (near[a * n + b].0, b))
            .expect("two alive at least")
    };
    let mut nearest: Vec<usize> = (0..n).map(|a| nearest_of(a, &alive)).collect();
    let mut left = n;
    while left > keep.max(1) {
        let victim = (0..n)
            .filter(|&a| alive[a])
            .min_by_key(|&a| (weight[a].saturating_mul(near[a * n + nearest[a]].0), a))
            .expect("alive");
        let into = nearest[victim];
        alive[victim] = false;
        left -= 1;
        weight[into] += weight[victim];
        // Everything the victim drew —itself and what it had taken— is now
        // drawn with `into`, composing the mirrors.
        let (fx, fy) = near[victim * n + into].1;
        for d in drawn.iter_mut().filter(|d| d.tile == victim) {
            *d = Drawn {
                tile: into,
                flip_x: d.flip_x ^ fx,
                flip_y: d.flip_y ^ fy,
            };
        }
        if left > 1 {
            for a in 0..n {
                if alive[a] && nearest[a] == victim {
                    nearest[a] = nearest_of(a, &alive);
                }
            }
        }
    }
    drawn
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tiles::SIDE;

    fn solid(c: u8) -> Tile {
        [[Some([c, c, c]); SIDE]; SIDE]
    }

    fn letter() -> Tile {
        let mut t = solid(0);
        for (y, row) in t.iter_mut().enumerate() {
            row[y] = Some([31, 31, 31]);
        }
        t
    }

    #[test]
    fn what_fits_is_kept() {
        let tiles = [solid(1), solid(2)];
        let drawn = merge_least_visible_tiles(&tiles, &[1, 1], 2, false);
        assert_eq!(drawn.iter().map(|d| d.tile).collect::<Vec<_>>(), vec![0, 1]);
    }

    #[test]
    fn two_rows_of_a_gradient_melt_before_a_letter() {
        // Three steps of a gradient and a letter, one tile too many: the
        // two nearest steps merge, the lighter one into the heavier.
        let tiles = [solid(10), solid(11), solid(20), letter()];
        let drawn = merge_least_visible_tiles(&tiles, &[5, 1, 5, 1], 3, false);
        assert_eq!(drawn[1].tile, 0);
        assert_eq!(drawn[3].tile, 3);
        assert_eq!(drawn[2].tile, 2);
    }

    #[test]
    fn a_tile_merges_into_the_mirror_of_its_nearest() {
        let mut a = solid(0);
        a[0][0] = Some([31, 0, 0]);
        let mut b = solid(0);
        b[0][SIDE - 1] = Some([31, 0, 0]);
        b[1][1] = Some([1, 0, 0]);
        let drawn = merge_least_visible_tiles(&[a, b, solid(31)], &[3, 1, 3], 2, true);
        assert_eq!(
            drawn[1],
            Drawn {
                tile: 0,
                flip_x: true,
                flip_y: false
            }
        );
        assert_eq!(flipped(&a, true, false)[0][SIDE - 1], Some([31, 0, 0]));
    }
}
