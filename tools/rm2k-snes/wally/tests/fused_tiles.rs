//! `wally map` with a background that has more distinct tiles than any
//! layout holds: the last resort fuses the cells most alike, says so, and
//! leaves untouched a map that already fits.
//!
//! A small game is generated inside each test: a map whose 144 ground tiles
//! are drawn with 576 distinct cells that differ a few pixels from each
//! other. None of this needs a game.

use rm2k_render::{picture, Picture};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::Command;

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("wally-fused-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn write(path: &Path, width: usize, height: usize, pixel: impl Fn(usize, usize) -> [u8; 4]) {
    let mut rgba = Vec::with_capacity(width * height * 4);
    for y in 0..height {
        for x in 0..width {
            rgba.extend_from_slice(&pixel(x, y));
        }
    }
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    picture::write_png(path, &Picture { width, height, rgba }).unwrap();
}


fn game(dir: &Path) -> (PathBuf, PathBuf) {
    let dump = dir.join("dump");
    std::fs::create_dir_all(dump.join("maps")).unwrap();
    std::fs::create_dir_all(dump.join("db")).unwrap();
    std::fs::write(dump.join("ditto.json"), json!({"ditto": 2, "view": "resolved"}).to_string()).unwrap();
    std::fs::write(
        dump.join("db/chipsets.json"),
        json!([{"id": 2, "chipset_name": "tiles", "passable_data_lower": vec![15u8; 162],
                "passable_data_upper": vec![15u8; 144]}])
        .to_string(),
    )
    .unwrap();
    std::fs::write(
        dump.join("db/actors.json"),
        json!([{"id": 1, "character_name": "Folk", "character_index": 1}]).to_string(),
    )
    .unwrap();
    std::fs::write(dump.join("db/commonevents.json"), "[]").unwrap();
    std::fs::write(
        dump.join("maps.json"),
        json!({"maps": [], "start": {"party_map_id": 9, "party_x": 1, "party_y": 1}}).to_string(),
    )
    .unwrap();
    // 144 different ground tiles, one per cell of the map.
    let lower: Vec<usize> = (0..24 * 6).map(|n| 5000 + n % 144).collect();
    std::fs::write(
        dump.join("maps/Map0007.json"),
        json!({"chipset_id": 2, "width": 24, "height": 6, "events": [],
               "lower_layer": lower, "upper_layer": vec![10000; 24 * 6]})
        .to_string(),
    )
    .unwrap();
    let pictures = dir.join("game");
    // The ChipSet's ground tiles are its 16x16 squares from the third column
    // of its right half: 144 of them, four cells each. A cell is two colours
    // in a pattern that is its number's bits, so no two are alike but all are
    // near each other.
    write(&pictures.join("ChipSet/tiles.png"), 480, 256, |x, y| {
        if x < 192 {
            return [0, 0, 0, 255];
        }
        let col = (x - 192) / 16;
        let tile = col / 6 * 96 + y / 16 * 6 + col % 6;
        // The upper layer draws nothing: its tile 0, the 145th, is clear.
        if tile == 144 {
            return [0, 0, 0, 0];
        }
        let k = tile * 4 + (y / 8 % 2) * 2 + (x / 8) % 2;
        let bit = ((k >> ((x % 4) + (y % 2) * 4)) ^ (k >> 8)) & 1;
        let (a, b) = (k % 3, k % 5);
        let c = if bit == 1 { [200, 60 + a as u8 * 40, 60] } else { [40, 60 + b as u8 * 40, 180] };
        [c[0], c[1], c[2], 255]
    });
    write(&pictures.join("CharSet/Folk.png"), 288, 256, |x, y| {
        if (x * 3 + y * 5) % 7 == 0 {
            return [0, 0, 0, 0];
        }
        let k = (x / 6 + y / 4 * 3) % 9;
        [(k * 40 % 256) as u8, (k * 90 % 256) as u8, (k * 150 % 256) as u8, 255]
    });
    (dump, pictures)
}

/// The map with these layouts: its notes and how many background tiles it
/// spends.
fn convert(dir: &Path, dump: &Path, pictures: &Path, layouts: Value) -> (Vec<String>, usize) {
    let request = dir.join("request.json");
    let body = json!({
        "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
        "test_event": false, "leaders": [1], "pages": [],
        "route_graphics": [], "also_walk": [],
        "timer": null, "rain": false, "picture": null,
        "battle_animation": false, "singles": [], "palette_weight": {},
        "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
        "layouts": layouts, "window_colors": 13,
    });
    std::fs::write(&request, body.to_string()).unwrap();
    let out = dir.join("out");
    let _ = std::fs::remove_dir_all(&out);
    let done = Command::new(env!("CARGO_BIN_EXE_wally"))
        .args(["map", "--data"])
        .arg(dump)
        .arg("--search-dir")
        .arg(pictures)
        .arg("--request")
        .arg(&request)
        .arg("--out")
        .arg(&out)
        .output()
        .unwrap();
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    let answer: Value = serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
    let notes = answer["notes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["text"].as_str().unwrap().to_string())
        .collect();
    (notes, std::fs::read(out.join("background.bin")).unwrap().len() / 64)
}

#[test]
fn a_background_that_does_not_fit_is_fused_and_one_that_fits_is_not() {
    let dir = scratch("fuse");
    let (dump, pictures) = game(&dir);
    // Room for all of it: nothing is fused, nothing is said.
    let (notes, whole) = convert(&dir, &dump, &pictures, json!([[1000, 1000, 1000]]));
    assert!(whole > 100, "the toy map was meant to spend many tiles and spends {whole}");
    assert!(notes.iter().all(|n| !n.contains("fused")), "{notes:?}");
    // Room for a hundred, which is what it is over on: it fits, and says it
    // was fused.
    let (notes, fused) = convert(&dir, &dump, &pictures, json!([[100, 1000, 1000]]));
    assert!(fused <= 100, "{fused} tiles in a layout of 100");
    assert!(notes.iter().any(|n| n.contains("WARNING") && n.contains("fused")), "{notes:?}");
    // And with no layout that can hold its sprites, it is not touched: the
    // background is not what it is over on.
    let (notes, same) = convert(&dir, &dump, &pictures, json!([[100, 0, 1000]]));
    assert_eq!(same, whole);
    assert!(notes.iter().all(|n| !n.contains("fused")), "{notes:?}");
}
