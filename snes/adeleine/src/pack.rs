//! Grouping colours into palettes so that every tile draws with one of them.

use crate::fail::Result;
use crate::merge::luma_distance;
use crate::Bad;
use crate::Color;
use std::cmp::Reverse;
use std::collections::{BTreeMap, BTreeSet, BinaryHeap};

/// A palette as it is being built, or a tile's colours: which colours, in
/// order.
pub type Colors = BTreeSet<Color>;

/// Splits the colours into at most `limit` palettes of at most `per_palette`
/// colours each, so that each tile uses only one. `None` if they do not fit.
///
/// Colours may repeat across palettes: what has to be achieved is that the
/// set of colours of each tile is contained in one of them. Best-fit, the
/// tiles with the most colours first, each into the group that grows the
/// least; on a tie, the first group.
///
/// Tiles with the same number of colours go **in the order of their
/// colours**, so what comes out depends on which tiles there are and not on
/// the order they were handed in. The Python this replaced used to take them
/// in the order of a Python `set`, which is the order of CPython's hashes and
/// nothing another language can reproduce; it moved to this order first, on
/// its own.
///
/// A tile with more colours than a palette holds fits in none, so it is
/// `None` too, and `reduce_colors` merges until it fits. Until 2026-10-05 it
/// went in as a group of its own, of that many colours, and the palette
/// spilled into the next one: the tile was drawn with two.
pub fn try_pack(tiles: &[Colors], limit: usize, per_palette: usize) -> Option<Vec<Colors>> {
    if tiles.iter().any(|t| t.len() > per_palette) {
        return None;
    }
    let mut order: Vec<&Colors> = tiles.iter().collect();
    order.sort_by(|a, b| b.len().cmp(&a.len()).then_with(|| a.cmp(b)));
    let mut groups: Vec<Colors> = Vec::new();
    for colors in order {
        let mut best: Option<(usize, usize)> = None;
        for (index, group) in groups.iter().enumerate() {
            let size = group.len() + colors.difference(group).count();
            if size <= per_palette && best.is_none_or(|(_, s)| size < s) {
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

/// What one tile becomes in a palette reduction.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReducedTile {
    /// The palette this tile uses; `None` for a transparent tile.
    pub palette: Option<usize>,
    /// For each colour of the tile, in sorted order, the colour it becomes.
    pub mapping: Vec<Color>,
}

/// One palette-local colour change. The same source colour may have a
/// different target in another palette: that is precisely what a global
/// merge could not express.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PaletteMerge {
    pub palette: usize,
    pub victim: Color,
    pub target: Color,
    pub pixels: u64,
}

/// What `reduce_colors` decided.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Reduced {
    /// The palettes, in the order their indices use.
    pub palettes: Vec<Colors>,
    /// What each tile of the request becomes, in the order given.
    pub tiles: Vec<ReducedTile>,
    /// Palette-local changes, sorted by palette, source and target.
    pub merges: Vec<PaletteMerge>,
}

/// Reduces the tiles into at most `limit` palettes.
///
/// If they already fit, this is exactly [`try_pack`]: every colour stays and
/// the same best-fit palettes come out. Otherwise tiles are clustered by
/// their mean colour, each cluster chooses its own `per_palette` colours,
/// and every tile maps to the nearest colour of its cluster's palette. The
/// chosen colours always came from the tiles; nothing is invented.
///
/// `counts` is every colour with its pixels over the whole picture, and
/// `tiles` the colours of each tile. Counts are distributed exactly among
/// the tiles that use a colour, which lets repeated tiles carry their share
/// of the picture without requiring a count for every tile in the request.
/// All choices and ties use integer costs and sorted colours, so the answer
/// is deterministic.
pub fn reduce_colors(
    counts: &[(Color, u64)],
    tiles: &[Colors],
    limit: usize,
    per_palette: usize,
) -> Result<Reduced> {
    let nonempty: Vec<Colors> = tiles.iter().filter(|t| !t.is_empty()).cloned().collect();
    if nonempty.is_empty() {
        return Ok(Reduced {
            palettes: Vec::new(),
            tiles: vec![
                ReducedTile {
                    palette: None,
                    mapping: Vec::new()
                };
                tiles.len()
            ],
            merges: Vec::new(),
        });
    }
    if limit == 0 || per_palette == 0 {
        return Err(Bad::answer("The palette could not be reduced enough."));
    }

    let weights = tile_weights(counts, tiles)?;
    if let Some(palettes) = try_pack(&nonempty, limit, per_palette) {
        let decided = tiles
            .iter()
            .map(|tile| ReducedTile {
                palette: (!tile.is_empty()).then(|| {
                    palettes
                        .iter()
                        .position(|p| tile.is_subset(p))
                        .expect("try_pack fitted every tile")
                }),
                mapping: tile.iter().copied().collect(),
            })
            .collect();
        return Ok(Reduced {
            palettes,
            tiles: decided,
            merges: Vec::new(),
        });
    }

    let active: Vec<usize> = tiles
        .iter()
        .enumerate()
        .filter_map(|(i, tile)| (!tile.is_empty()).then_some(i))
        .collect();
    let groups = limit.min(active.len());
    let mut assigned = initial_groups(tiles, &weights, &active, groups);
    // The palettes of the groups as they are now: choosing them is most of
    // the time, so it is done once per assignment, the last one included.
    let mut palettes = choose_palettes(tiles, &weights, &active, &assigned, groups, per_palette);
    for _ in 0..12 {
        let mut next: Vec<usize> = active
            .iter()
            .map(|&i| {
                palettes
                    .iter()
                    .enumerate()
                    .min_by_key(|(g, palette)| (tile_cost(&weights[i], palette), *g))
                    .map(|(g, _)| g)
                    .expect("there is at least one palette")
            })
            .collect();
        fill_empty_groups(&mut next, &active, tiles, &weights, &palettes, groups);
        if next == assigned {
            break;
        }
        assigned = next;
        palettes = choose_palettes(tiles, &weights, &active, &assigned, groups, per_palette);
    }

    // An iteration may leave a group empty. Empty palettes buy nothing and
    // would make their indices depend on an implementation detail.
    let used: BTreeSet<usize> = assigned.iter().copied().collect();
    let mut renumber = vec![0usize; palettes.len()];
    let mut compact = Vec::new();
    for (old, palette) in palettes.into_iter().enumerate() {
        if used.contains(&old) {
            renumber[old] = compact.len();
            compact.push(palette);
        }
    }
    let mut active_at = vec![None; tiles.len()];
    for (&tile, &group) in active.iter().zip(&assigned) {
        active_at[tile] = Some(renumber[group]);
    }

    let mut changes: BTreeMap<(usize, Color, Color), u64> = BTreeMap::new();
    let mut decided = Vec::with_capacity(tiles.len());
    for (i, tile) in tiles.iter().enumerate() {
        let Some(palette) = active_at[i] else {
            decided.push(ReducedTile {
                palette: None,
                mapping: Vec::new(),
            });
            continue;
        };
        let mapping: Vec<Color> = tile
            .iter()
            .map(|&color| nearest(color, &compact[palette]))
            .collect();
        for ((&victim, &target), pixels) in tile.iter().zip(&mapping).zip(weights[i].values()) {
            if victim != target {
                *changes.entry((palette, victim, target)).or_default() += pixels;
            }
        }
        decided.push(ReducedTile {
            palette: Some(palette),
            mapping,
        });
    }
    let merges = changes
        .into_iter()
        .map(|((palette, victim, target), pixels)| PaletteMerge {
            palette,
            victim,
            target,
            pixels,
        })
        .collect();
    Ok(Reduced {
        palettes: compact,
        tiles: decided,
        merges,
    })
}

fn fill_empty_groups(
    assigned: &mut [usize],
    active: &[usize],
    tiles: &[Colors],
    weights: &[BTreeMap<Color, u64>],
    palettes: &[Colors],
    groups: usize,
) {
    let mut sizes = vec![0usize; groups];
    for &group in assigned.iter() {
        sizes[group] += 1;
    }
    for empty in 0..groups {
        if sizes[empty] != 0 {
            continue;
        }
        let move_at = (0..assigned.len())
            .filter(|&k| sizes[assigned[k]] > 1)
            .max_by(|&a, &b| {
                let cost = |k: usize| tile_cost(&weights[active[k]], &palettes[assigned[k]]);
                cost(a)
                    .cmp(&cost(b))
                    .then_with(|| tiles[active[b]].cmp(&tiles[active[a]]))
                    .then_with(|| b.cmp(&a))
            })
            .expect("more active tiles than groups leaves a movable tile");
        sizes[assigned[move_at]] -= 1;
        assigned[move_at] = empty;
        sizes[empty] = 1;
    }
}

fn tile_weights(counts: &[(Color, u64)], tiles: &[Colors]) -> Result<Vec<BTreeMap<Color, u64>>> {
    let mut totals = BTreeMap::new();
    for &(color, pixels) in counts {
        if totals.insert(color, pixels).is_some() {
            return Err(Bad::usage(format!(
                "colour ({}, {}, {}) is given twice",
                color[0], color[1], color[2]
            )));
        }
    }
    let mut out = vec![BTreeMap::new(); tiles.len()];
    let all: BTreeSet<Color> = tiles.iter().flat_map(|t| t.iter().copied()).collect();
    for color in all {
        let mut owners: Vec<usize> = tiles
            .iter()
            .enumerate()
            .filter_map(|(i, tile)| tile.contains(&color).then_some(i))
            .collect();
        owners.sort_by(|&a, &b| tiles[a].cmp(&tiles[b]).then(a.cmp(&b)));
        let total = totals.get(&color).copied().unwrap_or(1);
        let each = total / owners.len() as u64;
        let extra = total % owners.len() as u64;
        for (k, &i) in owners.iter().enumerate() {
            out[i].insert(color, each + u64::from((k as u64) < extra));
        }
    }
    Ok(out)
}

const MEAN_SCALE: u128 = 1 << 16;

fn mean(weights: &BTreeMap<Color, u64>) -> ([u128; 3], u128) {
    let total: u128 = weights.values().map(|&n| u128::from(n.max(1))).sum();
    if total == 0 {
        return ([0; 3], 1);
    }
    let mut sum = [0u128; 3];
    for (&color, &pixels) in weights {
        let pixels = u128::from(pixels.max(1));
        for channel in 0..3 {
            sum[channel] += u128::from(color[channel]) * pixels;
        }
    }
    for channel in &mut sum {
        *channel = *channel * MEAN_SCALE / total;
    }
    (sum, total)
}

fn mean_distance(a: ([u128; 3], u128), b: ([u128; 3], u128)) -> u128 {
    (0..3)
        .map(|channel| a.0[channel].abs_diff(b.0[channel]).pow(2))
        .sum()
}

fn initial_groups(
    tiles: &[Colors],
    weights: &[BTreeMap<Color, u64>],
    active: &[usize],
    groups: usize,
) -> Vec<usize> {
    let means: Vec<_> = weights.iter().map(mean).collect();
    let canonical = |a: usize, b: usize| tiles[a].cmp(&tiles[b]).then(a.cmp(&b));
    let first = *active
        .iter()
        .max_by(|&&a, &&b| means[a].1.cmp(&means[b].1).then_with(|| canonical(b, a)))
        .expect("there is an active tile");
    let mut centres = vec![first];
    while centres.len() < groups {
        let next = *active
            .iter()
            .filter(|i| !centres.contains(i))
            .max_by(|&&a, &&b| {
                let far = |i: usize| -> u128 {
                    centres
                        .iter()
                        .map(|&c| mean_distance(means[i], means[c]))
                        .min()
                        .unwrap_or(0)
                        * means[i].1
                };
                far(a).cmp(&far(b)).then_with(|| canonical(b, a))
            })
            .expect("there are enough active tiles");
        centres.push(next);
    }

    let mut assigned: Vec<usize> = active
        .iter()
        .map(|&i| {
            centres
                .iter()
                .enumerate()
                .min_by_key(|(g, &c)| (mean_distance(means[i], means[c]), *g))
                .map(|(g, _)| g)
                .unwrap_or(0)
        })
        .collect();
    for _ in 0..20 {
        let mut sums = vec![[0u128; 3]; groups];
        let mut totals = vec![0u128; groups];
        for (&i, &group) in active.iter().zip(&assigned) {
            totals[group] += means[i].1;
            for channel in 0..3 {
                sums[group][channel] += means[i].0[channel] * means[i].1;
            }
        }
        let centroids: Vec<_> = (0..groups)
            .map(|group| {
                if totals[group] == 0 {
                    means[centres[group]]
                } else {
                    (
                        [
                            sums[group][0] / totals[group],
                            sums[group][1] / totals[group],
                            sums[group][2] / totals[group],
                        ],
                        totals[group],
                    )
                }
            })
            .collect();
        let next: Vec<usize> = active
            .iter()
            .map(|&i| {
                centroids
                    .iter()
                    .enumerate()
                    .min_by_key(|(g, &c)| (mean_distance(means[i], c), *g))
                    .map(|(g, _)| g)
                    .unwrap_or(0)
            })
            .collect();
        if next == assigned {
            break;
        }
        assigned = next;
    }
    assigned
}

fn choose_palettes(
    tiles: &[Colors],
    weights: &[BTreeMap<Color, u64>],
    active: &[usize],
    assigned: &[usize],
    groups: usize,
    per_palette: usize,
) -> Vec<Colors> {
    (0..groups)
        .map(|group| {
            let members: Vec<usize> = active
                .iter()
                .zip(assigned)
                .filter_map(|(&i, &g)| (g == group).then_some(i))
                .collect();
            let candidates: Colors = members
                .iter()
                .flat_map(|&i| tiles[i].iter().copied())
                .collect();
            let mut totals = BTreeMap::new();
            for &i in &members {
                for (&color, &pixels) in &weights[i] {
                    *totals.entry(color).or_default() += pixels;
                }
            }
            select_colors(&candidates, &totals, per_palette)
        })
        .collect()
}

/// Greedy filling, then up to two best swaps, with every trial palette
/// costed as [`tile_cost`] would cost it.
///
/// It does not call [`tile_cost`]: a trial differs from the palette so far
/// in one colour, so each weighted colour's distance to the trial is its
/// distance to the palette —without the victim, on a swap— against its
/// distance to the newcomer, out of a table computed once. Until 2026-10-10
/// it built every trial as a set and costed it from scratch: the same
/// answer, but a picture with groups of 1,800 candidate colours took four
/// minutes instead of two seconds. The choice has to stay the same pick by
/// pick, ties included, because every palette depends on it.
fn select_colors(candidates: &Colors, weights: &BTreeMap<Color, u64>, keep: usize) -> Colors {
    let candidates: Vec<Color> = candidates.iter().copied().collect();
    let weighted: Vec<(Color, u64)> = weights
        .iter()
        .map(|(&color, &pixels)| (color, pixels.max(1)))
        .collect();
    let distances: Vec<Vec<u32>> = candidates
        .iter()
        .map(|&candidate| {
            weighted
                .iter()
                .map(|&(color, _)| {
                    u32::try_from(luma_distance(color, candidate))
                        .expect("a luma distance between 8-bit channels fits in 32 bits")
                })
                .collect()
        })
        .collect();
    // The cost in u64 when no sum can overflow it, which is any picture a
    // console shows: the sums vectorise in u64 and not in u128.
    let worst = distances.iter().flatten().copied().max().unwrap_or(0);
    let pixels: u128 = weighted.iter().map(|&(_, w)| u128::from(w)).sum();
    let weights: Vec<u64> = weighted.iter().map(|&(_, w)| w).collect();
    let chosen = if pixels * u128::from(worst) <= u128::from(u64::MAX) {
        best_colors::<u64>(&weights, &distances, keep)
    } else {
        best_colors::<u128>(&weights, &distances, keep)
    };
    candidates
        .iter()
        .zip(&chosen)
        .filter_map(|(&color, &kept)| kept.then_some(color))
        .collect()
}

/// The integer a cost is added up in.
trait Cost:
    Copy
    + Ord
    + From<u32>
    + From<u64>
    + std::ops::Mul<Output = Self>
    + std::ops::Add<Output = Self>
    + std::ops::Sub<Output = Self>
    + std::iter::Sum
{
    /// The cost of an empty palette.
    const FAR: Self;
}

impl Cost for u64 {
    const FAR: Self = u64::MAX;
}

impl Cost for u128 {
    const FAR: Self = u128::MAX;
}

/// The distance from a colour to an empty palette.
const FAR: u32 = u32::MAX;

/// [`select_colors`] over indices: `distances[k][c]` is from candidate `k`
/// to weighted colour `c`, and the answer is which candidates stay.
fn best_colors<T: Cost>(weights: &[u64], distances: &[Vec<u32>], keep: usize) -> Vec<bool> {
    let weights: Vec<T> = weights.iter().map(|&w| T::from(w)).collect();
    // The cost of the palette whose distances are `nearest`, plus candidate
    // k. A distance is FAR only to an empty palette, and then `d` is less.
    let cost_with = |nearest: &[u32], k: usize| -> T {
        weights
            .iter()
            .zip(nearest)
            .zip(&distances[k])
            .map(|((&w, &n), &d)| w * T::from(n.min(d)))
            .sum()
    };
    let take = |k: usize, chosen: &mut [bool], nearest: &mut [u32]| {
        chosen[k] = true;
        for (n, &d) in nearest.iter_mut().zip(&distances[k]) {
            *n = (*n).min(d);
        }
    };

    let mut chosen = vec![false; distances.len()];
    let mut nearest = vec![FAR; weights.len()];
    let rounds = keep.min(distances.len());
    if rounds > 0 {
        // Candidates go in colour order, so the first of equal cost wins, as
        // with the `(cost, candidate)` key this replaced.
        let mut pick: Option<(T, usize)> = None;
        for k in 0..distances.len() {
            let cost = cost_with(&nearest, k);
            if pick.is_none_or(|(c, _)| cost < c) {
                pick = Some((cost, k));
            }
        }
        let (_, k) = pick.expect("there is a candidate");
        take(k, &mut chosen, &mut nearest);
    }
    // From the second colour on, the least cost is the most gain —what the
    // candidate takes off the cost so far—, and a candidate's gain only
    // shrinks as the palette grows. So a gain measured rounds ago bounds the
    // one now from above, and a candidate whose gain is fresh and beats every
    // bound is the pick, without measuring the rest again. `Reverse(k)` in
    // the key keeps the first in colour order on a tie.
    let gain = |nearest: &[u32], k: usize| -> T {
        weights
            .iter()
            .zip(nearest)
            .zip(&distances[k])
            .map(|((&w, &n), &d)| w * T::from(n - n.min(d)))
            .sum()
    };
    let mut bounds: BinaryHeap<(T, Reverse<usize>, usize)> = (0..distances.len())
        .filter(|&k| !chosen[k])
        .map(|k| (gain(&nearest, k), Reverse(k), 1))
        .collect();
    for round in 1..rounds {
        loop {
            let (_, Reverse(k), measured) = bounds.pop().expect("a candidate remains");
            if measured == round {
                take(k, &mut chosen, &mut nearest);
                break;
            }
            bounds.push((gain(&nearest, k), Reverse(k), round));
        }
    }

    // Greedy filling can commit early to a middle colour that becomes
    // redundant after the rest arrive. Two best swaps recover that slot
    // without turning palette choice into an unbounded local search.
    for _ in 0..2 {
        let members: Vec<usize> = (0..distances.len()).filter(|&k| chosen[k]).collect();
        let current = if members.is_empty() {
            T::FAR
        } else {
            weights
                .iter()
                .zip(&nearest)
                .map(|(&w, &n)| w * T::from(n))
                .sum()
        };
        // Taking a victim out only moves the colours it was the nearest of:
        // each colour goes to the victim it belongs to —the first nearest
        // member— with its distance to the others. A colour two members are
        // as near to stays where it is either way.
        let mut owned: Vec<Vec<(usize, u32)>> = vec![Vec::new(); members.len()];
        for c in 0..weights.len() {
            let mut first: Option<(u32, usize)> = None;
            for (slot, &m) in members.iter().enumerate() {
                if first.is_none_or(|(d, _)| distances[m][c] < d) {
                    first = Some((distances[m][c], slot));
                }
            }
            if let Some((_, slot)) = first {
                let others = members
                    .iter()
                    .enumerate()
                    .filter(|&(s, _)| s != slot)
                    .map(|(_, &m)| distances[m][c])
                    .min()
                    .unwrap_or(FAR);
                owned[slot].push((c, others));
            }
        }
        // Victims and replacements in colour order: the first of equal cost
        // is the smallest `(cost, victim, replacement)`, the key this replaced.
        let replacements: Vec<(usize, T)> = (0..distances.len())
            .filter(|&k| !chosen[k])
            .map(|k| (k, cost_with(&nearest, k)))
            .collect();
        let mut swap: Option<(T, usize, usize)> = None;
        for (slot, &victim) in members.iter().enumerate() {
            for &(k, kept) in &replacements {
                // `kept` is the cost with the victim still in: its colours
                // trade their distance to it for the one to the others.
                let mut cost = kept;
                for &(c, others) in &owned[slot] {
                    let d = distances[k][c];
                    cost = cost - weights[c] * T::from(nearest[c].min(d))
                        + weights[c] * T::from(others.min(d));
                }
                if swap.is_none_or(|(c, _, _)| cost < c) {
                    swap = Some((cost, victim, k));
                }
            }
        }
        match swap {
            Some((cost, victim, k)) if cost < current => {
                chosen[victim] = false;
                chosen[k] = true;
                nearest = vec![FAR; weights.len()];
                let kept: Vec<usize> = (0..distances.len()).filter(|&m| chosen[m]).collect();
                for m in kept {
                    take(m, &mut chosen, &mut nearest);
                }
            }
            _ => break,
        }
    }
    chosen
}

fn tile_cost(weights: &BTreeMap<Color, u64>, palette: &Colors) -> u128 {
    if palette.is_empty() {
        return u128::MAX;
    }
    weights
        .iter()
        .map(|(&color, &pixels)| {
            u128::from(pixels.max(1))
                * u128::try_from(luma_distance(color, nearest(color, palette))).unwrap_or(0)
        })
        .sum()
}

fn nearest(color: Color, palette: &Colors) -> Color {
    *palette
        .iter()
        .min_by_key(|&&candidate| (luma_distance(color, candidate), candidate))
        .expect("a used palette is not empty")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn grey(v: u8) -> Color {
        [v, v, v]
    }

    /// `select_colors` as it was until 2026-10-10: every trial a set, costed
    /// from scratch. Slow, and obviously what it says; the fast one has to
    /// answer the same.
    fn select_colors_by_trial(
        candidates: &Colors,
        weights: &BTreeMap<Color, u64>,
        keep: usize,
    ) -> Colors {
        let mut chosen = Colors::new();
        while chosen.len() < keep.min(candidates.len()) {
            let next = candidates
                .iter()
                .filter(|c| !chosen.contains(*c))
                .min_by_key(|&&candidate| {
                    let mut trial = chosen.clone();
                    trial.insert(candidate);
                    (tile_cost(weights, &trial), candidate)
                })
                .copied()
                .expect("a candidate remains");
            chosen.insert(next);
        }
        for _ in 0..2 {
            let current = tile_cost(weights, &chosen);
            let best = chosen
                .iter()
                .flat_map(|&victim| {
                    candidates
                        .iter()
                        .filter(|replacement| !chosen.contains(*replacement))
                        .map(move |&replacement| (victim, replacement))
                })
                .map(|(victim, replacement)| {
                    let mut trial = chosen.clone();
                    trial.remove(&victim);
                    trial.insert(replacement);
                    (tile_cost(weights, &trial), victim, replacement, trial)
                })
                .min_by_key(|(cost, victim, replacement, _)| (*cost, *victim, *replacement));
            match best {
                Some((cost, _, _, trial)) if cost < current => chosen = trial,
                _ => break,
            }
        }
        chosen
    }

    /// A xorshift: the same cases on every run and every machine.
    struct Dice(u64);

    impl Dice {
        fn roll(&mut self, below: u64) -> u64 {
            self.0 ^= self.0 << 13;
            self.0 ^= self.0 >> 7;
            self.0 ^= self.0 << 17;
            self.0 % below
        }
    }

    /// Few channel values and few weights make ties everywhere, which is
    /// where a faster search most easily picks another colour; huge weights
    /// take the u128 sums.
    #[test]
    fn choosing_colours_answers_as_trying_every_palette() {
        let mut dice = Dice(0x9E37_79B9_7F4A_7C15);
        for case in 0..300 {
            let levels = 2 + dice.roll(30);
            // Greys of one weight are symmetric, so equal costs are the rule.
            let greys = case % 3 == 0;
            let room = if greys { levels } else { levels.pow(3) };
            let colours = (1 + dice.roll(60) as usize).min(room as usize);
            let heavy = case % 10 == 1;
            let mut weights = BTreeMap::new();
            while weights.len() < colours {
                let colour = match greys {
                    true => grey(dice.roll(levels) as u8),
                    false => [0, 0, 0].map(|_: u8| dice.roll(levels) as u8),
                };
                let pixels = match (greys, heavy) {
                    (true, _) => 1,
                    (false, true) => u64::MAX - dice.roll(1000),
                    (false, false) => dice.roll(4),
                };
                weights.insert(colour, pixels);
            }
            let candidates: Colors = weights.keys().copied().collect();
            let keep = 1 + dice.roll(16) as usize;
            assert_eq!(
                select_colors(&candidates, &weights, keep),
                select_colors_by_trial(&candidates, &weights, keep),
                "case {case}: {colours} colours of {levels} levels, keeping {keep}"
            );
        }
    }

    /// A tile of seventeen colours fits in no palette of fifteen, however
    /// many palettes there are: it went in as a group of seventeen.
    #[test]
    fn a_tile_with_more_colours_than_a_palette_fits_nowhere() {
        let tile: Colors = (0..17).map(grey).collect();
        assert_eq!(try_pack(&[tile.clone()], 8, 15), None);
        let counts: Vec<(Color, u64)> = (0..17).map(|v| (grey(v), 1 + u64::from(v))).collect();
        let reduced = reduce_colors(&counts, &[tile], 8, 15).unwrap();
        assert!(reduced.palettes.iter().all(|p| p.len() <= 15));
        assert_eq!(reduced.merges.len(), 2);
    }

    #[test]
    fn palette_groups_keep_their_own_nearby_colours() {
        let counts: Vec<(Color, u64)> = [0, 1, 2, 10, 11, 20]
            .into_iter()
            .map(|v| (grey(v), 10))
            .collect();
        let tiles = [
            [0, 1, 2].into_iter().map(grey).collect(),
            [2, 10, 11].into_iter().map(grey).collect(),
            [0, 11, 20].into_iter().map(grey).collect(),
        ];

        let reduced = reduce_colors(&counts, &tiles, 2, 2).unwrap();
        let kept: Colors = reduced.palettes.iter().flatten().copied().collect();

        assert_eq!(kept.len(), 4);
    }

    #[test]
    fn what_already_fits_loses_nothing() {
        let transparent = Colors::new();
        let left: Colors = [1, 2].into_iter().map(grey).collect();
        let right: Colors = [10, 11].into_iter().map(grey).collect();
        let tiles = [transparent, left.clone(), right.clone()];
        let counts = [(grey(1), 8), (grey(2), 4), (grey(10), 9), (grey(11), 3)];

        let reduced = reduce_colors(&counts, &tiles, 2, 2).unwrap();

        assert_eq!(reduced.palettes, try_pack(&[left, right], 2, 2).unwrap());
        assert_eq!(reduced.tiles[0].palette, None);
        assert_eq!(reduced.tiles[1].mapping, vec![grey(1), grey(2)]);
        assert_eq!(reduced.tiles[2].mapping, vec![grey(10), grey(11)]);
        assert!(reduced.merges.is_empty());
    }

    #[test]
    fn grouped_reduction_is_deterministic_and_stays_inside_the_limits() {
        let counts: Vec<(Color, u64)> = (0..24).map(|v| (grey(v), u64::from(v + 1))).collect();
        let tiles: Vec<Colors> = (0..8)
            .map(|start| (start..start + 10).map(grey).collect())
            .collect();

        let first = reduce_colors(&counts, &tiles, 3, 4).unwrap();
        let second = reduce_colors(&counts, &tiles, 3, 4).unwrap();

        assert_eq!(first, second);
        assert!(first.palettes.len() <= 3);
        assert!(first.palettes.iter().all(|palette| palette.len() <= 4));
        assert!(first.tiles.iter().all(|tile| tile.palette.is_some()));
    }
}
