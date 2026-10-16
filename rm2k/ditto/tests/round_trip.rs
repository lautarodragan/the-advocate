//! The test that makes Ditto worth anything: read an RPG Maker file, dump it
//! to JSON, write it back from the JSON, and get a binary **identical** to the
//! original.
//!
//! "Almost" is no good: the idea is to open the game with the real editor and
//! come back, and one byte too many breaks somebody else's game.
//!
//! By default it runs over a small sample so that `cargo test` stays something
//! one runs without thinking about it. The whole corpus —every map, the LDB and
//! the tree— sits behind an environment variable:
//!
//!     DITTO_ALL=1 cargo test --release -- --nocapture
//!
//! Every test here needs a game to measure against; see `tests/common/mod.rs`
//! for how it is found and why it skips instead of failing when there is none.

mod common;

use std::path::{Path, PathBuf};

/// Reads, dumps to JSON, comes back, and compares. Says where the difference is.
fn round_trip(path: &Path) -> Result<(), String> {
    let original = std::fs::read(path).map_err(|e| format!("could not read: {e}"))?;
    let doc = ditto::file::read(&original).map_err(|e| format!("while reading: {e}"))?;

    // The JSON is not a decorative middle step: if it does not close, the game
    // cannot live in a repository as JSON, which is the point of all this.
    let json = serde_json::to_vec(&doc).map_err(|e| format!("while serializing: {e}"))?;
    let back: ditto::file::Document =
        serde_json::from_slice(&json).map_err(|e| format!("while deserializing: {e}"))?;
    if back != doc {
        return Err("the JSON does not give back the same structure".into());
    }

    let binary = ditto::file::write(&back).map_err(|e| format!("while writing: {e}"))?;
    if binary == original {
        return Ok(());
    }
    let n = binary
        .iter()
        .zip(original.iter())
        .position(|(a, b)| a != b)
        .unwrap_or(binary.len().min(original.len()));
    Err(format!(
        "differs at byte {n} (of {} original bytes, {} came out): {:02x?} instead of {:02x?}",
        original.len(),
        binary.len(),
        &binary[n.saturating_sub(4)..(n + 4).min(binary.len())],
        &original[n.saturating_sub(4)..(n + 4).min(original.len())],
    ))
}

fn batch(files: &[PathBuf]) {
    let mut failed = Vec::new();
    for a in files {
        if let Err(e) = round_trip(a) {
            failed.push(format!("{}: {e}", a.file_name().unwrap().to_string_lossy()));
        }
    }
    println!(
        "byte-for-byte round trip: {} of {}",
        files.len() - failed.len(),
        files.len()
    );
    for f in &failed {
        println!("  {f}");
    }
    assert!(failed.is_empty(), "{} files do not come back equal", failed.len());
}

#[test]
fn the_database_and_the_tree_come_back_equal() {
    let Some(dir) = common::dir() else { return };
    let Some(files) = common::files(&dir) else { return };
    batch(&files[..2]);
}

#[test]
fn a_sample_of_maps_comes_back_equal() {
    let Some(dir) = common::dir() else { return };
    let Some(_) = common::files(&dir) else { return };
    let all = common::maps(&dir);
    if std::env::var("DITTO_ALL").is_ok() {
        batch(&all);
        return;
    }
    // One in twenty, plus the first and the last: enough for a regression in
    // the codec to show without paying for the whole corpus on every
    // `cargo test`.
    let sample: Vec<PathBuf> = all
        .iter()
        .step_by(20)
        .chain(all.last())
        .cloned()
        .collect();
    batch(&sample);
}

/// The whole corpus. This is the number that gets reported.
#[test]
#[ignore = "the long batch: `cargo test --release -- --ignored --nocapture`"]
fn the_whole_game_comes_back_equal() {
    let Some(dir) = common::dir() else { return };
    let Some(files) = common::files(&dir) else { return };
    batch(&files);
}

/// The bug that started all of this, from both sides: a field that is not there
/// —in the binary or in the JSON— holds what `fields.csv` says, and not the
/// zero of its type. An `Enemy`'s `max_hp` is 10; a reader that defaulted it to
/// 1 gave an enemy that died in one hit.
///
/// This one needs no corpus: it is about the generated schema.
#[test]
fn a_missing_field_holds_the_format_default() {
    let e: ditto::schema::Enemy = serde_json::from_str("{}").unwrap();
    assert_eq!(e.max_hp, 10, "max_hp of an Enemy with no data");
    assert_eq!(e.max_sp, 10, "max_sp of an Enemy with no data");
    assert_eq!(e.attack, 10);
    // And the same when reading the binary: an absent chunk is not a zero.
    let empty = ditto::lcf::dec_struct::<ditto::schema::Enemy>(&[], false).unwrap();
    assert_eq!(empty.max_hp, 10);
    // The one struct whose defaults change with the version: an actor with no
    // chunks is level 50 in a 2000 database and 99 in a 2003 one.
    let actor = ditto::lcf::dec_struct::<ditto::schema::Actor>(&[], false).unwrap();
    assert_eq!((actor.final_level, actor.exp_base, actor.exp_inflation), (50, 30, 30));
    let actor = ditto::lcf::dec_struct::<ditto::schema::Actor>(&[], true).unwrap();
    assert_eq!((actor.final_level, actor.exp_base, actor.exp_inflation), (99, 300, 300));

    let a: ditto::schema::Actor = serde_json::from_str(r#"{"name":"Alex"}"#).unwrap();
    assert_eq!(a.name, "Alex");
    assert_eq!(a.initial_level, 1);
    assert_eq!(a.final_level, 50, "in RPG Maker 2000, not 99");
    assert_eq!(a.exp_base, 30);
    assert!(a.critical_hit, "the declared default is True");
}

/// The round trip alone is not enough as a test: a reader that understood
/// **nothing** and kept every chunk raw would also come back byte for byte, and
/// the JSON would be useless. So it is also required that not a single chunk
/// goes unnamed. `unknown` only shows up in the JSON when it has something in
/// it.
#[test]
fn no_chunk_goes_unnamed() {
    let Some(dir) = common::dir() else { return };
    let Some(files) = common::files(&dir) else { return };
    for a in files[..2]
        .iter()
        .cloned()
        .chain(common::maps(&dir).into_iter().step_by(20))
    {
        let doc = ditto::file::read(&std::fs::read(&a).unwrap()).unwrap();
        let json = serde_json::to_string(&doc).unwrap();
        assert!(
            !json.contains("\"unknown\""),
            "{:?} has chunks the schema does not name",
            a.file_name().unwrap()
        );
    }
}
