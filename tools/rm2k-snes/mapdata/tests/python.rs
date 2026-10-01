//! What this emits, against what the Python it replaced emitted for the same
//! input: the hashes of its text, taken from the converter's Python on
//! 2026-10-01, before it was deleted.
//!
//! The input is made up to go through every path: an own route and a forced
//! one, a page without code, one that turns and one that changes graphic, a
//! walking event and a still one that animates, a leader without a graphic,
//! both ChipSet animation families, a flat terrain and a table, two maps
//! sharing blocks and a pose bank, and one quantized differently.

use rm2k_snes_mapdata::record;
use rm2k_snes_mapdata::request::{self, Maps};
use sha2::{Digest, Sha256};
use std::path::Path;

fn sha(text: &str) -> String {
    Sha256::digest(text.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn maps() -> Maps {
    request::read(&Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json")).unwrap()
}

#[test]
fn what_goes_per_map_comes_out_as_the_python_wrote_it() {
    let written = record::maps(&maps().maps).unwrap();
    assert_eq!(
        sha(&written.offsets),
        "1739ecfe74a25a7d9c0fa8001ea8c338117c81189df83a9196643a6173976fc1"
    );
    assert_eq!(
        sha(&written.maps),
        "ea442d16df61339c4262bd32108e54dd3b829af1a89d015d16044127d0a69807"
    );
    assert_eq!(
        sha(&written.tables),
        "acba6054928ecdddcc976fa6e356982285a5f87c13898832e41b1d5358c754b2"
    );
}

#[test]
fn what_it_says_is_what_the_python_said() {
    let written = record::maps(&maps().maps).unwrap();
    assert_eq!(
        written.notes,
        [
            "  map 8: Chubby2:2 goes with a pose bank of its own, quantized differently than in \
             another map",
            "  poses: 33 distinct out of 36, 1.5 KB less"
        ]
    );
    assert_eq!(
        written.report,
        [
            "  map_tiles         0.2 KB in LZ2, was    0.2",
            "  above_tiles       0.1 KB in LZ2, was    0.1",
            "  sprite_tiles      0.3 KB in LZ2, was    0.4",
            "  anim_tiles        0.3 KB in LZ2, was    0.6",
            "  map_cells         0.7 KB in LZ2, was    1.6",
            "                    1.6 KB in LZ2, was    2.8: 1.2 KB less",
            "  map_tiles       1 shared block(s),    0.2 KB",
            "  map_cgram       1 shared block(s),    0.0 KB",
            "                  2                 0.2 KB in total"
        ]
    );
    assert_eq!(written.frames, [0.4246914407996558, 0.3328360627343178]);
}

#[test]
fn a_map_that_does_not_fit_its_layout_is_refused() {
    let mut maps = maps().maps;
    maps[0].tiles = vec![0; 449 * 64];
    let bad = record::maps(&maps).err().unwrap();
    assert_eq!(
        bad.message(),
        "map 7: with this VRAM layout, tiles needs 449 tiles and 448 fit"
    );
}

#[test]
fn an_event_without_its_slot_is_refused() {
    let mut maps = maps().maps;
    maps[0].movable.clear();
    let bad = record::maps(&maps).err().unwrap();
    assert_eq!(
        bad.message(),
        "map 7: event 2 is drawn and has no slot in the sprite bank"
    );
}
