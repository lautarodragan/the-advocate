//! The two halves of a map do not know each other.
//!
//! `background` takes the lower half of colour memory and the two tile
//! layers; `sprites`, the upper half and the object bank. Neither uses the
//! other, nor the rest of this crate: what needs both —baking an event into
//! a layer, laying out the VRAM— is the rest's, which may use both. Until
//! 2026-10-02 they were two crates of their own and Cargo kept that; inside
//! one crate nothing does but this test.
//!
//! It reads the source, not the compiled crate: a half reaches outside
//! itself only through a path that starts at the crate root, so every
//! `crate::` in a half has to be followed by that half's name, and no
//! `super::` may climb out of it. That asks the halves to write their own
//! paths as `crate::background::…`, not `super::…`, which is how they are
//! written. Comments are read too, so a doc link to the other half fails
//! like a `use` would.

use std::path::{Path, PathBuf};

const HALVES: [&str; 2] = ["background", "sprites"];

fn sources(dir: &Path) -> Vec<PathBuf> {
    let mut found = Vec::new();
    for entry in std::fs::read_dir(dir).unwrap() {
        let path = entry.unwrap().path();
        if path.is_dir() {
            found.extend(sources(&path));
        } else if path.extension().is_some_and(|e| e == "rs") {
            found.push(path);
        }
    }
    found.sort();
    found
}

/// What in `text`, a file of `half`, reaches outside it: one line each.
fn reaches_out(half: &str, file: &Path, text: &str) -> Vec<String> {
    let own = format!("crate::{half}::");
    // `mod.rs` is the half itself: its `super` is the crate root. Any other
    // file is a module inside the half, whose `super::super` is the root.
    let climb = if file.file_name().is_some_and(|n| n == "mod.rs") {
        "super::"
    } else {
        "super::super"
    };
    let mut wrong = Vec::new();
    for (number, line) in text.lines().enumerate() {
        let outside = line
            .match_indices("crate::")
            .any(|(at, _)| !line[at..].starts_with(&own))
            || line.contains(climb);
        if outside {
            wrong.push(format!(
                "{}:{}: {}",
                file.display(),
                number + 1,
                line.trim()
            ));
        }
    }
    wrong
}

#[test]
fn neither_half_uses_the_other_nor_the_rest_of_the_crate() {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut wrong = Vec::new();
    for half in HALVES {
        let files = sources(&src.join(half));
        // A half that is not where this looks would pass for having nothing
        // to say.
        assert!(!files.is_empty(), "no source in src/{half}/");
        for file in files {
            let text = std::fs::read_to_string(&file).unwrap();
            wrong.extend(reaches_out(half, &file, &text));
        }
    }
    assert!(
        wrong.is_empty(),
        "a half of the map reaches outside itself; what needs both halves goes in the rest of the crate:\n{}",
        wrong.join("\n")
    );
}

#[test]
fn what_counts_as_reaching_out() {
    let file = Path::new("layers.rs");
    let out = |text: &str| !reaches_out("background", file, text).is_empty();
    assert!(!out("use crate::background::fail::Bad;"));
    assert!(!out("    use super::*;"));
    assert!(out("use crate::sprites::npc::Npc;"));
    assert!(out("use crate::map::Map;"));
    assert!(out("use crate::{background, sprites};"));
    assert!(out("use super::super::sprites;"));
    assert!(out("/// See [`crate::sprites::bank`]."));
    // In `mod.rs` one `super` is already the crate root.
    assert!(reaches_out("background", Path::new("mod.rs"), "pub mod blocks;").is_empty());
    assert!(!reaches_out("background", Path::new("mod.rs"), "use super::sprites;").is_empty());
}
