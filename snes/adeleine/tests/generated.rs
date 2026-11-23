//! The decisions over colours a generator makes: merges down to fifteen
//! out of sixty and of three hundred, tiles packed into palettes, colours
//! reduced into two and three palettes, the most used kept.
//!
//! **The path it guards**: sizes and ties a game's pictures may not have.
//! Every map, screen and picture of a game goes through these on each
//! build; A Blurred Line's goldens see what they drew and its versioned
//! patches hold every merge; `superfamiconv.rs` holds `try_pack` against
//! another packer. What is checked here is what any answer owes the
//! console: no more colours than were asked for, every colour mapped to
//! one that stayed, every tile in a palette that holds its colours.

use adeleine::{
    keep_most_used, merge_least_visible, reduce_colors, try_pack, Bad, Color, Colors, Merged,
    USABLE_COLORS,
};
use std::collections::BTreeSet;

/// A linear congruential generator, so every run sees the same colours.
struct Lcg(u64);

impl Lcg {
    fn next(&mut self, n: u64) -> u64 {
        self.0 = (self.0 * 1103515245 + 12345) % (1 << 31);
        (self.0 >> 8) % n
    }

    fn color(&mut self) -> Color {
        let mut channel = || self.next(32) as u8;
        [channel(), channel(), channel()]
    }
}

/// Up to `n` colours, each with 1 to 500 pixels, in the order they came out.
fn counts_case(seed: u64, n: usize) -> Vec<(Color, u64)> {
    let mut r = Lcg(seed);
    let mut counts: Vec<(Color, u64)> = Vec::new();
    for _ in 0..n {
        let c = r.color();
        if !counts.iter().any(|&(k, _)| k == c) {
            let pixels = 1 + r.next(500);
            counts.push((c, pixels));
        }
    }
    counts
}

/// `tiles` distinct draws of one to `most` pixels from a pool of `pool`
/// colours, each repeated one to four times: the pixels of every colour,
/// counted in the order they appear, and the colours of each tile.
fn tiles_case(seed: u64, pool: usize, tiles: usize, most: u64) -> (Vec<(Color, u64)>, Vec<Colors>) {
    let mut r = Lcg(seed);
    let mut colors: Vec<Color> = Vec::new();
    while colors.len() < pool {
        let c = r.color();
        if !colors.contains(&c) {
            colors.push(c);
        }
    }
    let mut counts: Vec<(Color, u64)> = Vec::new();
    let mut sets = Vec::new();
    for _ in 0..tiles {
        let k = 1 + r.next(most);
        let line: Vec<Color> = (0..k)
            .map(|_| colors[r.next(pool as u64) as usize])
            .collect();
        let times = 1 + r.next(4);
        for _ in 0..times {
            for &c in &line {
                match counts.iter_mut().find(|(k, _)| *k == c) {
                    Some((_, n)) => *n += 1,
                    None => counts.push((c, 1)),
                }
            }
        }
        sets.push(line.into_iter().collect::<BTreeSet<_>>());
    }
    (counts, sets)
}

/// What any merge owes: at most `keep` colours left, a merge per colour
/// that went, each colour mapped to one that stayed —itself if it did—.
fn check_merged(counts: &[(Color, u64)], keep: usize, merged: &Merged) {
    let given: BTreeSet<Color> = counts.iter().map(|&(c, _)| c).collect();
    let left: BTreeSet<Color> = merged.mapping.iter().copied().collect();
    assert_eq!(left.len(), given.len().min(keep), "colours left");
    assert_eq!(merged.merges.len(), given.len() - left.len(), "merges");
    assert!(left.is_subset(&given), "a colour that was not given");
    for (&(c, _), &to) in counts.iter().zip(&merged.mapping) {
        if left.contains(&c) {
            assert_eq!(to, c, "{c:?} stayed and maps elsewhere");
        }
    }
    for m in &merged.merges {
        assert!(
            !left.contains(&m.victim),
            "{:?} merged and stayed",
            m.victim
        );
    }
}

/// Five colours with the same pixels, four of them one step apart on red:
/// every merge is a tie on cost, broken by the colour.
#[test]
fn ties_go_to_the_smaller_colour() {
    let counts = [
        ([3, 0, 0], 10),
        ([0, 0, 0], 10),
        ([1, 0, 0], 10),
        ([2, 0, 0], 10),
        ([0, 1, 0], 10),
    ];
    let merged = merge_least_visible(&counts, 1).unwrap();
    check_merged(&counts, 1, &merged);
    let order: Vec<(Color, Color)> = merged.merges.iter().map(|m| (m.victim, m.target)).collect();
    assert_eq!(order, TIES);
}

#[test]
fn sixty_colours_down_to_fifteen() {
    let counts = counts_case(1, 60);
    check_merged(&counts, 15, &merge_least_visible(&counts, 15).unwrap());
}

/// About as many as the busiest sheet has.
#[test]
fn three_hundred_colours_down_to_fifteen() {
    let counts = counts_case(7, 300);
    check_merged(&counts, 15, &merge_least_visible(&counts, 15).unwrap());
}

#[test]
fn fewer_colours_than_kept_merge_nothing() {
    let counts = counts_case(3, 20);
    let merged = merge_least_visible(&counts, 30).unwrap();
    assert!(merged.merges.is_empty());
    check_merged(&counts, 30, &merged);
}

