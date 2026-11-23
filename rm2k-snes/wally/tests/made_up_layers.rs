//! A map's layers and its blocks, over layers built inside this file,
//! which needs no real game.
//!
//! The layers are made to touch every path: a background that fits and one
//! that has to merge; a layer above that is empty, one that fits in one
//! palette, one that takes three and so leaves the background less, and
//! two whose tiles bring more colours than fit and have to merge; and a
//! background with both families of the ChipSet's animation, each moving
//! its own cells. Colours go in at 24 bits, so the 15-bit cut is in it too.
//!
//! The blocks are made of those layers' tilemaps, over made-up tile ids of
//! every family, passability and terrain: the terrain from a ChipSet whose
//! table is not all 1, through `rm2k-rules`.
//!
//!
//! **The path it guards**: those layers' shapes. A game's maps go through
//! the same conversion on every build, A Blurred Line's goldens see them
//! and its versioned patches hold every merge it makes; what is here is
//! the counts that say each path was taken —how many colours were drawn,
//! kept and merged, where the layer above starts, which animation runs—,
//! and what any conversion owes the console: no more colours than the
//! budget, and every cell on a block that exists.

use ditto::schema::Chipset;
use rm2k_render::{Family, Layers, Picture};
use rm2k_rules::chipset::terrain_of;
use wally::background::blocks::{blocks, Map};
use wally::background::convert;

/// The colour-memory entries a message window takes after the backdrop:
/// eight, as it took until 2026-10-04, which these layers' counts are of.
const WINDOW_COLORS: usize = 8;

fn h(n: u64) -> u64 {
    let mut n = (n * 2654435761) & 0xFFFF_FFFF;
    n ^= n >> 13;
    n = (n * 1274126177) & 0xFFFF_FFFF;
    n ^ (n >> 16)
}

/// What a drawing looks like: `kinds` distinct cells of `colors` colours —times `groups`,
/// each kind drawing from one group—, `holes` in 256 of them transparent in
/// part or whole, and `change` = (d, every, rem) redraws the cells whose
/// kind is `rem` modulo `every`, for drawing `d` of an animation.
struct Drawing {
    width: u64,
    height: u64,
    seed: u64,
    colors: u64,
    kinds: u64,
    holes: u64,
    change: Option<(u64, u64, u64)>,
    groups: u64,
}

fn drawing(width: u64, height: u64, seed: u64, colors: u64, kinds: u64) -> Drawing {
    Drawing {
        width,
        height,
        seed,
        colors,
        kinds,
        holes: 0,
        change: None,
        groups: 1,
    }
}

impl Drawing {
    fn holes(mut self, holes: u64) -> Self {
        self.holes = holes;
        self
    }

    fn change(mut self, d: u64, every: u64, rem: u64) -> Self {
        self.change = Some((d, every, rem));
        self
    }

    fn groups(mut self, groups: u64) -> Self {
        self.groups = groups;
        self
    }

    fn picture(&self) -> Picture {
        let mut rgba = Vec::new();
        for y in 0..self.height {
            for x in 0..self.width {
                let mut kind = h(self.seed * 7919 + x / 8 + 1000 * (y / 8)) % self.kinds;
                if let Some((d, every, rem)) = self.change {
                    if kind % every == rem {
                        kind += d * 101;
                    }
                }
                let k = h(kind * 64 + x % 8 + 8 * (y % 8) + self.seed) % self.colors
                    + (kind % self.groups) * self.colors;
                let channel = |i: u64| (h(k * 3 + i + self.seed) & 255) as u8;
                let mut a = 255;
                if self.holes > 0
                    && h(kind + 77) % 256 < self.holes
                    && !h(kind * 5 + (x % 8) * 3 + y % 8).is_multiple_of(3)
                {
                    a = 0;
                }
                if self.holes > 0 && h(kind + 91) % 256 < self.holes / 2 {
                    a = 0;
                }
                rgba.extend_from_slice(&[channel(0), channel(1), channel(2), a]);
            }
        }
        Picture {
            width: self.width as usize,
            height: self.height as usize,
            rgba,
        }
    }
}

