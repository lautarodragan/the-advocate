//! Fitting the colours into palettes, and losing the ones that do not fit.
//!
//! Two jobs that always turn up together. **Packing** decides which palette
//! each cell uses, and it is allowed to repeat a colour across palettes: all
//! that has to hold is that every cell's colours are contained in *some*
//! palette. **Merging** is what happens when no packing exists — some colour
//! has to go, and the question is which one hurts least.
//!
//! Both are deterministic down to the tie-breaks, on purpose. There is no
//! single right answer to either, so the only useful property is that the same
//! input gives the same output every time, on every machine, in every order
//! the caller happens to hand things over. Every comparison here therefore
//! ends in the colour itself, which is a total order.

use crate::color::{luma_distance, Rgb15};
use crate::fail::{Bad, Result};
use crate::grid::{color_counts, tile_colors, Grid, Tile};
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// How many colours a 4-bit palette holds, index 0 included.
pub const COLORS_PER_PALETTE: usize = 16;

/// How many of those a cell may actually use: index 0 is transparent.
pub const USABLE_COLORS: usize = COLORS_PER_PALETTE - 1;

/// Spread the colours over palettes so that every cell uses only one.
///
/// Best-fit: the cells with the most colours first, each into whichever
/// palette grows least by taking it. Returns `None` when it cannot be done
/// with `limit` palettes of `per_palette` colours — which is an answer, not a
/// failure: the caller decides whether to merge colours and ask again.
///
/// The order is `(most colours first, then the colours themselves)`. The
/// second half of that is what makes this reproducible: ties on size are
/// extremely common — every cell with two colours ties with every other — and
/// leaving them to whatever order the caller's container happened to have
/// would silently change which palettes come out.
pub fn try_pack(
    sets: &BTreeSet<BTreeSet<Rgb15>>,
    limit: usize,
    per_palette: usize,
) -> Option<Vec<BTreeSet<Rgb15>>> {
    // The sets arrive in lexicographic order, so a *stable* sort on size
    // leaves the colours themselves as the tie-break.
    let mut order: Vec<&BTreeSet<Rgb15>> = sets.iter().collect();
    order.sort_by_key(|s| std::cmp::Reverse(s.len()));

    let mut groups: Vec<BTreeSet<Rgb15>> = Vec::new();
    for colors in order {
        let mut best: Option<(usize, usize)> = None;
        for (index, group) in groups.iter().enumerate() {
            let size = group.union(colors).count();
            if size <= per_palette && best.is_none_or(|(_, b)| size < b) {
                best = Some((index, size));
            }
        }
        match best {
            Some((index, _)) => groups[index].extend(colors.iter().copied()),
            None if groups.len() < limit => groups.push(colors.clone()),
            None => return None,
        }
    }
    Some(groups)
}

/// What a run of merges did.
#[derive(Debug)]
pub struct Merge {
    /// Where every original colour ended up. A colour that survived maps to
    /// itself.
    pub mapping: BTreeMap<Rgb15, Rgb15>,
    /// The merges in the order they were made: victim, target, and how many
    /// pixels the victim covered when it went.
    pub merged: Vec<(Rgb15, Rgb15, u64)>,
}

impl Merge {
    /// The colour a pixel becomes. A colour that was never in the counts maps
    /// to itself.
    pub fn of(&self, color: Rgb15) -> Rgb15 {
        *self.mapping.get(&color).unwrap_or(&color)
    }

    /// A cell with every colour replaced.
    pub fn tile(&self, tile: &Tile) -> Tile {
        let mut out = *tile;
        for row in out.iter_mut() {
            for pixel in row.iter_mut() {
                if let Some(color) = pixel {
                    *pixel = Some(self.of(*color));
                }
            }
        }
        out
    }
}

