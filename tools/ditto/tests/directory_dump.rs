//! The round trip through the **directory** dump: `unpack` a game into a tree
//! of JSON, `pack` the tree back, and get the same binaries.
//!
//! The single-file round trip (`round_trip.rs`) does not cover this: the tree
//! splits the database into sections, takes the tile layers out into a text
//! grid and drops the `format`/`header` envelope, so everything needed to write
//! the binary back has to have found a place in the layout. If it did not, this
//! is where it shows.
//!
//! Every test here needs a game to measure against; see `tests/common/mod.rs`.

mod common;

use std::path::{Path, PathBuf};

/// A directory of our own under the system's temp, removed on the way out.
struct Temp(PathBuf);

impl Temp {
    fn new(what: &str) -> Temp {
        let n = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let d = std::env::temp_dir().join(format!("ditto-{what}-{}-{n}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        Temp(d)
    }

    fn join(&self, s: &str) -> PathBuf {
        self.0.join(s)
    }
}

impl Drop for Temp {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// Unpacks `game` and packs it back, and compares every file of `game` against
/// what came out. Returns the ones that differ.
fn there_and_back(game: &Path, tmp: &Temp) -> Vec<String> {
    let dump = tmp.join("dump");
    let back = tmp.join("back");
    ditto::dump::unpack(game, &dump).expect("unpack");
    ditto::dump::pack(&dump, &back).expect("pack");

    let mut originals = vec![game.join("RPG_RT.ldb"), game.join("RPG_RT.lmt")];
    originals.extend(common::maps(game));
    let mut failed = Vec::new();
    for a in &originals {
        let name = a.file_name().unwrap().to_string_lossy().to_string();
        let original = std::fs::read(a).unwrap();
        match std::fs::read(back.join(&name)) {
            Err(e) => failed.push(format!("{name}: it was not written back: {e}")),
            Ok(b) if b == original => {}
            Ok(b) => failed.push(format!(
                "{name}: {} bytes came out and it had {}",
                b.len(),
                original.len()
            )),
        }
    }
    println!(
        "directory round trip: {} of {}",
        originals.len() - failed.len(),
        originals.len()
    );
    for f in &failed {
        println!("  {f}");
    }
    failed
}

/// A game of three maps, so `cargo test` covers the layout without paying for
/// the whole corpus.
#[test]
fn a_small_game_comes_back_equal() {
    let Some(dir) = common::dir() else { return };
    let Some(_) = common::files(&dir) else { return };
    let tmp = Temp::new("small");
    let game = tmp.join("game");
    std::fs::create_dir_all(&game).unwrap();
    for f in ["RPG_RT.ldb", "RPG_RT.lmt"] {
        std::fs::copy(dir.join(f), game.join(f)).unwrap();
    }
    for m in common::maps(&dir).iter().take(3) {
        std::fs::copy(m, game.join(m.file_name().unwrap())).unwrap();
    }
    let failed = there_and_back(&game, &tmp);
    assert!(failed.is_empty(), "{} files do not come back equal", failed.len());
}

/// The whole corpus through the tree. This is the number that gets reported
/// next to the single-file one.
#[test]
#[ignore = "the long batch: `cargo test --release -- --ignored --nocapture`"]
fn the_whole_game_comes_back_equal_through_the_tree() {
    let Some(dir) = common::dir() else { return };
    let Some(_) = common::files(&dir) else { return };
    let tmp = Temp::new("whole");
    let failed = there_and_back(&dir, &tmp);
    assert!(failed.is_empty(), "{} files do not come back equal", failed.len());
}

/// What the layout is for: the `.tiles` is a grid a person can read and edit,
/// and editing it changes the map. A dump nobody can read would have been
/// cheaper as one big JSON.
#[test]
fn the_tiles_are_a_grid_and_editing_it_changes_the_map() {
    let Some(dir) = common::dir() else { return };
    let Some(_) = common::files(&dir) else { return };
    let Some(first) = common::maps(&dir).into_iter().next() else { return };

    let tmp = Temp::new("tiles");
    let game = tmp.join("game");
    std::fs::create_dir_all(&game).unwrap();
    for f in ["RPG_RT.ldb", "RPG_RT.lmt"] {
        std::fs::copy(dir.join(f), game.join(f)).unwrap();
    }
    let name = first.file_name().unwrap().to_string_lossy().to_string();
    std::fs::copy(&first, game.join(&name)).unwrap();

    let dump = tmp.join("dump");
    ditto::dump::unpack(&game, &dump).unwrap();

    let stem = name.trim_end_matches(".lmu").to_string();
    let json = std::fs::read_to_string(dump.join("maps").join(format!("{stem}.json"))).unwrap();
    assert!(
        !json.contains("lower_layer"),
        "the layers should have left the JSON"
    );

    let tiles_path = dump.join("maps").join(format!("{stem}.tiles"));
    let tiles = std::fs::read_to_string(&tiles_path).unwrap();
    let rows: Vec<&str> = tiles
        .lines()
        .filter(|l| !l.trim_start().starts_with('#'))
        .collect();
    assert!(!rows.is_empty(), "no grid in {tiles_path:?}");

    // One line per row of the map, both layers.
    let original = ditto::file::read(&std::fs::read(&first).unwrap()).unwrap();
    let ditto::file::Document::Lmu { data: map, .. } = original else {
        panic!("{name} is not a map")
    };
    assert_eq!(rows.len(), map.height as usize * 2);
    assert_eq!(rows[0].split_whitespace().count(), map.width as usize);

    // And it is the source of truth: change one number and the binary changes.
    let changed = tiles.replacen(
        rows[0],
        &rows[0].replacen(
            rows[0].split_whitespace().next().unwrap(),
            &format!("{}", map.lower_layer[0] + 1),
            1,
        ),
        1,
    );
    assert_ne!(changed, tiles, "the edit did not take");
    std::fs::write(&tiles_path, changed).unwrap();

    let back = tmp.join("back");
    ditto::dump::pack(&dump, &back).unwrap();
    let rewritten = ditto::file::read(&std::fs::read(back.join(&name)).unwrap()).unwrap();
    let ditto::file::Document::Lmu { data: after, .. } = rewritten else {
        panic!("what came back is not a map")
    };
    assert_eq!(after.lower_layer[0], map.lower_layer[0] + 1);
    assert_eq!(after.lower_layer[1..], map.lower_layer[1..], "only that tile");
}
