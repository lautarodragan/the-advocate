//! The executable: its two ways in, what it writes, and how it says no.
//!
//! A small map and a ChipSet are generated inside each test, as a request
//! and as a Ditto dump with its project file, so none of this needs a game.

use rm2k_render::{picture, Picture};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("rm2k-render-cli-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn run(args: &[&str], cwd: &Path) -> Output {
    Command::new(env!("CARGO_BIN_EXE_rm2k-render"))
        .args(args)
        .current_dir(cwd)
        .output()
        .unwrap()
}

/// A ChipSet where every pixel is opaque and differs from its neighbours,
/// written as `<dir>/ChipSet/<file>`.
fn chipset(dir: &Path, file: &str) -> PathBuf {
    let folder = dir.join("ChipSet");
    std::fs::create_dir_all(&folder).unwrap();
    let rgba = (0..256usize)
        .flat_map(|y| (0..480usize).flat_map(move |x| [x as u8, y as u8, (x ^ y) as u8, 255]))
        .collect();
    let path = folder.join(file);
    picture::write_png(
        &path,
        &Picture {
            width: 480,
            height: 256,
            rgba,
        },
    )
    .unwrap();
    path
}

/// A 3x2 map with water, an animated tile and a terrain on the lower layer
/// and one tile drawn above the hero.
const LOWER: [i64; 6] = [0, 3000, 4000, 5000, 5001, 5002];
const UPPER: [i64; 6] = [10000, 10001, 10000, 10000, 10000, 10000];

fn passability() -> (Vec<u8>, Vec<u8>) {
    let mut upper = vec![15u8; 144];
    upper[1] = 0x1F; // the star: above the hero
    (vec![15u8; 162], upper)
}

fn chipset_entry(name: &str) -> serde_json::Value {
    let (lower, upper) = passability();
    serde_json::json!({
        "chipset_name": name,
        "passable_data_lower": lower,
        "passable_data_upper": upper,
    })
}

fn request(dir: &Path, lower: &[i64]) -> PathBuf {
    let path = dir.join("map.json");
    let body = serde_json::json!({
        "width": 3, "height": 2,
        "lower_layer": lower, "upper_layer": UPPER,
        "chipset": chipset_entry("Tiles"),
    });
    std::fs::write(&path, body.to_string()).unwrap();
    path
}

fn names(dir: &Path) -> Vec<String> {
    let mut names: Vec<String> = std::fs::read_dir(dir)
        .unwrap()
        .map(|e| e.unwrap().file_name().to_string_lossy().to_string())
        .collect();
    names.sort();
    names
}