fn case(name: &str) -> Layers {
    let (lower, upper, variants) = match name {
        "plain" => (
            drawing(64, 48, 1, 40, 12),
            drawing(64, 48, 2, 1, 1).holes(256),
            vec![],
        ),
        "crowded" => (
            drawing(96, 64, 3, 200, 60),
            drawing(96, 64, 4, 90, 40).holes(120),
            vec![],
        ),
        "animated" => {
            let water = |d| drawing(80, 64, 5, 60, 20).change(d, 4, 1).picture();
            let animated = |d: u64| drawing(80, 64, 5, 60, 20).change(d + 5, 4, 2).picture();
            (
                drawing(80, 64, 5, 60, 20).change(0, 4, 1),
                drawing(80, 64, 6, 20, 10).holes(200),
                vec![
                    (Family::Water, vec![water(1), water(2)]),
                    (
                        Family::Animated,
                        vec![animated(1), animated(2), animated(3)],
                    ),
                ],
            )
        }
        "split" => (
            drawing(64, 64, 9, 60, 16),
            drawing(64, 64, 10, 12, 24).holes(90).groups(3),
            vec![],
        ),
        "above" => (
            drawing(64, 64, 7, 30, 10),
            drawing(64, 64, 8, 120, 30).holes(60),
            vec![],
        ),
        _ => unreachable!(),
    };
    Layers {
        lower: lower.picture(),
        upper: upper.picture(),
        variants,
    }
}

struct Expected {
    above_first: usize,
    above_merged: usize,
    colors: usize,
    used: usize,
    budget: usize,
    merged: usize,
    runs: &'static [(&'static str, usize, usize)],
}

const EXPECTED: [(&str, Expected); 5] = [
    (
        "plain",
        Expected {
            above_first: 7,
            above_merged: 0,
            colors: 40,
            used: 40,
            budget: 103,
            merged: 0,
            runs: &[],
        },
    ),
    (
        "crowded",
        Expected {
            above_first: 7,
            above_merged: 75,
            colors: 199,
            used: 103,
            budget: 103,
            merged: 96,
            runs: &[],
        },
    ),
    (
        "animated",
        Expected {
            above_first: 5,
            above_merged: 9,
            colors: 60,
            used: 60,
            budget: 71,
            merged: 0,
            runs: &[("water", 11, 5), ("animated", 16, 5)],
        },
    ),
    (
        "split",
        Expected {
            above_first: 5,
            above_merged: 0,
            colors: 60,
            used: 60,
            budget: 71,
            merged: 0,
            runs: &[],
        },
    ),
    (
        "above",
        Expected {
            above_first: 3,
            above_merged: 318,
            colors: 30,
            used: 30,
            budget: 39,
            merged: 0,
            runs: &[],
        },
    ),
];

/// Each layer's counts, and no layer past its budget.
#[test]
fn each_layer_takes_its_path_and_keeps_to_its_budget() {
    for (name, want) in &EXPECTED {
        let done = convert(&case(name), WINDOW_COLORS).unwrap();
        let (bg, above) = (&done.background, &done.above);
        assert_eq!(
            above.first, want.above_first,
            "{name}: where the layer above starts"
        );
        assert_eq!(
            above.merges.len(),
            want.above_merged,
            "{name}: merged above"
        );
        assert_eq!(bg.colors, want.colors, "{name}: the colours drawn");
        assert_eq!(bg.used, want.used, "{name}: the colours kept");
        assert_eq!(bg.budget, want.budget, "{name}: the budget");
        assert_eq!(bg.merges.len(), want.merged, "{name}: merged");
        assert!(bg.used <= bg.budget, "{name}: past the budget");
        assert_eq!(
            bg.merges.is_empty(),
            bg.colors <= bg.budget,
            "{name}: merged only what did not fit"
        );
        let runs: Vec<(&str, usize, usize)> = bg
            .runs
            .iter()
            .map(|r| (r.family.name(), r.base, r.tiles))
            .collect();
        assert_eq!(runs, want.runs, "{name}: the runs of the animation");
        // Drawing 0 of each run is what the tiles carry where it starts,
        // and every drawing is as long.
        for r in &bg.runs {
            let bytes = r.drawings[0].len() / r.tiles;
            assert!(
                r.drawings.iter().all(|d| d.len() == r.tiles * bytes),
                "{name}: the drawings of {} differ in size",
                r.family.name()
            );
            assert_eq!(
                bg.tiles[r.base * bytes..(r.base + r.tiles) * bytes],
                r.drawings[0][..],
                "{name}: drawing 0 of {} is not the tiles'",
                r.family.name()
            );
        }
    }
}

