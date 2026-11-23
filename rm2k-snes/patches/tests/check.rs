//! What the check says when the versioned patches went stale, every way
//! they can.
//!
//! **The path it guards**: every complaint of `check` and the removal in
//! `copy`. ABL's `tests/tooling/test_patches.py` runs `--check` over real
//! builds, but there it is green: it only ever walks the path where
//! everything matches. `command_line.rs` sees one stale animation and one
//! window. Every other message is only produced here.
//!
//! The small game of `game/` touches every edge: a map name with quotes and
//! a backslash, a map without merges and one with empty lists, a battler
//! whose key has a space, an animation and a battler only the tests ask for
//! and a test map; and for the check, a second cartridge that decided
//! differently in every field, a third that decided the same as the
//! second —whose complaints must not repeat—, a versioned map nobody
//! converts, and an animation the playable ROM converts with no versioned
//! patch.

use rm2k_snes_patches::{check, copy, versioned, write, Key, Kind, Request};
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

/// The kinds this game has. The message window's it has none of: it is
/// `command_line.rs`'s to check.
const KINDS: [Kind; 3] = [Kind::Map, Kind::Animation, Kind::Battler];

fn game(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join(name)
}

fn request(name: &str) -> Request {
    serde_json::from_str(&std::fs::read_to_string(game(name)).unwrap()).unwrap()
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("rm2k-snes-patches-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn key_json(key: &Key) -> Value {
    match key {
        Key::Number(n) => json!(n),
        Key::Text(t) => json!(t),
    }
}

#[test]
fn every_stale_patch_is_told_once_and_with_what_changed() {
    let root = scratch("stale");
    let release = root.join("build/release");
    let special = root.join("build/tests/special");
    let encounter = root.join("build/tests/encounter");
    let auto = root.join("patches/auto");
    let tests: BTreeSet<i64> = [52].into();

    write(&release, &request("game/release.json")).unwrap();
    write(&special, &request("game/special.json")).unwrap();
    write(&encounter, &request("game/special.json")).unwrap();
    std::fs::copy(game("game/uses.json"), release.join("patches/uses.json")).unwrap();

    // What the playable ROM decided, to the versioned ones, over a file it
    // no longer carries.
    std::fs::create_dir_all(auto.join("maps")).unwrap();
    std::fs::write(auto.join("maps/0500.toml"), "map = 500\n").unwrap();
    let mut copied = Vec::new();
    for kind in KINDS {
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
    assert_eq!(
        copied,
        [
            "  patches/auto/maps/0500.toml: the game no longer carries it, removing it",
            "3 patch(es) in patches/auto/maps, 2933 B",
            "2 patch(es) in patches/auto/animations, 1599 B",
            "2 patch(es) in patches/auto/battlers, 1775 B",
        ]
    );

    // And then it goes stale: an animation loses its patch, and a map that
    // no cartridge converts gets one.
    std::fs::remove_file(auto.join("animations/0082.toml")).unwrap();
    let town = std::fs::read_to_string(auto.join("maps/0012.toml")).unwrap();
    std::fs::write(
        auto.join("maps/0777.toml"),
        town.replace("map = 12", "map = 777"),
    )
    .unwrap();
    let mut listed = serde_json::Map::new();
    for kind in KINDS {
        let keys: Vec<Value> = versioned(&auto, kind)
            .unwrap()
            .iter()
            .map(key_json)
            .collect();
        listed.insert(kind.key().into(), json!(keys));
    }
    assert_eq!(
        Value::Object(listed),
        json!({"map": [3, 12, 777, 1234], "animation": [1], "battler": ["rusty knight", "slime-60"]})
    );

    let builds = [
        PathBuf::from("build/release"),
        PathBuf::from("build/tests/special"),
        PathBuf::from("build/tests/encounter"),
    ];
    let builds: Vec<PathBuf> = builds.iter().map(|b| root.join(b)).collect();
    let checked = check(&auto, &builds, &tests, &root).unwrap();
    assert_eq!(
        checked.complaints,
        [
            "patches/auto/maps/0003.toml is stale (cartridge «special» says so), and what changed in map 3 is this:\n    layer lower: colors went from 176 to 175\n    layer lower: it merged 3 color(s) and now merges 2\n    layer lower: merge 0 sent [1, 2, 3] to [4, 5, 6] and now sends [1, 2, 3] to [4, 5, 7]\n    layer lower: merge 1 of [7, 8, 9] moved 3 pixel(s) and now moves 4\n    layer lower: no longer merges [31, 0, 0] -> [30, 1, 0]\n    layer upper: it merged 1 color(s) and now merges 2\n    layer upper: extra merge [9, 9, 9] -> [8, 8, 8]\n  If the change is the one intended, run `rm2k-snes-patches` on the playable ROM's build and commit; if not, something moved what is seen.",
            "map 777 has a versioned patch and none of the built cartridges converts it: either the game stopped carrying it —and then the file is left over— or the cartridge that has it is not built.",
            "animation 82 went into «release», the playable ROM, and has no versioned patch: run `rm2k-snes-patches` on its build.",
            "patches/auto/animations/0001.toml is stale (cartridge «special» says so), and what changed in animation 1 is this:\n    it was drawn at 56x64 and now it is drawn at 64x56\n    it came from 96x110 in RM2k and now comes from 96x111\n    it had 7 frame(s) and now has 8\n    it came from sheet 'hit' and now comes from 'hit2'\n  If the change is the one intended, run `rm2k-snes-patches` on the playable ROM's build and commit; if not, something moved what is seen.",
            "patches/auto/battlers/rusty_knight.toml is stale (cartridge «special» says so), and what changed in battler rusty knight is this:\n    the same colors in another palette order\n  If the change is the one intended, run `rm2k-snes-patches` on the playable ROM's build and commit; if not, something moved what is seen.",
            "patches/auto/battlers/slime-60.toml is stale (cartridge «special» says so), and what changed in battler slime-60 is this:\n    keeps [0, 11, 0], which used to be merged\n    loses [0, 10, 0], which used to stay\n    size went from [40, 30] to [40, 31]\n    colors went from 20 to 21\n    hue went from 60 to 90\n    18 merges were needed and now 19\n  If the change is the one intended, run `rm2k-snes-patches` on the playable ROM's build and commit; if not, something moved what is seen.",
        ]
    );
    let mut own = serde_json::Map::new();
    for (kind, which) in &checked.own {
        let which: serde_json::Map<String, Value> = which
            .iter()
            .map(|(k, c)| (k.to_string(), json!(c)))
            .collect();
        own.insert(kind.key().into(), Value::Object(which));
    }
    // What only the suite's cartridges carry, each with who carried it: the
    // maps, animations and battlers the check lets decide on their own.
    assert_eq!(
        Value::Object(own),
        json!({"map": {"52": ["release"], "99": ["special", "encounter"]}, "animation": {"82": ["special", "encounter"], "91": ["release"]}, "battler": {"ghost": ["release"]}})
    );
    std::fs::remove_dir_all(&root).unwrap();
}