/// Merge the pair of colours that shows least, until `accept` says stop.
///
/// "Shows least" is **how many pixels move, times how far they move**: sending
/// colour `a` to colour `b` costs `pixels(a) * luma_distance(a, b)`, which is
/// the error the change adds to the picture. The cheapest pair goes, the
/// victim's pixels are added to the survivor, and it repeats.
///
/// The obvious alternative — kill the least used colour — is worse, and
/// visibly so. A colour can cover very few pixels and still *define* the
/// drawing: a highlight, an eye, the rim of a helmet. Sending it ten units
/// away is seen. Meanwhile two near-identical greys covering half the picture
/// both survive, because neither is the least used. Weighting by distance
/// flips that around: the two greys merge for almost nothing and the highlight
/// stays.
///
/// No colour is invented: the survivor is always one that was already there,
/// so there is nothing to re-quantise afterwards and the result does not
/// depend on the arithmetic of whatever library produced the picture.
pub fn merge_until<T, F>(counts: &BTreeMap<Rgb15, u64>, mut accept: F) -> Result<(Merge, T)>
where
    F: FnMut(&Merge, &BTreeSet<Rgb15>) -> Option<T>,
{
    let mut state = Merge {
        mapping: counts.keys().map(|c| (*c, *c)).collect(),
        merged: Vec::new(),
    };
    let mut weight: BTreeMap<Rgb15, u64> = counts.clone();
    let mut alive: BTreeSet<Rgb15> = counts.keys().copied().collect();

    // The cheapest neighbour of every surviving colour, and what it costs to
    // go there. Only the colours whose neighbour just died —and the one that
    // just grew— are recomputed, which is what keeps this out of cubic time:
    // a busy picture reaches three hundred colours and merges a hundred.
    let mut near: BTreeMap<Rgb15, (u64, Rgb15)> = BTreeMap::new();
    for color in alive.iter().copied().collect::<Vec<_>>() {
        recalculate(color, &alive, &weight, &mut near);
    }

    loop {
        if let Some(value) = accept(&state, &alive) {
            return Ok((state, value));
        }
        if alive.len() <= 1 {
            return Err(Bad::answer(
                "the palette cannot be reduced any further: one colour is left \
                 and it still does not fit",
            ));
        }

        let victim = *alive
            .iter()
            .min_by_key(|c| {
                let (cost, neighbour) = near[*c];
                (cost, **c, neighbour)
            })
            .expect("alive is not empty");
        let target = near[&victim].1;

        for current in state.mapping.values_mut() {
            if *current == victim {
                *current = target;
            }
        }
        state.merged.push((victim, target, weight[&victim]));
        let moved = weight[&victim];
        *weight.get_mut(&target).expect("target is alive") += moved;
        alive.remove(&victim);
        near.remove(&victim);

        recalculate(target, &alive, &weight, &mut near);
        let orphans: Vec<Rgb15> = alive
            .iter()
            .copied()
            .filter(|c| *c != target && near[c].1 == victim)
            .collect();
        for color in orphans {
            recalculate(color, &alive, &weight, &mut near);
        }
    }
}

fn recalculate(
    color: Rgb15,
    alive: &BTreeSet<Rgb15>,
    weight: &BTreeMap<Rgb15, u64>,
    near: &mut BTreeMap<Rgb15, (u64, Rgb15)>,
) {
    let neighbour = alive
        .iter()
        .filter(|o| **o != color)
        .min_by_key(|o| (luma_distance(color, **o), **o))
        .copied();
    match neighbour {
        None => {
            near.remove(&color);
        }
        Some(other) => {
            near.insert(color, (weight[&color] * luma_distance(color, other), other));
        }
    }
}

/// Merge until at most `keep` colours are left.
pub fn merge_to(counts: &BTreeMap<Rgb15, u64>, keep: usize) -> Result<Merge> {
    let (merge, ()) = merge_until(counts, |_, alive| (alive.len() <= keep).then_some(()))?;
    Ok(merge)
}

/// What reducing a grid produced.
pub struct Reduced {
    /// The grid with every colour replaced by the one it merged into.
    pub grid: Grid,
    /// The palettes the reduced grid packs into.
    pub groups: Vec<BTreeSet<Rgb15>>,
    /// The merges that were needed, in order.
    pub merged: Vec<(Rgb15, Rgb15, u64)>,
    /// What each colour covered before any of this.
    pub counts: BTreeMap<Rgb15, u64>,
}

/// Merge colours until the cells fit in `limit` palettes.
///
/// The real limit is not how many colours there are but how they are spread: a
/// cell with fourteen colours forces those fourteen into one palette. The tail
/// of the distribution is usually colours covering one or two pixels, so
/// merging the cheapest pair and trying the packing again costs very little.
///
/// The work is done on the distinct cells, which number in the hundreds, and
/// not on the grid, which can be tens of thousands.
pub fn reduce_colors(grid: &Grid, limit: usize, per_palette: usize) -> Result<Reduced> {
    let counts = color_counts(&[grid]);
    let unique: Vec<Tile> = {
        let mut seen: BTreeSet<Vec<Option<Rgb15>>> = BTreeSet::new();
        let mut out = Vec::new();
        for tile in grid.cells() {
            let key: Vec<Option<Rgb15>> = tile.iter().flatten().copied().collect();
            if seen.insert(key) {
                out.push(*tile);
            }
        }
        out
    };

    let (merge, groups) = merge_until(&counts, |state, _| {
        let sets: BTreeSet<BTreeSet<Rgb15>> = unique
            .iter()
            .map(|tile| tile_colors(&state.tile(tile)))
            .collect();
        // A packing whose palettes are all within capacity, which is stricter
        // than what `try_pack` alone answers: a cell with more colours than a
        // palette holds opens an oversized group there and would be taken for
        // a fit. Here that is the one case merging is *for* — the cell has to
        // lose colours until it fits — so it has to be asked about.
        try_pack(&sets, limit, per_palette)
            .filter(|groups| groups.iter().all(|g| g.len() <= per_palette))
    })?;

    let remapped = Grid {
        columns: grid.columns,
        rows: grid
            .rows
            .iter()
            .map(|row| row.iter().map(|tile| merge.tile(tile)).collect())
            .collect(),
    };
    Ok(Reduced {
        grid: remapped,
        groups,
        merged: merge.merged,
        counts,
    })
}

