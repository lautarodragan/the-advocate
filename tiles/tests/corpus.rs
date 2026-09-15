//! Replaying calls recorded from another implementation of the same rules.
//!
//! None of these decisions has a single right answer — how the colours are
//! grouped, which pair is merged first, which cell becomes which tile — so
//! "as good as" is not a useful bar. The only bar that means anything is
//! **the same bytes**. Since there is a working implementation to compare
//! against, that comparison is worth more than any amount of reasoning about
//! whether the port is faithful.
//!
//! The corpus is a directory of `<function>.jsonl` files, one recorded call per
//! line, `{"in": ..., "out": ...}`. It is not in this repository: it comes from
//! whatever the caller is porting, so `TILES_CORPUS` points at it and without
//! that variable these tests say so and pass. A corpus is evidence, not a
//! dependency.
//!
//!     TILES_CORPUS=/some/recorded/calls cargo test --release -- --nocapture
//!
//! `--release` is worth it: the recorded grids are whole pictures and the
//! debug build takes minutes over them.

use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use tiles::color::Rgb15;
use tiles::grid::{Grid, Tile};

fn corpus() -> Option<PathBuf> {
    match std::env::var_os("TILES_CORPUS") {
        Some(dir) => Some(PathBuf::from(dir)),
        None => {
            println!("TILES_CORPUS is not set: skipping, nothing was compared");
            None
        }
    }
}

/// Every recorded call in one file, or nothing if the corpus has no such file
/// — a corpus is allowed to cover only some of the functions.
fn calls(name: &str) -> Vec<Value> {
    let Some(dir) = corpus() else { return Vec::new() };
    let path = dir.join(format!("{name}.jsonl"));
    let Ok(text) = std::fs::read_to_string(&path) else {
        println!("{}: not in the corpus, skipping", path.display());
        return Vec::new();
    };
    text.lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            serde_json::from_str(l)
                .unwrap_or_else(|e| panic!("{}: {e}", path.display()))
        })
        .collect()
}

fn color(v: &Value) -> Rgb15 {
    let a = v.as_array().expect("a colour is three numbers");
    (num(&a[0]) as u8, num(&a[1]) as u8, num(&a[2]) as u8)
}

fn num(v: &Value) -> u64 {
    v.as_u64().expect("a number")
}

fn pixel(v: &Value) -> Option<Rgb15> {
    if v.is_null() {
        None
    } else {
        Some(color(v))
    }
}

fn colors(v: &Value) -> Vec<Rgb15> {
    v.as_array().unwrap().iter().map(color).collect()
}

fn color_set(v: &Value) -> BTreeSet<Rgb15> {
    v.as_array().unwrap().iter().map(color).collect()
}

fn tile(v: &Value) -> Tile {
    let rows = v.as_array().unwrap();
    let mut out: Tile = [[None; 8]; 8];
    for (y, row) in rows.iter().enumerate() {
        for (x, p) in row.as_array().unwrap().iter().enumerate() {
            out[y][x] = pixel(p);
        }
    }
    out
}

fn indices(v: &Value) -> tiles::Indices {
    let rows = v.as_array().unwrap();
    let mut out = [[0u8; 8]; 8];
    for (y, row) in rows.iter().enumerate() {
        for (x, n) in row.as_array().unwrap().iter().enumerate() {
            out[y][x] = num(n) as u8;
        }
    }
    out
}

fn grid(v: &Value) -> Grid {
    let rows: Vec<Vec<Tile>> = v
        .as_array()
        .unwrap()
        .iter()
        .map(|row| row.as_array().unwrap().iter().map(tile).collect())
        .collect();
    Grid {
        columns: rows.first().map_or(0, |r| r.len()),
        rows,
    }
}

fn groups_of(v: &Value) -> Vec<BTreeSet<Rgb15>> {
    v.as_array().unwrap().iter().map(color_set).collect()
}

fn counted(v: &Value) -> BTreeMap<Rgb15, u64> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|pair| {
            let p = pair.as_array().unwrap();
            (color(&p[0]), num(&p[1]))
        })
        .collect()
}

fn done(name: &str, n: usize) {
    if n > 0 {
        println!("{name}: {n} recorded call(s), all identical");
    }
}

