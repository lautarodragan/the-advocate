//! The patches against what the Python that wrote them answered.
//!
//! Until 2026-09-30 the patches were written and checked by the converter's
//! Python. It was deleted once both gave the same files byte for byte on
//! every cartridge of a whole game, and the same messages from the check;
//! what is left of it is `python.json`: what it answered for the small game
//! in `game/`, which needs no real game.
//!
//! The game touches every edge: a map name with quotes and a backslash, a
//! map without merges and one with empty lists, a battler whose key has a
//! space, an animation and a battler only the tests ask for and a test map;
//! and for the check, a second cartridge that decided differently in every
//! field, a third that decided the same as the second —whose complaints
//! must not repeat—, a versioned map nobody converts, and an animation the
//! playable ROM converts with no versioned patch.
//!
//! **If one of these changes, what the check says or a byte of what is
//! versioned changed.** The answers are not to be regenerated to make a
//! test pass: the Python that produced them is gone, and with it the only
//! independent answer.
//!
//! On 2026-10-02 the battler with a space, which was one of the game this
//! was built for, became an invented one of the same length, and the hash
//! of its patch moved with it: the new file, with the old name put back, is
//! the Python's byte for byte.
//!
//! On 2026-10-04 the header of every file and two of the check's messages
//! stopped naming a recipe of that game's and name `rm2k-snes-patches`
//! instead; the hashes and the sizes moved with them. Every new file, with
//! the old header put back, is the Python's byte for byte, and the messages
//! differ from its only in that sentence.

use rm2k_snes_patches::{check, copy, versioned, write, Key, Kind, Request};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// The kinds the Python wrote. The message window's, since 2026-10-05, it
/// never had: this game has none, and it is `command_line.rs`'s to check.
const PYTHON_KINDS: [Kind; 3] = [Kind::Map, Kind::Animation, Kind::Battler];

fn game(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests").join(name)
}

fn request(name: &str) -> Request {
    serde_json::from_str(&std::fs::read_to_string(game(name)).unwrap()).unwrap()
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-snes-patches-{name}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn files_below(root: &Path, dir: &Path, out: &mut BTreeMap<String, String>) {
    for entry in std::fs::read_dir(dir).unwrap() {
        let path = entry.unwrap().path();
        if path.is_dir() {
            files_below(root, &path, out);
        } else {
            let digest = Sha256::digest(std::fs::read(&path).unwrap());
            let hex: String = digest.iter().map(|b| format!("{b:02x}")).collect();
            out.insert(
                path.strip_prefix(root).unwrap().display().to_string(),
                hex,
            );
        }
    }
}

fn key_json(key: &Key) -> Value {
    match key {
        Key::Number(n) => json!(n),
        Key::Text(t) => json!(t),
    }
}

#[test]
fn the_files_and_the_check_say_what_the_python_said() {
    let expected: Value =
        serde_json::from_str(&std::fs::read_to_string(game("python.json")).unwrap()).unwrap();
    let root = scratch("python");
    let release = root.join("build/release");
    let special = root.join("build/tests/special");
    let encounter = root.join("build/tests/encounter");
    let auto = root.join("patches/auto");
    let tests: BTreeSet<i64> = [52].into();

    let written: Vec<Value> = write(&release, &request("game/release.json"))
        .unwrap()
        .iter()
        .filter(|w| w.kind != Kind::Window)
        .map(|w| json!([w.files, w.bytes]))
        .collect();
    assert_eq!(json!(written), expected["written"]);
    write(&special, &request("game/special.json")).unwrap();
    write(&encounter, &request("game/special.json")).unwrap();
    std::fs::copy(game("game/uses.json"), release.join("patches/uses.json")).unwrap();

    let mut files = BTreeMap::new();
    files_below(&release, &release.join("patches/auto"), &mut files);
    assert_eq!(json!(files), expected["files"]);

    // What the playable ROM decided, to the versioned ones, over a file it
    // no longer carries.
    std::fs::create_dir_all(auto.join("maps")).unwrap();
    std::fs::write(auto.join("maps/0500.toml"), "map = 500\n").unwrap();
    let mut copied = Vec::new();
    for kind in PYTHON_KINDS {
        let (count, bytes, removed) = copy(&auto, &release, kind, &tests).unwrap();
        for path in removed {
            copied.push(format!(
                "  {}: the game no longer carries it, removing it",
                rm2k_project::relative(&path, &root).display()
            ));
        }
        copied.push(format!(
            "{count} patch(es) in {}, {bytes} B",
            rm2k_project::relative(auto.join(kind.directory()), &root).display()
        ));
    }
    assert_eq!(json!(copied), expected["copied"]);

    // And then it goes stale: an animation loses its patch, and a map that
    // no cartridge converts gets one.
    std::fs::remove_file(auto.join("animations/0082.toml")).unwrap();
    let town = std::fs::read_to_string(auto.join("maps/0012.toml")).unwrap();
    std::fs::write(auto.join("maps/0777.toml"), town.replace("map = 12", "map = 777")).unwrap();
    let mut listed = serde_json::Map::new();
    for kind in PYTHON_KINDS {
        let keys: Vec<Value> = versioned(&auto, kind).unwrap().iter().map(key_json).collect();
        listed.insert(kind.key().into(), json!(keys));
    }
    assert_eq!(Value::Object(listed), expected["versioned"]);

    let builds = [
        PathBuf::from("build/release"),
        PathBuf::from("build/tests/special"),
        PathBuf::from("build/tests/encounter"),
    ];
    let builds: Vec<PathBuf> = builds.iter().map(|b| root.join(b)).collect();
    let checked = check(&auto, &builds, &tests, &root).unwrap();
    assert_eq!(json!(checked.complaints), expected["complaints"]);
    let mut own = serde_json::Map::new();
    for (kind, which) in &checked.own {
        let which: serde_json::Map<String, Value> =
            which.iter().map(|(k, c)| (k.to_string(), json!(c))).collect();
        own.insert(kind.key().into(), Value::Object(which));
    }
    assert_eq!(Value::Object(own), expected["own"]);
    std::fs::remove_dir_all(&root).unwrap();
}