#[test]
fn the_pictures_are_what_was_decided() {
    let done = convert(&case("animated"), WINDOW_COLORS).unwrap();
    let names: Vec<&str> = done.pictures.iter().map(|p| p.name.as_str()).collect();
    assert_eq!(
        names,
        [
            "background",
            "water-1",
            "water-2",
            "animated-1",
            "animated-2",
            "animated-3",
            "above"
        ]
    );
    // The background's indices are its colours from the first entry past
    // the window's, and the layer above's are inside its palettes.
    let background = &done.pictures[0].picture;
    assert!(background.pixels.iter().all(|&i| i >= 9));
    let above = &done.pictures[6].picture;
    let first = done.above.first * 16;
    assert!(above.pixels.iter().all(|&i| i == 0 || i as usize > first));
}

struct ExpectedBlocks {
    blocks: usize,
}

const BLOCKS: [(&str, ExpectedBlocks); 5] = [
    ("plain", ExpectedBlocks { blocks: 12 }),
    ("crowded", ExpectedBlocks { blocks: 24 }),
    ("animated", ExpectedBlocks { blocks: 20 }),
    ("split", ExpectedBlocks { blocks: 16 }),
    ("above", ExpectedBlocks { blocks: 16 }),
];

/// Tile ids for `n` cells, made up: water, animated,
/// terrain and plain ones below, a few plain ones above.
fn tile_ids(n: usize, seed: u64) -> (Vec<i32>, Vec<i32>) {
    (0..n as u64)
        .map(|i| {
            let r = h(i * 13 + seed);
            let lower = [
                r % 3000,
                3000 + r % 150,
                4000 + r % 600,
                5000 + r % 144,
                5000 + r % 3,
            ][(r % 5) as usize];
            (lower as i32, (10000 + h(i * 17 + seed) % 4) as i32)
        })
        .unzip()
}

/// How many blocks each map makes, and every cell on one of them.
#[test]
fn each_map_makes_its_blocks_and_every_cell_has_one() {
    let chipset = Chipset {
        terrain_data: (0..162).map(|k| (1 + h(k * 11) % 3) as i16).collect(),
        ..Chipset::default()
    };
    for (name, want) in &BLOCKS {
        let done = convert(&case(name), WINDOW_COLORS).unwrap();
        let tilemap = &done.background.tilemap;
        let (width, height) = (tilemap[0].len() / 2, tilemap.len() / 2);
        let seed = name.len() as u64;
        let (lower, upper) = tile_ids(width * height, seed);
        let passability: Vec<u8> = (0..(width * height) as u64)
            .map(|i| (h(i * 7 + seed) % 4) as u8)
            .collect();
        let terrain: Vec<i32> = lower.iter().map(|&id| terrain_of(&chipset, id)).collect();
        let made = blocks(
            &Map {
                width,
                height,
                lower: &lower,
                upper: &upper,
                passability: &passability,
                terrain: &terrain,
                apart: &Default::default(),
            },
            tilemap,
            &done.above.tilemap,
        )
        .unwrap();
        let n = made.passability.len();
        assert_eq!(n, want.blocks, "{name}: how many blocks");
        assert_eq!(made.terrain.len(), n, "{name}: a terrain per block");
        assert_eq!(made.cells.len(), width * height, "{name}: a block per cell");
        assert!(
            made.cells.iter().all(|&c| (c as usize) < n),
            "{name}: a cell on a block that is not there"
        );
        assert_eq!(made.table.len() % n, 0, "{name}: the table");
    }
}