/// Packing is the one thing here that cannot be compared for equality against
/// an arbitrary recording, and the reason is worth writing down.
///
/// Best-fit walks the colour sets in some order, and ties on "how many
/// colours" are the common case, not the exception. Whatever produced the
/// recording had *some* order for those ties; if that order came out of a hash
/// table it is not part of the input and cannot be reproduced from it — and it
/// is not stable for the recorder either. So what is checked here is what can
/// be checked: the packing is **valid** (every recorded cell fits in one of
/// the palettes, none is over capacity, there are no more than were allowed)
/// and it **succeeds wherever the recording succeeded**. Then the exact
/// matches are counted and printed, because a drop in that number is worth
/// looking at even though it is not by itself a failure.
#[test]
fn recorded_packings_are_valid_and_never_worse() {
    let cases = calls("try_pack");
    let mut exact = 0;
    for (i, case) in cases.iter().enumerate() {
        let input = &case["in"];
        let sets: BTreeSet<BTreeSet<Rgb15>> =
            input["sets"].as_array().unwrap().iter().map(color_set).collect();
        let limit = num(&input["limit"]) as usize;
        let per_palette = num(&input["per_palette"]) as usize;
        let got = tiles::try_pack(&sets, limit, per_palette);
        let want = if case["out"].is_null() {
            None
        } else {
            Some(groups_of(&case["out"]))
        };

        if want.is_some() {
            assert!(
                got.is_some(),
                "call {i}: the recording found a packing and this did not"
            );
        }
        if let Some(groups) = &got {
            assert!(groups.len() <= limit, "call {i}: {} palettes", groups.len());
            for set in &sets {
                // A set already too big for one palette is the caller's to
                // catch: best-fit opens it as an oversized group on purpose.
                if set.len() > per_palette {
                    continue;
                }
                assert!(
                    groups.iter().any(|g| set.is_subset(g)),
                    "call {i}: a cell's colours are in no single palette"
                );
            }
            for group in groups {
                assert!(
                    group.len() <= per_palette
                        || sets.iter().any(|s| s.len() > per_palette),
                    "call {i}: a palette came out over capacity"
                );
            }
        }
        exact += usize::from(got == want);
    }
    if !cases.is_empty() {
        println!(
            "try_pack: {} recorded call(s), all valid, {exact} identical to the recording",
            cases.len()
        );
    }
}

#[test]
fn recorded_merges_pick_the_same_colours_in_the_same_order() {
    let cases = calls("merge_least_visible");
    for (i, case) in cases.iter().enumerate() {
        let counts = counted(&case["in"]["counts"]);
        let merge = tiles::merge_to(&counts, num(&case["in"]["keep"]) as usize)
            .unwrap_or_else(|e| panic!("call {i}: {e}"));

        let want_mapping: BTreeMap<Rgb15, Rgb15> = case["out"]["mapping"]
            .as_array()
            .unwrap()
            .iter()
            .map(|pair| {
                let p = pair.as_array().unwrap();
                (color(&p[0]), color(&p[1]))
            })
            .collect();
        assert_eq!(merge.mapping, want_mapping, "call {i}: mapping");

        let want_merged: Vec<(Rgb15, Rgb15, u64)> = case["out"]["merged"]
            .as_array()
            .unwrap()
            .iter()
            .map(|entry| {
                let e = entry.as_array().unwrap();
                (color(&e[0]), color(&e[1]), num(&e[2]))
            })
            .collect();
        assert_eq!(merge.merged, want_merged, "call {i}: the order of the merges");
    }
    done("merge_least_visible", cases.len());
}