#[test]
fn a_request_draws_both_layers_and_each_family_it_uses() {
    let dir = scratch("request");
    let file = chipset(&dir, "Tiles.png");
    let req = request(&dir, &LOWER);
    let out = dir.join("out");
    let done = run(
        &[
            "layers",
            "--request",
            req.to_str().unwrap(),
            "--chipset-file",
            file.to_str().unwrap(),
            "--out",
            out.to_str().unwrap(),
        ],
        &dir,
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    assert_eq!(
        names(&out),
        [
            "animated-1.png",
            "animated-2.png",
            "animated-3.png",
            "lower.png",
            "upper.png",
            "water-1.png",
            "water-2.png"
        ]
    );
    let lower = picture::read_rgba(&out.join("lower.png")).unwrap();
    assert_eq!((lower.width, lower.height), (48, 32));
    let upper = picture::read_rgba(&out.join("upper.png")).unwrap();
    // Cell (1, 0) carries the starred tile, and nothing else is in front.
    assert_eq!(upper.get(16, 0)[3], 255);
    assert_eq!(upper.get(0, 0), [0; 4]);
    assert_eq!(upper.get(32, 16), [0; 4]);

    // Drawn again with only plain tiles, the families' files go away: whoever
    // reads the directory learns which families there are from them.
    let req = request(&dir, &[5000; 6]);
    let done = run(
        &[
            "layers",
            "--request",
            req.to_str().unwrap(),
            "--chipset-file",
            file.to_str().unwrap(),
            "--out",
            out.to_str().unwrap(),
        ],
        &dir,
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    assert_eq!(names(&out), ["lower.png", "upper.png"]);
    std::fs::remove_dir_all(&dir).unwrap();
}

/// A project with its dump: the map in `maps/`, its layers in the `.tiles`
/// beside it, and the ChipSet entry in `db/chipsets.json`.
fn project(dir: &Path) {
    std::fs::write(dir.join("rm2k-snes.toml"), "[paths]\ndata = \"dump\"\n").unwrap();
    let maps = dir.join("dump").join("maps");
    let db = dir.join("dump").join("db");
    std::fs::create_dir_all(&maps).unwrap();
    std::fs::create_dir_all(&db).unwrap();
    std::fs::write(
        maps.join("Map0007.json"),
        serde_json::json!({"id": 7, "chipset_id": 2, "width": 3, "height": 2}).to_string(),
    )
    .unwrap();
    let row = |layer: &[i64]| {
        layer
            .chunks(3)
            .map(|r| {
                r.iter()
                    .map(|t| format!("{t:6}"))
                    .collect::<Vec<_>>()
                    .join("")
            })
            .collect::<Vec<_>>()
            .join("\n")
    };
    std::fs::write(
        maps.join("Map0007.tiles"),
        format!(
            "# 3x2\n# lower\n{}\n# upper\n{}\n",
            row(&LOWER),
            row(&UPPER)
        ),
    )
    .unwrap();
    let mut entry = chipset_entry("tiles");
    entry["id"] = 2.into();
    std::fs::write(
        db.join("chipsets.json"),
        serde_json::json!([entry]).to_string(),
    )
    .unwrap();
}

#[test]
fn a_map_from_the_dump_draws_what_the_same_request_draws() {
    let dir = scratch("dump");
    project(&dir);
    // Upper case on disk, lower case in the database: the lookup ignores it.
    let game = dir.join("game");
    let file = chipset(&game, "TILES.png");
    let from_dump = dir.join("from-dump");
    let done = run(
        &[
            "layers",
            "--map",
            "7",
            "--game-dir",
            game.to_str().unwrap(),
            "--rtp-dir",
            dir.join("no-rtp").to_str().unwrap(),
            "--out",
            from_dump.to_str().unwrap(),
        ],
        &dir.join("dump").join("maps"),
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );

    let from_request = dir.join("from-request");
    let req = request(&dir, &LOWER);
    let done = run(
        &[
            "layers",
            "--request",
            req.to_str().unwrap(),
            "--chipset-file",
            file.to_str().unwrap(),
            "--out",
            from_request.to_str().unwrap(),
        ],
        &dir,
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    for name in names(&from_request) {
        assert_eq!(
            picture::read_rgba(&from_dump.join(&name)).unwrap(),
            picture::read_rgba(&from_request.join(&name)).unwrap(),
            "{name}"
        );
    }
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_missing_chipset_is_an_answer_and_a_missing_flag_is_misuse() {
    let dir = scratch("errors");
    let req = request(&dir, &LOWER);
    let out = dir.join("out");
    let done = run(
        &[
            "layers",
            "--request",
            req.to_str().unwrap(),
            "--game-dir",
            dir.to_str().unwrap(),
            "--out",
            out.to_str().unwrap(),
        ],
        &dir,
    );
    assert_eq!(done.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&done.stderr).contains("ChipSet \"Tiles\" is in none of"));

    let done = run(
        &[
            "layers",
            "--request",
            req.to_str().unwrap(),
            "--out",
            out.to_str().unwrap(),
        ],
        &dir,
    );
    assert_eq!(done.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&done.stderr).contains("pass --game-dir"));
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_layer_of_the_wrong_size_is_refused() {
    let dir = scratch("size");
    let file = chipset(&dir, "Tiles.png");
    let req = request(&dir, &LOWER[..5]);
    let done = run(
        &[
            "layers",
            "--request",
            req.to_str().unwrap(),
            "--chipset-file",
            file.to_str().unwrap(),
            "--out",
            dir.join("out").to_str().unwrap(),
        ],
        &dir,
    );
    assert_eq!(done.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&done.stderr).contains("the lower layer has 5 tiles for a 3x2 map")
    );
    std::fs::remove_dir_all(&dir).unwrap();
}
