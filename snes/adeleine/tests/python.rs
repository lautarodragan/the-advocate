//! Stable decisions for colours generated here.
//!
//! Each case builds its colours and tiles with a small generator, runs them
//! through the library and hashes the answer as the executable writes it.
//! The merge and pack hashes are those of the same answer from the Python
//! version, fed the same generator on 2026-09-29. Reduction deliberately
//! differs: its hashes freeze the grouped result. A case that changes hash
//! changed what some picture looks like.

use adeleine::request::{merged_answer, packed_answer, reduced_answer};
use adeleine::{
    keep_most_used, merge_least_visible, reduce_colors, try_pack, Bad, Color, Colors, USABLE_COLORS,
};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

/// A linear congruential generator: the one the Python side used, so both
/// see the same colours.
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

fn sha(answer: &serde_json::Value) -> String {
    Sha256::digest(answer.to_string().as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn merge(counts: &[(Color, u64)], keep: usize) -> String {
    sha(&merged_answer(&merge_least_visible(counts, keep).unwrap()))
}

fn pack(seed: u64, pool: usize, tiles: usize, most: u64, limit: usize) -> String {
    let (_, sets) = tiles_case(seed, pool, tiles, most);
    sha(&packed_answer(
        try_pack(&sets, limit, USABLE_COLORS).as_deref(),
    ))
}

fn reduce(seed: u64, pool: usize, tiles: usize, most: u64, limit: usize) -> String {
    let (counts, sets) = tiles_case(seed, pool, tiles, most);
    sha(&reduced_answer(
        &reduce_colors(&counts, &sets, limit, USABLE_COLORS).unwrap(),
    ))
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
    assert_eq!(
        merge(&counts, 1),
        "49e5d44b7c8d743277c4116ab4e87441dd49f921c2e3c3f98f6405d6b24d6ddd"
    );
}

#[test]
fn sixty_colours_down_to_fifteen() {
    assert_eq!(
        merge(&counts_case(1, 60), 15),
        "265bb24b74aea3088862a1840230e4c07a37e80f79c041cdfecfb5f75e646b30"
    );
}

/// About as many as the busiest sheet has, and merged the same way.
#[test]
fn three_hundred_colours_down_to_fifteen() {
    assert_eq!(
        merge(&counts_case(7, 300), 15),
        "d3b76a59e001adcb620b62d8a08af551cdf5cb0aa32619162713ce6aacd3d6a0"
    );
}

#[test]
fn fewer_colours_than_kept_merge_nothing() {
    let counts = counts_case(3, 20);
    let merged = merge_least_visible(&counts, 30).unwrap();
    assert!(merged.merges.is_empty());
    assert_eq!(
        merge(&counts, 30),
        "699584d22b272a37c19b108ca61fa7bdd609fc4ecb624aa463fbbd0996d820bf"
    );
}

/// Forty tiles of one to eight colours, with many the same size: the order
/// among those is the colours'.
#[test]
fn tiles_into_eight_palettes() {
    assert_eq!(
        pack(11, 24, 40, 8, 8),
        "a68d73741b785abcda1bf066c77c18f234f5bd6662a233a2e8654abe1056ae06"
    );
}

#[test]
fn tiles_that_do_not_fit_answer_null() {
    assert_eq!(
        pack(12, 24, 40, 8, 2),
        "9e7104ac8ee681bfe5e515d889ad25be974cd7671dda0a2116da615d3298d78d"
    );
}

#[test]
fn sixty_colours_into_two_palettes() {
    assert_eq!(
        reduce(21, 60, 30, 12, 2),
        "b485b1a77a5d33f631dda848db89f7bb6ab90cc4baafc3b203f397a5120a7aa4"
    );
}

/// Tiles of up to fifteen colours: some fit a palette only by themselves.
#[test]
fn full_tiles_into_three_palettes() {
    assert_eq!(
        reduce(22, 40, 200, 15, 3),
        "37985aeb222d7982a08d0419bad763340d2ed86bf07488ca8abe94363bd57914"
    );
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

/// Keeping the most used, the other way down to N colours, against what
/// the converter's `palette.reduce` gave on 2026-09-30 for the same
/// colours: black first, and with black in the picture or not. The answer
/// is written by hand, keys in order, as the Python wrote it.
#[test]
fn keeping_the_most_used_is_the_pythons() {
    let cases: &[(u64, usize, usize, bool, &str)] = &[
        (
            11,
            300,
            16,
            false,
            "0ead955370a25d35ce6e07223891a07bf19ac2e5681c4901e143b848c96e80ea",
        ),
        (
            12,
            300,
            96,
            true,
            "2f7f8f08d5cf44efc700b0592ed9638b4e8482f6607d8018e514c4c1cdb95167",
        ),
        (
            13,
            40,
            15,
            false,
            "5637024fe2d407998c678f263729f31c39d3450fc9f92d3eca1eee15bce395d6",
        ),
        (
            14,
            10,
            16,
            true,
            "eb2ae1268fb6da8e0f7f856e5181a9bbefc7376abfb264acaa8829991b695bf2",
        ),
        (
            15,
            2000,
            256,
            true,
            "4255093032494dae4005ad916dbf00bade486b241b051a3a5fffa0f423151b6f",
        ),
    ];
    let list = |colors: &[Color]| {
        let each: Vec<String> = colors
            .iter()
            .map(|c| format!("[{},{},{}]", c[0], c[1], c[2]))
            .collect();
        format!("[{}]", each.join(","))
    };
    for &(seed, n, keep, black, expected) in cases {
        let mut counts = counts_case(seed, n);
        if black {
            counts.push(([0, 0, 0], 7));
        }
        let kept = keep_most_used(&counts, keep, [0, 0, 0]);
        let text = format!(
            "{{\"mapping\":{},\"palette\":{}}}",
            list(&kept.mapping),
            list(&kept.palette)
        );
        let got: String = Sha256::digest(text.as_bytes())
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_eq!(got, expected, "seed {seed}");
    }
}
