//! Grouping colours into palettes so that every tile draws with one of them.

use crate::fail::Result;
use crate::merge::{merge_until, Merge};
use crate::Color;
use std::collections::{BTreeSet, HashMap};

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

/// What `reduce_colors` decided.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Reduced {
    /// For each colour of `counts`, in that order, the colour it became.
    pub mapping: Vec<Color>,
    /// The palettes, which the tiles fit in once `mapping` is applied.
    pub palettes: Vec<Colors>,
    pub merges: Vec<Merge>,
}

/// Merges colours until the tiles fit in `limit` palettes.
///
/// The real limit is not the number of colours but how they are
/// distributed: a tile with 14 colours forces those 14 to be in the same
/// palette. The tail of the distribution is usually colours of one or two
/// pixels, so merging the one that shows least into its nearest neighbour
/// and retrying costs very little.
///
/// `counts` is every colour with its pixels over the whole picture, and
/// `tiles` the colours of each distinct tile: a tile that appears a thousand
/// times is one set, and its pixels are already in `counts`. The same tile
/// twice changes nothing.
pub fn reduce_colors(
    counts: &[(Color, u64)],
    tiles: &[Colors],
    limit: usize,
    per_palette: usize,
) -> Result<Reduced> {
    let (merged, palettes) = merge_until(counts, |progress| {
        let now: HashMap<Color, Color> = counts
            .iter()
            .zip(&progress.mapping)
            .map(|(&(c, _), &to)| (c, to))
            .collect();
        let mapped: BTreeSet<Colors> = tiles
            .iter()
            .map(|tile| tile.iter().map(|c| *now.get(c).unwrap_or(c)).collect())
            .collect();
        let mapped: Vec<Colors> = mapped.into_iter().collect();
        try_pack(&mapped, limit, per_palette)
    })?;
    Ok(Reduced {
        mapping: merged.mapping,
        palettes,
        merges: merged.merges,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn grey(v: u8) -> Color {
        [v, v, v]
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
}
