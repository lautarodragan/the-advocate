//! Where the corpus comes from.
//!
//! Ditto measures itself against a real RPG Maker 2000 game: every `.lmu`, the
//! `RPG_RT.ldb` and the `RPG_RT.lmt` are read, dumped to JSON, written back and
//! compared against the original. No game ships with this repository —they are
//! somebody else's— so the tests that need one take it from the environment:
//!
//!     DITTO_CORPUS=/path/to/a/game cargo test
//!
//! Without it those tests **skip with a message** instead of failing: a missing
//! corpus is not a defect of the code under test. The ones that do not need a
//! game —the defaults of the schema, for one— always run.
//!
//! Each test file compiles its own copy of this module and not all of them use
//! every function, so the ones a file leaves out are not dead code.

#![allow(dead_code)]

use std::path::PathBuf;

/// The environment variable that points at the game directory.
pub const VAR: &str = "DITTO_CORPUS";

/// The corpus directory, or `None` with the reason printed. Every caller that
/// gets `None` must return without asserting.
pub fn dir() -> Option<PathBuf> {
    let Some(raw) = std::env::var_os(VAR) else {
        println!(
            "SKIPPED: {VAR} is not set. Point it at an RPG Maker 2000 game \
             directory (the one holding RPG_RT.ldb, RPG_RT.lmt and the \
             Map*.lmu files) to run this test."
        );
        return None;
    };
    let dir = PathBuf::from(raw);
    if !dir.is_dir() {
        println!("SKIPPED: {VAR} points at {dir:?}, which is not a directory.");
        return None;
    }
    Some(dir)
}

/// Every `.lmu` of the corpus, sorted.
pub fn maps(dir: &std::path::Path) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = std::fs::read_dir(dir)
        .map(|it| it.filter_map(|e| e.ok().map(|e| e.path())).collect())
        .unwrap_or_default();
    v.retain(|p| p.extension().is_some_and(|x| x.eq_ignore_ascii_case("lmu")));
    v.sort();
    v
}

/// The whole corpus: the database, the map tree and every map. Returns `None`,
/// with the reason printed, when the directory does not look like a game.
pub fn files(dir: &std::path::Path) -> Option<Vec<PathBuf>> {
    let mut v = Vec::new();
    for name in ["RPG_RT.ldb", "RPG_RT.lmt"] {
        let p = dir.join(name);
        if !p.is_file() {
            println!("SKIPPED: {dir:?} has no {name}; it is not a game directory.");
            return None;
        }
        v.push(p);
    }
    let maps = maps(dir);
    if maps.is_empty() {
        println!("SKIPPED: {dir:?} has no .lmu files.");
        return None;
    }
    v.extend(maps);
    Some(v)
}
