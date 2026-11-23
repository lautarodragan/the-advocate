//! The disk cache's values: whole or nothing, under writers that race, and
//! the same key from two checkouts with the same content.

use std::fs;
use std::path::{Path, PathBuf};

use rm2k_project::cache;

/// A fresh directory under the target dir, one per test.
fn scratch(name: &str) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("cache")
        .join(name);
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

/// A value big enough that writing it takes a while, all of it the same
/// byte except the last, so a reader that gets half of it can tell.
fn big(fill: u8) -> Vec<u8> {
    let mut value = vec![fill; 8 << 20];
    *value.last_mut().unwrap() = 0xEE;
    value
}

/// Two worktrees that build the same thing at once store the same key at
/// the same time —and so do two threads of one converter—: whoever reads
/// meanwhile has to find the whole value or none, never a half-written
/// one. Several writers and several readers, for a while.
#[test]
fn writers_that_race_leave_a_reader_the_whole_value_or_nothing() {
    let dir = scratch("race");
    let value = big(0x5A);
    let rounds = 20;
    std::thread::scope(|scope| {
        for _ in 0..4 {
            scope.spawn(|| {
                for _ in 0..rounds {
                    assert!(cache::store(&dir, "stage", "k", &value));
                }
            });
        }
        for _ in 0..4 {
            scope.spawn(|| {
                for _ in 0..rounds * 20 {
                    if let Some(read) = cache::load(&dir, "stage", "k") {
                        assert!(
                            read.len() == value.len() && read == value,
                            "a reader got {} bytes of {}",
                            read.len(),
                            value.len()
                        );
                    }
                }
            });
        }
    });
    // And nothing left aside.
    let left: Vec<_> = fs::read_dir(dir.join("stage"))
        .unwrap()
        .map(|e| e.unwrap().file_name())
        .collect();
    assert_eq!(left, ["k"]);
}

/// A file fetched out of the cache into a build is the cache's own when it
/// is a hard link: replacing it in the build —a new track over an old one—
/// must leave the cache's copy as it was.
#[test]
fn replacing_a_fetched_file_does_not_touch_the_cache() {
    let dir = scratch("fetched");
    let build = dir.join("build");
    fs::create_dir_all(&build).unwrap();
    let made = build.join("made.pcm");
    fs::write(&made, b"old track").unwrap();
    assert!(cache::store_file(&dir, "tracks", "old", &made));
    let out = build.join("game-1.pcm");
    assert!(cache::fetch_file(&dir, "tracks", "old", &out));
    assert_eq!(fs::read(&out).unwrap(), b"old track");
    fs::write(build.join("new"), b"new track").unwrap();
    assert!(cache::store_file(&dir, "tracks", "new", &build.join("new")));
    assert!(cache::fetch_file(&dir, "tracks", "new", &out));
    assert_eq!(fs::read(&out).unwrap(), b"new track");
    assert_eq!(
        fs::read(cache::entry(&dir, "tracks", "old")).unwrap(),
        b"old track"
    );
    assert!(!cache::fetch_file(&dir, "tracks", "missing", &out));
}

/// A directory goes into a key by what is in it, so two checkouts of the
/// same dump give the same key; and a file renamed is another tree.
#[test]
fn a_tree_is_its_names_and_contents_not_its_place() {
    let dir = scratch("tree");
    for side in ["one", "two"] {
        fs::create_dir_all(dir.join(side).join("maps")).unwrap();
        fs::write(dir.join(side).join("maps").join("Map0001.json"), "{}").unwrap();
        fs::write(dir.join(side).join(".hidden"), "x").unwrap();
    }
    let one = cache::tree_version(&dir.join("one")).unwrap();
    assert_eq!(one, cache::tree_version(&dir.join("two")).unwrap());
    fs::write(dir.join("two").join(".hidden"), "y").unwrap();
    assert_ne!(one, cache::tree_version(&dir.join("two")).unwrap());
    fs::write(dir.join("two").join(".hidden"), "x").unwrap();
    fs::rename(
        dir.join("two").join("maps").join("Map0001.json"),
        dir.join("two").join("maps").join("Map0002.json"),
    )
    .unwrap();
    assert_ne!(one, cache::tree_version(&dir.join("two")).unwrap());
}
