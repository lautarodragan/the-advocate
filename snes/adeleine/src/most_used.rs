//! Keeping the most used colours, and sending each of the others to its
//! nearest neighbour among them.
//!
//! It is the other way of bringing a picture down to N colours, and a
//! blunter one than [`merge_least_visible`](crate::merge_least_visible): it
//! looks only at how many pixels each colour covers, so a highlight of a few
//! pixels goes to whatever is nearest, however far that is. It is kept
//! because it is **what a picture already converted with it looks like**:
//! changing a picture's reducer changes its pixels.
//!
//! Like the merge, it invents no colour —each one goes to a colour that was
//! there— and it is deterministic: counts tie by the colour, and distances
//! too.

use crate::Color;

/// The palette that stayed, and what became of each colour.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Kept {
    /// `first`, then the most used colours, most used first.
    pub palette: Vec<Color>,
    /// For each colour of `counts`, **in the order it was given**, the one
    /// of `palette` it became: itself if it stayed.
    pub mapping: Vec<Color>,
}

/// How far apart two colours are, squared: plain Euclidean, no weights.
///
/// The colours this sends somewhere are the ones that barely appear, and
/// the neighbour they get is usually a step away, so weighting the channels
/// would change nothing that shows.
pub fn distance(a: Color, b: Color) -> i64 {
    (0..3)
        .map(|k| {
            let d = i64::from(a[k]) - i64::from(b[k]);
            d * d
        })
        .sum()
}

/// Brings `counts` —each colour with its pixels, none twice— down to `keep`
/// colours, **`first` always among them and always first**, whether the
/// picture has it or not: whoever calls knows why that entry is special.
/// The other `keep - 1` are the most used, ties broken by the colour; each
/// colour left out goes to the nearest of the palette, `first` included,
/// ties broken by the colour it goes to.
pub fn keep_most_used(counts: &[(Color, u64)], keep: usize, first: Color) -> Kept {
    let mut order: Vec<(Color, u64)> = counts
        .iter()
        .copied()
        .filter(|&(c, _)| c != first)
        .collect();
    order.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    let stays = keep.saturating_sub(1).min(order.len());
    let mut palette = vec![first];
    palette.extend(order[..stays].iter().map(|&(c, _)| c));
    let mapping = counts
        .iter()
        .map(|&(color, _)| {
            if palette.contains(&color) {
                return color;
            }
            *palette
                .iter()
                .min_by_key(|&&p| (distance(color, p), p))
                .expect("the palette has `first` at least")
        })
        .collect();
    Kept { palette, mapping }
}

#[cfg(test)]
mod tests {
    use super::*;

    const BLACK: Color = [0, 0, 0];

    #[test]
    fn the_first_colour_goes_first_even_if_the_picture_lacks_it() {
        let kept = keep_most_used(&[([9, 9, 9], 5), ([1, 2, 3], 7)], 4, BLACK);
        assert_eq!(kept.palette, vec![BLACK, [1, 2, 3], [9, 9, 9]]);
        assert_eq!(kept.mapping, vec![[9, 9, 9], [1, 2, 3]]);
    }

    #[test]
    fn the_first_colour_is_not_counted_twice() {
        let kept = keep_most_used(&[(BLACK, 1), ([5, 5, 5], 9), ([6, 6, 6], 9)], 2, BLACK);
        assert_eq!(kept.palette, vec![BLACK, [5, 5, 5]]);
        assert_eq!(kept.mapping, vec![BLACK, [5, 5, 5], [5, 5, 5]]);
    }

    #[test]
    fn a_tie_in_distance_goes_to_the_lower_colour() {
        // [2, 0, 0] is as far from [0, 0, 0] as from [4, 0, 0].
        let kept = keep_most_used(&[([4, 0, 0], 9), ([2, 0, 0], 1)], 2, BLACK);
        assert_eq!(kept.mapping, vec![[4, 0, 0], BLACK]);
    }
}