/// Which palette a cell's colours fit in, if any.
pub fn palette_for(colors: &BTreeSet<Rgb15>, palettes: &[Vec<Rgb15>]) -> Option<usize> {
    palettes
        .iter()
        .position(|palette| colors.iter().all(|c| palette.contains(c)))
}

/// Groups as palettes: each one's colours in a fixed order.
pub fn as_palettes(groups: &[BTreeSet<Rgb15>]) -> Vec<Vec<Rgb15>> {
    groups
        .iter()
        .map(|g| g.iter().copied().collect::<Vec<_>>())
        .collect()
}

/// A colour counts map keyed by colour, from pairs.
pub fn counts_of<I: IntoIterator<Item = (Rgb15, u64)>>(pairs: I) -> BTreeMap<Rgb15, u64> {
    let mut map = BTreeMap::new();
    for (color, n) in pairs {
        *map.entry(color).or_insert(0) += n;
    }
    map
}

/// Distinct cells, so a caller can count them without re-deriving the set.
pub fn distinct_cells(grid: &Grid) -> usize {
    let mut seen: HashMap<Vec<Option<Rgb15>>, ()> = HashMap::new();
    for tile in grid.cells() {
        seen.insert(tile.iter().flatten().copied().collect(), ());
    }
    seen.len()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn set(colors: &[Rgb15]) -> BTreeSet<Rgb15> {
        colors.iter().copied().collect()
    }

    #[test]
    fn two_cells_that_share_their_colours_share_a_palette() {
        let sets: BTreeSet<_> = [set(&[(1, 1, 1), (2, 2, 2)]), set(&[(2, 2, 2)])]
            .into_iter()
            .collect();
        let groups = try_pack(&sets, 4, USABLE_COLORS).unwrap();
        assert_eq!(groups.len(), 1);
    }

    /// A set that is already too big for one palette is still opened as a new
    /// group, oversized, rather than refused. That is on purpose and it is why
    /// `convert` checks the busiest cell before it ever gets here: best-fit has
    /// nothing to say about a set that fits nowhere, and answering `None` here
    /// would make "these cells cannot be grouped" and "this one cell is too
    /// big" the same answer, which are the two different things a caller has to
    /// be told apart.
    #[test]
    fn a_set_too_big_for_any_palette_comes_back_oversized_not_refused() {
        let many: Vec<Rgb15> = (0..16u8).map(|i| (i, 0, 0)).collect();
        let sets: BTreeSet<_> = [set(&many)].into_iter().collect();
        let groups = try_pack(&sets, 8, USABLE_COLORS).unwrap();
        assert_eq!(groups[0].len(), 16);
    }

    /// With no room left for a new group it does refuse, which is the answer
    /// that means "merge some colours and ask again".
    #[test]
    fn with_no_palette_left_to_open_it_refuses() {
        let sets: BTreeSet<_> = [
            set(&[(1, 0, 0), (2, 0, 0)]),
            set(&[(3, 0, 0), (4, 0, 0)]),
        ]
        .into_iter()
        .collect();
        assert!(try_pack(&sets, 1, 2).is_none());
    }

    #[test]
    fn packing_does_not_depend_on_the_order_the_caller_had() {
        let a = set(&[(1, 0, 0), (2, 0, 0)]);
        let b = set(&[(3, 0, 0), (4, 0, 0)]);
        let one: BTreeSet<_> = [a.clone(), b.clone()].into_iter().collect();
        let two: BTreeSet<_> = [b, a].into_iter().collect();
        assert_eq!(
            try_pack(&one, 2, 2).unwrap(),
            try_pack(&two, 2, 2).unwrap()
        );
    }

    /// The point of weighting by distance: a nearly identical pair goes even
    /// though one of them covers the whole picture, and the lone highlight
    /// that covers four pixels stays.
    #[test]
    fn the_cheapest_pair_goes_not_the_least_used_colour() {
        let counts = counts_of([
            ((10, 10, 10), 500),
            ((10, 10, 11), 500),
            ((31, 31, 31), 4),
        ]);
        let merge = merge_to(&counts, 2).unwrap();
        assert_eq!(merge.merged.len(), 1);
        let (victim, target, _) = merge.merged[0];
        assert!(victim == (10, 10, 10) || victim == (10, 10, 11), "{victim:?}");
        assert!(target == (10, 10, 10) || target == (10, 10, 11), "{target:?}");
        assert_eq!(merge.of((31, 31, 31)), (31, 31, 31));
    }

    #[test]
    fn merging_invents_no_colour() {
        let counts = counts_of([((0, 0, 0), 1), ((4, 4, 4), 1), ((31, 31, 31), 1)]);
        let merge = merge_to(&counts, 1).unwrap();
        for survivor in merge.mapping.values() {
            assert!(counts.contains_key(survivor), "{survivor:?}");
        }
    }

    #[test]
    fn asking_for_no_colours_at_all_is_refused_and_says_why() {
        let counts = counts_of([((0, 0, 0), 1), ((4, 4, 4), 1)]);
        let e = merge_to(&counts, 0).unwrap_err();
        assert!(e.message().contains("cannot be reduced any further"), "{e}");
    }
}