/// What any pack owes: no more palettes than the limit, none past its
/// colours, and every tile's colours inside one of them.
fn check_packed(sets: &[Colors], limit: usize, palettes: &[Colors]) {
    assert!(palettes.len() <= limit, "{} palettes", palettes.len());
    assert!(palettes.iter().all(|p| p.len() <= USABLE_COLORS));
    for (t, tile) in sets.iter().enumerate() {
        assert!(
            palettes.iter().any(|p| tile.is_subset(p)),
            "tile {t} fits in no palette"
        );
    }
}

/// Forty tiles of one to eight colours, with many the same size.
#[test]
fn tiles_into_eight_palettes() {
    let (_, sets) = tiles_case(11, 24, 40, 8);
    let palettes = try_pack(&sets, 8, USABLE_COLORS).expect("they fit");
    check_packed(&sets, 8, &palettes);
}

#[test]
fn tiles_that_do_not_fit_answer_none() {
    let (_, sets) = tiles_case(12, 24, 40, 8);
    assert_eq!(try_pack(&sets, 2, USABLE_COLORS), None);
}

/// What any reduction owes: no more palettes than the limit, none past its
/// colours, and every tile in one that holds what its colours became.
fn check_reduced(seed: u64, pool: usize, tiles: usize, most: u64, limit: usize) {
    let (counts, sets) = tiles_case(seed, pool, tiles, most);
    let reduced = reduce_colors(&counts, &sets, limit, USABLE_COLORS).unwrap();
    assert!(reduced.palettes.len() <= limit);
    assert!(reduced.palettes.iter().all(|p| p.len() <= USABLE_COLORS));
    assert_eq!(reduced.tiles.len(), sets.len());
    for (t, (tile, colors)) in reduced.tiles.iter().zip(&sets).enumerate() {
        assert_eq!(tile.mapping.len(), colors.len(), "tile {t}");
        let palette = &reduced.palettes[tile.palette.expect("no tile here is transparent")];
        assert!(
            tile.mapping.iter().all(|c| palette.contains(c)),
            "tile {t} maps outside its palette"
        );
    }
    for m in &reduced.merges {
        assert!(!reduced.palettes[m.palette].contains(&m.victim) || m.victim == m.target);
    }
}

#[test]
fn sixty_colours_into_two_palettes() {
    check_reduced(21, 60, 30, 12, 2);
}

/// Tiles of up to fifteen colours: some fit a palette only by themselves.
#[test]
fn full_tiles_into_three_palettes() {
    check_reduced(22, 40, 200, 15, 3);
}

#[test]
fn no_palettes_is_an_answer_not_a_crash() {
    let (counts, sets) = tiles_case(21, 60, 30, 12);
    assert_eq!(
        reduce_colors(&counts, &sets, 0, USABLE_COLORS),
        Err(Bad::answer("The palette could not be reduced enough."))
    );
}

#[test]
fn a_colour_given_twice_is_a_bad_call() {
    let counts = [([1, 2, 3], 4), ([1, 2, 3], 5)];
    assert!(matches!(
        merge_least_visible(&counts, 1),
        Err(Bad::Usage(_))
    ));
}

/// Keeping the most used, the other way down to N colours: black first,
/// with black in the picture or not, then the most used; every colour
/// becomes one of the palette, and one that stayed becomes itself.
#[test]
fn keeping_the_most_used_keeps_black_first_and_the_rest_by_use() {
    for (seed, n, keep, black) in [
        (11, 300, 16, false),
        (12, 300, 96, true),
        (13, 40, 15, false),
        (14, 10, 16, true),
        (15, 2000, 256, true),
    ] {
        let mut counts = counts_case(seed, n);
        if black {
            counts.push(([0, 0, 0], 7));
        }
        let kept = keep_most_used(&counts, keep, [0, 0, 0]);
        let distinct: BTreeSet<Color> = counts.iter().map(|&(c, _)| c).chain([[0, 0, 0]]).collect();
        assert_eq!(kept.palette[0], [0, 0, 0], "seed {seed}");
        assert_eq!(kept.palette.len(), keep.min(distinct.len()), "seed {seed}");
        let used = |c: &Color| counts.iter().find(|(k, _)| k == c).map_or(0, |&(_, n)| n);
        assert!(
            kept.palette[1..]
                .windows(2)
                .all(|w| used(&w[0]) >= used(&w[1])),
            "seed {seed}: not most used first"
        );
        for (&(c, _), to) in counts.iter().zip(&kept.mapping) {
            assert!(kept.palette.contains(to), "seed {seed}: {c:?}");
            if kept.palette.contains(&c) {
                assert_eq!(*to, c, "seed {seed}: {c:?} stayed");
            }
        }
    }
}

/// The merges of [`ties_go_to_the_smaller_colour`], in order: the smallest
/// colour left goes first, each into the red one step up.
const TIES: [(Color, Color); 4] = [
    ([0, 0, 0], [1, 0, 0]),
    ([2, 0, 0], [1, 0, 0]),
    ([0, 1, 0], [1, 0, 0]),
    ([3, 0, 0], [1, 0, 0]),
];
