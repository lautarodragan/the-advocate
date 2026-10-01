//! What this emits, against what the Python it replaced emitted for the same
//! input: the hashes of its text, taken from the converter's Python on
//! 2026-10-01, before it was deleted.
//!
//! The maps (`tests/maps.json`) are made up to go through every path: an own
//! route and a forced one, a page without code, one that turns and one that
//! changes graphic, a walking event and a still one that animates, a leader
//! without a graphic, both ChipSet animation families, a flat terrain and a
//! table, two maps sharing blocks and a pose bank, and one quantized
//! differently.
//!
//! The whole `.inc` goes twice over them (`tests/emit-*.json`), with the
//! database of `rm2k-snes-battle`'s test game: once bare —no title, no Game
//! Over, no picture, no animations, no battle audio, no troop pages— and
//! once with all of it, a hero above, the enemies' HP, dead texts and a case
//! slot.
//!
//! **If one of these changes, a byte of the cartridge changed.** The hashes
//! are not to be regenerated to make a test pass: the Python that produced
//! them is gone.
//!
//! They are regenerated when the cartridge changes **on purpose**, and the
//! commit says so. Since then they are this code's and not the Python's:
//! on 2026-10-01 the block table and its passability went into LZ2, behind
//! the grid —`map_ram` in `materials.rs`—, and so did the battlers
//! —`scene.rs`—; what the console makes of the new bytes is checked by the
//! game's tests, not here.

use rm2k_snes_battle::db::Db;
use rm2k_snes_mapdata::record;
use rm2k_snes_mapdata::request::{self, Emit, Maps};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

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
        "f50f5ddb1bbb489f102fe5928b9a8faf983ef2a50b6df947db0a7c1c131538e4"
    );
    assert_eq!(
        sha(&written.tables),
        "5c92d2735deee22b2af3594b590873b172cf17d4777fde8191f96f3f4d13be61"
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
            "  map_ram           0.1 KB in LZ2, was    0.1",
            "                    1.7 KB in LZ2, was    2.9: 1.2 KB less",
            "  map_tiles       1 shared block(s),    0.2 KB",
            "  map_cgram       1 shared block(s),    0.0 KB",
            "                  2                 0.2 KB in total"
        ]
    );
    assert_eq!(written.frames, [0.43519558379009593, 0.34244623610855024]);
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

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

/// A whole cartridge's request: the test maps, each with its timer's mask,
/// and the rest of `emit-<name>.json`.
fn emit_request(name: &str) -> Emit {
    let read = |file: &str| -> serde_json::Value {
        serde_json::from_str(&std::fs::read_to_string(here().join(file)).unwrap()).unwrap()
    };
    let mut value = read(&format!("tests/emit-{name}.json"));
    let mut maps = read("tests/maps.json");
    for m in maps["maps"].as_array_mut().unwrap() {
        let id = m["id"].as_i64().unwrap();
        m["sprite"]["timer_mask"] = (id * 3).into();
    }
    value["maps"] = maps["maps"].take();
    serde_json::from_value(value).unwrap()
}

/// `rm2k-snes-battle`'s test game: its actors, items, skills, enemies and
/// troops are what the tables of the `.inc` are read from.
fn db() -> Db {
    Db::from_dump(&here().join("../battle/tests/game/dump"), true).unwrap()
}

#[test]
fn a_bare_cartridge_comes_out_as_the_python_wrote_it() {
    let emitted = rm2k_snes_mapdata::emit::emit(&emit_request("bare"), &db()).unwrap();
    assert_eq!(emitted.text.lines().count(), 3522);
    assert_eq!(
        sha(&emitted.text),
        "2b62419f8039f1e71dd2a854745c77bfd6d746b08182b9634d07639d4c4868a8"
    );
}

#[test]
fn a_whole_cartridge_comes_out_as_the_python_wrote_it() {
    let emitted = rm2k_snes_mapdata::emit::emit(&emit_request("whole"), &db()).unwrap();
    assert_eq!(emitted.text.lines().count(), 3719);
    assert_eq!(
        sha(&emitted.text),
        "4c320eb93b602ea9c8e8f1899454226a5b614fdfd7c9218bc9658daa4e823536"
    );
}

#[test]
fn a_troop_page_that_asks_for_a_variable_carries_its_tables() {
    // The Python never wrote these two tables full —no page of the game it
    // converted asks for a variable—, and it would have failed: it read the
    // trigger's fields by their old names. This is what the console reads.
    let mut request = emit_request("whole");
    let pages = request.troop_pages.as_mut().unwrap();
    pages["per_troop"][0][1][0][0] = serde_json::json!([4, 5, 0, 17, -2, 0, 0, 0, 0, 0, 0, 0, 0]);
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    assert!(text.contains(".block 6\ntpage_var:\n    .word 17, 0, 0\n"));
    assert!(text.contains(".block 6\ntpage_value:\n    .word 65534, 0, 0\n"));
    assert!(text.contains(".block 2\ntpage_sw_b:\n    .word 0\n"));
}