/// A reduction inherits the packing's order-dependence: the packing is what
/// decides when enough colours have been given up, so a different tie-break
/// can stop a merge earlier or later. What is asserted is therefore what holds
/// regardless: the result is valid, and it never gives up **more** colours
/// than the recording did. Exact matches are counted and printed.
#[test]
fn recorded_reductions_are_valid_and_never_lose_more() {
    let cases = calls("reduce_colors");
    let mut exact = 0;
    for (i, case) in cases.iter().enumerate() {
        let before = grid(&case["in"]["grid"]);
        let budget = num(&case["in"]["budget"]) as usize;
        let per_palette = tiles::COLORS_PER_PALETTE - 1;
        let reduced = tiles::reduce_colors(&before, budget, per_palette)
            .unwrap_or_else(|e| panic!("call {i}: {e}"));

        let want: Vec<(Rgb15, Rgb15, u64)> = case["out"]["merged"]
            .as_array()
            .unwrap()
            .iter()
            .map(|entry| {
                let e = entry.as_array().unwrap();
                (color(&e[0]), color(&e[1]), num(&e[2]))
            })
            .collect();
        assert!(
            reduced.merged.len() <= want.len(),
            "call {i}: {} colours given up where the recording gave up {}",
            reduced.merged.len(),
            want.len()
        );
        // As far as they both went, they gave up the same colours in the same
        // order: that part is fully determined by the input.
        let common = reduced.merged.len().min(want.len());
        assert_eq!(
            reduced.merged[..common],
            want[..common],
            "call {i}: the order the colours were given up in"
        );

        assert!(reduced.groups.len() <= budget, "call {i}: too many palettes");
        for tile in reduced.grid.cells() {
            let colors = tiles::tile_colors(tile);
            assert!(
                colors.is_empty() || reduced.groups.iter().any(|g| colors.is_subset(g)),
                "call {i}: a reduced cell fits in no palette"
            );
        }
        let after = grid(&case["out"]["grid"]);
        exact += usize::from(
            reduced.grid.rows == after.rows
                && reduced.merged == want
                && reduced.groups == groups_of(&case["out"]["groups"]),
        );
    }
    if !cases.is_empty() {
        println!(
            "reduce_colors: {} recorded call(s), all valid and none worse, \
             {exact} identical to the recording",
            cases.len()
        );
    }
}

#[test]
fn recorded_cuts_give_back_the_same_cells() {
    let cases = calls("cut_tiles");
    for (i, case) in cases.iter().enumerate() {
        let rows: Vec<Vec<Option<Rgb15>>> = case["in"]["rows"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| row.as_array().unwrap().iter().map(pixel).collect())
            .collect();
        let picture = tiles::Picture {
            width: rows.first().map_or(0, |r| r.len()),
            height: rows.len(),
            rows,
        };
        assert_eq!(tiles::cut_tiles(&picture).rows, grid(&case["out"]).rows, "call {i}");
    }
    done("cut_tiles", cases.len());
}

#[test]
fn recorded_indices_number_the_colours_the_same_way() {
    let cases = calls("to_indices");
    for (i, case) in cases.iter().enumerate() {
        let input = &case["in"];
        let got = tiles::to_indices(
            &tile(&input["tile"]),
            &colors(&input["palette"]),
            num(&input["base"]) as u8,
        )
        .unwrap_or_else(|e| panic!("call {i}: {e}"));
        assert_eq!(got, indices(&case["out"]), "call {i}");
    }
    done("to_indices", cases.len());
}

#[test]
fn recorded_tiles_pack_to_the_same_bytes() {
    let cases = calls("pack_tile");
    for (i, case) in cases.iter().enumerate() {
        let input = &case["in"];
        let got = tiles::pack_tile(&indices(&input["indices"]), num(&input["planes"]) as usize);
        let want: Vec<u8> = case["out"]
            .as_array()
            .unwrap()
            .iter()
            .map(|b| num(b) as u8)
            .collect();
        assert_eq!(got, want, "call {i}");
        // And the other way, which the recording cannot check on its own.
        assert_eq!(
            tiles::unpack_tile(&got, num(&input["planes"]) as usize),
            indices(&input["indices"]),
            "call {i}: unpacking"
        );
    }
    done("pack_tile", cases.len());
}

#[test]
fn recorded_colours_become_the_same_words() {
    let cases = calls("cgram_word");
    for (i, case) in cases.iter().enumerate() {
        assert_eq!(
            tiles::cgram_word(color(&case["in"]["color"])) as u64,
            num(&case["out"]),
            "call {i}"
        );
    }
    done("cgram_word", cases.len());
}

#[test]
fn recorded_distances_are_the_same_integers() {
    let cases = calls("luma_distance");
    for (i, case) in cases.iter().enumerate() {
        assert_eq!(
            tiles::luma_distance(color(&case["in"]["a"]), color(&case["in"]["b"])),
            num(&case["out"]),
            "call {i}"
        );
    }
    done("luma_distance", cases.len());
}

#[test]
fn recorded_tilemap_entries_have_the_same_bits() {
    let cases = calls("entry");
    for (i, case) in cases.iter().enumerate() {
        let input = &case["in"];
        assert_eq!(
            tiles::entry(
                num(&input["tile"]) as u16,
                num(&input["h"]) as u8,
                num(&input["v"]) as u8,
                num(&input["p"]) as u8,
                0,
            ) as u64,
            num(&case["out"]),
            "call {i}"
        );
    }
    done("entry", cases.len());
}
